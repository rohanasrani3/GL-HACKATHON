"""Run every screenshot in evals/screenshots (and screenshots/real/) through the pipeline and score it.

    cd backend && .venv/Scripts/python ../evals/run.py            # calls the pipeline in-process
    cd backend && .venv/Scripts/python ../evals/run.py --url http://localhost:8000   # via the API

Expected file format (evals/expected/<image stem>.json):
    {
      "captured_at": "2026-09-19T14:00:00+08:00",
      "events": [ {"title_contains": "AI", "start": "2026-09-25T16:00", "end": "...", "location_contains": "LG01"} ],
      "forms":  [ {"domain_contains": "docs.google.com", "min_fields": 3, "max_fields": 9, "prefill_style": "google_forms"} ]
    }
An empty "events" list means "no event should be proposed"; an empty "forms" list means "no form
should be detected". Omitting "forms" entirely means the screenshot makes no claim either way.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from snapsort.models import get_client  # noqa: E402
from snapsort.pipeline import analyze  # noqa: E402


def check(exp: dict, res: dict) -> tuple[bool, list[str]]:
    problems = _check_events(exp.get("events", []), res["proposals"])
    problems += _check_forms(exp.get("forms"), res.get("forms", []))
    return not problems, problems


def _check_forms(expected: list[dict] | None, forms: list[dict]) -> list[str]:
    """Score the v3 form path. `None` means this screenshot has no recorded expectation."""
    if expected is None:
        return []
    if not expected:
        return [f"unexpected form: {[f['payload']['domain'] for f in forms]}"] if forms else []
    problems = []
    for want in expected:
        domain = want.get("domain_contains", "")
        match = next((f["payload"] for f in forms if domain.lower() in f["payload"]["domain"].lower()), None)
        if match is None:
            problems.append(f"missing form '{domain}' (got {[f['payload']['domain'] for f in forms]})")
            continue
        n = len(match["fields"])
        if n < want.get("min_fields", 0):
            problems.append(f"form {domain}: {n} fields < {want['min_fields']} expected")
        # An upper bound catches the opposite regression: radio/checkbox groups that stop being
        # collapsed show up as one field per option.
        if "max_fields" in want and n > want["max_fields"]:
            problems.append(f"form {domain}: {n} fields > {want['max_fields']} expected (options not grouped?)")
        if "prefill_style" in want and match["prefill_style"] != want["prefill_style"]:
            problems.append(f"form {domain}: prefill_style {match['prefill_style']} != {want['prefill_style']}")
    return problems


def _check_events(expected: list[dict], proposals: list[dict]) -> list[str]:
    problems = []
    if not expected:
        if proposals:
            problems.append(f"false positive: {[p['payload']['title'] for p in proposals]}")
        return problems
    for exp in expected:
        # Several proposals can share words ("Application deadline: X" vs "X"): prefer one whose start also matches.
        titled = [p["payload"] for p in proposals if exp.get("title_contains", "").lower() in p["payload"]["title"].lower()]
        dated = [pl for pl in titled if "start" in exp and pl["start"].startswith(exp["start"])]
        match = (dated or titled or [None])[0]
        if match is None:
            problems.append(f"missing event '{exp.get('title_contains')}' (got {[p['payload']['title'] for p in proposals]})")
            continue
        if "start" in exp and not match["start"].startswith(exp["start"]):
            problems.append(f"start {match['start']} != {exp['start']}")
        if "end" in exp and not match["end"].startswith(exp["end"]):
            problems.append(f"end {match['end']} != {exp['end']}")
        if "location_contains" in exp and exp["location_contains"].lower() not in (match["location"]["name"] or "").lower():
            problems.append(f"location {match['location']['name']!r} missing {exp['location_contains']!r}")
    return problems


async def run_one(img: Path, exp: dict, url: str | None, token: str = "") -> dict:
    if url:
        import httpx

        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(
                f"{url}/analyze",
                files={"file": (img.name, img.read_bytes(), "image/png")},
                data={"captured_at": exp["captured_at"]},
                headers={"X-Api-Token": token} if token else {},
            )
            r.raise_for_status()
            return r.json()
    res = await analyze(get_client(), img.read_bytes(), datetime.fromisoformat(exp["captured_at"]))
    return res.model_dump()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--token", default=os.getenv("API_TOKEN", ""), help="X-Api-Token for a protected server")
    ap.add_argument("--only", default=None, help="substring filter on file name")
    args = ap.parse_args()

    images = sorted(p for p in (ROOT / "screenshots").rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if args.only:
        images = [p for p in images if args.only in p.name]
    passed, latencies, model = 0, [], "?"
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    scored: set[str] = set()

    for img in images:
        exp_file = ROOT / "expected" / f"{img.stem}.json"
        if not exp_file.exists():
            print(f"SKIP {img.name} (no expected json)")
            continue
        exp = json.loads(exp_file.read_text(encoding="utf-8"))
        try:
            res = await run_one(img, exp, args.url, args.token)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {img.name}: {e}")
            continue
        ok, problems = check(exp, res)
        passed += ok
        scored.add(img.stem)
        latencies.append(res["latency_ms"])
        model = res["model"]
        (results_dir / f"{img.stem}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

        # Summarise every part of the response, not just the calendar half: a screenshot can
        # legitimately yield a form and no event at all.
        found = [f"{p['payload']['title']} @ {p['payload']['start']} ({p['confidence']})" for p in res["proposals"]]
        found += [f"form {f['payload']['domain']} ({len(f['payload']['fields'])} fields)" for f in res.get("forms", [])]
        print(f"{'PASS' if ok else 'FAIL'} {img.name} [{res['latency_ms']}ms] {found or res['skipped_reason']}")
        for link in res.get("links", []):
            print(f"       link {link['domain']} is_form={link['is_form']} via {link['source']} · {link['title'] or '-'}")
        for pr in problems:
            print(f"     - {pr}")

    # Expectations whose screenshot isn't on this machine (evals/screenshots/real/ is git-ignored
    # because real screenshots carry personal data). Say so rather than silently scoring fewer.
    # Skipped under --only, where "not scored" just means "filtered out".
    if not args.only:
        on_disk = {p.stem for p in (ROOT / "screenshots").rglob("*")}
        for f in sorted((ROOT / "expected").glob("*.json")):
            if f.stem not in scored and f.stem not in on_disk:
                print(f"NOT RUN {f.stem} (expected json present, screenshot not on this machine)")

    n = len(latencies)
    if n:
        print(f"\n{passed}/{n} passed · median latency {sorted(latencies)[n // 2]}ms · model {model}")


if __name__ == "__main__":
    asyncio.run(main())
