"""Hosted models via OpenRouter (OpenAI-compatible /chat/completions, JSON-schema structured output).

One API key, any vision model: set OPENROUTER_MODEL (+ optional fallbacks) in backend/.env.
"""
import asyncio
import copy
import json
import logging
import re

import httpx

from ..schema import Extraction
from .ollama_client import _inline_refs

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Only ids, sizes and error text - never the model's extracted content, which is OCR of a
# possibly-rejected screenshot (CLAUDE.md §4.4).
log = logging.getLogger("snapsort")


class ModelAPIError(RuntimeError):
    """Raised with a message that's safe to show in the app log (no keys, no image content)."""


def _strict(node):
    """OpenAI-style strict schemas: every property required, no extra keys, no defaults.

    Strips the *keywords* "title"/"default" (Pydantic labels), but never entries inside "properties":
    our events have a real field called "title".
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "properties":
                out[k] = {name: _strict(sub) for name, sub in v.items()}
            elif k not in ("default", "title"):
                out[k] = _strict(v)
        node = out
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"].keys())
            node["additionalProperties"] = False
        return node
    if isinstance(node, list):
        return [_strict(v) for v in node]
    return node


EXTRACTION_SCHEMA = _strict(_inline_refs(copy.deepcopy(Extraction.model_json_schema())))


def _loads_lenient(text: str) -> dict:
    """Parse JSON, tolerating the malformations small models actually produce.

    Only safe, structural repairs: trailing junk after the object, and trailing commas. An
    unescaped quote inside a string is *not* repaired here — guessing where the string was meant
    to end risks silently changing an extracted value, so that case falls through and the caller
    retries on another model instead.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Prose or a second object after the JSON: take the first complete value.
    try:
        obj, _ = json.JSONDecoder().raw_decode(text.lstrip())
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Trailing commas: {"a": 1,} / [1,2,]
    return json.loads(re.sub(r",\s*([}\]])", r"\1", text))


def _parse_content(content: str) -> Extraction:
    """Validate the model's JSON. Tolerates ```json fences some providers add despite response_format."""
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    return Extraction.model_validate(_loads_lenient(text))


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, fallbacks: list[str], transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.models = [model, *[m for m in fallbacks if m and m != model]]
        self.name = f"openrouter:{model}"
        self._transport = transport  # tests inject httpx.MockTransport

    def _body(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> dict:
        body = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_jpeg_b64}"}},
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "strict": True, "schema": EXTRACTION_SCHEMA},
            },
            "provider": {
                "require_parameters": True,  # only route to providers that honour response_format
                "data_collection": "deny",   # screenshots are personal: skip providers that store/train on prompts
            },
            "temperature": 0,
            # A dense screenshot (a timetable, or a page with several events plus links) can run
            # long; truncated output is unparseable, and unused output tokens cost nothing.
            "max_tokens": 8000,
        }
        # `models` = primary + automatic fallbacks (OpenRouter tries them in order if one is down).
        if len(self.models) > 1:
            body["models"] = self.models
        else:
            body["model"] = self.models[0]
        return body

    async def _call(self, body: dict) -> tuple[str, str]:
        """One request. Returns (content, model that served it)."""
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Title": "Snapsort"}
        async with httpx.AsyncClient(timeout=90, transport=self._transport) as client:
            for attempt in range(3):
                r = await client.post(API_URL, headers=headers, json=body)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))  # rate limit / provider hiccup
                    continue
                break

        if r.status_code == 401:
            raise ModelAPIError("OpenRouter rejected the API key (401)")
        if r.status_code == 402:
            raise ModelAPIError("OpenRouter account is out of credits (402)")
        if r.status_code >= 400:
            raise ModelAPIError(f"OpenRouter error {r.status_code}: {r.text[:200]}")

        data = r.json()
        if "error" in data:  # OpenRouter can return 200 with an error object
            raise ModelAPIError(f"OpenRouter error: {str(data['error'])[:200]}")
        return data["choices"][0]["message"].get("content") or "", str(data.get("model", "?"))

    async def extract(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> Extraction:
        if not self.api_key:
            raise ModelAPIError("OPENROUTER_API_KEY is not set (add it to backend/.env)")

        body = self._body(image_jpeg_b64, system_prompt, user_prompt)
        content, served_by = await self._call(body)
        try:
            return _parse_content(content)
        except (json.JSONDecodeError, ValueError) as first_error:
            # A small model occasionally emits a stray quote mid-string and the whole object
            # becomes unparseable. OpenRouter's own `models` fallback only triggers on provider
            # errors, not on bad JSON, so do it here: re-ask on the next model, which is usually
            # stricter about structured output. Better a slower answer than a failed screenshot.
            log.warning(
                "invalid JSON from %s (%s chars): %s", served_by, len(content), first_error
            )
            for alternative in self.models[1:]:
                retry = dict(body)
                retry.pop("models", None)
                retry["model"] = alternative
                try:
                    content, served_by = await self._call(retry)
                    parsed = _parse_content(content)
                except (json.JSONDecodeError, ValueError):
                    continue
                except ModelAPIError:
                    break
                log.warning("recovered on fallback model %s", served_by)
                return parsed
            raise ModelAPIError(
                f"model returned invalid JSON ({served_by}): {first_error}"
            ) from first_error

    async def warmup(self) -> None:
        return None  # hosted: nothing to load
