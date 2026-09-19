"""The live perceive -> decide -> act loop.

This is the one place in osagent where the LLM sits inside the control loop.
The deterministic replay path (compiler/ + runner/) deliberately does not.
Everything observable is pushed through `emit` so the CLI and the web UI can
render the same run without knowing anything about each other.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..actuation.desktop import DesktopActuator
from ..actuation.safety import (Aborted, NeedsConfirmation, arm_kill_switch,
                                check_abort, gate, reset_abort)
from ..config import CONFIG
from ..model import get_client
from ..perception import get_perceiver
from .actions import Action, InvalidAction, parse, render_elements
from .dispatch import perform
from .prompts import AGENT_SYSTEM, AGENT_USER, NO_HISTORY
from .rank import rank

Emit = Callable[[str, dict], None]


@dataclass
class AgentResult:
    status: str = "running"          # done | failed | aborted | max_steps
    reason: str = ""
    steps: int = 0
    llm_calls: int = 0
    llm_tokens: int = 0
    elapsed_s: float = 0.0
    history: list[str] = field(default_factory=list)


class AgentLoop:
    def __init__(self, goal: str, dry_run: bool = True, emit: Emit | None = None,
                 overlay=None, max_steps: int | None = None,
                 approve_destructive: bool = False) -> None:
        self.goal = goal
        self.dry_run = dry_run
        self.emit = emit or (lambda kind, data: None)
        self.overlay = overlay
        self.approve = approve_destructive
        self.max_steps = max_steps or int(CONFIG.get_agent("max_steps", 14))
        self.cap = int(CONFIG.get_agent("elements_in_prompt", 55))
        self.settle = float(CONFIG.get_agent("settle_ms", 600)) / 1000.0
        self.client = get_client()
        self.perceiver = get_perceiver()
        self.actuator = DesktopActuator(
            dry_run=dry_run,
            on_action=lambda w, d: self.emit("actuate", {"verb": w, "detail": d}))
        self.result = AgentResult()

    # -- one turn -----------------------------------------------------------
    def _perceive(self) -> tuple[str, str, list]:
        app, window = self.perceiver.frontmost_app()
        elements = rank(self.perceiver.snapshot(max_elements=400), self.cap)
        self.emit("perceive", {"app": app, "window": window, "count": len(elements)})
        return app, window, elements

    def _decide(self, app: str, window: str, elements: list, note: str = "") -> Action:
        history = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(self.result.history[-6:]))
        user = AGENT_USER.format(
            goal=self.goal, history=("Already done:\n" + history) if history else NO_HISTORY,
            app=app, window=window, elements=render_elements(elements))
        if note:
            user += f"\n\nYour last reply was rejected: {note}\nTry again."
        resp = self.client.chat(AGENT_SYSTEM, user, json_mode=True)
        self.result.llm_calls += 1
        self.result.llm_tokens += resp.total_tokens
        payload = resp.json()
        self.emit("think", {"thought": str(payload.get("thought", ""))[:300],
                            "raw": payload, "tokens": resp.total_tokens})
        return parse(payload, elements)

    def _act(self, act: Action) -> None:
        gate(act.action, act.thought or act.describe(), act.text, approved=self.approve)
        if self.overlay is not None and act.element is not None:
            self.overlay.show(act.element.bbox, f"{act.action}: {act.element.label()}")
        perform(act, self.actuator)

    # -- the loop -----------------------------------------------------------
    def run(self) -> AgentResult:
        started = time.time()
        reset_abort()
        armed = arm_kill_switch()
        self.emit("start", {"goal": self.goal, "dry_run": self.dry_run,
                            "kill_switch": armed, "max_steps": self.max_steps})
        note = ""
        try:
            while self.result.steps < self.max_steps:
                check_abort()
                self.result.steps += 1
                self.emit("step", {"n": self.result.steps, "max": self.max_steps})
                try:
                    app, window, elements = self._perceive()
                    act = self._decide(app, window, elements, note)
                except (Aborted, NeedsConfirmation):
                    raise
                except Exception as e:
                    # A malformed reply, an unreadable screen or a model timeout
                    # all cost a step and get described back to the model, but
                    # none of them should end the run.
                    note = str(e) if isinstance(e, (InvalidAction, ValueError)) \
                        else f"{type(e).__name__}: {e}"
                    self.emit("reject", {"error": note})
                    continue
                note = ""
                self.emit("action", {"action": act.action, "describe": act.describe(),
                                     "thought": act.thought, "bbox": act.element.bbox
                                     if act.element is not None else None})
                if act.action in ("done", "fail"):
                    self.result.status = "done" if act.action == "done" else "failed"
                    self.result.reason = act.reason
                    break
                try:
                    self._act(act)
                    # In a dry run nothing moved, so say so: otherwise the model
                    # sees an unchanged screen and repeats itself forever.
                    note_sim = " (simulated, screen unchanged)" if self.dry_run else ""
                    self.result.history.append(act.describe() + note_sim)
                except (Aborted, NeedsConfirmation):
                    raise
                except Exception as e:      # one bad action must not end the run
                    note = f"{type(e).__name__}: {e}"
                    self.result.history.append(f"{act.describe()} -> FAILED: {e}")
                    self.emit("error", {"error": note})
                finally:
                    if self.overlay is not None:
                        self.overlay.hide()
                time.sleep(self.settle)
            else:
                self.result.status = "max_steps"
                self.result.reason = f"stopped after {self.max_steps} steps"
        except Aborted as e:
            self.result.status, self.result.reason = "aborted", str(e)
        except NeedsConfirmation as e:
            self.result.status = "needs_confirmation"
            self.result.reason = e.description
        self.result.elapsed_s = round(time.time() - started, 2)
        self.emit("finish", {"status": self.result.status, "reason": self.result.reason,
                             "steps": self.result.steps, "llm_calls": self.result.llm_calls,
                             "llm_tokens": self.result.llm_tokens,
                             "elapsed_s": self.result.elapsed_s})
        return self.result
