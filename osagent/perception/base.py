"""Perceiver contract plus the platform factory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..config import HOST_OS
from .element import UIElement


class PerceptionError(RuntimeError):
    """Raised when the a11y backend is unavailable or refuses to talk."""


class Perceiver(ABC):
    """Reads the live UI tree. Never mutates anything."""

    platform: str = "unknown"

    @abstractmethod
    def snapshot(self, app: str | None = None, max_elements: int = 400) -> list[UIElement]:
        """Flattened list of interactable elements, frontmost app by default."""

    @abstractmethod
    def frontmost_app(self) -> tuple[str, str]:
        """(process/app name, window title) of the focused window."""

    @abstractmethod
    def element_at(self, x: int, y: int) -> UIElement | None:
        """The deepest element under a screen point. Used by the recorder."""

    def screenshot(self, path: str | Path | None = None, region=None):
        from .screen import capture
        return capture(path, region)

    def check_permissions(self) -> tuple[bool, str]:
        """(ok, human readable explanation) - what doctor prints."""
        return True, "no special permissions required"


def get_perceiver() -> Perceiver:
    """Import only the host platform's backend, so the other deps stay optional."""
    if HOST_OS == "windows":
        from .a11y_windows import WindowsPerceiver
        return WindowsPerceiver()
    if HOST_OS == "macos":
        from .a11y_macos import MacPerceiver
        return MacPerceiver()
    if HOST_OS == "linux":
        from .a11y_linux import LinuxPerceiver
        return LinuxPerceiver()
    raise PerceptionError(f"unsupported platform: {HOST_OS}")
