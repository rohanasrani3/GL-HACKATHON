"""Screenshot → proposals. Preprocess image, call the model, resolve dates, score, filter."""
import asyncio
import base64
import hashlib
import io
import time as clock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image

from .config import settings
from .datetime_resolve import DEFAULT_DURATION, parse_hhmm, resolve_date, split_range
from .formdetect import detect_form, form_likelihood, page_meta
from .forms import qr_urls
from .links import UnsafeUrlError, normalise
from .links import fetch as fetch_page
from .models import ModelClient
from .schema import (
    AnalyzeResponse,
    CalendarPayload,
    Extraction,
    FormPayload,
    FormProposal,
    LinkContext,
    Location,
    Proposal,
    RawEvent,
)

_SKILLS = Path(__file__).parent / "skills"
# One model call serves both skills; each still owns its own prompt file (CLAUDE.md §5, D2).
SKILL_PROMPT = "\n\n".join(
    (_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    for name in ("calendar_event", "form_fill")
)


class InvalidInputError(ValueError):
    """The supplied timezone or image is invalid."""


def preprocess_image(data: bytes, max_side: int) -> str:
    """Downscale, drop EXIF/GPS (by re-encoding), return base64 JPEG."""
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)  # re-encode without exif
    return base64.b64encode(out.getvalue()).decode("ascii")


def build_user_prompt(captured_at: datetime, locale: str) -> str:
    return (
        f"Screenshot captured at: {captured_at.strftime('%A %d %B %Y, %H:%M')} "
        f"(timezone {captured_at.tzinfo}, locale {locale}).\n"
        "Find any events in this screenshot and return the JSON."
    )


# Signals that the event is unclear even when the model sounds sure: always ask first.
MAX_RANGE_DAYS = 31  # longer "events" are usually misreads (or semesters nobody wants as one block)


def decide(confidence: float, notes: list[str]) -> str:
    """Policy gate (CLAUDE.md §2.5): confidence alone decides whether to add or ask.

    Signals like `parser_model_disagree` or `no_time_all_day` used to force "ask" even at high
    confidence. They no longer do — they already cost confidence through the penalties in
    to_proposal(), so counting them twice meant confident events still interrupted the user.
    The notes are still emitted for debugging and evals.

    Safe because a calendar add is reversible and ships with Undo (CLAUDE.md §2.5, D8 covers only
    irreversible actions). Form proposals are unaffected: those are always "ask".
    """
    return "auto_add" if confidence >= settings.auto_add_threshold else "ask"


def resolve_end_date(ev: RawEvent, range_end_text: Optional[str], start_date, captured_at: datetime, locale: str, notes: list[str]):
    """Last day of a multi-day event, or None for single-day events."""
    end_text = range_end_text or ev.end_date_text
    if not end_text and not ev.end_date_guess:
        return None, 0.0
    # The model itself says it ends the same day: single-day event, whatever the end text parses to.
    if not range_end_text and ev.end_date_guess == start_date.isoformat():
        return None, 0.0
    r = resolve_date(end_text, ev.end_date_guess, captured_at, locale)
    notes += [f"end:{n}" for n in r.notes]
    end = r.value
    if end is None or end == start_date:
        return None, 0.0
    if end < start_date:
        try:
            end = end.replace(year=end.year + 1)  # "28 Dec - 2 Jan"
        except ValueError:
            end = None
    if end is None or (end - start_date).days > MAX_RANGE_DAYS:
        notes.append("range_ignored")
        return None, 0.1
    return end, r.penalty / 2


