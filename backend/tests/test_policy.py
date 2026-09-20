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
    assert to_proposal(event(confidence=0.4), "chat", NOW, HK, "en-HK").decision == "ask"


def test_missing_time_becomes_all_day_and_costs_confidence():
    """The uncertainty is priced into the confidence, not charged again as a forced ask."""
    p = to_proposal(event(start_time=None, end_time=None), "poster", NOW, HK, "en-HK")
    assert p.payload.all_day
    assert "no_time_all_day" in p.notes
    assert p.confidence < 0.95  # penalised relative to the same event with a time


def test_date_disagreement_costs_confidence():
    p = to_proposal(event(date_guess=(NEXT_WEEK + timedelta(days=1)).isoformat()), "poster", NOW, HK, "en-HK")
    assert any("disagree" in n for n in p.notes)
    assert p.confidence < 0.95


def test_past_event_dropped():
    past = (NOW - timedelta(days=3)).date()
    assert to_proposal(event(date_text=past.strftime("%d %B %Y"), date_guess=past.isoformat()), "poster", NOW, HK, "en-HK") is None


def test_same_event_same_id():
    a = to_proposal(event(), "poster", NOW, HK, "en-HK")
    b = to_proposal(event(title=" ai talk "), "poster", NOW, HK, "en-HK")
    assert a.id == b.id


def test_decide_thresholds():
    """Confidence alone decides: at or above the threshold it adds, below it asks."""
    assert decide(0.6) == "auto_add"
    assert decide(0.59) == "ask"
    assert decide(1.0) == "auto_add"


def test_unclear_signals_do_not_force_a_confirmation():
    """Signals like `no_time_all_day` already cost confidence inside to_proposal(). Charging for
    them a second time at the gate meant confident events still interrupted the user."""
    p = to_proposal(event(start_time=None, end_time=None), "poster", NOW, HK, "en-HK")
    assert "no_time_all_day" in p.notes
    assert p.decision == "auto_add"


# ---- multi-day ----
def test_range_in_date_text_becomes_multi_day_all_day():
    start = NEXT_WEEK
    end = NEXT_WEEK + timedelta(days=4)
    text = f"{start.day} - {end.day} {end.strftime('%B %Y')}" if start.month == end.month else \
        f"{start.day} {start.strftime('%B')} - {end.day} {end.strftime('%B %Y')}"
    p = to_proposal(event(date_text=text, start_time=None, end_time=None), "poster", NOW, HK, "en-HK")
    assert p.payload.all_day
    assert p.payload.start == start.isoformat()
    assert p.payload.end == (end + timedelta(days=1)).isoformat()  # exclusive
    assert p.decision == "auto_add"  # explicit range is clear, not "missing time"


def test_model_end_date_fields():
    end = NEXT_WEEK + timedelta(days=2)
    p = to_proposal(event(end_date_text=end.strftime("%d %B %Y"), end_date_guess=end.isoformat()), "poster", NOW, HK, "en-HK")
    assert p.payload.all_day and p.payload.end == (end + timedelta(days=1)).isoformat()
    assert p.payload.description.startswith("Daily 16:00–17:30")


def test_ongoing_multi_day_event_kept():
    start = (NOW - timedelta(days=1)).date()
    end = (NOW + timedelta(days=2)).date()
    p = to_proposal(event(date_text=start.strftime("%d %B %Y"), date_guess=start.isoformat(),
                          end_date_text=end.strftime("%d %B %Y"), end_date_guess=end.isoformat()),
                    "poster", NOW, HK, "en-HK")
    assert p is not None and p.payload.start == start.isoformat()


def test_absurd_range_is_ignored():
    """A 120-day "event" is a misread: keep the single day and note why."""
    end = NEXT_WEEK + timedelta(days=120)
    p = to_proposal(event(end_date_text=end.strftime("%d %B %Y"), end_date_guess=end.isoformat()), "poster", NOW, HK, "en-HK")
    assert not p.payload.all_day
    assert "range_ignored" in p.notes
    assert p.confidence < 0.95


def test_end_time_in_end_date_field_stays_single_day():
    # Regression: model put "6:00 pm" in end_date_text; it used to become a 2-day event.
    p = to_proposal(event(end_date_text="6:00 pm", end_date_guess=NEXT_WEEK.isoformat(),
                          start_time="08:30", end_time="18:00"), "poster", NOW, HK, "en-HK")
    assert not p.payload.all_day
    assert p.payload.start.startswith(NEXT_WEEK.isoformat() + "T08:30")
    assert p.payload.end.startswith(NEXT_WEEK.isoformat() + "T18:00")


def test_finished_today_event_dropped():
    earlier = (NOW - timedelta(hours=6))
    if earlier.date() != NOW.date():
        return  # test only meaningful when 6h ago is still today
    p = to_proposal(event(date_text=NOW.strftime("%B %d, %Y (%a); 8:30 am – %I:%M %p"), date_guess=NOW.date().isoformat(),
                          end_date_text=earlier.strftime("%I:%M %p"), end_date_guess=NOW.date().isoformat(),
                          start_time="00:00", end_time=earlier.strftime("%H:%M")), "poster", NOW, HK, "en-HK")
    assert p is None
