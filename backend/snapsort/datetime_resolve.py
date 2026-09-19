"""Deterministic date/time resolution (skills.md §2.3).

The model copies the date phrase from the screenshot and gives its own guess. Here we
re-parse the phrase against the *capture time* with dateparser and reconcile the two.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

import dateparser

SLANG = {
    r"\btmrw\b|\btmr\b|\btmrow\b|\btomoz\b": "tomorrow",
    r"\btdy\b|\btday\b": "today",
    r"\btonite\b|\btonight\b": "today",
    r"\bnxt\b": "next",
}

# Locales that write day before month (26/9). Everything else defaults to month first.
DMY_REGIONS = {"HK", "IN", "GB", "AU", "SG", "MY", "NZ", "IE", "ZA", "FR", "DE", "ES", "IT"}


@dataclass
class ResolvedDate:
    value: Optional[date]
    notes: list[str] = field(default_factory=list)
    penalty: float = 0.0


def _normalise(text: str) -> str:
    text = text.lower().strip()
    for pattern, repl in SLANG.items():
        text = re.sub(pattern, repl, text)
    # "this friday" -> "friday" (dateparser + PREFER_DATES_FROM=future handles bare weekdays)
    text = re.sub(r"\bthis\s+(?=mon|tue|wed|thu|fri|sat|sun)", "", text)
    # Drop ordinal suffixes: 26th -> 26
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)
    return text


def _date_order(locale: str) -> str:
    region = locale.replace("_", "-").split("-")[-1].upper() if locale else ""
    return "DMY" if region in DMY_REGIONS else "MDY"


def resolve_date(date_text: Optional[str], date_guess: Optional[str], anchor: datetime, locale: str = "en-HK") -> ResolvedDate:
    """Resolve a date phrase against `anchor` (the screenshot's capture time, tz-aware)."""
    anchor_naive = anchor.replace(tzinfo=None)
    parsed: Optional[date] = None
    guess: Optional[date] = None
    notes: list[str] = []

    if date_text:
        dt = dateparser.parse(
            _normalise(date_text),
            settings={
                "RELATIVE_BASE": anchor_naive,
                "PREFER_DATES_FROM": "future",
                "DATE_ORDER": _date_order(locale),
                "PREFER_DAY_OF_MONTH": "first",
            },
        )
        if dt:
            parsed = dt.date()

    if date_guess:
        try:
            guess = date.fromisoformat(date_guess)
        except ValueError:
            notes.append("bad_model_date_guess")

    if parsed and guess:
        if parsed == guess:
            return ResolvedDate(parsed, notes + ["parser_and_model_agree"])
        return ResolvedDate(parsed, notes + [f"parser_model_disagree(model={guess})"], penalty=0.15)
    if parsed:
        return ResolvedDate(parsed, notes + ["parser_only"], penalty=0.05)
    if guess:
        return ResolvedDate(guess, notes + ["model_guess_only"], penalty=0.1)
    return ResolvedDate(None, notes + ["no_date"], penalty=1.0)


def parse_hhmm(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
    if not m:
        return None
    h, mnt = int(m.group(1)), int(m.group(2))
    if h > 23 or mnt > 59:
        return None
    return time(h, mnt)


DEFAULT_DURATION = {
    "chat": timedelta(hours=1),
    "email": timedelta(hours=1),
    "ticket": timedelta(hours=2),
    "poster": timedelta(hours=2),
    "social_post": timedelta(hours=2),
    "timetable": timedelta(hours=1),
    "other": timedelta(hours=1),
}
