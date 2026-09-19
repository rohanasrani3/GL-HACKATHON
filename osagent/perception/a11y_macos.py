"""macOS backend: AXUIElement via pyobjc.

Not the host platform for this checkout, so this is a thin, honest stub: it
raises with the exact setup instruction instead of pretending to work.
"""
from __future__ import annotations

from .base import Perceiver, PerceptionError
from .element import UIElement

HINT = ("macOS backend not implemented in this build. Needs "
        "pyobjc-framework-ApplicationServices and Accessibility permission "
        "(System Settings > Privacy & Security > Accessibility).")


class MacPerceiver(Perceiver):
    platform = "macos"

    def __init__(self) -> None:
        raise PerceptionError(HINT)

    def snapshot(self, app: str | None = None, max_elements: int = 400) -> list[UIElement]:
        raise PerceptionError(HINT)

    def frontmost_app(self) -> tuple[str, str]:
        raise PerceptionError(HINT)

    def element_at(self, x: int, y: int) -> UIElement | None:
        raise PerceptionError(HINT)

    def check_permissions(self) -> tuple[bool, str]:
        return False, HINT
