"""Form-fill skill: link detection, form parsing, profile mapping and the safety rules."""
import io
import json

import pytest
from PIL import Image

from snapsort import pipeline
from snapsort.forms import _extract_load_data, looks_like_form, parse_form_html, profile_key_for
from snapsort.schema import Extraction, FormPayload


def _load_data(questions: list) -> str:
    """Minimal page carrying a FB_PUBLIC_LOAD_DATA_ array shaped like a real Google Form."""
    data = [None, [None, questions], None]
    return f"<html><title>Signup</title><script>var FB_PUBLIC_LOAD_DATA_ = {json.dumps(data)};</script></html>"


def _question(entry_id: int, title: str, qtype: int = 0, required: bool = False, options=None):
    opts = [[o] for o in (options or [])] or None
    return [1234, title, None, qtype, [[entry_id, opts, 1 if required else 0]]]


# ---------- link detection ----------

@pytest.mark.parametrize("url", [
    "https://docs.google.com/forms/d/1abc/viewform",
    "https://docs.google.com/forms/d/e/1FAIpQLS_x/viewform",
    "https://forms.gle/abc123",
    "forms.gle/abc123",
])
def test_form_links_are_recognised(url):
    assert looks_like_form(url)


@pytest.mark.parametrize("url", [
    None, "", "https://example.com/register", "https://docs.google.com/document/d/1abc/edit",
    "https://evil.com/docs.google.com/forms/d/1abc",  # host must actually be Google
])
def test_non_form_links_are_rejected(url):
    assert not looks_like_form(url)


# ---------- profile mapping ----------

@pytest.mark.parametrize("question,key", [
    ("Name?", "full_name"),
    ("Full Name", "full_name"),
    ("Email?", "email"),
    ("E-mail address", "email"),
    ("Phone Number?", "phone"),
    ("Age?", "age"),
    ("Location?", "location"),
    ("Which university do you attend?", "organisation"),
    ("Student ID", "student_id"),          # must not be captured by the generic name/id patterns
    ("Any dietary requirements?", "dietary"),
    ("What is your favourite colour?", None),  # nothing in the profile answers this
])
def test_questions_map_to_profile_keys(question, key):
    assert profile_key_for(question) == key


# ---------- parsing ----------

def test_parses_fields_and_entry_ids():
    html = _load_data([_question(1046611833, "Name?"), _question(373191682, "Email?", required=True)])
    payload = parse_form_html(html, "https://docs.google.com/forms/d/e/X/viewform")
    assert [f.entry_id for f in payload.fields] == ["entry.1046611833", "entry.373191682"]
    assert [f.profile_key for f in payload.fields] == ["full_name", "email"]
    assert payload.fields[1].required is True
    assert payload.domain == "docs.google.com"


def test_parses_choice_options():
    html = _load_data([_question(1, "T-shirt size", qtype=2, options=["S", "M", "L"])])
    payload = parse_form_html(html, "https://docs.google.com/forms/d/e/X/viewform")
    assert payload.fields[0].type == "multiple_choice"
    assert payload.fields[0].options == ["S", "M", "L"]


def test_bracket_inside_a_question_does_not_truncate_the_form():
    """Regex-to-first-`];` breaks here; the bracket scanner must not."""
    html = _load_data([_question(1, "Name [as on your ID]?"), _question(2, "Email?")])
    payload = parse_form_html(html, "https://docs.google.com/forms/d/e/X/viewform")
    assert len(payload.fields) == 2


def test_page_without_load_data_is_not_a_form():
    assert _extract_load_data("<html>no form here</html>") is None
    assert parse_form_html("<html>no form here</html>", "https://docs.google.com/x") is None


def test_form_with_no_questions_is_ignored():
    assert parse_form_html(_load_data([]), "https://docs.google.com/forms/d/e/X/viewform") is None


# ---------- pipeline integration + safety ----------

def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buf, format="PNG")
    return buf.getvalue()


