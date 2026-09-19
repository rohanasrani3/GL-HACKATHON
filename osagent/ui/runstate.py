"""Run registry for the web UI.

There is exactly one physical mouse, so there is exactly one active run. The
agent loop runs on a worker thread and appends to an event log that the SSE
endpoint reads with a cursor, so a browser that connects late still sees the
whole run and two open tabs do not compete for events.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..actuation.safety import ABORT


@dataclass
class Run:
    id: str
    goal: str
    dry_run: bool
    events: list[tuple[str, dict]] = field(default_factory=list)
    done: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: str = ""


RUNS: dict[str, Run] = {}
_current: Run | None = None
_lock = threading.Lock()


class Busy(RuntimeError):
    """A run is already driving the desktop."""


def current() -> Run | None:
    return _current


def start(goal: str, execute: bool, steps: int | None, approve: bool,
          use_overlay: bool = True) -> Run:
    global _current
    with _lock:
        if _current is not None and not _current.done.is_set():
            raise Busy("a run is already in progress")
        run = Run(id=uuid.uuid4().hex[:10], goal=goal, dry_run=not execute)
        RUNS[run.id] = run
        _current = run

    def emit(kind: str, data: dict) -> None:
        run.events.append((kind, data))   # append is atomic; readers just index in

    def worker() -> None:
        overlay = None
        try:
            from ..agent.loop import AgentLoop
            if use_overlay and execute:
                from .overlay import Overlay
                overlay = Overlay()
                overlay.start()
            loop = AgentLoop(goal, dry_run=not execute, emit=emit, overlay=overlay,
                             max_steps=steps, approve_destructive=approve)
            run.result = loop.run()
        except Exception as e:                      # the UI must always learn why
            run.error = f"{type(e).__name__}: {e}"
            emit("error", {"error": run.error})
            emit("finish", {"status": "crashed", "reason": run.error, "steps": 0,
                            "llm_calls": 0, "llm_tokens": 0, "elapsed_s": 0})
        finally:
            if overlay is not None:
                overlay.stop()
            run.done.set()

    threading.Thread(target=worker, daemon=True).start()
    return run


def abort() -> bool:
    """Same flag the ESC watcher sets, so the loop stops the same way."""
    if _current is None or _current.done.is_set():
        return False
    ABORT.set()
    return True
