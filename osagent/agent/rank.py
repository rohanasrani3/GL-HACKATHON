"""Choosing which elements the model gets to see.

A window can expose hundreds of elements while the prompt has room for a few
dozen, and naive truncation takes them in tree order. In Calculator that means
the model receives the window chrome and the trigonometry menu and never sees
the number pad - the digits sit at index 98 of 132. It then correctly reports
that it cannot find the 7 button, because as far as it knows there isn't one.

So: actionable controls first, always, then as much surrounding text as fits.
"""
from __future__ import annotations

from ..perception.element import UIElement

ACTIONABLE = {"button", "splitbutton", "menuitem", "listitem", "tabitem", "treeitem",
              "checkbox", "radiobutton", "combobox", "edit", "hyperlink", "slider",
              "spinner", "datagrid", "dataitem"}
CONTEXT = {"text", "document"}          # not clickable, but tells the model the state


def rank(elements: list[UIElement], cap: int) -> list[UIElement]:
    """Up to `cap` elements: every actionable one that fits, then context text.

    Order within each tier is preserved, so the list still reads top-to-bottom
    the way the window is laid out.
    """
    actionable, context, other = [], [], []
    for el in elements:
        if not el.visible:
            continue
        if el.role in ACTIONABLE and (el.name or el.value):
            actionable.append(el)
        elif el.role in CONTEXT and (el.name or el.value):
            context.append(el)
        else:
            other.append(el)

    out = actionable[:cap]
    room = cap - len(out)
    if room > 0:
        useful = sorted(_dedupe(context, out), key=_context_score, reverse=True)
        out += useful[:room]
        room = cap - len(out)
    if room > 0:
        out += other[:room]
    return out


def _context_score(el: UIElement) -> int:
    """How much a piece of static text is worth spending a slot on.

    A result display is what the agent checks its own work against, so it has to
    outrank the dozen three-letter labels that sit next to buttons of the same
    name. Without this, Calculator's "Display is 0" loses its slot to "sin".
    """
    name = f"{el.name} {el.value}".strip().lower()
    score = 0
    if any(w in name for w in ("display", "result", "total", "output", "status")):
        score += 6
    if any(c.isdigit() for c in name):
        score += 3
    if len(name) <= 3:                       # "sin", "hyp": the button says it already
        score -= 3
    if not any(c.isalnum() for c in name):   # icon glyphs with no text at all
        score -= 6
    return score


def _dedupe(context: list[UIElement], chosen: list[UIElement]) -> list[UIElement]:
    """Drop text that merely repeats a control already in the list - a button
    and its own label are one thing to click, not two."""
    taken = {e.name.strip().lower() for e in chosen if e.name}
    return [e for e in context if e.name.strip().lower() not in taken]
