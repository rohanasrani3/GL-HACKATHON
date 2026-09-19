"""Step-1 smoke tests: the scaffolding holds together and perception is real."""
from __future__ import annotations

import pytest

from osagent.config import CONFIG, HOST_OS, load_config
from osagent.doctor import run_checks
from osagent.perception import UIElement, get_perceiver


def test_config_loads_and_env_defaults():
    cfg = load_config()
    assert cfg.model.provider in ("ollama", "openai_compat")
    assert cfg.model.base_url.startswith("http")
    assert cfg.dir("workflows").exists()


def test_host_os_detected():
    assert HOST_OS in ("windows", "macos", "linux")


def test_uielement_id_is_stable_and_content_addressed():
    a = UIElement(role="button", name="Save", app="x.exe", window_title="w", path=[["button", 3]])
    b = UIElement(role="button", name="Save", app="x.exe", window_title="w", path=[["button", 3]])
    c = UIElement(role="button", name="Cancel", app="x.exe", window_title="w", path=[["button", 3]])
    assert a.id == b.id != c.id
    assert UIElement.from_dict(a.to_dict()) == a


def test_uielement_center():
    assert UIElement(bbox=[10, 20, 100, 50]).center == (60, 45)


def test_doctor_never_raises():
    results = run_checks()
    assert {"python", "host os", "config"} <= {name for name, _, _ in results}
    assert all(isinstance(ok, bool) for _, ok, _ in results)


def test_snapshot_returns_real_elements():
    """Requires a desktop session - skipped on headless CI."""
    p = get_perceiver()
    ok, detail = p.check_permissions()
    if not ok:
        pytest.skip(detail)
    app, window = p.frontmost_app()
    assert isinstance(app, str)
    elements = p.snapshot(max_elements=50)
    assert elements, "expected at least one element in the frontmost window"
    assert all(e.visible for e in elements)
    assert all(e.id for e in elements)
