# tasks.md: Hackathon build tracker

**Goal (10h):** screenshot an event → confident events are **added automatically** and the user gets "✅ Added … [Undo]"; unclear ones get "Add '<event>' to calendar? [Add / Edit / Dismiss]" first.

**Hackathon scope** (a deliberate subset of [CLAUDE.md](CLAUDE.md) / [skills.md](skills.md)):
- Android only, Kotlin. Watcher = foreground service + `ContentObserver` (not WorkManager).
- No on-device OCR. The phone uploads the image and the backend does triage + extraction in one model call.
- Backend = FastAPI on the laptop. **Model = hosted via OpenRouter** (`google/gemma-4-26b-a4b-it`, fallback `google/gemini-2.5-flash-lite`). Local Ollama, Claude and mock remain selectable with `MODEL_PROVIDER`.
- **Policy gate lives in the backend** so Android and iOS behave the same: each proposal carries `decision` = `auto_add` (confidence ≥ 0.8 and nothing unclear) or `ask` (0.5–0.8, or date/time uncertain). Below 0.5 is dropped.
- Calendar write: `auto_add` writes directly (Android CalendarContract / iOS EventKit), then notifies with **Undo**. `ask` waits for **Add**. Without calendar permission everything falls back to `ask` + the calendar app's editor.
- iOS app is built by a coworker (with Codex) from [frontend.md](frontend.md).
- Phone ↔ laptop over phone hotspot or Tailscale.

Legend: `[x]` done · `[~]` in progress · `[ ]` todo · `[!]` blocked / needs decision

## Phase 0: Setup
- [x] Environment check: Python 3.12, Java 17, Ollama 0.34, GTX 1650 (4 GB). **No Android SDK on this laptop.**
- [x] Ollama running with `gemma4:12b` (vision). **Needs `OLLAMA_LLM_LIBRARY=cuda_v12`**: the default cuda_v13 backend crashes on the GTX 1650.
- [x] Repo scaffold + `.gitignore`

## Phase 1: Backend (`/backend`)
- [x] `schema.py`: model output (`Extraction`) + API contract (`AnalyzeResponse`/`Proposal`)
- [x] `skills/calendar_event/SKILL.md`: prompt, including the prompt-injection rule
- [x] `models/`: `ModelClient` interface, `OllamaClient`, `ClaudeClient` (fallback)
- [x] `datetime_resolve.py`: dateparser anchored to `captured_at`, reconciled with the model's guess
- [x] `pipeline.py`: preprocess (downscale, strip EXIF), extract, resolve, score, filter past events
- [x] `main.py`: `POST /analyze`, `GET /health`, model warm-up on start
- [x] `test.py`: pick any picture and see the raw model output + final proposals
- [x] Policy gate: `decision` (`auto_add`/`ask`) + stable proposal `id` on every proposal
- [x] `POST /feedback` (ids + outcome only → `evals/results/feedback.jsonl`); `/health` returns thresholds + `api_version`
- [x] `MODEL_PROVIDER=mock`: canned auto_add / ask / skip cycle so frontends can be built without a model
- [x] Unit + API tests: 21/21 passing
- [x] **Latency fixed:** switched default to `gemma4:e2b-it-qat` → **5–9 s per screenshot** (was 34–77 s with gemma4:12b). Fallbacks if needed: `OLLAMA_MODEL=gemma4:12b` (slower, same accuracy on evals) or `MODEL_PROVIDER=claude`.
- [x] Ollama client retries once on 5xx (model-loading race on first request)

## Phase 2: Evals (`/evals`)
- [x] `make_samples.py`: 5 synthetic screenshots (poster, chat, ticket, meme, injection)
- [x] `run.py`: scores each against `expected/*.json`
- [x] gemma4:12b: **5/5 correct**, median 72 s
- [x] gemma4:e2b-it-qat: **5/5 correct**, median 8.8 s ← current default
- [ ] Team: add 15 real screenshots to `evals/screenshots/real/` + expected JSON

## Phase 3: Android (`/android`)
- [x] Gradle project (Kotlin, minSdk 29, targetSdk 35, no XML layouts)
- [x] `ScreenshotWatcherService`: foreground service + debounced ContentObserver, screenshots-only filter, skips backlog
- [x] `Uploader`: downscale → JPEG → multipart POST with `captured_at`, timezone, locale
- [x] `Notifier`: "Reading your screenshot…" progress; **ADDED** ("✅ Added…" + Undo/Open) and **ASK** ("Add…?" + Add/Edit/Dismiss)
- [x] `CalendarWriter`: direct insert into the primary calendar + delete for Undo
- [x] `ActionReceiver`: Add / Undo / Dismiss buttons + `/feedback` (no activity trampolines, Android 12+ safe)
- [x] `MainActivity`: server URL, test connection, start/stop, pick-from-gallery test, share-to-Snapsort, activity log
- [ ] **Build + install on a real phone in Android Studio** (not compiled yet; no SDK on this laptop)

## Phase 3b: iOS (`/ios`, coworker + Codex)
- [x] Spec written: [frontend.md](frontend.md) (API contract, Swift models, decision logic, EventKit, notifications, screens, acceptance checklist)
- [ ] Build against `MODEL_PROVIDER=mock`, pass the frontend.md §14 checklist
- [ ] Point at the real backend

