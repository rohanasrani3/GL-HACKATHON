# tasks.md: Hackathon build tracker

**Goal (10h):** screenshot an event poster/chat → phone notification "Add '<event>' to calendar?" → tap → calendar opens pre-filled.

**Hackathon scope** (a deliberate subset of [CLAUDE.md](CLAUDE.md) / [skills.md](skills.md)):
- Android only, Kotlin. Watcher = foreground service + `ContentObserver` (not WorkManager).
- No on-device OCR. The phone uploads the image and the backend does triage + extraction in one model call.
- Backend = FastAPI on the laptop. Model = Gemma 3 via Ollama, with a hosted fallback switch (`MODEL_PROVIDER`).
- Calendar write = `Intent.ACTION_INSERT` (no calendar permission; user taps Save, which keeps a human in the loop).
- The policy gate and dedup are simplified to a confidence threshold in the app.
- Phone ↔ laptop over phone hotspot or Tailscale.

Legend: `[x]` done · `[~]` in progress · `[ ]` todo · `[!]` blocked

## Phase 0: Setup
- [x] Environment check: Python 3.12, Java 17, Ollama 0.34, GTX 1650 (4 GB). **No Android SDK on this laptop**, so Android code is written but compiled in Android Studio.
- [~] Start Ollama, pull `gemma3:4b`, time one image
- [ ] Repo scaffold + `.gitignore`

## Phase 1: Backend (`/backend`)
- [ ] `schema.py`: Pydantic models (proposal contract from skills.md §1)
- [ ] `skills/calendar_event/SKILL.md`: prompt
- [ ] `models/`: `ModelClient` interface, Ollama client, hosted fallback
- [ ] `datetime_resolve.py`: deterministic date resolution anchored to `captured_at`
- [ ] `main.py`: FastAPI `POST /analyze`, `GET /health`
- [ ] Unit tests for date resolution
- [ ] Smoke test with a generated poster image

## Phase 2: Evals (`/evals`)
- [ ] `run.py`: run every screenshot in `evals/screenshots` against `/analyze`, compare with `expected/*.json`
- [ ] Synthetic sample screenshots (poster, chat, meme)
- [ ] Team: add 15 real screenshots + expected JSON

## Phase 3: Android (`/android`)
- [ ] Gradle project (Kotlin, minSdk 29)
- [ ] `ScreenshotWatcherService`: foreground service + ContentObserver on MediaStore, filtered to Screenshots
- [ ] `Uploader`: downscale + multipart POST to `/analyze`
- [ ] `Notifier`: "Add to calendar?" notification → `ACTION_INSERT` intent
- [ ] `MainActivity`: server URL field, start/stop, permission requests, activity list
- [ ] Build + install on a real phone (needs Android Studio)

## Phase 4: Demo
- [ ] End-to-end on the real phone and network
- [ ] Pitch slides
- [ ] Backup video (by hour 9)

## Log
- 17:35: Started. Environment checked. Ollama wasn't running, so started `ollama serve`.
