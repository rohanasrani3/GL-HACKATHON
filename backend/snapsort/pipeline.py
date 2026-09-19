"""Screenshot → proposals. Preprocess image, call the model, resolve dates, score, filter."""
import base64
import hashlib
import io
import time as clock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image

from .config import settings
from .datetime_resolve import DEFAULT_DURATION, parse_hhmm, resolve_date, split_range
from .models import ModelClient
from .schema import AnalyzeResponse, CalendarPayload, Extraction, Location, Proposal, RawEvent

SKILL_PROMPT = (Path(__file__).parent / "skills" / "calendar_event" / "SKILL.md").read_text(encoding="utf-8")


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
UNCLEAR_NOTES = ("parser_model_disagree", "model_guess_only", "no_time_all_day", "range_ignored")
MAX_RANGE_DAYS = 31  # longer "events" are usually misreads (or semesters nobody wants as one block)


def decide(confidence: float, notes: list[str]) -> str:
    """Policy gate (CLAUDE.md §2.5): add automatically only when confident *and* nothing is unclear."""
    if confidence >= settings.auto_add_threshold and not any(u in n for n in notes for u in UNCLEAR_NOTES):
        return "auto_add"
    return "ask"


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
        genre=extraction.genre,
        skipped_reason=None if proposals else (skipped or "not_actionable"),
        model=client.name,
        latency_ms=int((clock.perf_counter() - t0) * 1000),
    )