## Phase 4: Demo
- [ ] End-to-end on the real phone and network
- [ ] Pitch slides
- [ ] Backup video (by hour 9)

## How to run

**Backend (laptop):**
```bash
# 1. One-time: copy backend/.env.example to backend/.env and paste your OPENROUTER_API_KEY
#    (only if MODEL_PROVIDER=ollama: OLLAMA_LLM_LIBRARY=cuda_v12 ollama serve)
# 2. API
cd backend
.venv/Scripts/python -m uvicorn snapsort.main:app --host 0.0.0.0 --port 8000
# 3. Try a picture
.venv/Scripts/python test.py
# 4. Evals
.venv/Scripts/python ../evals/run.py
```

**Android:** open `/android` in Android Studio → Run on the phone (USB debugging on) or an emulator. Then connect the phone to the laptop with the **USB tunnel**:
```bash
"$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe" reverse tcp:8000 tcp:8000
```
Server URL in the app: **`http://127.0.0.1:8000`** (the default). Re-run the `adb reverse` command after every re-plug/restart.
- Why not Wi-Fi? Campus Wi-Fi may isolate devices, and the laptop's VPN (ProTUN, `10.2.0.2`) is **not** reachable from the phone. Wi-Fi fallback: `http://<Wi-Fi IPv4 from ipconfig>:8000`, with firewall rule "Snapsort 8000" (already added).
- Debug the app's saved settings/log: `adb shell run-as com.snapsort.app cat shared_prefs/snapsort.xml`

## Log
- 17:35: Started. Environment checked. Started Ollama.
- 17:41: gemma4:12b crashed on load (CUDA error in the cuda_v13 backend). Fixed by forcing `OLLAMA_LLM_LIBRARY=cuda_v12`.
- 17:50: Backend done, 10/10 unit tests pass. Evals 5/5 correct, but latency is 34–77s.
- 17:55: Added `test.py` (user request). Verified on the chat sample.
- 18:05: Android app written (5 Kotlin files). Needs building in Android Studio.
- 18:10: Paused. Resume: (1) decide on model speed (download gemma4:e2b-it-qat / use Claude / bigger GPU), (2) build Android app in Android Studio, (3) end-to-end test. Nothing committed yet.
- Resumed. New requirements: auto-add confident events and notify afterwards; ask first for unclear ones. Backend now returns `decision` + `id`, has `/feedback` and a mock provider (21/21 tests). Android updated (CalendarWriter, ActionReceiver, new notifications). Wrote frontend.md for the iOS coworker. **Still open:** model speed decision (download gemma4:e2b-it-qat?), Android build in Android Studio.
- 20:15: User installed `gemma4:e2b-it-qat`. Evals 5/5, median 8.8 s (8× faster). Now the default. Added a 5xx retry. **Next:** Android build in Android Studio, then phone ↔ laptop end-to-end.
- 22:35: Physical phone (OnePlus Nord CE) connected. "Failed to connect" was the app URL set to the VPN IP 10.2.0.2. Fixed via `adb reverse` + `http://127.0.0.1:8000` (now the app default).
- 23:00: Bug from real phone test: "12–16 Oct 2026" programme became a 1-day event. Fixed in code: `end_date_text/guess` fields, deterministic `split_range()`, multi-day → one all-day event (daily hours in the description), `dates_seen` pre-listing. 29 tests pass. **But gemma4:e2b (2B) only returns 1 of the 2 events on that dense page** (programme OR deadline, varies). Decision: **run the backend on a better laptop with a bigger model** (`gemma4:12b` or larger). Real screenshots for re-testing are in `evals/screenshots/real/` (git-ignored, copy manually).
- Switched default model provider to **OpenRouter** (no local LLM needed): `openrouter_client.py` with strict JSON-schema output, `models` fallback list, `data_collection: deny`, retries on 429/5xx, clear 401/402 errors. 44 tests pass (8 new, fake HTTP). **Needs:** `OPENROUTER_API_KEY` in `backend/.env`, then re-run evals incl. the real CEDARS screenshot.
- OpenRouter live: **7/7 evals pass, median ~9 s** (gemma-4-26b via SiliconFlow). Real CEDARS page now gives BOTH events: programme 12–16 Oct (all-day, auto_add) + deadline 20 Sep (ask). Fixed: schema cleaner was deleting the event's `title` field; eval scorer now matches title+date. API key moved from config.py to backend/.env (git-ignored). **Rotate that key**, it was exposed in chat.
- Backend deployed to **Render: https://gl-hackathon.onrender.com** (6/7 live, median 5.8 s). Fixed: end *time* in end-date field made single-day events 2-day (University Drive regression); messy date headers now parse. Added `GET /auth/check`. 51 tests.
- Teammate's Compose Home is sample-data only and had dropped URL/token/watcher controls, so added a **Settings sheet behind Home's ⋯ button** (server URL, API token, Save & test [health + token check], start/stop watching with permissions, check gallery image). Default server URL = Render. `./gradlew assembleDebug` builds ✅. **Next:** wire Home to real activity data; set API_TOKEN on Render; push.
