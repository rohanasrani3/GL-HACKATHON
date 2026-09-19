"""FastAPI app.

Run:  uvicorn snapsort.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from .config import settings
from .models import get_client
from .pipeline import analyze
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


@app.get("/health")
async def health():
    return {"ok": True, "model": client.name}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(
    file: UploadFile = File(...),
    captured_at: Optional[str] = Form(None, description="ISO 8601 with offset; defaults to now"),
    timezone: Optional[str] = Form(None, description="IANA tz, e.g. Asia/Hong_Kong"),
    locale: str = Form("en-HK"),
    x_api_token: Optional[str] = Header(None),
):
    if settings.api_token and x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="bad token")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image too large")

    cap = None
    if captured_at:
        try:
            cap = datetime.fromisoformat(captured_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="captured_at must be ISO 8601")

    try:
        result = await analyze(client, data, cap, timezone, locale)
    except Exception as e:  # noqa: BLE001 - surface model/network failures to the app as 502
        log.exception("analyze failed")
        raise HTTPException(status_code=502, detail=f"model error: {e}")

    # Log IDs and outcome only, never image content (CLAUDE.md §4).
    log.warning(
        "analyze genre=%s proposals=%d skipped=%s latency=%dms",
        result.genre, len(result.proposals), result.skipped_reason, result.latency_ms,
    )
    return result
