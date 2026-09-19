"""Maps one validated Action onto the Actuator. Kept separate from the loop so
the loop reads as control flow and this reads as a lookup table."""
from __future__ import annotations

import time

from ..actuation.base import Actuator
from .actions import Action, InvalidAction


def perform(act: Action, a: Actuator) -> None:
    """Execute a validated action. Raises on anything it cannot carry out."""
    if act.action == "click":
        a.click(act.element)
    elif act.action == "double_click":
        a.double_click(act.element)
    elif act.action == "type_text":
        if act.element is not None:
            a.click(act.element)      # focus the field before typing into it
            time.sleep(0.25)
        a.type_text(act.text)
    elif act.action == "key":
        a.key(act.key)
    elif act.action == "scroll":
        a.scroll(act.amount, act.element)
    elif act.action == "launch_app":
        a.launch_app(act.app)
    elif act.action == "focus_app":
        if not a.focus_app(act.app):
            raise InvalidAction(f"no open window matching {act.app!r}")
    elif act.action == "wait":
        time.sleep(1.0)
    else:
        raise InvalidAction(f"nothing to perform for {act.action!r}")
