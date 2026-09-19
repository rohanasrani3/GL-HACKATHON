"""Screenshot → proposals. Preprocess image, call the model, resolve dates, score, filter."""
import base64
import io
import time as clock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from PIL import Image

from .config import settings
from .datetime_resolve import DEFAULT_DURATION, parse_hhmm, resolve_date
from .models import ModelClient
from .schema import AnalyzeResponse, CalendarPayload, Extraction, Location, Proposal, RawEvent

SKILL_PROMPT = (Path(__file__).parent / "skills" / "calendar_event" / "SKILL.md").read_text(encoding="utf-8")


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


def to_proposal(ev: RawEvent, genre: str, captured_at: datetime, tz: ZoneInfo, locale: str) -> Optional[Proposal]:
    notes: list[str] = []
    confidence = max(0.0, min(1.0, ev.confidence))

    resolved = resolve_date(ev.date_text, ev.date_guess, captured_at, locale)
    notes += resolved.notes
    confidence -= resolved.penalty
    if resolved.value is None:
        return None

    start_t = parse_hhmm(ev.start_time)
    end_t = parse_hhmm(ev.end_time)

    if start_t is None:
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

    return Proposal(
        payload=CalendarPayload(
            title=ev.title.strip()[:120],
            start=start_s,
            end=end_s,
            all_day=all_day,
            timezone=str(tz),
            location=Location(name=ev.location, online_url=ev.online_url),
            description=ev.description,
        ),
        confidence=round(max(0.0, confidence), 2),
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
    tz = ZoneInfo(timezone or settings.default_timezone)
    captured_at = (captured_at or datetime.now(tz)).astimezone(tz)

    image_b64 = preprocess_image(image_bytes, settings.max_image_side)
    extraction: Extraction = await client.extract(image_b64, SKILL_PROMPT, build_user_prompt(captured_at, locale))

    proposals: list[Proposal] = []
    skipped = extraction.skipped_reason
    if extraction.sensitive:
        skipped = "sensitive_content"
    elif extraction.actionable:
        for ev in extraction.events[:10]:
            p = to_proposal(ev, extraction.genre, captured_at, tz, locale)
            if p and p.confidence >= settings.min_confidence:
                proposals.append(p)
        if not proposals and not skipped:
            skipped = "no_confident_future_events"

    return AnalyzeResponse(
        proposals=proposals,
        genre=extraction.genre,
        skipped_reason=None if proposals else (skipped or "not_actionable"),
        model=client.name,
        latency_ms=int((clock.perf_counter() - t0) * 1000),
    )
