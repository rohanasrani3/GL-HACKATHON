"""MODEL_PROVIDER=mock: instant canned answers so frontends can be built without a model.

Every call cycles through three scenarios so both notification types get exercised:
  1. one confident event        -> decision "auto_add"
  2. one unclear event          -> decision "ask"
  3. nothing (a meme)           -> no proposals
"""
import itertools
from datetime import datetime, timedelta

from ..schema import Extraction, RawEvent

_cycle = itertools.count()


class MockClient:
    name = "mock"

    async def extract(self, image_jpeg_b64: str, system_prompt: str, user_prompt: str) -> Extraction:
        day = datetime.now() + timedelta(days=3)
        n = next(_cycle) % 3
        if n == 0:
            return Extraction(
                genre="poster", sensitive=False, actionable=True, skipped_reason=None,
                events=[RawEvent(
                    title="Generative AI in Healthcare (talk)", date_text=day.strftime("%a %d %B"),
                    date_guess=day.date().isoformat(), start_time="16:00", end_time="17:30",
                    location="Main Building LG01, HKU", online_url=None,
                    description="Public lecture by Dr. Mei Chan", confidence=0.95,
                    evidence=f"{day.strftime('%a %d %b')} · 4:00-5:30pm",
                )],
            )
        if n == 1:
            return Extraction(
                genre="chat", sensitive=False, actionable=True, skipped_reason=None,
                events=[RawEvent(
                    title="Dinner with Sam", date_text="friday", date_guess=None,
                    start_time="19:30", end_time=None, location=None, online_url=None,
                    description=None, confidence=0.6, evidence="dinner fri? maybe 7:30",
                )],
            )
        return Extraction(genre="other", sensitive=False, actionable=False, events=[], skipped_reason="meme")

    async def warmup(self) -> None:
        return None
