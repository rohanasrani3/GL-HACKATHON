"""Google Forms: turn a form link seen in a screenshot into its real fields.

Deliberately deterministic (CLAUDE.md D3). The model only *reports* the URL it saw; this module
fetches the public form and reads the actual entry ids, so a hallucinated field name can never
reach the prefill URL.

No profile data passes through here. The backend names which profile key answers each question;
the phone supplies the values and builds the final URL (CLAUDE.md §2.8, §4.3).
"""
import json
import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from PIL import Image

from .schema import FormField, FormPayload

# Google Forms question types we can prefill via ?entry.N=value
_TYPES = {
    0: "short_text",
    1: "paragraph",
    2: "multiple_choice",
    3: "dropdown",
    4: "checkboxes",
    5: "linear_scale",
    7: "grid",
    9: "date",
    10: "time",
}

_FORM_HOSTS = ("docs.google.com", "forms.gle", "forms.google.com")

# Question text -> canonical profile key. First match wins, so order matters:
# "student id" must beat the bare "name"/"id" patterns.
_PROFILE_PATTERNS: list[tuple[str, str]] = [
    (r"student\s*(id|number)|matric|roll\s*no", "student_id"),
    (r"e-?mail", "email"),
    (r"phone|mobile|whatsapp|contact\s*(no|number)", "phone"),
    (r"\bage\b|how old", "age"),
    (r"full\s*name|your\s*name|\bname\b", "full_name"),
    (r"location|city|address|where.*(from|based)|country", "location"),
    (r"university|college|school|institution|organi[sz]ation|company|employer", "organisation"),
    (r"diet|allerg|food\s*preference", "dietary"),
    (r"website|portfolio|linkedin|github", "website"),
]


def qr_urls(image: "Image.Image") -> list[str]:
    """Every URL encoded in a QR code in the screenshot.

    Deterministic, and the reason this exists: a Google Forms id is 44 random characters, and a
    vision model reading it off a poster gets a character wrong often enough to matter (one wrong
    character 404s). A QR code carries the exact bytes, so prefer it whenever there is one.
    Returns [] when the decoder isn't installed.
    """
    try:
        import zxingcpp
    except ImportError:
        return []
    try:
        results = zxingcpp.read_barcodes(image)
    except Exception:  # noqa: BLE001 - a broken/odd image must never fail the whole analysis
        return []
    out: list[str] = []
    for r in results:
        text = (getattr(r, "text", "") or "").strip()
        if text.lower().startswith(("http://", "https://")):
            out.append(text)
    return out


def looks_like_form(url: Optional[str]) -> bool:
    """Cheap check before spending a network round-trip."""
    if not url:
        return False
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    if not any(host == h or host.endswith(f".{h}") for h in _FORM_HOSTS):
        return False
    return "forms.gle" in host or "/forms/" in url


def profile_key_for(question: str) -> Optional[str]:
    q = question.strip().lower()
    for pattern, key in _PROFILE_PATTERNS:
        if re.search(pattern, q):
            return key
    return None


def _extract_load_data(html: str) -> Optional[list]:
    """Pull the FB_PUBLIC_LOAD_DATA_ array out of the page.

    Scans for the matching bracket rather than regexing to the first `];`, which breaks as soon
    as a question contains one.
    """
    marker = re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*", html)
    if not marker:
        return None
    start = html.find("[", marker.end())
    if start < 0:
        return None
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(html)):
        ch = html[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html[start : i + 1])
    return None


def _title(html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return m.group(1).strip() if m else None


def parse_form_html(html: str, final_url: str) -> Optional[FormPayload]:
    """Build a FormPayload from a fetched Google Form page. Returns None if it isn't one."""
    data = _extract_load_data(html)
    if not data or len(data) < 2 or not data[1]:
        return None
    questions = data[1][1] if len(data[1]) > 1 and data[1][1] else []

    fields: list[FormField] = []
    for q in questions:
        if len(q) < 4:
            continue
        question, qtype = q[1], q[3]
        entries = q[4] if len(q) > 4 and q[4] else []
        for entry in entries:
            if not entry:
                continue
            options = [o[0] for o in entry[1] if o] if len(entry) > 1 and entry[1] else []
            fields.append(
                FormField(
                    entry_id=f"entry.{entry[0]}",
                    question=(question or "").strip(),
                    profile_key=profile_key_for(question or ""),
                    required=bool(entry[2]) if len(entry) > 2 else False,
                    type=_TYPES.get(qtype, str(qtype)),
                    options=[str(o) for o in options],
                )
            )

    if not fields:
        return None
    return FormPayload(
        form_url=final_url,
        title=_title(html),
        domain=urlparse(final_url).netloc,
        fields=fields,
    )


async def resolve_google_form(url: str, timeout: float = 15.0) -> Optional[FormPayload]:
    """Follow the link (forms.gle shorteners and /d/<id> both redirect to the public /d/e/<id>)."""
    if not url.startswith("http"):
        url = f"https://{url}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (later.exe)"})
        if r.status_code != 200:
            return None
        return parse_form_html(r.text, str(r.url))
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return None
