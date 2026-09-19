# tasks.md: Hackathon build tracker

**Goal (10h):** screenshot an event poster/chat → phone notification "Add '<event>' to calendar?" → tap → calendar opens pre-filled.

**Hackathon scope** (a deliberate subset of [CLAUDE.md](CLAUDE.md) / [skills.md](skills.md)):
- Android only, Kotlin. Watcher = foreground service + `ContentObserver` (not WorkManager).
- No on-device OCR. The phone uploads the image and the backend does triage + extraction in one model call.
- Backend = FastAPI on the laptop. Model = Gemma 4 via Ollama, with a hosted fallback switch (`MODEL_PROVIDER=claude`).
- Calendar write = `Intent.ACTION_INSERT` (no calendar permission; user taps Save, which keeps a human in the loop).
- The policy gate is simplified: backend drops confidence < 0.3, app shows ≥ 0.5.
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
- [x] Unit tests: 10/10 passing
- [!] **Latency: 34–77s per screenshot** with gemma4:12b (only 8/49 layers fit in 4 GB VRAM). Options:
  1. Pull `gemma4:e2b-it-qat` (4.3 GB) → should fit mostly on GPU. **Needs approval to download.**
  2. `MODEL_PROVIDER=claude` for the live demo (needs an API key).
  3. Run the backend on a teammate's laptop with a bigger GPU.

## Phase 2: Evals (`/evals`)
- [x] `make_samples.py`: 5 synthetic screenshots (poster, chat, ticket, meme, injection)
- [x] `run.py`: scores each against `expected/*.json`
- [x] Result with gemma4:12b: **5/5 correct**, including ignoring the prompt-injection image
- [ ] Team: add 15 real screenshots to `evals/screenshots/real/` + expected JSON

## Phase 3: Android (`/android`)
- [x] Gradle project (Kotlin, minSdk 29, targetSdk 35, no XML layouts)
- [x] `ScreenshotWatcherService`: foreground service + debounced ContentObserver, screenshots-only filter, skips backlog
- [x] `Uploader`: downscale → JPEG → multipart POST with `captured_at`, timezone, locale
- [x] `Notifier`: "Reading your screenshot…" progress + "Add '…' to calendar?" with Add → `ACTION_INSERT`
- [x] `MainActivity`: server URL, test connection, start/stop, pick-from-gallery test, share-to-Snapsort, activity log
- [ ] **Build + install on a real phone in Android Studio** (not compiled yet; no SDK on this laptop)

## Phase 4: Demo
- [ ] End-to-end on the real phone and network
- [ ] Pitch slides
- [ ] Backup video (by hour 9)

## How to run

**Backend (laptop):**
```bash
# 1. Model server (GTX 1650 needs the CUDA 12 backend)
OLLAMA_LLM_LIBRARY=cuda_v12 ollama serve
# 2. API
cd backend
.venv/Scripts/python -m uvicorn snapsort.main:app --host 0.0.0.0 --port 8000
# 3. Try a picture
.venv/Scripts/python test.py
# 4. Evals
.venv/Scripts/python ../evals/run.py
```

**Android:** open `/android` in Android Studio → let it sync (it'll offer to create the Gradle wrapper) → Run on your phone → enter `http://<laptop IP>:8000` → *Save & test connection* → *Start watching*. The laptop IP comes from `ipconfig` on the hotspot or Tailscale interface. Allow port 8000 through Windows Firewall.

## Log
- 17:35: Started. Environment checked. Started Ollama.
- 17:41: gemma4:12b crashed on load (CUDA error in the cuda_v13 backend). Fixed by forcing `OLLAMA_LLM_LIBRARY=cuda_v12`.
- 17:50: Backend done, 10/10 unit tests pass. Evals 5/5 correct, but latency is 34–77s.
- 17:55: Added `test.py` (user request). Verified on the chat sample.
- 18:05: Android app written (5 Kotlin files). Needs building in Android Studio.
