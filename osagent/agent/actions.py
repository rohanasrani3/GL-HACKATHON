"""Turning a model's JSON into something safe to execute.

A small model will hallucinate element numbers, omit required fields and invent
action names. Everything it says is treated as a proposal to be validated
against the elements actually on screen this turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..perception.element import UIElement

VALID = {"click", "double_click", "type_text", "key", "scroll",
         "launch_app", "focus_app", "wait", "done", "fail"}
NEEDS_ELEMENT = {"click", "double_click"}
TERMINAL = {"done", "fail"}


class InvalidAction(ValueError):
    """The model proposed something that cannot be executed as written."""


@dataclass
class Action:
    action: str
    thought: str = ""
    element_index: int | None = None
    element: UIElement | None = None
    text: str = ""
    key: str = ""
    amount: int = -3
    app: str = ""
    reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        if self.action in TERMINAL:
            return f"{self.action}: {self.reason or '-'}"
        bits = [self.action]
        if self.element is not None:
            bits.append(f"{self.element.role} {self.element.name or '<unnamed>'!r}")
        if self.text:
            bits.append(f"text={self.text[:40]!r}")
        if self.key:
            bits.append(f"key={self.key}")
        if self.app:
            bits.append(f"app={self.app}")
        if self.action == "scroll":
            bits.append(str(self.amount))
        return " ".join(bits)


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


def parse(payload: Any, elements: list[UIElement]) -> Action:
    """Validate one model turn against the elements that are really on screen."""
    if not isinstance(payload, dict):
        raise InvalidAction(f"expected a JSON object, got {type(payload).__name__}")

    name = str(payload.get("action", "")).strip().lower().replace("-", "_")
    if name not in VALID:
        raise InvalidAction(f"unknown action {name!r}; valid: {', '.join(sorted(VALID))}")

    act = Action(
        action=name,
        thought=str(payload.get("thought", ""))[:300],
        text=str(payload.get("text") or ""),
        key=str(payload.get("key") or "").strip(),
        app=str(payload.get("app") or "").strip(),
        reason=str(payload.get("reason") or payload.get("done_reason") or "")[:300],
        raw=payload,
    )
    amount = _as_int(payload.get("amount"))
    if amount is not None:
        act.amount = amount

    idx = _as_int(payload.get("element"))
    if idx is not None:
        if not 0 <= idx < len(elements):
            raise InvalidAction(
                f"element {idx} does not exist; the list has 0..{len(elements) - 1}")
        act.element_index, act.element = idx, elements[idx]

    if name in NEEDS_ELEMENT and act.element is None:
        raise InvalidAction(f"{name} needs an \"element\" number from the list")
    if name == "type_text" and not act.text:
        raise InvalidAction('type_text needs a non-empty "text"')
    if name == "key" and not act.key:
        raise InvalidAction('key needs a "key" such as "enter" or "ctrl+s"')
    if name in ("launch_app", "focus_app") and not act.app:
        raise InvalidAction(f'{name} needs an "app" name')
    return act


def render_elements(elements: list[UIElement]) -> str:
    """The numbered list the model points into. Index here == index in the list."""
    lines = []
    for i, el in enumerate(elements):
        name = " ".join((el.name or "").split())[:60] or "<unnamed>"
        line = f'[{i}] {el.role} "{name}"'
        if el.value:
            line += f' = "{" ".join(el.value.split())[:30]}"'
        x, y = el.center
        line += f" at ({x},{y})"
        if not el.attrs.get("enabled", True):
            line += " DISABLED"
        lines.append(line)
    return "\n".join(lines) or "(no elements detected)"
