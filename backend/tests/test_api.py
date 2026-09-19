"""API contract tests with a fake model (no Ollama needed)."""
import io
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image

import snapsort.main as main
from snapsort.schema import Extraction, RawEvent

HK = ZoneInfo("Asia/Hong_Kong")
DAY = (datetime.now(HK) + timedelta(days=5)).date()


class FakeClient:
    name = "fake"

    def __init__(self, extraction):
        self.extraction = extraction

    async def extract(self, *_):
        return self.extraction

    async def warmup(self):
        return None


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 200), "white").save(buf, format="PNG")
    return buf.getvalue()


def ev(conf, title):
    return RawEvent(title=title, date_text=DAY.strftime("%d %B"), date_guess=DAY.isoformat(), start_time="10:00",
                    end_time=None, location=None, online_url=None, description=None, confidence=conf, evidence="x")


def test_analyze_contract(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="poster", sensitive=False, actionable=True, skipped_reason=None,
        events=[ev(0.95, "Clear"), ev(0.6, "Unclear"), ev(0.2, "Noise")])))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                   data={"captured_at": datetime.now(HK).isoformat(), "timezone": "Asia/Hong_Kong"})
    assert r.status_code == 200, r.text
    body = r.json()
    decisions = {p["payload"]["title"]: p["decision"] for p in body["proposals"]}
    assert decisions == {"Clear": "auto_add", "Unclear": "ask"}  # 0.2 dropped
    p = body["proposals"][0]
    assert set(p) >= {"id", "action", "decision", "payload", "confidence", "evidence"}
    assert set(p["payload"]) >= {"title", "start", "end", "all_day", "timezone", "location", "description"}


def test_sensitive_is_skipped(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="other", sensitive=True, actionable=True, skipped_reason=None, events=[ev(0.99, "OTP")])))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                   data={"captured_at": "2026-09-19T14:00:00+08:00"})
    assert r.json()["proposals"] == [] and r.json()["skipped_reason"] == "sensitive_content"


def test_health_and_feedback(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "client", FakeClient(None))
    monkeypatch.setattr(main, "FEEDBACK_FILE", tmp_path / "fb.jsonl")
    with TestClient(main.app) as c:
        h = c.get("/health").json()
        assert h["ok"] and h["api_version"] == 1 and "auto_add_threshold" in h
        r = c.post("/feedback", json={"proposal_id": "abc", "decision": "ask", "outcome": "added", "platform": "ios"})
        assert r.status_code == 204
        assert c.post("/feedback", json={"proposal_id": "abc", "decision": "ask", "outcome": "bogus"}).status_code == 422
    assert json.loads((tmp_path / "fb.jsonl").read_text())["outcome"] == "added"


def test_bad_inputs(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(None))
    with TestClient(main.app) as c:
        assert c.post("/analyze", files={"file": ("s.png", b"", "image/png")}).status_code == 400
        assert c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                      data={"captured_at": "yesterday"}).status_code == 400


def test_invalid_timezone_returns_400(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="other", sensitive=False, actionable=False, events=[], skipped_reason="not_actionable")))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                   data={"captured_at": datetime.now(HK).isoformat(), "timezone": "Invalid/Timezone"})
    assert r.status_code == 400, r.text


def test_non_image_upload_returns_400(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="other", sensitive=False, actionable=False, events=[], skipped_reason="not_actionable")))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", b"not an image", "image/png")},
                   data={"captured_at": datetime.now(HK).isoformat(), "timezone": "Asia/Hong_Kong"})
    assert r.status_code == 400, r.text


def test_missing_captured_at_returns_400(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="other", sensitive=False, actionable=False, events=[], skipped_reason="not_actionable")))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                   data={"timezone": "Asia/Hong_Kong"})
    assert r.status_code == 400, r.text


def test_captured_at_without_offset_returns_400(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="other", sensitive=False, actionable=False, events=[], skipped_reason="not_actionable")))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                   data={"captured_at": "2026-09-19T14:00:00", "timezone": "Asia/Hong_Kong"})
    assert r.status_code == 400, r.text


def test_duplicate_events_preserve_distinct_proposals_in_order(monkeypatch):
    event = ev(0.95, "One talk")
    monkeypatch.setattr(main, "client", FakeClient(Extraction(
        genre="poster", sensitive=False, actionable=True, skipped_reason=None,
        events=[event, ev(0.95, "Another talk"), event])))
    with TestClient(main.app) as c:
        r = c.post("/analyze", files={"file": ("s.png", png(), "image/png")},
                   data={"captured_at": datetime.now(HK).isoformat(), "timezone": "Asia/Hong_Kong"})
    assert r.status_code == 200, r.text
    assert [p["payload"]["title"] for p in r.json()["proposals"]] == ["One talk", "Another talk"]


def test_auth_check(monkeypatch):
    monkeypatch.setattr(main, "client", FakeClient(None))
    object.__setattr__(main.settings, "api_token", "s3cret")
    try:
        with TestClient(main.app) as c:
            assert c.get("/auth/check").status_code == 401
            assert c.get("/auth/check", headers={"X-Api-Token": "wrong"}).status_code == 401
            assert c.get("/auth/check", headers={"X-Api-Token": "s3cret"}).status_code == 204
    finally:
        object.__setattr__(main.settings, "api_token", "")