def to_proposal(ev: RawEvent, genre: str, captured_at: datetime, tz: ZoneInfo, locale: str) -> Optional[Proposal]:
    notes: list[str] = []
    confidence = max(0.0, min(1.0, ev.confidence))

    # "12 - 16 October 2026" in date_text: split it ourselves, even if the model didn't.
    rng = split_range(ev.date_text) or split_range(ev.end_date_text)
    start_text = rng[0] if rng else ev.date_text

    resolved = resolve_date(start_text, ev.date_guess, captured_at, locale)
    notes += resolved.notes
    confidence -= resolved.penalty
    if resolved.value is None:
        return None

    end_date, end_penalty = resolve_end_date(ev, rng[1] if rng else None, resolved.value, captured_at, locale, notes)
    confidence -= end_penalty

    start_t = parse_hhmm(ev.start_time)
    end_t = parse_hhmm(ev.end_time)
    description = ev.description

    if end_date is not None:
        # Multi-day: one all-day event across the whole range. Daily hours go in the description,
        # so the calendar doesn't show one block running through the nights.
        all_day = True
        start_s = resolved.value.isoformat()
        end_s = (end_date + timedelta(days=1)).isoformat()  # exclusive
        notes.append(f"multi_day({(end_date - resolved.value).days + 1}d)")
        if start_t:
            hours = f"Daily {start_t:%H:%M}" + (f"–{end_t:%H:%M}" if end_t else "")
            description = f"{hours}. {description}" if description else hours
        event_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tz)
    elif start_t is None:
        # No time: all-day event (deadlines, festivals). Slightly less sure.
        all_day = True
        start_s = resolved.value.isoformat()
        end_s = (resolved.value + timedelta(days=1)).isoformat()
        confidence -= 0.1
        notes.append("no_time_all_day")
        event_end = datetime.combine(resolved.value + timedelta(days=1), datetime.min.time(), tz)
    else:
        all_day = False
        start = datetime.combine(resolved.value, start_t, tz)
        if end_t is not None:
            end = datetime.combine(resolved.value, end_t, tz)
            if end <= start:  # e.g. 22:00-01:00
                end += timedelta(days=1)
        else:
            end = start + DEFAULT_DURATION.get(genre, timedelta(hours=1))
            notes.append("default_duration")
        start_s, end_s = start.isoformat(), end.isoformat()
        event_end = end

    if event_end < datetime.now(tz):
        notes.append("event_in_past")
        return None

    confidence = round(max(0.0, confidence), 2)
    return Proposal(
        id=hashlib.sha1(f"{ev.title.strip().lower()}|{start_s}".encode()).hexdigest()[:12],
        decision=decide(confidence, notes),
        payload=CalendarPayload(
            title=ev.title.strip()[:120],
            start=start_s,
            end=end_s,
            all_day=all_day,
            timezone=str(tz),
            location=Location(name=ev.location, online_url=ev.online_url),
            description=description,
        ),
        confidence=confidence,
        evidence=ev.evidence,
        notes=notes,
    )


MAX_LINKS = 4  # bounds latency and how much of a screenshot's link list we will chase


