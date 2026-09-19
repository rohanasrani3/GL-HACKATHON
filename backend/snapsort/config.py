"""Runtime configuration, read from environment variables (see .env.example)."""
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    model_provider: str = os.getenv("MODEL_PROVIDER", "ollama")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:12b")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5")
    api_token: str = os.getenv("API_TOKEN", "")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Hong_Kong")
    # Proposals below this confidence are dropped server-side (the app applies its own, higher threshold).
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "0.3"))
    # Longest image side sent to the model, in pixels.
    max_image_side: int = int(os.getenv("MAX_IMAGE_SIDE", "1280"))


settings = Settings()
