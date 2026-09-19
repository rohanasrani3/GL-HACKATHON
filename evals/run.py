"""Run every screenshot in evals/screenshots (and screenshots/real/) through the pipeline and score it.

    cd backend && .venv/Scripts/python ../evals/run.py            # calls the pipeline in-process
    cd backend && .venv/Scripts/python ../evals/run.py --url http://localhost:8000   # via the API

Expected file format (evals/expected/<image stem>.json):
    {
      "captured_at": "2026-09-19T14:00:00+08:00",
      "events": [ {"title_contains": "AI", "start": "2026-09-25T16:00", "end": "...", "location_contains": "LG01"} ]
    }
An empty "events" list means "nothing should be proposed".
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from snapsort.models import get_client  # noqa: E402
from snapsort.pipeline import analyze  # noqa: E402


def check(expected: list[dict], proposals: list[dict]) -> tuple[bool, list[str]]:
    problems = []
    if not expected:
        if proposals:
            problems.append(f"false positive: {[p['payload']['title'] for p in proposals]}")
        return not problems, problems
    for exp in expected:
        match = None
        for p in proposals:
            pl = p["payload"]
            if exp.get("title_contains", "").lower() in pl["title"].lower():
                match = pl
                break
        if match is None:
            problems.append(f"missing event '{exp.get('title_contains')}' (got {[p['payload']['title'] for p in proposals]})")
            continue
        if "start" in exp and not match["start"].startswith(exp["start"]):
            problems.append(f"start {match['start']} != {exp['start']}")
        if "end" in exp and not match["end"].startswith(exp["end"]):
            problems.append(f"end {match['end']} != {exp['end']}")
        if "location_contains" in exp and exp["location_contains"].lower() not in (match["location"]["name"] or "").lower():
            problems.append(f"location {match['location']['name']!r} missing {exp['location_contains']!r}")
    return not problems, problems


async def run_one(img: Path, exp: dict, url: str | None) -> dict:
    if url:
        import httpx

        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(
                f"{url}/analyze",
                files={"file": (img.name, img.read_bytes(), "image/png")},
                data={"captured_at": exp["captured_at"]},
            )
            r.raise_for_status()
            return r.json()
    res = await analyze(get_client(), img.read_bytes(), datetime.fromisoformat(exp["captured_at"]))
    return res.model_dump()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--only", default=None, help="substring filter on file name")
    args = ap.parse_args()

    images = sorted(p for p in (ROOT / "screenshots").rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if args.only:
        images = [p for p in images if args.only in p.name]
    passed, latencies = 0, []
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    for img in images:
        exp_file = ROOT / "expected" / f"{img.stem}.json"
        if not exp_file.exists():
            print(f"SKIP {img.name} (no expected json)")
            continue
        exp = json.loads(exp_file.read_text(encoding="utf-8"))
        try:
            res = await run_one(img, exp, args.url)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {img.name}: {e}")
            continue
        ok, problems = check(exp["events"], res["proposals"])
        passed += ok
        latencies.append(res["latency_ms"])
        (results_dir / f"{img.stem}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        titles = [f"{p['payload']['title']} @ {p['payload']['start']} ({p['confidence']})" for p in res["proposals"]]
        print(f"{'PASS' if ok else 'FAIL'} {img.name} [{res['latency_ms']}ms] {titles or res['skipped_reason']}")
        for pr in problems:
            print(f"     - {pr}")

    n = len(latencies)
    if n:
        print(f"\n{passed}/{n} passed · median latency {sorted(latencies)[n // 2]}ms · model {res['model']}")


if __name__ == "__main__":
    asyncio.run(main())
