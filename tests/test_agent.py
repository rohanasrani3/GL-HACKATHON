"""Tests for the live-agent pieces that must not regress: action validation,
element ranking, and the safety gates."""
from __future__ import annotations

import pytest

from osagent.actuation.safety import (ABORT, Aborted, NeedsConfirmation, allowed_app,
                                      check_abort, gate, is_destructive, reset_abort)
from osagent.agent.actions import InvalidAction, parse, render_elements
from osagent.agent.rank import rank
from osagent.perception.element import UIElement


def el(role="button", name="Save", **kw):
    kw.setdefault("bbox", [0, 0, 60, 20])
    return UIElement(role=role, name=name, **kw)


# -- action validation ------------------------------------------------------
def test_parse_accepts_a_well_formed_action():
    els = [el(name="Save"), el(role="edit", name="Filename")]
    act = parse({"action": "click", "element": 0, "thought": "save"}, els)
    assert act.action == "click" and act.element is els[0]


def test_parse_accepts_a_stringified_index():
    els = [el(), el(role="edit", name="Name")]
    assert parse({"action": "type_text", "element": "1", "text": "x"}, els).element_index == 1


@pytest.mark.parametrize("payload, fragment", [
    ({"action": "click", "element": 99}, "does not exist"),
    ({"action": "teleport"}, "unknown action"),
    ({"action": "click"}, "needs an"),
    ({"action": "type_text", "element": 0, "text": ""}, "non-empty"),
    ({"action": "key"}, "needs a"),
    ({"action": "launch_app"}, "needs an"),
    ("not a dict", "expected a JSON object"),
])
def test_parse_rejects_malformed_actions(payload, fragment):
    with pytest.raises(InvalidAction) as e:
        parse(payload, [el()])
    assert fragment in str(e.value)


def test_hallucinated_index_is_never_executed():
    """The whole point: a model may name any number, only real ones survive."""
    with pytest.raises(InvalidAction):
        parse({"action": "click", "element": 7}, [el(), el()])


def test_render_elements_numbers_match_list_positions():
    els = [el(name="A"), el(name="B"), el(name="C")]
    lines = render_elements(els).splitlines()
    assert lines[1].startswith("[1]") and '"B"' in lines[1]


# -- ranking ----------------------------------------------------------------
def test_actionable_elements_survive_the_cap():
    """Calculator's digits sit at index 98 of 132; naive truncation loses them."""
    noise = [el(role="text", name=f"label{i}") for i in range(100)]
    buttons = [el(name=n) for n in ("Seven", "Eight", "Equals")]
    out = rank(noise + buttons, cap=20)
    assert {"Seven", "Eight", "Equals"} <= {e.name for e in out}
    assert len(out) == 20


def test_ranking_prefers_informative_text_over_glyph_labels():
    els = [el(role="text", name="sin"), el(role="text", name="hyp"),
           el(role="text", name="Display is 0")]
    assert rank(els, cap=1)[0].name == "Display is 0"


def test_ranking_drops_invisible_elements():
    assert rank([el(bbox=[0, 0, 0, 0])], cap=10) == []


# -- safety -----------------------------------------------------------------
def test_destructive_words_are_caught_and_ordinary_ones_are_not():
    assert is_destructive("click", "Send the invoice")
    assert not is_destructive("click", "Open the file")


def test_gate_blocks_until_approved():
    with pytest.raises(NeedsConfirmation):
        gate("click", "Delete account")
    gate("click", "Delete account", approved=True)     # must not raise


def test_launching_is_allowlisted():
    assert allowed_app("notepad.exe")
    assert not allowed_app("cmd")


def test_abort_flag_stops_the_next_action():
    reset_abort()
    check_abort()
    ABORT.set()
    try:
        with pytest.raises(Aborted):
            check_abort()
    finally:
        reset_abort()
