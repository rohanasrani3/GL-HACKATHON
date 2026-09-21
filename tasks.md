# tasks.md: Hackathon build tracker

**Goal (10h):** screenshot an event → confident events are **added automatically** and the user gets "✅ Added … [Undo]"; unclear ones get "Add '<event>' to calendar? [Add / Edit / Dismiss]" first.

**Hackathon scope** (a deliberate subset of [CLAUDE.md](CLAUDE.md) / [skills.md](skills.md)):
- Android only, Kotlin. Watcher = foreground service + `ContentObserver` (not WorkManager).
- No on-device OCR. The phone uploads the image and the backend does triage + extraction in one model call.
- Backend = FastAPI on the laptop. **Model = hosted via OpenRouter** (`google/gemma-4-26b-a4b-it`, fallback `google/gemini-2.5-flash-lite`). Local Ollama, Claude and mock remain selectable with `MODEL_PROVIDER`.
- **Policy gate lives in the backend** so Android and iOS behave the same: each proposal carries `decision` = `auto_add` (confidence ≥ 0.6) or `ask` (0.5–0.6). Below 0.5 is dropped. Signals like `no_time_all_day` reduce confidence rather than forcing an ask.
- Calendar write: `auto_add` writes directly (Android CalendarContract / iOS EventKit), then notifies with **Undo**. `ask` waits for **Add**. Without calendar permission everything falls back to `ask` + the calendar app's editor.
- iOS app: SwiftUI port of the Android app in `/ios`, spec in [frontend.md](frontend.md), built and tested in CI on a GitHub macOS runner.
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
- [x] Unit + API tests: **121 passing** (`cd backend && pytest`)
- [x] **Latency fixed:** default is now hosted OpenRouter `google/gemma-4-26b-a4b-it` → **~9 s median**. Local fallback: `MODEL_PROVIDER=ollama` with a **vision** model (`gemma4:12b`); `MODEL_PROVIDER=claude` also works.
- [x] Ollama client retries once on 5xx (model-loading race on first request)

## Phase 2: Evals (`/evals`)
- [x] `make_samples.py`: 5 synthetic screenshots (poster, chat, ticket, meme, injection)
- [x] `run.py`: scores each against `expected/*.json`
- [x] gemma4:12b: **5/5 correct**, median 72 s
- [x] gemma4:e2b-it-qat: **5/5 correct**, median 8.8 s ← current default
- [x] Form evals: `synthetic_form_poster` (QR → Google Form) and `synthetic_generic_form` (QR → plain `<form>`) now have expected JSON; `run.py` scores `forms` as well as `proposals`
- [ ] Team: add 15 real screenshots to `evals/screenshots/real/` + expected JSON

## Phase 3: Android (`/android`)
- [x] Gradle project (Kotlin, minSdk 29, targetSdk 35, no XML layouts)
- [x] `ScreenshotWatcherService`: foreground service + debounced ContentObserver, screenshots-only filter, skips backlog
- [x] `Uploader`: downscale → JPEG → multipart POST with `captured_at`, timezone, locale
- [x] `Notifier`: "Reading your screenshot…" progress; **ADDED** ("✅ Added…" + Undo/Open) and **ASK** ("Add…?" + Add/Edit/Dismiss)
- [x] `CalendarWriter`: direct insert into the primary calendar + delete for Undo
- [x] `ActionReceiver`: Add / Undo / Dismiss buttons + `/feedback` (no activity trampolines, Android 12+ safe)
- [x] `MainActivity`: Compose Home (live activity feed) + Settings sheet behind ⋯ — server URL, test connection, start/stop, pick-from-gallery, share-to-later.exe, activity log
- [x] **Build + install on a real phone** (OnePlus Nord CE). `./gradlew assembleDebug` builds; end-to-end verified over `adb reverse`.

## Phase 3b: iOS (`/ios`)
- [x] Spec written: [frontend.md](frontend.md) (API contract, Swift models, decision logic, EventKit, notifications, Relay screens, acceptance checklist)
- [x] SwiftUI port of the Android app in `/ios`: Relay Home + Settings + Review sheet, EventKit auto-add/Undo, ASK/ADDED notifications, retry queue, background refresh, App Intents for Back Tap / share sheet ([ios/README.md](ios/README.md))
- [~] CI on a GitHub macOS runner (`.github/workflows/ios.yml`): build, unit tests, screenshots, end-to-end vs `MODEL_PROVIDER=mock`
- [ ] Manual checks on a real iPhone (frontend.md §14 items without 🤖): needs a Mac + Xcode to install
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
The app's **default** server URL is the deployed Render backend, so it works with no laptop. For a laptop backend, set it to **`http://127.0.0.1:8000`** in Settings and re-run `adb reverse` after every re-plug/restart.
- Why not Wi-Fi? Campus Wi-Fi may isolate devices, and the laptop's VPN (ProTUN, `10.2.0.2`) is **not** reachable from the phone. Wi-Fi fallback: `http://<Wi-Fi IPv4 from ipconfig>:8000`, with firewall rule "later.exe 8000" (already added).
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
- **Cleanup pass.** Removed verified-dead code (`resolve_google_form` — an unreferenced fetcher with no SSRF guards; `looks_like_form`; `Store.updateActivity`; `Profile.known/clear/set`; `HomeScreen.onItemClick`; `Proposal.confidence`, which was parsed with `getDouble` and would have thrown if the key ever went missing). Each fetched link is now parsed **once** instead of twice (`formdetect.read_page`) — verified 8 → 4 BeautifulSoup parses for a 4-link screenshot with byte-identical output. Dropped the vendored `.agents/` skill collection (103 files, referenced by nothing) and the resolved `.scratch/` tickets. Added `backend/pyproject.toml` so bare `pytest` works and stops collecting the interactive `test.py`. Robolectric 4.14.1 → 4.16, which fixes the `Unsupported class file major version 69` failure on JDK 25 — **7 of 8 Android unit tests now pass**.
- **Known failing test:** `ScreenshotRetryTest.failedScreenshotIsRetriedAfterWatcherRestartWithOriginalCaptureTime`. Pre-existing — it fails identically at commit `0f48e14` with the same Robolectric version, so the cleanup did not cause it. It is the only test that drives the real service through `Dispatchers.IO`, and Robolectric is not thread-safe, so the retry never reaches MockWebServer within 5 s. The retry logic itself *is* covered, on the test thread, by `retryAfterPartialSuccessDoesNotDuplicateCalendarEntries`, which passes. Fixing it properly means injecting a test dispatcher into `ScreenshotWatcherService` — a product change for a test-only reason, so it is being left as a decision rather than done quietly.
- **Still open:** rotate the OpenRouter key (see the note above); `AUTO_ADD_THRESHOLD` is 0.6 in code but Render may still run older code — redeploy after pushing, since `zxing-cpp`, `beautifulsoup4` and the form/link modules need a rebuild there.
