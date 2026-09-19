"""Policy gate: when does the app auto-add vs ask first?"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from snapsort.pipeline import decide, to_proposal
from snapsort.schema import RawEvent

HK = ZoneInfo("Asia/Hong_Kong")
NOW = datetime.now(HK).replace(second=0, microsecond=0)
NEXT_WEEK = (NOW + timedelta(days=7)).date()


def event(**kw) -> RawEvent:
    base = dict(
        title="AI Talk", date_text=NEXT_WEEK.strftime("%d %B %Y"), date_guess=NEXT_WEEK.isoformat(),
        start_time="16:00", end_time="17:30", location="LG01", online_url=None,
        description=None, confidence=0.95, evidence="...",
    )
    base.update(kw)
    return RawEvent(**base)


def test_clear_event_is_auto_added():
    p = to_proposal(event(), "poster", NOW, HK, "en-HK")
    assert p.decision == "auto_add"
    assert p.payload.start.startswith(NEXT_WEEK.isoformat() + "T16:00")
    assert len(p.id) == 12


def test_low_confidence_asks():
    assert to_proposal(event(confidence=0.6), "chat", NOW, HK, "en-HK").decision == "ask"


def test_missing_time_asks_even_if_confident():
    p = to_proposal(event(start_time=None, end_time=None), "poster", NOW, HK, "en-HK")
    assert p.payload.all_day and p.decision == "ask"


def test_date_disagreement_asks():
    p = to_proposal(event(date_guess=(NEXT_WEEK + timedelta(days=1)).isoformat()), "poster", NOW, HK, "en-HK")
    assert p.decision == "ask"


def test_past_event_dropped():
    past = (NOW - timedelta(days=3)).date()
    assert to_proposal(event(date_text=past.strftime("%d %B %Y"), date_guess=past.isoformat()), "poster", NOW, HK, "en-HK") is None


def test_same_event_same_id():
    a = to_proposal(event(), "poster", NOW, HK, "en-HK")
    b = to_proposal(event(title=" ai talk "), "poster", NOW, HK, "en-HK")
    assert a.id == b.id


def test_decide_thresholds():
    assert decide(0.8, []) == "auto_add"
    assert decide(0.79, []) == "ask"
    assert decide(0.99, ["model_guess_only"]) == "ask"
