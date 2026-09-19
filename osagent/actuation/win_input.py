"""Unicode keystrokes via SendInput.

pyautogui's write() is ASCII-only and silently drops anything else, which turns
a typed em-dash or accented name into missing characters with no error. This
sends the character directly as a Unicode scancode instead - no clipboard, so
the human's clipboard survives the run.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_unicode(ch: str) -> None:
    """Press and release one character, whatever codepoint it is."""
    for code in [ord(c) for c in ch]:
        events = (_INPUT * 2)()
        for i, flags in enumerate((KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)):
            events[i].type = INPUT_KEYBOARD
            events[i].ki = _KEYBDINPUT(0, code, flags, 0, None)
        ctypes.windll.user32.SendInput(2, ctypes.byref(events), ctypes.sizeof(_INPUT))


def force_foreground(hwnd: int) -> bool:
    """Actually bring a window to the front, and report honestly if it did not.

    Windows refuses SetForegroundWindow from a process that does not already own
    the foreground, and returns success anyway. Attaching to the current
    foreground thread's input queue lifts that restriction; verifying afterwards
    is what stops the agent from looping on a focus that never happened.
    """
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    SW_RESTORE = 9
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
    if u32.GetForegroundWindow() == hwnd:
        return True

    fg = u32.GetForegroundWindow()
    own_tid = k32.GetCurrentThreadId()
    fg_tid = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_tid and fg_tid != own_tid
                    and u32.AttachThreadInput(fg_tid, own_tid, True))
    try:
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            u32.AttachThreadInput(fg_tid, own_tid, False)

    # The switch is not instant, and the window that ends up in front may be a
    # sibling of the one we asked for (Firefox does this), so settle, then
    # compare owning processes rather than window handles.
    want = _pid_of(hwnd)
    deadline = time.monotonic() + 1.2
    while time.monotonic() < deadline:
        now = u32.GetForegroundWindow()
        if now == hwnd or (want and _pid_of(now) == want):
            return True
        time.sleep(0.05)
    return False


def _pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value
