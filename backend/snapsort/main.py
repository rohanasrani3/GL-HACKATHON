"""FastAPI app.

Run:  uvicorn snapsort.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from .config import settings
from .models import get_client
from .pipeline import InvalidInputError, analyze
from .schema import AnalyzeResponse

log = logging.getLogger("snapsort")
client = get_client()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the model in the background so the first demo screenshot isn't a cold start.
    async def _warm():
        try:
            await client.warmup()
            log.warning("model warm: %s", client.name)
        except Exception as e:  # noqa: BLE001 - warmup is best-effort
            log.warning("warmup failed: %s", e)

    task = asyncio.create_task(_warm())
    yield
    task.cancel()


app = FastAPI(title="Snapsort", lifespan=lifespan)


API_VERSION = 1
FEEDBACK_FILE = Path(__file__).resolve().parents[2] / "evals" / "results" / "feedback.jsonl"


def check_token(token: Optional[str]) -> None:
    if settings.api_token and token != settings.api_token:
        raise HTTPException(status_code=401, detail="bad token")


@app.get("/health")
async def health():
    return {
        "ok": True,
        "api_version": API_VERSION,
        "model": client.name,
        "auto_add_threshold": settings.auto_add_threshold,
        "ask_threshold": settings.ask_threshold,
    }


@app.get("/auth/check", status_code=204)
async def auth_check(x_api_token: Optional[str] = Header(None)):
    """Lets apps verify their API token in Settings ("Save & test") without sending an image."""
    check_token(x_api_token)


class Feedback(BaseModel):
    proposal_id: str
    decision: Literal["auto_add", "ask"]
    outcome: Literal["added", "dismissed", "undone", "edited", "failed"]
    platform: Literal["ios", "android", "other"] = "other"


@app.post("/feedback", status_code=204)
async def feedback(fb: Feedback, x_api_token: Optional[str] = Header(None)):
    """What the user did with a proposal. IDs + outcome only, never event content (CLAUDE.md §4)."""
    check_token(x_api_token)
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    row = fb.model_dump() | {"t": datetime.now(dt_timezone.utc).isoformat()}
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(
    file: UploadFile = File(...),
    captured_at: Optional[str] = Form(None, description="Required ISO 8601 timestamp with UTC offset"),
    timezone: Optional[str] = Form(None, description="IANA tz, e.g. Asia/Hong_Kong"),
    locale: str = Form("en-HK"),
    x_api_token: Optional[str] = Header(None),
):
    check_token(x_api_token)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image too large")

    if not captured_at:
        raise HTTPException(status_code=400, detail="captured_at is required")
    try:
        cap = datetime.fromisoformat(captured_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="captured_at must be ISO 8601")
    if cap.utcoffset() is None:
        raise HTTPException(status_code=400, detail="captured_at must include a UTC offset")

    try:
        result = await analyze(client, data, cap, timezone, locale)
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 - surface model/network failures to the app as 502
        log.exception("analyze failed")
        raise HTTPException(status_code=502, detail=f"model error: {e}")

    # Log IDs and outcome only, never image content (CLAUDE.md §4).
    log.warning(
        "analyze genre=%s proposals=%d skipped=%s latency=%dms",
        result.genre, len(result.proposals), result.skipped_reason, result.latency_ms,
    )
    return result
