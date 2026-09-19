# later.exe

> Your screenshot folder already knows what you need to do. later.exe acts on it.

later.exe is an agentic AI assistant that lives in your phone's screenshot folder. Each time you take a screenshot, later.exe checks whether it contains something worth acting on, such as an event invite, a flight confirmation, a webinar link or a deadline in a group chat. If it does, later.exe creates the matching calendar entry, so the screenshot doesn't get lost among hundreds of others.

*"later.exe" is a working name.*

---

## The problem

People screenshot things they mean to deal with later:

- A poster for a campus talk
- A WhatsApp message saying "dinner Friday 8pm at Luk Yu"
- A Zoom invite, a ticket confirmation, an exam timetable
- An Instagram story about a pop-up event

Later rarely comes. The screenshot sits in the camera roll with no reminder attached, and the event passes. Copying the details into a calendar by hand takes a few taps each time, and people skip it.

## What later.exe does (v1: Calendar)

1. **Watches** the device's screenshot folder for new images.
2. **Triages** each new screenshot with a quick, cheap check: does it look like it contains an event?
3. **Extracts** structured details: title, date, start and end time, timezone, location, link, organiser and notes.
4. **Resolves ambiguity** using context. "This Friday" is worked out from the screenshot's timestamp, a missing year is inferred, and the timezone comes from the location or the device.
5. **Checks for duplicates** against events already in your calendar.
6. **Acts** according to your autonomy setting:
   - **Suggest:** a notification says "Add 'HKU AI Talk, Tue 24 Sep 6pm' to your calendar?" and you tap once to confirm.
   - **Auto-add:** high-confidence events are added straight away and you get an undo notification.
7. **Links back** by attaching the original screenshot, or a deep link to it, to the calendar event.

Screenshots with nothing to act on, such as memes, code or chat banter, are ignored silently.

### Example

| Screenshot | Result |
|---|---|
| Poster: *"Generative AI in Healthcare, 26 Sept, 4–5:30pm, Main Building LG01"* | Event created on 26 Sep, 16:00–17:30, location "Main Building LG01, HKU" |
| Chat: *"let's do lunch tmrw 1pm?" "ok!"* | Suggestion: "Lunch" tomorrow at 13:00. Confidence is medium, so later.exe asks before adding. |
| Meme | Ignored |

## Roadmap

| Phase | Capability | Output |
|---|---|---|
| **v1** | Events → Calendar | Google Calendar / Apple Calendar / Outlook event |
| **v2** | Receipts → Budget | Expense entry (merchant, amount, currency, category, date) pushed to a budgeting app or sheet |
| **v3** | Forms, links and QR codes → Autofill | Decode the QR or link, open the form and pre-fill it from your profile, then **pause for your review before submitting** |
| Later | More domains | Boarding passes to Wallet, parcel tracking numbers to a tracker, contacts from business cards |

The architecture is designed so that adding a new domain means adding a new **skill** rather than rewriting the agent. See [CLAUDE.md](CLAUDE.md) and [skills.md](skills.md).

## Principles

- **Privacy first.** Screenshots are sensitive. Triage runs on-device where possible. Only screenshots that pass triage are sent for full extraction, and they are not kept after processing. No screenshot is used for training.
- **The user stays in control.** The agent never does anything irreversible without permission. Calendar adds can be undone. Payments and form submissions **always** need explicit confirmation.
- **Silence is the default.** A useful agent only speaks up when something is worth acting on.
- **Confidence-aware.** Every action carries a confidence score. When confidence is low, later.exe asks instead of acting.

## High-level architecture

```
 ┌──────────────┐   new file   ┌──────────────┐  candidate  ┌──────────────────┐
 │ Screenshot   │ ───────────▶ │  Watcher     │ ──────────▶ │  Triage          │
 │ folder       │              │  (OS hooks)  │             │  (on-device/fast)│
 └──────────────┘              └──────────────┘             └────────┬─────────┘
                                                                     │ has_actionable?
                                                                     ▼
                                                            ┌──────────────────┐
                                                            │  Orchestrator    │
                                                            │  agent (router)  │
                                                            └────────┬─────────┘
                                   ┌─────────────────────────────────┼──────────────────────┐
                                   ▼                                 ▼                      ▼
                          ┌────────────────┐               ┌────────────────┐     ┌────────────────┐
                          │ calendar-event │               │ receipt-budget │     │ form-autofill  │
                          │ skill  (v1)    │               │ skill  (v2)    │     │ skill  (v3)    │
                          └───────┬────────┘               └────────────────┘     └────────────────┘
                                  ▼
                        ┌───────────────────┐     ┌──────────────────────┐
                        │ Policy / confirm  │ ──▶ │ Calendar connector   │
                        │ gate + notifier   │     │ (Google/Apple/MS)    │
                        └───────────────────┘     └──────────────────────┘
```

## Platform notes

| | Android | iOS |
|---|---|---|
| Detect new screenshots | `ContentObserver` on `MediaStore.Images` filtered to the `Screenshots` bucket, or `WorkManager` periodic scan | `PHPhotoLibraryChangeObserver` plus the `PHAssetMediaSubtype.photoScreenshot` filter. iOS can't run code when a screenshot is taken, so processing happens on app open, while the app is open, via `BGAppRefreshTask` (timing up to iOS), or from a share extension. |
| Calendar write | `CalendarContract` or the Google Calendar API | `EventKit` |
| On-device OCR | ML Kit Text Recognition | Vision `VNRecognizeTextRequest` |

## Getting started (development)

Hackathon build in progress. See [tasks.md](tasks.md) for status and run instructions.

```
/backend        FastAPI + model clients (Gemma via Ollama, Claude, mock) + calendar-event skill
/android        Kotlin app (screenshot watcher, auto-add / ask notifications)
/ios            Swift app, built from frontend.md
/evals          labelled screenshots, expected outputs, eval runner
```

## Documentation

- [CLAUDE.md](CLAUDE.md) covers agent architecture, design decisions and conventions for contributors, including AI coding agents.
- [skills.md](skills.md) is the skill catalogue: what each skill does, its inputs and outputs, tools and guardrails.
- [frontend.md](frontend.md) is the iOS app spec and the backend API contract (`/health`, `/analyze`, `/feedback`).
- [tasks.md](tasks.md) is the hackathon build tracker and how to run everything.
