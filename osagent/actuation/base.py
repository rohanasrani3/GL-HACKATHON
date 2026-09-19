"""Actuator contract. Everything that touches the real mouse or keyboard goes
through one of these six verbs, so the safety layer has exactly six chokepoints."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..perception.element import UIElement


class ActuationError(RuntimeError):
    """The action could not be performed."""


class Actuator(ABC):
    """Drives input. Takes resolved UIElements, not raw coordinates."""

    dry_run: bool = True

    @abstractmethod
    def move_to(self, x: int, y: int, duration: float = 0.35) -> None: ...

    @abstractmethod
    def click(self, target: UIElement | tuple[int, int]) -> None: ...

    @abstractmethod
    def double_click(self, target: UIElement | tuple[int, int]) -> None: ...

    @abstractmethod
    def type_text(self, text: str, interval: float = 0.02) -> None: ...

    @abstractmethod
    def key(self, combo: str) -> None:
        """A single key or a chord like 'ctrl+s'."""

    @abstractmethod
    def scroll(self, amount: int, target: UIElement | None = None) -> None: ...

    @abstractmethod
    def focus_app(self, name: str) -> bool:
        """Bring an already-running window to the front. True if found."""

    @abstractmethod
    def launch_app(self, name: str) -> bool:
        """Start an application by name. Subject to the allowlist in safety."""

    @staticmethod
    def point_of(target: UIElement | tuple[int, int]) -> tuple[int, int]:
        if isinstance(target, UIElement):
            if not target.visible:
                raise ActuationError(f"element has no on-screen box: {target.label()}")
            return target.center
        return int(target[0]), int(target[1])
