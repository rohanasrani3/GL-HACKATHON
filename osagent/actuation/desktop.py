"""Desktop actuator: pyautogui for input, uiautomation for window activation.

Importing osagent.perception.screen first is deliberate - it declares per-monitor
DPI awareness before pyautogui caches a screen size, so element coordinates and
click coordinates live in the same pixel space.
"""
from __future__ import annotations

import subprocess
import time

from ..config import CONFIG, HOST_OS
from ..perception.element import UIElement
from ..perception.screen import ensure_dpi_aware
from .base import Actuator, ActuationError
from .safety import check_abort, allowed_app, allowlist

ensure_dpi_aware()

KEY_ALIASES = {"enter": "enter", "return": "enter", "esc": "escape", "del": "delete",
               "win": "win", "cmd": "command", "ctrl": "ctrl", "control": "ctrl"}

# What the model calls an app vs. what Windows will actually start. "Calculator"
# and "Paint" are UWP apps with no matching .exe of that name.
LAUNCH = {"calculator": "calc", "calc": "calc", "paint": "mspaint", "mspaint": "mspaint",
          "notepad": "notepad", "wordpad": "write", "explorer": "explorer",
          "file explorer": "explorer", "edge": "msedge", "microsoft edge": "msedge",
          "word": "winword", "notepad++": "notepad++"}


class DesktopActuator(Actuator):
    def __init__(self, dry_run: bool = True, on_action=None) -> None:
        import pyautogui
        pyautogui.FAILSAFE = False   # we have our own ESC kill switch
        pyautogui.PAUSE = 0.05
        self.gui = pyautogui
        self.dry_run = dry_run
        self.on_action = on_action or (lambda *_: None)
        self.move_duration = float(CONFIG.get_agent("move_duration_s", 0.35))

    def _log(self, what: str, detail: str = "") -> None:
        self.on_action(what, detail)

    # -- pointer ------------------------------------------------------------
    def move_to(self, x: int, y: int, duration: float | None = None) -> None:
        check_abort()
        if self.dry_run:
            return
        self.gui.moveTo(int(x), int(y),
                        duration=self.move_duration if duration is None else duration)

    def click(self, target: UIElement | tuple[int, int]) -> None:
        x, y = self.point_of(target)
        check_abort()
        self._log("click", f"({x},{y})")
        if self.dry_run:
            return
        self.move_to(x, y)
        self.gui.click()

    def double_click(self, target: UIElement | tuple[int, int]) -> None:
        x, y = self.point_of(target)
        check_abort()
        self._log("double_click", f"({x},{y})")
        if self.dry_run:
            return
        self.move_to(x, y)
        self.gui.doubleClick()

    # -- keyboard -----------------------------------------------------------
    def type_text(self, text: str, interval: float = 0.02) -> None:
        check_abort()
        self._log("type_text", text[:60])
        if self.dry_run:
            return
        if text.isascii():
            self.gui.write(text, interval=interval)
            return
        # pyautogui.write() drops non-ASCII without complaining, so send those directly.
        from .win_input import send_unicode
        for ch in text:
            check_abort()
            if ch.isascii():
                self.gui.write(ch)
            else:
                send_unicode(ch)
            time.sleep(interval)

    def key(self, combo: str) -> None:
        check_abort()
        parts = [KEY_ALIASES.get(p.strip().lower(), p.strip().lower())
                 for p in combo.replace(" ", "").split("+") if p.strip()]
        if not parts:
            raise ActuationError(f"empty key combo: {combo!r}")
        self._log("key", "+".join(parts))
        if self.dry_run:
            return
        self.gui.hotkey(*parts) if len(parts) > 1 else self.gui.press(parts[0])

    def scroll(self, amount: int, target: UIElement | None = None) -> None:
        check_abort()
        self._log("scroll", str(amount))
        if self.dry_run:
            return
        if target is not None and target.visible:
            self.move_to(*target.center)
        self.gui.scroll(int(amount))

    # -- windows ------------------------------------------------------------
    def focus_app(self, name: str) -> bool:
        check_abort()
        self._log("focus_app", name)
        if HOST_OS != "windows":
            raise ActuationError("focus_app is implemented for Windows only in this build")
        import uiautomation as auto
        from .win_input import force_foreground

        needle = name.lower().replace(".exe", "").strip()
        for win in auto.GetRootControl().GetChildren():
            if needle not in (win.Name or "").lower():
                continue
            if self.dry_run:
                return True
            hwnd = getattr(win, "NativeWindowHandle", 0)
            if not hwnd:
                continue
            ok = force_foreground(int(hwnd))
            time.sleep(0.6)
            return ok        # False, honestly, if Windows refused the switch
        return False

    def launch_app(self, name: str) -> bool:
        check_abort()
        if not allowed_app(name):
            raise ActuationError(
                f"'{name}' is not in safety.allowed_apps. Allowed: {', '.join(allowlist())}")
        self._log("launch_app", name)
        if self.dry_run:
            return True
        key = name.lower().replace(".exe", "").strip()
        exe = LAUNCH.get(key, key)
        try:
            subprocess.Popen([f"{exe}.exe"], shell=False)
        except FileNotFoundError as e:
            raise ActuationError(f"cannot start {name!r}: no executable named {exe}.exe") from e
        time.sleep(2.0)
        return True
