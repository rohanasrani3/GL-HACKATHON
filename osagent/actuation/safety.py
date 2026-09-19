"""The brakes. A live agent drives the same mouse the human is holding, so every
one of these is load-bearing:

  - ESC sets a process-wide abort flag, checked before every single action.
  - Destructive-looking actions stop and ask, unless explicitly pre-approved.
  - Launching applications is allowlisted, not open season on the filesystem.
"""
from __future__ import annotations

import threading

from ..config import CONFIG

ABORT = threading.Event()
_listener = None


class Aborted(RuntimeError):
    """ESC was pressed, or the caller asked to stop."""


class NeedsConfirmation(RuntimeError):
    """A destructive action was reached without approval."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


def arm_kill_switch() -> bool:
    """Start the ESC watcher. Idempotent; returns False if pynput is unavailable."""
    global _listener
    if _listener is not None:
        return True
    try:
        from pynput import keyboard
    except Exception:
        return False

    def on_press(k):
        if k == keyboard.Key.esc:
            ABORT.set()

    _listener = keyboard.Listener(on_press=on_press, daemon=True)
    _listener.start()
    return True


def disarm_kill_switch() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def reset_abort() -> None:
    ABORT.clear()


def check_abort() -> None:
    """Call before every action. Raises if the human hit ESC."""
    if ABORT.is_set():
        raise Aborted("aborted by ESC")


def is_destructive(action: str, description: str = "", value: str = "") -> bool:
    words = CONFIG.safety.get("destructive_keywords", [])
    haystack = f"{action} {description} {value}".lower()
    return any(w.lower() in haystack for w in words)


def gate(action: str, description: str = "", value: str = "", approved: bool = False) -> None:
    """Raise NeedsConfirmation for a destructive action that was not pre-approved."""
    if not approved and is_destructive(action, description, value):
        raise NeedsConfirmation(description or action)


def allowed_app(name: str) -> bool:
    allow = [a.lower() for a in CONFIG.safety.get("allowed_apps", [])]
    n = name.lower().replace(".exe", "").strip()
    return n in allow


def allowlist() -> list[str]:
    return list(CONFIG.safety.get("allowed_apps", []))
