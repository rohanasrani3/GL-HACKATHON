"""Windows backend: UIAutomation through the `uiautomation` package."""
from __future__ import annotations

from .base import Perceiver, PerceptionError
from .element import UIElement
from .screen import ensure_dpi_aware
from .win_util import CLICKABLE, INTERACTABLE, _bbox, _process_name, _role, _value


class WindowsPerceiver(Perceiver):
    platform = "windows"

    def __init__(self) -> None:
        ensure_dpi_aware()
        try:
            import uiautomation as auto
        except ImportError as e:  # pragma: no cover
            raise PerceptionError("pip install uiautomation") from e
        self.auto = auto
        auto.SetGlobalSearchTimeout(2)

    # -- window level ------------------------------------------------------
    def _foreground(self):
        win = self.auto.GetForegroundControl()
        if win is None:
            raise PerceptionError("no foreground window")
        return win

    def frontmost_app(self) -> tuple[str, str]:
        win = self._foreground()
        top = win.GetTopLevelControl() or win
        return _process_name(getattr(top, "ProcessId", 0)), (top.Name or "")

    # -- tree walk ---------------------------------------------------------
    def snapshot(self, app: str | None = None, max_elements: int = 400) -> list[UIElement]:
        top = self._foreground().GetTopLevelControl()
        if top is None:
            raise PerceptionError("cannot reach the top level window")
        app_name = _process_name(getattr(top, "ProcessId", 0))
        window_title = top.Name or ""
        out: list[UIElement] = []
        self._walk(top, app_name, window_title, [], out, max_elements, depth=0, max_depth=18)
        return out

    def _walk(self, control, app, window, path, out, cap, depth, max_depth) -> None:
        if len(out) >= cap or depth > max_depth:
            return
        try:
            children = control.GetChildren()
        except Exception:
            children = []
        for index, child in enumerate(children):
            if len(out) >= cap:
                return
            role = _role(child)
            child_path = path + [[role, index]]
            try:
                name = (child.Name or "").strip()
            except Exception:
                name = ""
            bbox = _bbox(child)
            if bbox[2] > 0 and bbox[3] > 0 and role in INTERACTABLE and (name or role in CLICKABLE):
                out.append(UIElement(
                    role=role, name=name[:200], value=_value(child)[:200],
                    app=app, window_title=window, bbox=bbox, path=child_path,
                    attrs={"automation_id": getattr(child, "AutomationId", "") or "",
                           "class_name": getattr(child, "ClassName", "") or "",
                           "enabled": bool(getattr(child, "IsEnabled", True)),
                           "clickable": role in CLICKABLE},
                ))
            self._walk(child, app, window, child_path, out, cap, depth + 1, max_depth)

    def element_at(self, x: int, y: int) -> UIElement | None:
        try:
            control = self.auto.ControlFromPoint(int(x), int(y))
        except Exception:
            return None
        if control is None:
            return None
        top = control.GetTopLevelControl()
        return UIElement(
            role=_role(control), name=(control.Name or "").strip()[:200], value=_value(control)[:200],
            app=_process_name(getattr(control, "ProcessId", 0)),
            window_title=(top.Name if top else "") or "", bbox=_bbox(control),
            path=self._path_to_root(control),
            attrs={"automation_id": getattr(control, "AutomationId", "") or "",
                   "class_name": getattr(control, "ClassName", "") or ""},
        )

    def _path_to_root(self, control) -> list[list]:
        """Role/index pairs from the window root down to this control."""
        chain: list[list] = []
        node = control
        for _ in range(24):
            parent = node.GetParentControl()
            if parent is None:
                break
            try:
                siblings = parent.GetChildren()
                index = next((i for i, s in enumerate(siblings) if s.Element == node.Element), 0)
            except Exception:
                index = 0
            chain.append([_role(node), index])
            if parent.ControlTypeName == "WindowControl" and parent.GetParentControl() is None:
                break
            node = parent
        return list(reversed(chain))

    def check_permissions(self) -> tuple[bool, str]:
        try:
            self._foreground()
            return True, "UIAutomation reachable (no OS permission prompt on Windows)"
        except Exception as e:
            return False, f"UIAutomation unreachable: {e}"
