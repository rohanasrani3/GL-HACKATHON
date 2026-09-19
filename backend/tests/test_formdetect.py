"""Generic form detection: any page with a form, not just Google Forms."""
import pytest

from snapsort.formdetect import detect_form, form_likelihood, provider_for
from snapsort.links import FetchedPage


def page(html: str, url: str = "https://example.com/register") -> FetchedPage:
    return FetchedPage(url=url, html=html, content_type="text/html")


REGISTER_FORM = """
<html><title>Club signup</title><body>
<form method="get" action="/submit">
  <label for="n">Your name</label><input id="n" name="fullname" type="text" required>
  <label for="e">Email address</label><input id="e" name="email" type="email" required>
  <input name="phone" type="tel" placeholder="Mobile number">
  <label for="u">Which university?</label><input id="u" name="uni" type="text">
  <select name="size"><option>S</option><option>M</option></select>
  <textarea name="notes" aria-label="Anything else?"></textarea>
  <input type="hidden" name="csrf" value="x">
  <input type="submit" value="Join">
</form></body></html>
"""


def test_generic_form_is_detected_with_fields():
    payload = detect_form(page(REGISTER_FORM))
    names = [f.entry_id for f in payload.fields]
    assert names == ["fullname", "email", "phone", "uni", "size", "notes"]
    assert payload.provider == "generic"
    assert payload.title == "Club signup"


def test_hidden_and_submit_inputs_are_ignored():
    payload = detect_form(page(REGISTER_FORM))
    assert "csrf" not in [f.entry_id for f in payload.fields]


def test_labels_come_from_label_aria_or_placeholder():
    fields = {f.entry_id: f.question for f in detect_form(page(REGISTER_FORM)).fields}
    assert fields["fullname"] == "Your name"          # <label for>
    assert fields["phone"] == "Mobile number"          # placeholder
    assert fields["notes"] == "Anything else?"         # aria-label


def test_profile_keys_are_mapped_from_labels():
    keys = {f.entry_id: f.profile_key for f in detect_form(page(REGISTER_FORM)).fields}
    assert keys["fullname"] == "full_name"
    assert keys["email"] == "email"
    assert keys["phone"] == "phone"
    assert keys["uni"] == "organisation"


def test_required_and_options_are_read():
    fields = {f.entry_id: f for f in detect_form(page(REGISTER_FORM)).fields}
    assert fields["email"].required is True
    assert fields["phone"].required is False
    assert fields["size"].options == ["S", "M"]
    assert fields["size"].type == "dropdown"


def test_get_form_is_prefillable_by_query():
    assert detect_form(page(REGISTER_FORM)).prefill_style == "query"


def test_post_form_cannot_be_prefilled_by_url():
    html = REGISTER_FORM.replace('method="get"', 'method="post"')
    assert detect_form(page(html)).prefill_style == "none"


# ---------- CLAUDE.md §4.6: never fill these ----------

@pytest.mark.parametrize("field", [
    '<input name="password" type="password">',
    '<input name="card_number" type="text">',
    '<label for="c">Credit card number</label><input id="c" name="cc" type="text">',
    '<label for="s">Passport number</label><input id="s" name="doc" type="text">',
    '<input name="cvv" type="text">',
])
def test_sensitive_fields_are_never_given_a_profile_key(field):
    html = f"<html><body><form method='get'>{field}<input name='email' type='email'></form></body></html>"
    payload = detect_form(page(html))
    risky = [f for f in payload.fields if f.entry_id != "email"]
    # A password input is dropped outright; anything else is reported but never auto-filled.
    for f in risky:
        assert f.sensitive is True
        assert f.profile_key is None


def test_password_inputs_are_dropped_entirely():
    html = "<html><body><form method='get'><input name='pw' type='password'></form></body></html>"
    assert detect_form(page(html)) is None


# ---------- hosted builders ----------

@pytest.mark.parametrize("url,provider", [
    ("https://form.typeform.com/to/abc", "typeform"),
    ("https://tally.so/r/abc", "tally"),
    ("https://forms.office.com/r/abc", "microsoft_forms"),
    ("https://myform.jotform.com/12345", "jotform"),
    ("https://docs.google.com/forms/d/e/X/viewform", "google_forms"),
])
def test_known_builders_are_recognised_by_host(url, provider):
    assert provider_for(url)[0] == provider


def test_javascript_rendered_builder_still_counts_as_a_form():
    """Typeform renders its questions in JS, so there is nothing to parse - but it is a form."""
    payload = detect_form(page("<html><title>My typeform</title><div id=root></div></html>",
                               url="https://form.typeform.com/to/abc"))
    assert payload is not None
    assert payload.provider == "typeform"
    assert payload.fields == []
    assert any("typeform" in r for r in payload.reasons)


def test_ordinary_page_is_not_a_form():
    assert detect_form(page("<html><title>News</title><p>Hello</p></html>")) is None


# ---------- guessing ----------

def test_likelihood_rises_with_evidence():
    bare, _ = form_likelihood("https://example.com/news", None)
    path_hint, _ = form_likelihood("https://example.com/register", None)
    with_form, reasons = form_likelihood("https://example.com/register", page(REGISTER_FORM))
    assert bare == 0
    assert path_hint > bare
    assert with_form > path_hint
    assert any("<form>" in r for r in reasons)


def test_radio_and_checkbox_groups_collapse_into_one_question():
    """A 3-option radio group is one question, not three fields with a duplicate prefill param."""
    html = """
    <html><body><form method="get">
      <fieldset><legend>Pizza Size</legend>
        <input type="radio" name="size" value="small"><input type="radio" name="size" value="large">
      </fieldset>
      <fieldset><legend>Toppings</legend>
        <input type="checkbox" name="topping" value="bacon"><input type="checkbox" name="topping" value="onion">
      </fieldset>
      <input name="email" type="email">
    </form></body></html>
    """
    payload = detect_form(page(html))
    assert [f.entry_id for f in payload.fields] == ["size", "topping", "email"]
    size = payload.fields[0]
    assert size.question == "Pizza Size"          # from the <legend>, not an option label
    assert size.options == ["small", "large"]
    assert size.profile_key is None               # a choice group is never auto-answered
    assert payload.fields[1].options == ["bacon", "onion"]


def test_group_without_a_legend_falls_back_to_the_field_name():
    html = """
    <html><body><form method="get">
      <input type="radio" name="meal_choice" value="veg"><input type="radio" name="meal_choice" value="non-veg">
    </form></body></html>
    """
    assert detect_form(page(html)).fields[0].question == "Meal choice"
