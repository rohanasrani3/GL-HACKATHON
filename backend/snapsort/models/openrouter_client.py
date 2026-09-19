"""Hosted models via OpenRouter (OpenAI-compatible /chat/completions, JSON-schema structured output).

One API key, any vision model: set OPENROUTER_MODEL (+ optional fallbacks) in backend/.env.
"""
import asyncio
import copy
import json
import re

import httpx

from ..schema import Extraction
from .ollama_client import _inline_refs

API_URL = "https://openrouter.ai/api/v1/chat/completions"


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


def _parse_content(content: str) -> Extraction:
    """Validate the model's JSON. Tolerates ```json fences some providers add despite response_format."""
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    return Extraction.model_validate(json.loads(text))


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
            "max_tokens": 4000,
        }
        # `models` = primary + automatic fallbacks (OpenRouter tries them in order if one is down).
        if len(self.models) > 1:
            body["models"] = self.models
        else:
            body["model"] = self.models[0]
        return body

    async def extract(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> Extraction:
        if not self.api_key:
            raise ModelAPIError("OPENROUTER_API_KEY is not set (add it to backend/.env)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Title": "Snapsort",
        }
        body = self._body(image_jpeg_b64, system_prompt, user_prompt)
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
        content = data["choices"][0]["message"].get("content") or ""
        try:
            return _parse_content(content)
        except (json.JSONDecodeError, ValueError) as e:
            raise ModelAPIError(f"model returned invalid JSON ({data.get('model', '?')}): {e}") from e

    async def warmup(self) -> None:
        return None  # hosted: nothing to load
