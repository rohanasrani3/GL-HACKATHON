# osagent

Two modes, one perception layer.

**Agent mode** (`osagent ui`, `osagent agent`) — type a plain-English goal. The model reads
the live accessibility tree, picks one action, the actuator performs it, and the loop
re-reads the screen. You watch the cursor move and the buttons get clicked.

**Pipeline mode** (`record` → `compile` → `run`) — record a human doing a task once, compile
it into a deterministic replayable program, run it on new inputs, verify the result
out-of-band. Here the LLM is a *compiler*: it runs once, offline, and is never in the
replay loop.

These are deliberately separate. Agent mode is flexible and slow and costs tokens every
run; pipeline mode is rigid and fast and costs nothing after compilation. The intended
path is that agent mode eventually *produces* the recordings that pipeline mode compiles.

## Status

| # | Step | State |
|---|------|-------|
| 1 | Scaffolding, config, CLI, `doctor` | done |
| 2 | Actuator + overlay highlight | done |
| — | **Live agent loop + web UI** | **done** (added ahead of the plan) |
| 3 | Recorder | stub |
| 4 | Workflow model + deterministic runner | stub |
| 5 | Verification checks + RunReport | stub |
| 6 | LLM compiler (recording → workflow) | stub |
| 7 | Run-1-vs-run-2 cost panel | stub |

Stubbed commands print which step they land in and exit non-zero. They do not pretend.

## Quick start

```powershell
.\.venv\Scripts\osagent.exe doctor          # eight checks, then a live UI dump
.\.venv\Scripts\osagent.exe ui              # dashboard on http://127.0.0.1:8765
```

In the dashboard: type a goal, tick **Execute for real**, press Run. Leave it unticked for
a dry run where the model decides but nothing is clicked.

Same thing from the terminal:

```powershell
osagent agent "In the Calculator app, compute 7 times 8 by clicking the buttons" --execute
```

A real run of exactly that: 5 steps, 5 model calls, 45 seconds, and it stopped by reading
`56` off the display rather than by assuming it had worked.

## Setup

Detected host: **Windows 11**, Python 3.13 in `.venv`.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\osagent.exe doctor
```

`uv` was not on this machine, so the venv is plain `venv` + `pip`. If you install uv later,
`uv sync` works against the same `pyproject.toml`. Every command also runs as
`python -m osagent ...`.

### The model

Ollama at `http://localhost:11434`, model from `OSAGENT_MODEL` (default `gemma4`). On this
machine the tag is `gemma4:12b`.

```powershell
ollama pull gemma4
$env:OSAGENT_MODEL = "gemma4:12b"
```

Two settings in `config.yaml` are load-bearing, and both were found the hard way:

- **`think: false`** — gemma4 is a reasoning model. Ollama puts its reasoning in
  `message.thinking` and leaves `message.content` empty until it finishes. Combined with a
  token cap, that means *every reply is empty*. Turning thinking off took a call from
  9.3s to 4.5s and made the content appear.
- **`max_tokens: 300`** (`num_predict`) — given a 70-element list, the model will pad a
  one-line action out to 2450 tokens. Capping it took a call from **166s to 12s**.

To swap in any OpenAI-compatible endpoint, no code change:

```
OSAGENT_PROVIDER=openai_compat
OSAGENT_BASE_URL=https://api.openai.com/v1
OSAGENT_MODEL=gpt-4o-mini
OSAGENT_API_KEY=sk-...
```

### Permissions — Windows

**There is no accessibility permission to grant.** UI Automation is open to any process in
the same desktop session. What actually matters:

1. **Run as a normal user in the same session as the apps you are driving.** Not over SSH,
   not as a service, not in Session 0.
2. **Elevation must match.** A non-elevated process cannot read or click into an elevated
   window. If `doctor` shows a window title but zero elements, this is why.
3. **Screen unlocked and awake.** A locked workstation has no UI tree and screenshots come
   back black.
4. **DPI scaling is handled, but only if osagent sets it first.** This display is at 1.25x.
   `perception/screen.py` declares per-monitor DPI awareness at import so element
   coordinates and click coordinates share one pixel space. Do not import `pyautogui`
   before osagent in your own scripts.
5. **Antivirus / EDR may flag synthetic input.** `pyautogui` drives `SendInput`; some
   endpoint agents treat that as a keylogger.

