"""Decide whether a fetched page is a form, and read its fields.

Three tiers, most reliable first:

1. **Google Forms** - the field ids are in the page data, so prefill is exact.
2. **Known hosted builders** (Typeform, Tally, Jotform, Microsoft Forms, ...) - the markup is
   rendered by JavaScript so there is usually nothing to parse, but the host itself is proof
   that it's a form, and several accept `?name=value` prefill.
3. **Any page with a real `<form>`** - parse the inputs and use their `name` attributes.

Everything here works on already-fetched HTML (see links.py for the fetch rules). Page content is
data, never instruction: nothing read here can change what later.exe does, only what it reports.
"""
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .forms import parse_form_html, profile_key_for
from .links import FetchedPage
from .schema import FormField, FormPayload

# Hosts that are forms by definition. Value is the prefill style they accept.
KNOWN_PROVIDERS: dict[str, tuple[str, str]] = {
    "docs.google.com": ("google_forms", "google_forms"),
    "forms.gle": ("google_forms", "google_forms"),
    "forms.google.com": ("google_forms", "google_forms"),
    "forms.office.com": ("microsoft_forms", "none"),
    "forms.microsoft.com": ("microsoft_forms", "none"),
    "typeform.com": ("typeform", "query"),
    "tally.so": ("tally", "query"),
    "jotform.com": ("jotform", "query"),
    "airtable.com": ("airtable", "query"),
    "cognitoforms.com": ("cognito", "query"),
    "wufoo.com": ("wufoo", "query"),
    "formstack.com": ("formstack", "query"),
    "surveymonkey.com": ("surveymonkey", "none"),
    "fillout.com": ("fillout", "query"),
}

# Words in a URL path that suggest a form without needing the page at all.
_PATH_HINTS = ("form", "register", "registration", "signup", "sign-up", "apply",
               "application", "rsvp", "survey", "enrol", "enroll", "join", "booking")

# CLAUDE.md §4.6: never fill these, whatever the profile holds.
_SENSITIVE = re.compile(
    r"password|passwd|\bpin\b|cvv|cvc|card.?number|credit.?card|iban|account.?number|"
    r"ssn|social.?security|passport|aadhaar|hkid|national.?id|govern",
    re.I,
)

_SKIP_TYPES = {"hidden", "submit", "button", "image", "reset", "file", "password"}


def provider_for(url: str) -> tuple[Optional[str], Optional[str]]:
    host = (urlparse(url).hostname or "").lower()
    for known, (provider, style) in KNOWN_PROVIDERS.items():
        if host == known or host.endswith(f".{known}"):
            return provider, style
    return None, None


def _label_for(el, soup) -> str:
    """Best human-readable name for an input: <label for>, wrapping label, aria-label, placeholder."""
    el_id = el.get("id")
    if el_id:
        lab = soup.find("label", attrs={"for": el_id})
        if lab and lab.get_text(strip=True):
            return lab.get_text(" ", strip=True)
    parent_label = el.find_parent("label")
    if parent_label and parent_label.get_text(strip=True):
        return parent_label.get_text(" ", strip=True)
    for attr in ("aria-label", "placeholder", "title", "name"):
        v = el.get(attr)
        if v:
            return str(v)
    return "Field"


def _field_from(el, soup) -> Optional[FormField]:
    tag = el.name.lower()
    itype = (el.get("type") or ("textarea" if tag == "textarea" else "text")).lower()
    if tag == "input" and itype in _SKIP_TYPES:
        return None
    name = el.get("name") or el.get("id")
    if not name:
        return None

    label = _label_for(el, soup)
    sensitive = bool(_SENSITIVE.search(f"{name} {label}")) or itype == "password"

    options: list[str] = []
    if tag == "select":
        options = [o.get_text(" ", strip=True) for o in el.find_all("option") if o.get_text(strip=True)]
        ftype = "dropdown"
    elif itype in ("radio", "checkbox"):
        ftype = "multiple_choice" if itype == "radio" else "checkboxes"
    elif tag == "textarea":
        ftype = "paragraph"
    else:
        ftype = {"email": "email", "tel": "phone", "number": "number", "date": "date"}.get(itype, "short_text")

    return FormField(
        entry_id=str(name),
        question=label.strip()[:200],
        # A sensitive field never gets a profile key, so nothing can auto-fill it.
        profile_key=None if sensitive else profile_key_for(f"{label} {name}"),
        required=el.has_attr("required") or (el.get("aria-required") == "true"),
        type=ftype,
        options=options[:20],
        sensitive=sensitive,
    )


def _group_label(el, soup, name: str) -> str:
    """Question text for a radio/checkbox group: the fieldset legend, else the input name."""
    fieldset = el.find_parent("fieldset")
    if fieldset:
        legend = fieldset.find("legend")
        if legend and legend.get_text(strip=True):
            return legend.get_text(" ", strip=True)
    return name.replace("_", " ").replace("-", " ").strip().capitalize()


