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