### Permissions — macOS and Linux (not this host)

Not implemented; the backends raise with the exact setup instruction rather than failing
silently.

- **macOS**: grant your terminal **Accessibility** and **Screen Recording** in System
  Settings → Privacy & Security, then fully quit and relaunch it. Install
  `pyobjc-framework-ApplicationServices`.
- **Linux**: X11 only (Wayland blocks synthetic input and cross-app inspection).
  `sudo apt install python3-pyatspi gir1.2-atspi-2.0` and
  `gsettings set org.gnome.desktop.interface toolkit-accessibility true`.

## Commands

```
osagent doctor [--elements N] [--delay S] [--no-snapshot]
osagent agent GOAL [--execute] [--steps N] [--yes] [--no-overlay] [-v]
osagent ui [--port N] [--no-open]
osagent record NAME                      # step 3
osagent compile NAME                     # step 6
osagent run NAME [--input data.csv] [--execute] [--yes]
osagent replay-last                      # step 4
osagent version
```

`doctor --delay 5` waits five seconds before snapshotting so you can alt-tab to the app you
actually want to inspect. Without it you get a UI dump of your own terminal.

## Safety model

Load-bearing, not decoration:

- **Nothing executes by default.** Both `agent` and `run` are dry runs until `--execute`
  (or the checkbox in the dashboard).
- **ESC aborts.** A daemon thread watches for it and sets a process-wide flag checked
  before every action. The dashboard's Stop button sets the same flag.
- **Destructive steps gate.** Anything matching `safety.destructive_keywords` (send, submit,
  delete, pay, purchase, transfer, remove, publish) raises `NeedsConfirmation` unless
  pre-approved.
- **Launching is allowlisted.** `safety.allowed_apps` in `config.yaml`. An app not on the
  list is refused outright, not confirmed.
- **No hallucinated targets.** The model points at an *integer* from the list it was just
  given. An index that does not exist is rejected before anything is clicked, and the
  rejection is fed back so it can retry.
- **No raw coordinate clicking** unless a selector explicitly says `match_strategy:
  "coordinate"`.

## Notes from the build

Three things bit hard enough to be worth writing down:

- **The agent kept perceiving itself.** The Tk highlight overlay was becoming the foreground
  window, so `snapshot()` returned the overlay's own empty tree and the agent went blind.
  Fixed twice over: `WS_EX_NOACTIVATE` on the overlay, and `_foreground()` in
  `a11y_windows.py` now skips any window owned by our own PID.
- **Windows lies about `SetForegroundWindow`.** It refuses the switch when the caller does
  not own the foreground, and returns success anyway — so `focus_app` reported success five
  times in a row while nothing moved. `actuation/win_input.py` attaches to the foreground
  thread's input queue and then *verifies*, so a failed focus is reported as failed.
- **Naive element truncation blinds the agent.** Calculator exposes 132 elements and its
  digits sit at index 98. Taking the first 40 in tree order handed the model the window
  chrome and the trig menu, and it correctly concluded there was no `7` button.
  `agent/rank.py` puts every actionable control ahead of decorative text.

## Layout

```
osagent/
  cli.py  config.py  doctor.py  render.py
  model/       client.py (LLMClient ABC, Ollama, OpenAI-compatible)  prompts.py
  perception/  base.py  element.py  screen.py  win_util.py
               a11y_windows.py  a11y_macos.py  a11y_linux.py
  actuation/   base.py  desktop.py  safety.py  win_input.py
  agent/       loop.py  actions.py  dispatch.py  rank.py  prompts.py  console.py
  recorder/    events.py  recorder.py
  compiler/    workflow.py  compile.py
  runner/      execute.py  repair.py
  verify/      checks.py  report.py
  ui/          server.py  runstate.py  overlay.py  static/index.html
workflows/  recordings/  runs/  tests/
```

JSON files on disk. No database, no auth, no accounts.

**The web UI is Starlette, not FastAPI.** FastAPI pulls in pydantic, whose native
`_pydantic_core.pyd` is blocked by Windows Application Control on this machine. Starlette is
FastAPI's own foundation and pure Python, so the UI works without anyone weakening a
security policy. The request bodies are three fields each.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q      # 24 passed
```

`test_snapshot_returns_real_elements` needs an interactive desktop session and skips
without one.