def _collect_fields(form_el, soup) -> list[FormField]:
    """Inputs of one <form>, with radio/checkbox groups collapsed into a single question.

    A three-option radio group is one question with three options, not three fields — emitting
    one field per option would both read wrong and produce duplicate prefill parameters.
    """
    out: list[FormField] = []
    by_name: dict[str, FormField] = {}
    for el in form_el.find_all(["input", "select", "textarea"]):
        field = _field_from(el, soup)
        if field is None:
            continue
        if field.type in ("multiple_choice", "checkboxes"):
            existing = by_name.get(field.entry_id)
            option = el.get("value") or field.question
            if existing is not None:
                if option and option not in existing.options:
                    existing.options.append(str(option))
                continue
            field.options = [str(option)] if option else []
            field.question = _group_label(el, soup, field.entry_id)
            field.profile_key = None  # a choice group is never answered from the profile
            by_name[field.entry_id] = field
        out.append(field)
    return out


def _page_meta(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    title = soup.title.get_text(strip=True) if soup.title else None
    desc = None
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            desc = tag["content"].strip()
            break
    return title, desc


@dataclass
class PageFacts:
    """Everything later.exe needs from one fetched page."""
    form: Optional[FormPayload]
    title: Optional[str]
    description: Optional[str]


def read_page(page: FetchedPage) -> PageFacts:
    """Parse the page **once** and answer both questions: what is it, and is it a form?

    One entry point on purpose. Form detection and the title/description both need the parsed
    document, and parsing every fetched page two or three times was by far the most expensive
    thing this module did.
    """
    soup = BeautifulSoup(page.html, "html.parser")
    title, description = _page_meta(soup)
    return PageFacts(form=_detect_form(page, soup, title), title=title, description=description)


def detect_form(page: FetchedPage) -> Optional[FormPayload]:
    """Return a FormPayload if this page is a form we can describe, else None."""
    return read_page(page).form


def _detect_form(page: FetchedPage, soup: BeautifulSoup, title: Optional[str]) -> Optional[FormPayload]:
    url = page.url
    provider, style = provider_for(url)
    reasons: list[str] = []

    # 1. Google Forms: exact field ids.
    if provider == "google_forms":
        payload = parse_form_html(page.html, url, title)
        if payload:
            payload.provider = "google_forms"
            payload.prefill_style = "google_forms"
            payload.reasons = ["google forms page", f"{len(payload.fields)} questions read from the form"]
            return payload
        reasons.append("google forms host, but the questions could not be read")

    # 2. Any real <form> on the page: use the one with the most usable inputs.
    best: list[FormField] = []
    best_method = "get"
    for form_el in soup.find_all("form"):
        fields = _collect_fields(form_el, soup)
        if len(fields) > len(best):
            best, best_method = fields, (form_el.get("method") or "get").lower()

    if best:
        reasons.append(f"page contains a form with {len(best)} fields")
        if any(f.sensitive for f in best):
            reasons.append("some fields are sensitive and will not be pre-filled")
        return FormPayload(
            form_url=url,
            title=title,
            domain=urlparse(url).netloc,
            fields=best,
            # A GET form takes its values in the query string; a POST form cannot be prefilled by URL.
            prefill_style=style or ("query" if best_method == "get" else "none"),
            provider=provider or "generic",
            reasons=reasons,
        )

    # 3. A known builder whose markup is JavaScript-rendered: no fields to read, but it is
    #    certainly a form, and opening it is still the useful action.
    if provider:
        reasons.append(f"{provider.replace('_', ' ')} link")
        reasons.append("questions are rendered by the page, so they can't be read in advance")
        return FormPayload(
            form_url=url, title=title, domain=urlparse(url).netloc, fields=[],
            prefill_style=style or "none", provider=provider, reasons=reasons,
        )

    return None


def form_likelihood(url: str, page: Optional[FetchedPage]) -> tuple[float, list[str]]:
    """How likely this link is a form, used when we want to guess before/without fetching."""
    score, reasons = 0.0, []
    provider, _ = provider_for(url)
    if provider:
        score += 0.8
        reasons.append(f"{provider.replace('_', ' ')} host")
    path = (urlparse(url).path or "").lower()
    if any(h in path for h in _PATH_HINTS):
        score += 0.3
        reasons.append("url path mentions registration")
    if page:
        lowered = page.html.lower()
        if "<form" in lowered:
            score += 0.4
            reasons.append("page contains a <form>")
        if "fb_public_load_data_" in lowered:
            score += 0.8
            reasons.append("google forms page data")
    return min(score, 1.0), reasons
