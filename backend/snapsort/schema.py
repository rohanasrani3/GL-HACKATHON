"""Data contracts.

Two layers:
- `Extraction` / `RawEvent`: what the *model* returns. Dates are kept as raw text plus a guess;
  deterministic code (datetime_resolve.py) turns them into real datetimes.
- `AnalyzeResponse` / `Proposal`: what the *API* returns to the phone (skills.md §1 contract).
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Genre = Literal["poster", "chat", "ticket", "email", "timetable", "social_post", "other"]


# ---------- Model output ----------

class RawEvent(BaseModel):
    title: str = Field(description="Short, clean event title, e.g. 'Generative AI in Healthcare (talk)'")
    date_text: Optional[str] = Field(
        description="The date exactly as written in the screenshot, e.g. 'Fri 26 Sept', 'tomorrow', 'next Tuesday'. null if no date."
    )
    date_guess: Optional[str] = Field(description="Your best guess of the date as YYYY-MM-DD, using the capture date as reference")
    end_date_text: Optional[str] = Field(
        default=None,
        description="Multi-day events only: the LAST day as written, e.g. '16 October 2026' for '12-16 October 2026'. null for single-day events.",
    )
    end_date_guess: Optional[str] = Field(default=None, description="Multi-day events only: the last day as YYYY-MM-DD, else null")
    start_time: Optional[str] = Field(description="Start time as 24h HH:MM, null if no time given")
    end_time: Optional[str] = Field(description="End time as 24h HH:MM, null if not given")
    location: Optional[str] = Field(description="Venue or address as written, null if none")
    online_url: Optional[str] = Field(description="Meeting / event URL if visible, else null")
    description: Optional[str] = Field(description="One-line useful detail (organiser, booking ref, speaker), else null")
    confidence: float = Field(description="0.0-1.0: how sure you are this is a real event the user would want in their calendar")
    evidence: str = Field(description="The exact text from the screenshot that states the date/time")


class Extraction(BaseModel):
    genre: Genre
    sensitive: bool = Field(description="true if the screenshot shows banking, passwords, OTPs, IDs or medical records")
    actionable: bool = Field(description="true if the screenshot contains at least one event, meeting, appointment or deadline")
    # Listed *before* events on purpose: making small models enumerate every date first stops them
    # from latching onto one date and missing the rest (e.g. a programme AND its application deadline).
    dates_seen: list[str] = Field(
        default_factory=list,
        description="Every date or date range written anywhere in the screenshot, copied exactly, e.g. ['20 Sept 2026 (Sun)', '12-16 October 2026']",
    )
    events: list[RawEvent] = Field(description="One event per distinct date or date range in dates_seen that is an event, deadline or appointment")
    # v3 (form autofill): the model only *reports* the link. Deterministic code fetches the form
    # and reads its real field ids, and the device fills the values (CLAUDE.md D3, §2.8, §4.3).
    links_seen: list[str] = Field(
        default_factory=list,
        description=(
            "Every web link visible anywhere in the screenshot, copied exactly as written: registration "
            "links, 'more info' URLs, links in a browser address bar, short links (bit.ly, forms.gle), "
            "and the caption under a QR code. Empty list if there are none."
        ),
    )
    form_url: Optional[str] = Field(
        default=None,
        description=(
            "Of the links in links_seen, the one that most looks like a form to fill in (registration, "
            "signup, RSVP, application, survey). null if none of them do."
        ),
    )
    skipped_reason: Optional[str] = Field(description="If actionable is false, a few words on why, else null")


# ---------- API output ----------

class Location(BaseModel):
    name: Optional[str] = None
    online_url: Optional[str] = None


class CalendarPayload(BaseModel):
    title: str
    start: str  # ISO 8601 with offset, or YYYY-MM-DD when all_day
    end: str
    all_day: bool
    timezone: str
    location: Location
    description: Optional[str] = None


Decision = Literal["auto_add", "ask"]


class Proposal(BaseModel):
    id: str  # stable hash of title+start: use for notification ids and dedup
    action: Literal["calendar.create"] = "calendar.create"
    decision: Decision  # "auto_add": add then notify with Undo · "ask": confirm with the user first
    payload: CalendarPayload
    confidence: float
    evidence: str
    notes: list[str] = []  # why confidence was adjusted, for debugging and evals


# Canonical keys for the on-device profile (CLAUDE.md §2.8). The backend only ever names these;
# the values live on the phone and are never sent here.
PROFILE_KEYS = (
    "full_name", "email", "phone", "age", "location",
    "organisation", "student_id", "dietary", "website",
)


class FormField(BaseModel):
    # The prefill query parameter: "entry.1046611833" on Google Forms, otherwise the input's name.
    entry_id: str
    question: str
    profile_key: Optional[str] = None  # which profile field answers this; null = ask the user
    required: bool = False
    type: str = "short_text"
    options: list[str] = []
    # Passwords, card numbers and government IDs. CLAUDE.md §4.6 forbids ever filling these, so
    # they are reported (so the user knows the form asks) but never prefilled.
    sensitive: bool = False


# How the destination accepts pre-filled answers:
#   google_forms - ?usp=pp_url&entry.N=value, exact and reliable
#   query        - ?<input name>=value; works on many GET forms and hosted builders
#   none         - no URL prefill; later.exe opens it and shows the values to copy
PrefillStyle = Literal["google_forms", "query", "none"]


class FormPayload(BaseModel):
    form_url: str  # the device appends the prefill query itself
    title: Optional[str] = None
    domain: str  # shown to the user before anything opens (CLAUDE.md §4.7)
    fields: list[FormField]
    prefill_style: PrefillStyle = "none"
    provider: str = "generic"  # google_forms | typeform | tally | ... | generic
    # Why we think this is a form, shown in the UI so the guess is never a black box.
    reasons: list[str] = []


class LinkContext(BaseModel):
    """What a link in the screenshot actually points at, so the app can explain it."""
    url: str
    domain: str
    title: Optional[str] = None
    description: Optional[str] = None
    is_form: bool = False
    source: str = "ocr"  # qr | ocr


class FormProposal(BaseModel):
    id: str
    action: Literal["form.prefill"] = "form.prefill"
    # Forms are never auto-filled-and-submitted: §4.6 and D8 make this always a confirmation.
    decision: Literal["ask"] = "ask"
    payload: FormPayload
    confidence: float
    evidence: str
    notes: list[str] = []


class AnalyzeResponse(BaseModel):
    proposals: list[Proposal]
    # Additive on purpose: existing clients that only read `proposals` keep working unchanged.
    forms: list[FormProposal] = []
    # What the links in the screenshot turned out to be — context beyond the date and title.
    links: list[LinkContext] = []
    genre: Optional[str] = None
    skipped_reason: Optional[str] = None
    model: str
    latency_ms: int
