"""Small Win32/UIAutomation helpers, kept out of the perceiver for readability."""
from __future__ import annotations

import ctypes
from ctypes import wintypes


INTERACTABLE = {
    "button", "checkbox", "radiobutton", "combobox", "edit", "document", "hyperlink",
    "listitem", "menuitem", "tabitem", "treeitem", "slider", "spinner", "splitbutton",
    "text", "image", "datagrid", "dataitem", "table", "custom", "group", "window", "pane",
}
CLICKABLE = INTERACTABLE - {"text", "group", "pane", "window", "custom", "image"}


def _role(control) -> str:
    name = getattr(control, "ControlTypeName", "") or ""
    return name[:-7].lower() if name.endswith("Control") else name.lower()


def _process_name(pid: int) -> str:
    """Executable name for a pid, via Win32 only (no psutil dependency)."""
    if not pid:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        k32.CloseHandle(h)


def _bbox(control) -> list[int]:
    try:
        r = control.BoundingRectangle
        return [int(r.left), int(r.top), int(r.right - r.left), int(r.bottom - r.top)]
    except Exception:
        return [0, 0, 0, 0]


def _value(control) -> str:
    for getter in ("GetValuePattern", "GetTogglePattern", "GetRangeValuePattern"):
        try:
            pattern = getattr(control, getter)()
        except Exception:
            continue
        for attr in ("Value", "ToggleState"):
            v = getattr(pattern, attr, None)
            if v not in (None, ""):
                return str(v)
    return ""


