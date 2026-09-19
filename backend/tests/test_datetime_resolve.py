from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from snapsort.datetime_resolve import parse_hhmm, resolve_date

HK = ZoneInfo("Asia/Hong_Kong")
# Saturday 19 Sep 2026, 14:00
ANCHOR = datetime(2026, 9, 19, 14, 0, tzinfo=HK)


def test_tomorrow_slang():
    assert resolve_date("tmrw", None, ANCHOR).value == date(2026, 9, 20)


def test_explicit_date_no_year():
    r = resolve_date("Fri 26 Sept", "2026-09-26", ANCHOR)
    assert r.value == date(2026, 9, 26)
    assert r.penalty == 0


def test_day_first_locale():
    assert resolve_date("3/10", None, ANCHOR, "en-HK").value == date(2026, 10, 3)


def test_month_first_locale():
    assert resolve_date("10/3", None, ANCHOR, "en-US").value == date(2026, 10, 3)


def test_past_date_rolls_to_next_year():
    assert resolve_date("5 Jan", None, ANCHOR).value == date(2027, 1, 5)


def test_past_relative_date_stays_in_capture_year():
    assert resolve_date("2 days ago", None, ANCHOR).value == date(2026, 9, 17)


def test_weekday_is_in_future():
    d = resolve_date("this Friday", None, ANCHOR).value
    assert d is not None and d >= ANCHOR.date() and d.weekday() == 4


def test_falls_back_to_model_guess():
    r = resolve_date("the day after the hackathon", "2026-09-21", ANCHOR)
    assert r.value == date(2026, 9, 21)
    assert "model_guess_only" in r.notes


def test_disagreement_penalised():
    r = resolve_date("26 Sept", "2026-09-27", ANCHOR)
    assert r.value == date(2026, 9, 26) and r.penalty > 0


def test_no_date():
    assert resolve_date(None, None, ANCHOR).value is None


def test_parse_hhmm():
    assert parse_hhmm("16:30") == time(16, 30)
    assert parse_hhmm("4pm") is None
    assert parse_hhmm("25:00") is None


# ---- date ranges ----
from snapsort.datetime_resolve import split_range  # noqa: E402


def test_split_range_day_first():
    assert split_range("12 - 16 October 2026 (Monday - Friday)") == ("12 October 2026", "16 October 2026")


def test_split_range_month_first():
    assert split_range("Oct 12–16, 2026") == ("12 Oct 2026", "16 Oct 2026")


def test_split_range_across_months():
    assert split_range("30 Sep - 2 Oct") == ("30 Sep", "2 Oct")
    assert split_range("Sep 30 to Oct 2 2026") == ("30 Sep 2026", "2 Oct 2026")


def test_split_range_not_a_range():
    assert split_range("20 Sept 2026 (Sun)") is None
    assert split_range("Room 12-16 Building") is None
    assert split_range(None) is None


# ---- messy real-world phrases (University Drive notice regression) ----
from snapsort.datetime_resolve import has_date_content  # noqa: E402


def test_time_only_text_is_not_a_date():
    assert not has_date_content("6:00 pm")
    assert not has_date_content("8:30 am – 6:00 pm")
    assert has_date_content("tomorrow 1pm")
    assert has_date_content("16 Oct")
    assert has_date_content("3/10")
    assert has_date_content("2 days ago") and has_date_content("in 3 weeks") and has_date_content("yesterday")


def test_time_only_end_text_does_not_become_next_day():
    late = datetime(2026, 9, 19, 22, 36, tzinfo=HK)  # screenshot taken after 6pm
    r = resolve_date("6:00 pm", "2026-09-19", late)
    assert r.value == date(2026, 9, 19) and "text_has_no_date" in r.notes


def test_messy_header_parses():
    r = resolve_date("September 19, 2026 (Sat); 8:30 am – 6:00 pm", "2026-09-19", ANCHOR)
    assert r.value == date(2026, 9, 19) and "parser_and_model_agree" in r.notes
