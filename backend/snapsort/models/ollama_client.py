"""Local Gemma via Ollama (/api/chat with a JSON-schema `format`)."""
import asyncio
import json

import httpx

from ..schema import Extraction


def _inline_refs(schema: dict) -> dict:
    """Pydantic emits $defs/$ref; inline them so Ollama's grammar converter sees a flat schema."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


EXTRACTION_SCHEMA = _inline_refs(Extraction.model_json_schema())


class OllamaClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"

    async def extract(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> Extraction:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt, "images": [image_jpeg_b64]},
            ],
            "format": EXTRACTION_SCHEMA,
            "stream": False,
            "think": False,  # thinking roughly doubles latency; extraction doesn't need it
            "keep_alive": "60m",  # keep the model loaded between demo screenshots
            "options": {"temperature": 0},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            # Ollama can 500 while the model is still loading (seen on the GTX 1650): retry once.
            for attempt in range(2):
                r = await client.post(f"{self.base_url}/api/chat", json=body)
                if r.status_code < 500 or attempt == 1:
                    break
                await asyncio.sleep(3)
            r.raise_for_status()
        content = r.json()["message"]["content"]
        return Extraction.model_validate(json.loads(content))

    async def warmup(self) -> None:
        # An empty generate request loads the model into memory.
        async with httpx.AsyncClient(timeout=300) as client:
            await client.post(f"{self.base_url}/api/generate", json={"model": self.model, "keep_alive": "60m"})
