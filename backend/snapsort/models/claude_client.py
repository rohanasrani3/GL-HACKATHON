"""Hosted fallback: Claude with structured outputs (messages.parse + Pydantic)."""
import anthropic

from ..schema import Extraction


class ClaudeClient:
    def __init__(self, model: str):
        self.model = model
        self.name = f"claude:{model}"
        self.client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY or `ant auth login` profile

    async def extract(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> Extraction:
        response = await self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_jpeg_b64},
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
            output_format=Extraction,
            # Server-side fallback: if a safety classifier declines, the API retries on a fallback model.
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            return Extraction(genre="other", sensitive=False, actionable=False, events=[], skipped_reason="model_refused")
        return response.parsed_output

    async def warmup(self) -> None:
        return None
