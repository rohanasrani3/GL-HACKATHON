"""LLM access. Deliberately behind an interface: the replay loop must never
call this, and the compiler must not care which endpoint is serving.

Every call returns an LLMResponse carrying token counts so RunReport can show
the run-1-vs-run-2 cost delta.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import CONFIG, ModelConfig


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def json(self) -> Any:
        """Parse the response as JSON, tolerating a ```json fence."""
        t = self.text.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            start, end = t.find("{"), t.rfind("}")
            if start == -1 or end <= start:
                raise
            return json.loads(t[start:end + 1])


class LLMClient(ABC):
    name: str = "abstract"

    def __init__(self, cfg: ModelConfig | None = None) -> None:
        self.cfg = cfg or CONFIG.model

    @abstractmethod
    def chat(self, system: str, user: str, json_mode: bool = True) -> LLMResponse: ...

    @abstractmethod
    def available_models(self) -> list[str]: ...

    def ping(self) -> tuple[bool, str]:
        """(reachable, detail) - used by `osagent doctor`."""
        try:
            models = self.available_models()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if self.cfg.name in models or any(m.startswith(self.cfg.name) for m in models):
            return True, f"{len(models)} model(s), '{self.cfg.name}' present"
        return False, f"reachable but '{self.cfg.name}' not pulled. have: {', '.join(models) or 'none'}"


class OllamaClient(LLMClient):
    name = "ollama"

    def chat(self, system: str, user: str, json_mode: bool = True) -> LLMResponse:
        payload = {
            "model": self.cfg.name,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
        }
        if json_mode:
            payload["format"] = "json"
        r = httpx.post(f"{self.cfg.base_url}/api/chat", json=payload, timeout=self.cfg.timeout_s)
        r.raise_for_status()
        d = r.json()
        return LLMResponse(
            text=d.get("message", {}).get("content", ""),
            prompt_tokens=d.get("prompt_eval_count", 0),
            completion_tokens=d.get("eval_count", 0),
            model=d.get("model", self.cfg.name), raw=d,
        )

    def available_models(self) -> list[str]:
        r = httpx.get(f"{self.cfg.base_url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


class OpenAICompatClient(LLMClient):
    name = "openai_compat"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}

    def chat(self, system: str, user: str, json_mode: bool = True) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.cfg.name,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": self.cfg.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = httpx.post(f"{self.cfg.base_url}/chat/completions", json=payload,
                       headers=self._headers(), timeout=self.cfg.timeout_s)
        r.raise_for_status()
        d = r.json()
        usage = d.get("usage", {})
        return LLMResponse(
            text=d["choices"][0]["message"]["content"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            model=d.get("model", self.cfg.name), raw=d,
        )

    def available_models(self) -> list[str]:
        r = httpx.get(f"{self.cfg.base_url}/models", headers=self._headers(), timeout=5)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]


def get_client(cfg: ModelConfig | None = None) -> LLMClient:
    cfg = cfg or CONFIG.model
    return OpenAICompatClient(cfg) if cfg.provider == "openai_compat" else OllamaClient(cfg)
