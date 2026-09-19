"""Screenshots via mss, plus the DPI plumbing Windows needs.

Windows lies about coordinates to non-DPI-aware processes: UIAutomation reports
physical pixels while an unaware process sees scaled logical pixels, so clicks
land in the wrong place on a scaled display. Declaring per-monitor awareness at
import time makes every layer agree on one coordinate space.
"""
from __future__ import annotations

from pathlib import Path

from ..config import HOST_OS

_dpi_ready = False


def ensure_dpi_aware() -> str:
    """Idempotent. Returns a short description of what was set."""
    global _dpi_ready
    if _dpi_ready or HOST_OS != "windows":
        _dpi_ready = True
        return "n/a" if HOST_OS != "windows" else "already set"
    import ctypes
    try:  # Windows 10 1703+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        out = "per-monitor DPI aware"
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            out = "system DPI aware (legacy)"
        except Exception as e:  # pragma: no cover
            out = f"DPI awareness failed: {e}"
    _dpi_ready = True
    return out


def scale_factor() -> float:
    """Logical->physical pixel ratio of the primary display."""
    if HOST_OS != "windows":
        return 1.0
    import ctypes
    try:
        return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0
    except Exception:
        return 1.0


def _sct():
    """mss 10 renamed the factory; support both so the pin can stay loose."""
    import mss
    return (mss.MSS if hasattr(mss, "MSS") else mss.mss)()


def screen_size() -> tuple[int, int]:
    ensure_dpi_aware()
    with _sct() as sct:
        m = sct.monitors[0]  # the virtual screen across all monitors
        return m["width"], m["height"]


def capture(path: str | Path | None = None, region: tuple[int, int, int, int] | None = None):
    """Save a PNG and return its path. region is (x, y, w, h) in screen pixels."""
    ensure_dpi_aware()
    import mss.tools

    with _sct() as sct:
        if region:
            x, y, w, h = region
            box = {"left": int(x), "top": int(y), "width": max(1, int(w)), "height": max(1, int(h))}
        else:
            box = sct.monitors[0]
        shot = sct.grab(box)
        if path is None:
            return shot
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mss.tools.to_png(shot.rgb, shot.size, output=str(p))
        return p
