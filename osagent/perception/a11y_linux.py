"""Linux backend: AT-SPI via pyatspi.

Not the host platform for this checkout, so this is a thin, honest stub: it
raises with the exact setup instruction instead of pretending to work.
"""
from __future__ import annotations

from .base import Perceiver, PerceptionError
from .element import UIElement

HINT = ("Linux backend not implemented in this build. Needs python3-pyatspi "
        "(apt install python3-pyatspi gir1.2-atspi-2.0) and the accessibility "
        "bus enabled: gsettings set org.gnome.desktop.interface toolkit-accessibility true")


class LinuxPerceiver(Perceiver):
    platform = "linux"

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
