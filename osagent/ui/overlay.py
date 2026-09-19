"""A transparent, click-through, always-on-top box drawn around the element the
agent is about to touch.

Runs on its own thread with its own Tk root: the agent loop and the web
server both want the main thread, and Tk will only take orders from the thread
that created it. All cross-thread requests go through a queue.
"""
from __future__ import annotations

import gc
import queue
import threading

from ..config import HOST_OS

TRANSPARENT = "#010203"   # a colour no real UI uses, keyed out to make the fill invisible


class Overlay:
    """Best-effort: if Tk is missing or the display refuses, the agent still runs."""

    def __init__(self, colour: str = "#00e5ff", width: int = 4) -> None:
        self.colour, self.width = colour, width
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._alive = threading.Event()
        self.enabled = True

    def start(self) -> bool:
        if self._thread or not self.enabled:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self._alive.wait(timeout=3.0)

    def show(self, bbox, label: str = "") -> None:
        if self.enabled and self._alive.is_set():
            self._q.put(("show", list(bbox), label))

    def hide(self) -> None:
        if self._alive.is_set():
            self._q.put(("hide", None, ""))

    def stop(self) -> None:
        if self._alive.is_set():
            self._q.put(("stop", None, ""))
        self._alive.clear()
        # Let the Tk thread tear its own interpreter down; destroying it from
        # another thread leaks it and prints a RuntimeWarning at exit.
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- Tk thread ----------------------------------------------------------
    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            return
        try:
            root = tk.Tk()
            root.withdraw()
            win = tk.Toplevel(root)
            win.overrideredirect(True)          # no titlebar, no taskbar entry
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.95)
            if HOST_OS == "windows":
                win.configure(bg=TRANSPARENT)
                win.attributes("-transparentcolor", TRANSPARENT)
            canvas = tk.Canvas(win, highlightthickness=0, bd=0, bg=TRANSPARENT)
            canvas.pack(fill="both", expand=True)
            win.withdraw()
        except Exception:
            return

        self._alive.set()
        if HOST_OS == "windows":
            win.after(120, lambda: _make_click_through(win))

        def pump() -> None:
            try:
                while True:
                    cmd, bbox, label = self._q.get_nowait()
                    if cmd == "stop":
                        root.destroy()
                        return
                    if cmd == "hide":
                        win.withdraw()
                    elif cmd == "show":
                        self._draw(win, canvas, bbox, label)
            except queue.Empty:
                pass
            root.after(40, pump)

        root.after(40, pump)
        root.mainloop()
        # The scheduled `pump` closure holds the widgets in a reference cycle.
        # Left alone it is collected on whichever thread runs the GC next, and
        # freeing a Tcl interpreter off its own thread prints a RuntimeWarning
        # at exit, so drop the references and collect here instead.
        del canvas, win, root, pump
        gc.collect()

    def _draw(self, win, canvas, bbox, label: str) -> None:
        x, y, w, h = [int(v) for v in bbox]
        pad = self.width + 2
        win.geometry(f"{w + pad * 2}x{h + pad * 2 + 22}+{x - pad}+{y - pad - 22}")
        win.deiconify()
        win.lift()
        canvas.delete("all")
        canvas.create_rectangle(pad, pad + 22, pad + w, pad + 22 + h,
                                outline=self.colour, width=self.width)
        if label:
            canvas.create_text(pad + 2, pad + 10, anchor="w", text=label[:70],
                               fill=self.colour, font=("Segoe UI", 10, "bold"))


def _make_click_through(win) -> None:
    """TRANSPARENT so the box never eats a click meant for the app, and
    NOACTIVATE so it never becomes the foreground window - otherwise the agent
    snapshots its own highlight box instead of the app it is driving."""
    try:
        import ctypes
        GWL_EXSTYLE = -20
        WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x8000000
        hwnd = int(win.frame(), 16)
        u32 = ctypes.windll.user32
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
    except Exception:
        pass