class _Stub:
    name = "stub"

    def __init__(self, **kw):
        self.kw = kw

    async def extract(self, *_a):
        return Extraction(
            genre="poster", sensitive=self.kw.get("sensitive", False), actionable=False,
            events=[], skipped_reason=None, form_url=self.kw.get("form_url"),
        )

    async def warmup(self):
        return None


def _payload() -> FormPayload:
    return FormPayload(
        form_url="https://docs.google.com/forms/d/e/X/viewform",
        title="Signup", domain="docs.google.com", fields=[],
    )


@pytest.mark.anyio
async def test_form_proposal_is_always_ask_never_auto(monkeypatch):
    """CLAUDE.md §4.6 / D8: a pre-filled form is one step from submitting, so it always confirms."""
    async def fake(url, timeout=15.0):
        return _payload()

    monkeypatch.setattr(pipeline, "resolve_google_form", fake)
    result = await pipeline.analyze(_Stub(form_url="https://forms.gle/abc"), _png())
    assert len(result.forms) == 1
    assert result.forms[0].decision == "ask"
    assert result.forms[0].action == "form.prefill"


@pytest.mark.anyio
async def test_sensitive_screenshot_never_resolves_a_form(monkeypatch):
    """CLAUDE.md §4.5: a banking/OTP screenshot is dropped before any network call."""
    async def boom(url, timeout=15.0):
        raise AssertionError("must not fetch a form from a sensitive screenshot")

    monkeypatch.setattr(pipeline, "resolve_google_form", boom)
    result = await pipeline.analyze(_Stub(form_url="https://forms.gle/abc", sensitive=True), _png())
    assert result.forms == []
    assert result.skipped_reason == "sensitive_content"


@pytest.mark.anyio
async def test_non_form_url_is_not_fetched(monkeypatch):
    async def boom(url, timeout=15.0):
        raise AssertionError("must not fetch a non-form link")

    monkeypatch.setattr(pipeline, "resolve_google_form", boom)
    result = await pipeline.analyze(_Stub(form_url="https://example.com/register"), _png())
    assert result.forms == []


# ---------- QR codes (CLAUDE.md §4.7) ----------

def test_qr_code_decodes_exactly():
    """The reason QR beats OCR: a 44-character form id survives verbatim."""
    qrcode = pytest.importorskip("qrcode")
    pytest.importorskip("zxingcpp")
    from snapsort.forms import qr_urls

    url = "https://docs.google.com/forms/d/1fLuq0w3qhlz0ix1MLPzWyAVcWwVVBP79RWaESEX8d64/viewform"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    canvas = Image.new("RGB", (900, 900), "white")
    canvas.paste(qr.make_image(fill_color="black", back_color="white").convert("RGB"), (100, 100))
    assert qr_urls(canvas) == [url]


def test_image_without_a_qr_yields_nothing():
    pytest.importorskip("zxingcpp")
    from snapsort.forms import qr_urls

    assert qr_urls(Image.new("RGB", (300, 300), "white")) == []


@pytest.mark.anyio
async def test_qr_link_beats_a_misread_url(monkeypatch):
    """A model OCRing the id off a poster gets characters wrong; the QR is authoritative."""
    right = "https://docs.google.com/forms/d/RIGHT/viewform"
    wrong = "https://docs.google.com/forms/d/WR0NG/viewform"
    seen = {}

    async def fake(url, timeout=15.0):
        seen["url"] = url
        return _payload()

    monkeypatch.setattr(pipeline, "qr_urls", lambda _im: [right])
    monkeypatch.setattr(pipeline, "resolve_google_form", fake)
    result = await pipeline.analyze(_Stub(form_url=wrong), _png())
    assert seen["url"] == right
    assert "source:qr" in result.forms[0].notes


@pytest.mark.anyio
async def test_unreadable_link_is_reported_rather_than_silent(monkeypatch):
    async def unresolvable(url, timeout=15.0):
        return None

    monkeypatch.setattr(pipeline, "resolve_google_form", unresolvable)
    result = await pipeline.analyze(_Stub(form_url="https://forms.gle/abc"), _png())
    assert result.forms == []
    assert result.skipped_reason == "form_link_unreadable"