def qr_links(image_bytes: bytes) -> list[str]:
    """URLs decoded from QR codes. Exact, unlike OCR of a long random id."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            return qr_urls(im.convert("RGB"))
    except Exception:  # noqa: BLE001 - QR decoding is best-effort, never fatal
        return []


def candidate_links(image_bytes: bytes, extraction: Extraction) -> list[tuple[str, str]]:
    """(url, source) worth visiting, best first, deduplicated.

    QR codes come first because they carry the exact bytes; the link the model singled out as a
    form comes next; everything else it saw follows.
    """
    ordered: list[tuple[str, str]] = [(u, "qr") for u in qr_links(image_bytes)]
    if extraction.form_url:
        ordered.append((extraction.form_url, "ocr"))
    ordered += [(u, "ocr") for u in extraction.links_seen]

    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for url, source in ordered:
        try:
            # Syntactic only. The address check that blocks private hosts lives in links.fetch,
            # so it runs once, on the real connection, including every redirect hop.
            normalised = normalise(url)
        except UnsafeUrlError:
            continue  # not a usable http(s) URL
        if normalised in seen:
            continue
        seen.add(normalised)
        out.append((normalised, source))
        if len(out) >= MAX_LINKS:
            break
    return out


def to_form_proposal(payload: FormPayload, evidence: str, source: str, likelihood: float) -> FormProposal:
    """Wrap a detected form.

    Always `decision="ask"`: opening a pre-filled form is one step from submitting it, so it never
    happens without the user (CLAUDE.md §4.6, D8).
    """
    known = sum(1 for f in payload.fields if f.profile_key)
    sensitive = sum(1 for f in payload.fields if f.sensitive)
    notes = [
        f"source:{source}",
        f"provider:{payload.provider}",
        f"prefill:{payload.prefill_style}",
        f"fields:{len(payload.fields)}",
        f"profile_known:{known}",
    ]
    if sensitive:
        notes.append(f"sensitive_fields_skipped:{sensitive}")
    return FormProposal(
        id=hashlib.sha1(payload.form_url.encode()).hexdigest()[:12],
        payload=payload,
        # Fields read off the live page are facts; the only doubt is whether a page with a <form>
        # on it is really the thing the user wants to fill.
        confidence=round(min(1.0, 0.6 + likelihood * 0.4), 2),
        evidence=evidence,
        notes=notes,
    )


async def explore_links(image_bytes: bytes, extraction: Extraction) -> tuple[list[FormProposal], list[LinkContext], Optional[str]]:
    """Visit the links in the screenshot to find out what it is actually about.

    Everything fetched is untrusted data (CLAUDE.md §4.1): it decides what we *report*, never what
    later.exe does. links.fetch refuses private addresses, so a link cannot reach internal hosts.
    """
    candidates = candidate_links(image_bytes, extraction)
    if not candidates:
        return [], [], None

    pages = await asyncio.gather(*(fetch_page(url) for url, _ in candidates))

    forms: list[FormProposal] = []
    contexts: list[LinkContext] = []
    unreachable = False
    for (url, source), page in zip(candidates, pages):
        if page is None:
            unreachable = True
            contexts.append(LinkContext(url=url, domain=urlparse(url).netloc, source=source))
            continue
        payload = detect_form(page)
        title, description = page_meta(page.html)
        contexts.append(
            LinkContext(
                url=page.url,
                domain=urlparse(page.url).netloc,
                title=title,
                description=(description or "")[:300] or None,
                is_form=payload is not None,
                source=source,
            )
        )
        if payload and len(forms) < 2:
            likelihood, reasons = form_likelihood(page.url, page)
            payload.reasons = payload.reasons + [r for r in reasons if r not in payload.reasons]
            forms.append(to_form_proposal(payload, evidence=url, source=source, likelihood=likelihood))

    error = "form_link_unreadable" if (unreachable and not forms) else None
    return forms, contexts, error


async def analyze(
    client: ModelClient,
    image_bytes: bytes,
    captured_at: Optional[datetime] = None,
    timezone: Optional[str] = None,
    locale: str = "en-HK",
) -> AnalyzeResponse:
    t0 = clock.perf_counter()
    try:
        tz = ZoneInfo(timezone or settings.default_timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        if not timezone:
            raise
        raise InvalidInputError("invalid timezone") from e
    captured_at = (captured_at or datetime.now(tz)).astimezone(tz)

    try:
        image_b64 = preprocess_image(image_bytes, settings.max_image_side)
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        raise InvalidInputError("invalid or corrupt image") from e
    extraction: Extraction = await client.extract(image_b64, SKILL_PROMPT, build_user_prompt(captured_at, locale))

    # A screenshot can hold a form and no event at all, so this is independent of `actionable`.
    # Sensitive screenshots are still dropped outright (CLAUDE.md §4.5).
    # Follow the links to learn what the screenshot is really about. Independent of `actionable`
    # (a page can be a form with no event) and skipped entirely for sensitive screenshots (§4.5).
    forms: list[FormProposal] = []
    links: list[LinkContext] = []
    form_error: Optional[str] = None
    if not extraction.sensitive:
        forms, links, form_error = await explore_links(image_bytes, extraction)

    proposals: list[Proposal] = []
    seen_ids: set[str] = set()
    skipped = extraction.skipped_reason
    if extraction.sensitive:
        skipped = "sensitive_content"
    elif extraction.actionable:
        for ev in extraction.events[:10]:
            p = to_proposal(ev, extraction.genre, captured_at, tz, locale)
            if p and p.confidence >= settings.ask_threshold and p.id not in seen_ids:
                proposals.append(p)
                seen_ids.add(p.id)
        if not proposals and not skipped:
            skipped = "no_confident_future_events"

    return AnalyzeResponse(
        proposals=proposals,
        forms=forms,
        links=links,
        genre=extraction.genre,
        skipped_reason=None if (proposals or forms) else (skipped or form_error or "not_actionable"),
        model=client.name,
        latency_ms=int((clock.perf_counter() - t0) * 1000),
    )
