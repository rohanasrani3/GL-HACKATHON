"""Web UI: a prompt box, a live step trace over SSE, and a stop button.

Built on Starlette rather than FastAPI. FastAPI pulls in pydantic, whose native
_pydantic_core.pyd is blocked by Windows Application Control on this machine;
Starlette is FastAPI's own foundation and pure Python, so the UI works without
asking anyone to weaken a security policy. The request bodies here are three
fields, which is not enough to miss a validation library over.

No auth, no accounts, no database. It binds to localhost and drives the machine
it runs on, which is exactly as much trust as it should ever have.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from ..actuation.safety import allowlist
from ..config import CONFIG, HOST_OS
from . import runstate

STATIC = Path(__file__).parent / "static"


async def index(request):
    return FileResponse(STATIC / "index.html")


async def status(request):
    run = runstate.current()
    return JSONResponse({
        "host_os": HOST_OS,
        "model": f"{CONFIG.model.provider}/{CONFIG.model.name}",
        "base_url": CONFIG.model.base_url,
        "max_steps": CONFIG.get_agent("max_steps", 14),
        "allowed_apps": allowlist(),
        "busy": bool(run and not run.done.is_set()),
        "run_id": run.id if run else None,
    })


async def start_run(request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "body must be JSON"}, status_code=400)

    goal = str(body.get("goal", "")).strip()
    if not goal:
        return JSONResponse({"detail": "goal is empty"}, status_code=400)

    steps = body.get("steps")
    steps = int(steps) if isinstance(steps, (int, float, str)) and str(steps).isdigit() else None
    try:
        run = runstate.start(goal, bool(body.get("execute")), steps,
                             bool(body.get("approve")), bool(body.get("overlay", True)))
    except runstate.Busy as e:
        return JSONResponse({"detail": str(e)}, status_code=409)
    return JSONResponse({"run_id": run.id, "dry_run": run.dry_run})


async def abort(request):
    return JSONResponse({"aborted": runstate.abort()})


def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"


async def stream(request):
    run = runstate.RUNS.get(request.path_params["run_id"])
    if run is None:
        return JSONResponse({"detail": "unknown run"}, status_code=404)

    def events():
        """A cursor into the run's event log, not a consuming queue: a browser
        that connects late still sees the whole run, and two open tabs do not
        steal each other's events."""
        i = 0
        while True:
            log = run.events
            while i < len(log):
                kind, data = log[i]
                i += 1
                yield _sse(kind, data)
            if run.done.is_set() and i >= len(run.events):
                break
            time.sleep(0.1)
        yield _sse("closed", {"status": getattr(run.result, "status", "") or "crashed"})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app = Starlette(routes=[
    Route("/", index),
    Route("/api/status", status),
    Route("/api/run", start_run, methods=["POST"]),
    Route("/api/abort", abort, methods=["POST"]),
    Route("/api/stream/{run_id}", stream),
])


def serve(port: int | None = None) -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port or int(CONFIG.ui.get("port", 8765)),
                log_level="warning")
