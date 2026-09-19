"""Config loading: config.yaml as the base, environment variables on top.

Host OS is detected here at import time so every other module can branch on
HOST_OS without repeating sys.platform checks.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_PLATFORMS = {"win32": "windows", "darwin": "macos", "linux": "linux"}
HOST_OS = _PLATFORMS.get(sys.platform, sys.platform)

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ModelConfig:
    provider: str = "ollama"
    name: str = "gemma4"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    temperature: float = 0.0
    timeout_s: int = 120


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    paths: dict[str, Any] = field(default_factory=dict)
    perception: dict[str, Any] = field(default_factory=dict)
    matching: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)
    ui: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None

    def dir(self, key: str) -> Path:
        """Absolute path for one of the data directories, created on demand."""
        p = ROOT / self.paths.get(key, key)
        p.mkdir(parents=True, exist_ok=True)
        return p


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path or os.getenv("OSAGENT_CONFIG") or ROOT / "config.yaml")
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    raw = _read_yaml(cfg_path)

    m = raw.get("model", {}) or {}
    model = ModelConfig(
        provider=os.getenv("OSAGENT_PROVIDER", m.get("provider", "ollama")),
        name=os.getenv("OSAGENT_MODEL", m.get("name", "gemma4")),
        base_url=os.getenv("OSAGENT_BASE_URL", m.get("base_url", "http://localhost:11434")),
        api_key=os.getenv("OSAGENT_API_KEY", m.get("api_key", "")),
        temperature=float(m.get("temperature", 0.0)),
        timeout_s=int(m.get("timeout_s", 120)),
    )
    return Config(
        model=model,
        paths=raw.get("paths", {}) or {},
        perception=raw.get("perception", {}) or {},
        matching=raw.get("matching", {}) or {},
        run=raw.get("run", {}) or {},
        safety=raw.get("safety", {}) or {},
        ui=raw.get("ui", {}) or {},
        source=cfg_path if cfg_path.exists() else None,
    )


CONFIG = load_config()
