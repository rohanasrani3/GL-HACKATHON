"""ModelClient interface: swap Gemma (local) and Claude (hosted) via MODEL_PROVIDER."""
from typing import Protocol

from ..schema import Extraction


class ModelClient(Protocol):
    name: str

    async def extract(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> Extraction:
        """Run one extraction over a screenshot and return a validated Extraction."""
        ...

    async def warmup(self) -> None:
        """Optional: load the model ahead of the first real request."""
        ...


def get_client() -> ModelClient:
    from ..config import settings

    if settings.model_provider == "mock":
        from .mock_client import MockClient

        return MockClient()
    if settings.model_provider == "claude":
        from .claude_client import ClaudeClient

        return ClaudeClient(settings.claude_model)
    from .ollama_client import OllamaClient

    return OllamaClient(settings.ollama_url, settings.ollama_model)
