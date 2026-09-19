"""OpenRouter client against a fake HTTP transport (no network, no key needed)."""
import asyncio
import json

import httpx
import pytest

from snapsort.models.openrouter_client import EXTRACTION_SCHEMA, ModelAPIError, OpenRouterClient

GOOD = {
    "genre": "poster", "sensitive": False, "actionable": True,
    "dates_seen": ["12-16 October 2026"],
    "events": [{
        "title": "Global Entrepreneurship Programme", "date_text": "12-16 October 2026", "date_guess": "2026-10-12",
        "end_date_text": "16 October 2026", "end_date_guess": "2026-10-16", "start_time": None, "end_time": None,
        "location": "HKU Campus", "online_url": None, "description": None, "confidence": 0.9, "evidence": "Date: 12 - 16 October 2026",
    }],
    "skipped_reason": None,
}


def client_with(handler, fallbacks=("google/gemini-2.5-flash-lite",), key="sk-or-test"):
    return OpenRouterClient(key, "google/gemma-4-26b-a4b-it", list(fallbacks), transport=httpx.MockTransport(handler))


def run(c):
    return asyncio.run(c.extract("aGVsbG8=", "system", "user"))


def test_request_shape_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"model": "x", "choices": [{"message": {"content": json.dumps(GOOD)}}]})

    ex = run(client_with(handler))
    assert ex.events[0].end_date_guess == "2026-10-16"
    body = seen["body"]
    assert seen["auth"] == "Bearer sk-or-test"
    assert body["models"] == ["google/gemma-4-26b-a4b-it", "google/gemini-2.5-flash-lite"]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["provider"] == {"require_parameters": True, "data_collection": "deny"}
    img = body["messages"][1]["content"][1]
    assert img["type"] == "image_url" and img["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_single_model_uses_model_field():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})

    run(client_with(handler, fallbacks=()))
    assert seen["body"]["model"] == "google/gemma-4-26b-a4b-it" and "models" not in seen["body"]


def test_strict_schema_keeps_fields_named_title():
    # Regression: stripping the "title" keyword once deleted the event's title *field*.
    ev = EXTRACTION_SCHEMA["properties"]["events"]["items"]
    assert "title" in ev["properties"] and "title" in ev["required"]
    assert "title" not in ev  # the Pydantic label keyword is still stripped


def test_strict_schema_requires_everything():
    ev = EXTRACTION_SCHEMA["properties"]["events"]["items"]
    assert set(ev["required"]) == set(ev["properties"]) and ev["additionalProperties"] is False
    assert set(EXTRACTION_SCHEMA["required"]) == set(EXTRACTION_SCHEMA["properties"])


def test_code_fenced_json_tolerated():
    fenced = "```json\n" + json.dumps(GOOD) + "\n```"
    ex = run(client_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": fenced}}]})))
    assert ex.genre == "poster"


def test_retries_rate_limit_then_succeeds(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_: real_sleep(0))
    calls = iter([httpx.Response(429), httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})])
    assert run(client_with(lambda r: next(calls))).actionable


@pytest.mark.parametrize("status,msg", [(401, "API key"), (402, "credits")])
def test_clear_errors(status, msg):
    with pytest.raises(ModelAPIError, match=msg):
        run(client_with(lambda r: httpx.Response(status, json={"error": {"message": "x"}})))


def test_missing_key_fails_at_request_not_startup():
    c = client_with(lambda r: httpx.Response(200), key="")  # constructing must not raise
    with pytest.raises(ModelAPIError, match="OPENROUTER_API_KEY"):
        run(c)


def test_invalid_json_reported():
    with pytest.raises(ModelAPIError, match="invalid JSON"):
        run(client_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "sorry, no"}}]})))


# ---------- recovering from malformed JSON ----------

def _content(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}], "model": "primary"})


def test_trailing_prose_after_the_object_is_tolerated():
    body = json.dumps(GOOD) + "\n\nHope that helps!"
    ex = run(client_with(lambda r: _content(body)))
    assert ex.events[0].title == "Global Entrepreneurship Programme"


def test_trailing_commas_are_tolerated():
    body = json.dumps(GOOD).replace('"skipped_reason": null}', '"skipped_reason": null,}')
    ex = run(client_with(lambda r: _content(body)))
    assert ex.actionable is True


def test_unparseable_primary_falls_back_to_the_next_model():
    """A stray quote mid-string kills the object. Re-ask a stricter model rather than fail."""
    seen = []

    def handler(req: httpx.Request):
        payload = json.loads(req.content)
        seen.append(payload.get("model") or payload.get("models"))
        if len(seen) == 1:
            # what actually happens: an unescaped quote ends the string early
            return _content('{"genre": "poster", "evidence": "he said "hi" there", ')
        return _content(json.dumps(GOOD))

    ex = run(client_with(handler))
    assert ex.events[0].location == "HKU Campus"
    assert seen[0] == ["google/gemma-4-26b-a4b-it", "google/gemini-2.5-flash-lite"]
    assert seen[1] == "google/gemini-2.5-flash-lite"  # retry is pinned to the fallback


def test_gives_up_when_every_model_returns_junk():
    with pytest.raises(ModelAPIError, match="invalid JSON"):
        run(client_with(lambda r: _content('{"broken": "yes" "no"}')))


def test_no_fallback_configured_still_reports_clearly():
    with pytest.raises(ModelAPIError, match="invalid JSON"):
        run(client_with(lambda r: _content("not json at all"), fallbacks=()))
