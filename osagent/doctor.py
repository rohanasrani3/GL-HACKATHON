"""Environment checks behind `osagent doctor`.

Each check returns (name, ok, detail) and never raises - a broken environment is
exactly the thing doctor exists to describe, so it has to survive describing it.
"""
from __future__ import annotations

import importlib
import platform
import sys

from .config import CONFIG, HOST_OS

Check = tuple[str, bool, str]

# module name -> which platform needs it
CORE_DEPS = ["typer", "rich", "yaml", "dotenv", "httpx", "mss", "PIL"]
PLATFORM_DEPS = {"windows": ["uiautomation", "comtypes"], "macos": ["ApplicationServices"], "linux": ["pyatspi"]}
LATER_DEPS = ["rapidfuzz", "pyautogui", "pynput", "fastapi", "uvicorn"]


def check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 11)
    return ("python", ok, f"{platform.python_version()} at {sys.executable}")


def check_os() -> Check:
    known = HOST_OS in ("windows", "macos", "linux")
    return ("host os", known, f"{HOST_OS} ({platform.platform()})")


def _deps(label: str, mods: list[str], required: bool) -> Check:
    missing = [m for m in mods if importlib.util.find_spec(m) is None]
    detail = "all present" if not missing else f"missing: {', '.join(missing)}"
    return (label, (not missing) or (not required), detail)


def check_deps() -> list[Check]:
    return [
        _deps("core deps", CORE_DEPS, True),
        _deps(f"{HOST_OS} deps", PLATFORM_DEPS.get(HOST_OS, []), True),
        _deps("later-step deps", LATER_DEPS, False),
    ]


def check_config() -> Check:
    src = CONFIG.source
    return ("config", src is not None, str(src) if src else "config.yaml not found, using defaults")


def check_permissions() -> Check:
    try:
        from .perception import get_perceiver
        ok, detail = get_perceiver().check_permissions()
        return ("a11y permission", ok, detail)
    except Exception as e:
        return ("a11y permission", False, f"{type(e).__name__}: {e}")


def check_dpi() -> Check:
    try:
        from .perception.screen import ensure_dpi_aware, scale_factor, screen_size
        state = ensure_dpi_aware()
        w, h = screen_size()
        return ("display", True, f"{w}x{h} px, scale {scale_factor():.2f}x, {state}")
    except Exception as e:
        return ("display", False, f"{type(e).__name__}: {e}")


def check_llm() -> Check:
    m = CONFIG.model
    label = f"llm ({m.provider} {m.name})"
    try:
        from .model import get_client
        ok, detail = get_client().ping()
        return (label, ok, f"{m.base_url} - {detail}")
    except Exception as e:
        return (label, False, f"{m.base_url} - {type(e).__name__}: {e}")


def run_checks() -> list[Check]:
    return [check_python(), check_os(), check_config(), *check_deps(),
            check_permissions(), check_dpi(), check_llm()]


def snapshot_frontmost(limit: int = 25):
    """(app, window, elements, total) for the frontmost app. Raises on failure."""
    from .perception import get_perceiver
    p = get_perceiver()
    app, window = p.frontmost_app()
    elements = p.snapshot(max_elements=int(CONFIG.perception.get("max_elements", 400)))
    return app, window, elements[:limit], len(elements)
