# frontend.md: iOS app spec (Swift / SwiftUI)

> **The iOS app is implemented in [`/ios`](ios/README.md)** as a port of the Android app (`/android`): the same later.exe "Relay" UI and the same behaviour. This file is the spec it follows and the contract both apps share with the backend. When you change behaviour, change it here, in `/ios`, and in `/android`.
>
> Background reading (optional): [README.md](README.md) (product), [CLAUDE.md](CLAUDE.md) (architecture and rules). Anything marked *Stretch* is only for when the core checklist in §14 passes.

---

## 0. TL;DR

Snapsort (branded **later.exe** in the app) watches the user's **screenshots**. For each new screenshot the app:

1. Sends the image to our backend: `POST /analyze`.
2. Gets back zero or more **proposals** (calendar events), each with a `decision`:
   - `"auto_add"`: the backend is confident. **Add it to the calendar immediately, then send a notification** "✅ Added to your calendar: …" with an **Undo** button.
   - `"ask"`: the event is unclear. **Send a notification asking first**: "Add '…' to calendar?" with **Add / Edit / Dismiss**. It also appears on Home under **Needs your input**. Only add it if the user says so.
3. Records the outcome in the local activity feed that Home renders, and reports it: `POST /feedback`.

The **backend decides** `auto_add` vs `ask`. The app never re-scores confidence. It just follows `decision`, with one exception: if the app can't auto-add (no full calendar access), it falls back to `ask`.

**Target:** iOS 17+, Swift 5.9+, SwiftUI, async/await, **no third-party dependencies**. The project is generated with XcodeGen from `ios/project.yml`.

---

## 1. Running the backend for development

You don't need the AI model. Use the **mock** mode, which returns canned answers instantly:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
MODEL_PROVIDER=mock .venv/Scripts/python -m uvicorn snapsort.main:app --host 0.0.0.0 --port 8000
```

Mock mode cycles through 3 responses on successive `/analyze` calls, whatever image you send:

| Call # | Result |
|---|---|
| 1, 4, 7… | 1 proposal, `decision: "auto_add"` ("Generative AI in Healthcare (talk)", 3 days from now 16:00–17:30) |
| 2, 5, 8… | 1 proposal, `decision: "ask"` ("Dinner with Sam", this coming Friday 19:30) |
| 3, 6, 9… | 0 proposals, `skipped_reason: "meme"` |

With the real model (`MODEL_PROVIDER=openrouter`, hosted), one screenshot typically takes **~3–10 s**, longer if OpenRouter falls back to another provider or the network is slow. **All networking must tolerate a 240 s timeout**, and the UI must show progress.

**Base URL:** user-configurable in Settings, e.g. `http://192.168.1.23:8000` (laptop on the same Wi-Fi or hotspot) or `http://laptop.tailnet.ts.net:8000` (Tailscale). Default: `http://localhost:8000` (works in the iOS Simulator on the same Mac).

---

## 2. Backend API contract (v1)

All endpoints are plain HTTP + JSON, except `/analyze`, which takes a multipart upload.

**Auth:** if the user has set an API token in Settings, send it on **every** request as the header `X-Api-Token: <token>`. If it's empty, omit the header.

### 2.1 `GET /health`

Use this for the "Test connection" button and to read the policy thresholds (display only).

```json
{ "ok": true, "api_version": 1, "model": "openrouter:google/gemma-4-26b-a4b-it", "auto_add_threshold": 0.8, "ask_threshold": 0.5 }
```

If `api_version != 1`, show a warning: "Backend version mismatch".

### 2.2 `POST /analyze`

`Content-Type: multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | ✅ | JPEG, longest side ≤ 1600 px, quality 0.85, **no EXIF/GPS** (see §5). Filename: `screenshot.jpg`, part type `image/jpeg`. Max 15 MB. |
| `captured_at` | string | ✅ | When the screenshot was **taken** (`PHAsset.creationDate`), ISO 8601 **with offset**, e.g. `2026-09-19T14:02:11+08:00`. **Do not send upload time**: relative dates like "tomorrow" are resolved against this. |
| `timezone` | string | ✅ | IANA id: `TimeZone.current.identifier`, e.g. `Asia/Hong_Kong` |
| `locale` | string | ✅ | BCP-47: `Locale.current.identifier.replacingOccurrences(of: "_", with: "-")`, e.g. `en-HK`. Decides whether 3/10 means 3 Oct or 10 Mar. |

**Response 200:**

```json
{
  "proposals": [
    {
      "id": "3f9a1c0b7d2e",
      "action": "calendar.create",
      "decision": "auto_add",
      "payload": {
        "title": "Generative AI in Healthcare (talk)",
        "start": "2026-09-25T16:00:00+08:00",
        "end": "2026-09-25T17:30:00+08:00",
        "all_day": false,
        "timezone": "Asia/Hong_Kong",
        "location": { "name": "Main Building LG01, HKU", "online_url": null },
        "description": "Public lecture by Dr. Mei Chan"
      },
      "confidence": 0.95,
      "evidence": "Fri 25 Sept · 4:00 – 5:30pm",
      "notes": ["parser_and_model_agree"]
    }
  ],
  "genre": "poster",
  "skipped_reason": null,
  "model": "openrouter:google/gemma-4-26b-a4b-it",
  "latency_ms": 8759
}
```

Field rules:
- `proposals` may be empty. Then `skipped_reason` is a short string (`"not_actionable"`, `"sensitive_content"`, `"meme"`, `"no_confident_future_events"`, …). Show it only in the Activity log, **never as a notification**.
- `id`: a stable 12-char hash of title + start. The same poster screenshotted twice gives the **same id**. Use it for dedup (§9) and as the notification identifier.
- `decision`: `"auto_add"` or `"ask"`. Treat any unknown value as `"ask"`.
- **Timed events** (`all_day: false`): `start`/`end` are ISO 8601 with offset. Parse with `ISO8601DateFormatter` (`.withInternetDateTime`).
- **All-day events** (`all_day: true`): `start` is `YYYY-MM-DD` and `end` is the **next** day `YYYY-MM-DD` (exclusive). Parse them as dates in the device's time zone.
- `location.name`, `location.online_url` and `description` can each be `null`.
- `notes` and `evidence` are for debugging. Show `evidence` in the Activity detail view.
- Ignore unknown fields: the backend may add more.

**Errors:**

| Status | Meaning | App behaviour |
|---|---|---|
| 400 | Empty file or bad `captured_at` | Bug: log it, don't retry |
| 401 | Bad or missing token | Notification + Settings banner "Check API token" |
| 413 | Image too large | Re-encode smaller, retry once |
| 422 | Missing form field | Bug: log it |
| 502 | Model failed | Retry once after 5 s, then log "❌ Model error" |
| Timeout / no connection | Laptop off or unreachable | Keep the screenshot in the **retry queue** (§9) and retry on the next scan |

### 2.3 `POST /feedback`

Send this after **every** user-visible outcome. Fire-and-forget: ignore failures and never block the UI. It never includes event content.

```json
{ "proposal_id": "3f9a1c0b7d2e", "decision": "auto_add", "outcome": "added", "platform": "ios" }
```

`outcome` ∈ `added` | `dismissed` | `undone` | `edited` | `failed`. The response is `204 No Content`.

| When | outcome |
|---|---|
| `auto_add` written to the calendar | `added` |
| `ask` → user tapped **Add** and the write succeeded | `added` |
| `ask` → user tapped **Dismiss**, or cleared the notification | `dismissed` |
| User tapped **Undo** on an "Added" notification | `undone` |
| User opened **Edit** and saved in the event editor | `edited` |
| Calendar write failed | `failed` |

### 2.4 Swift models (copy these)

```swift
struct HealthResponse: Codable {
    let ok: Bool
    let apiVersion: Int
    let model: String
    let autoAddThreshold: Double
    let askThreshold: Double
}

struct AnalyzeResponse: Codable {
    let proposals: [Proposal]
    let genre: String?
    let skippedReason: String?
    let model: String
    let latencyMs: Int
}

struct Proposal: Codable, Identifiable, Hashable {
    let id: String
    let action: String
    let decision: String          // "auto_add" | "ask"
    let payload: CalendarPayload
    let confidence: Double
    let evidence: String
    let notes: [String]?

    var isAutoAdd: Bool { decision == "auto_add" }
}

struct CalendarPayload: Codable, Hashable {
    let title: String
    let start: String             // ISO 8601 with offset, or YYYY-MM-DD when allDay
    let end: String
    let allDay: Bool
    let timezone: String
    let location: EventLocation
    let description: String?
}

struct EventLocation: Codable, Hashable {
    let name: String?
    let onlineUrl: String?
}

struct FeedbackRequest: Codable {
    let proposalId: String
    let decision: String
    let outcome: String           // added | dismissed | undone | edited | failed
    let platform = "ios"
}
```

Use `JSONDecoder.keyDecodingStrategy = .convertFromSnakeCase` and `JSONEncoder.keyEncodingStrategy = .convertToSnakeCase`.

### 2.5 Multipart upload (URLSession, no dependencies)

```swift
func analyze(jpeg: Data, capturedAt: Date) async throws -> AnalyzeResponse {
    let boundary = "snapsort-\(UUID().uuidString)"
    var req = URLRequest(url: baseURL.appendingPathComponent("analyze"))
    req.httpMethod = "POST"
    req.timeoutInterval = 240
    req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
    if !token.isEmpty { req.setValue(token, forHTTPHeaderField: "X-Api-Token") }

    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    iso.timeZone = .current                       // keeps the local offset, e.g. +08:00
    let fields = [
        "captured_at": iso.string(from: capturedAt),
        "timezone": TimeZone.current.identifier,
        "locale": Locale.current.identifier.replacingOccurrences(of: "_", with: "-"),
    ]

    var body = Data()
    for (k, v) in fields {
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(k)\"\r\n\r\n\(v)\r\n".data(using: .utf8)!)
    }
    body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"screenshot.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
    body.append(jpeg)
    body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

    let (data, resp) = try await URLSession.shared.upload(for: req, from: body)
    guard let http = resp as? HTTPURLResponse else { throw APIError.noResponse }
    guard http.statusCode == 200 else { throw APIError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "") }
    let dec = JSONDecoder(); dec.keyDecodingStrategy = .convertFromSnakeCase
    return try dec.decode(AnalyzeResponse.self, from: data)
}
```

---

## 3. Decision handling (core logic)

All entry points (scan, manual pick, App Intents, Home, notification buttons) go through one class, `Agent` (`ios/Snapsort/Services/Agent.swift`). On Android the same logic lives in `ScreenshotWatcherService.process`, `ActionReceiver` and `MainActivity`.

`Agent.process(jpeg, capturedAt, sourceId)`:

```
processingSince = now                                  (Home shows "Reading screenshot… 12s")
result = POST /analyze
  on error → log "❌ …", lastError = message (Home shows OFFLINE), feed FAILED, "couldn't reach" notification,
             screenshot stays in the retry queue
lastError = nil
if no proposals → feed SKIPPED(skipped_reason), log "⏭ Skipped"   (never a notification)
for each proposal:
    if proposal.id already handled                     → skip (dedup)
    if decision == "auto_add" AND calendar == .fullAccess AND CalendarService.insert succeeds:
        notify ADDED; feed EXECUTED(eventId); feedback(added); log "✅ Added"
    else:
        notify ASK;   feed NEEDS_ATTENTION;               log "❓ Asked"
processingSince = nil
```

User actions:

| Where | Action | What happens |
|---|---|---|
| ADDED notification, or Home **Undo** | Undo | Delete the event, remove the notification, feed UNDONE, feedback `undone` |
| ADDED notification | **Open** (foreground) | Open Calendar at the event's start: `calshow:<start.timeIntervalSinceReferenceDate>` |
| ASK notification, or Home **Review → Add** | Add | `CalendarService.insert`. On success, **post an ADDED notification** (same id, so it replaces ASK), feed EXECUTED, feedback `added`. Without full access: from Home, open the pre-filled editor; from the notification, post "Couldn't add" (tap → editor) and send feedback `failed`. |
| ASK notification, or Home **Review → Edit** | Edit | Present `EKEventEditViewController` pre-filled. If saved: feed EXECUTED, feedback `edited`. |
| ASK notification (**Dismiss**, or cleared), or Home **Review → Dismiss** | Dismiss | Feed DISMISSED, feedback `dismissed` |

**Rule: after anything is added to the calendar, the user always gets a notification saying so, with Undo.**

---

## 4. Getting screenshots on iOS

iOS has **no** API to run code when a screenshot is taken, and **no** "screenshots folder" permission. Android uses a foreground service that reacts instantly; iOS combines these paths (all implemented):

1. **Scan on foreground.** When the app becomes active, fetch screenshots created after the cursor (`mediaSubtypes & .photoScreenshot`), oldest first. On the first start, set the cursor to now so the backlog is **not** processed. Found screenshots go into the **retry queue** first, then are processed sequentially. A failure keeps the screenshot queued, and it's dropped after 3 attempts.
2. **Live while open.** `PHPhotoLibraryChangeObserver`, debounced 1.5 s, runs the same scan. Demo: take a screenshot, switch back to later.exe, and the notification appears.
3. **Background refresh.** `BGAppRefreshTask` `com.snapsort.refresh`, rescheduled for +15 min after every run. At most **1 screenshot per run**, because the budget is about 30 s. iOS decides when it actually runs.
4. **App Intents (instant capture).**
   - **"Snapsort a screenshot"** takes an image. The user builds a Shortcut **Take Screenshot → Snapsort a screenshot** and binds it to **Back Tap** (Settings → Accessibility → Touch → Back Tap) or the **Action Button**. One gesture captures and processes without opening the app. The same intent receives images from the **share sheet** via Shortcuts, which matches Android's share-to-Snapsort.
   - **"Check latest screenshot"** processes the newest screenshot. It's exposed through `AppShortcutsProvider` (Siri, Spotlight, Shortcuts).
5. **Manual pick.** Settings → *Test with an image from Photos* (`PhotosPicker`). `captured_at` = now.
6. *Stretch:* a dedicated Share Extension target (needs App Groups and signing). The intent above already covers the share sheet.

**Photos permission:** `.readWrite`. `.limited` is treated as no access, and Settings says so.

---

## 5. Image preparation (privacy rules, non-negotiable)

- Request the image with `PHImageManager.requestImage(for:targetSize:contentMode:.aspectFit, options:)`, with `targetSize` longest side 1600 px, `deliveryMode = .highQualityFormat` and `isNetworkAccessAllowed = true`.
- Encode it with `UIImage.jpegData(compressionQuality: 0.85)`. Re-encoding from `UIImage` drops EXIF/GPS. **Never upload the original asset data.**
- Never write screenshots to disk outside the app's temp directory, and delete them after upload.
- Never log image data or event titles to remote services. The local Activity log is fine.

---

## 6. Calendar (EventKit)

- Request **full access**: `try await EKEventStore().requestFullAccessToEvents()` (iOS 17). Full access is needed for Undo, which reads the event back and removes it.
  - `.fullAccess` → auto-add allowed.
  - `.writeOnly` or `.denied` → **never auto-add**. Every proposal becomes ASK, and ASK → Add opens `EKEventEditViewController` instead of writing silently. Show a Settings banner: "Grant full calendar access to let Snapsort add events automatically."
- Keep **one shared `EKEventStore`** for the app's lifetime.
- `add(proposal) -> String?` (returns `eventIdentifier`):
  ```swift
  let e = EKEvent(eventStore: store)
  e.calendar = store.defaultCalendarForNewEvents
  e.title = p.payload.title
  e.location = p.payload.location.name ?? p.payload.location.onlineUrl
  e.notes = [p.payload.description, p.payload.location.onlineUrl, "Added by Snapsort from a screenshot"]
      .compactMap { $0 }.joined(separator: "\n")
  if let url = p.payload.location.onlineUrl.flatMap(URL.init) { e.url = url }
  if p.payload.allDay {
      e.isAllDay = true
      e.startDate = <start as local-midnight Date>
      e.endDate   = e.startDate          // EventKit all-day end is inclusive: same day
  } else {
      e.timeZone = TimeZone(identifier: p.payload.timezone)
      e.startDate = <ISO8601 parse of start>
      e.endDate   = <ISO8601 parse of end>
  }
  try store.save(e, span: .thisEvent, commit: true)
  return e.eventIdentifier
  ```
- `remove(eventId)`: `store.event(withIdentifier:)`, then `store.remove(_, span: .thisEvent, commit: true)`.
- Persist `proposal.id → eventIdentifier` so Undo still works after the app is relaunched.

---

## 7. Notifications (UserNotifications)

Request `[.alert, .sound, .badge]` authorization during onboarding.

Register these categories at launch, before any notification is posted:

| Category id | Actions (id → title, options) |
|---|---|
| `ADDED` | `UNDO` → "Undo" `[.destructive]` · `OPEN` → "Open" `[.foreground]` |
| `ASK` | `ADD` → "Add" `[]` · `EDIT` → "Edit" `[.foreground]` · `DISMISS` → "Dismiss" `[.destructive]` |

Set `customDismissAction` on `ASK`, so that clearing the notification counts as Dismiss.

Notification content:

| Type | Title | Body |
|---|---|---|
| ADDED | `✅ Added to your calendar: {title}` | `{Fri 25 Sep, 16:00} · {location}` |
| ASK | `Add “{title}” to calendar?` | `{Fri 25 Sep, 19:30} · {location}` + newline + `Not 100% sure about this one. Add it?` |
| Couldn't add | `Couldn't add “{title}” automatically` | `Tap to add it in Calendar` (tap → app → event editor) |
| Processing | *No notification on iOS.* Show an in-app progress row instead. | |
| Server unreachable | `Snapsort couldn't reach the server` | `{error}`. At most one per scan. |

- Date formatting: timed `EEE d MMM, HH:mm`, all-day `EEE d MMM (all day)`, in the device locale.
- Omit ` · {location}` when the location is null.
- **Identifier:** use the `proposal.id`, so an ADDED notification *replaces* the ASK notification for the same event after the user taps Add.
- **userInfo** (plist types only): `["proposal": <proposal JSON String>, "eventId": <String?>]`.
- Handle actions in `UNUserNotificationCenterDelegate.userNotificationCenter(_:didReceive:)`. Non-foreground actions (Add, Undo, Dismiss) run in the background, so do the EventKit work and the feedback call there and call the completion handler at the end.
- Show notifications even while the app is in the foreground: `willPresent` returns `[.banner, .sound, .list]`.

---

## 8. Screens (SwiftUI), later.exe "Relay"

Same design as the Android Compose app (`android/.../ui/home/HomeScreen.kt`, `ui/theme/*`). Dark only.

**Tokens** (`ios/Snapsort/UI/Theme.swift`):

| Token | Hex | Use |
|---|---|---|
| background | `#0D100B` | Screen background |
| surface | `#171B15` | Status strip, cards, rows |
| textPrimary | `#F1F1E8` | Titles; Review button fill |
| textMuted | `#A2AA9B` | Supporting text, labels |
| border | `#2B3228` | 1 pt borders, dividers, INACTIVE accent |
| green | `#2DFF60` | LIVE/WORKING, EXECUTED, Undo |
| lime | `#80ED28` | Brand mark, ".exe" |
| amber | `#E7C17D` | NEEDS INPUT, FAILED, RETRYING |

Type: headline 26 semibold · titleLarge 20 semibold · titleMedium 17 semibold · bodyLarge 16 · bodyMedium 14 · labelLarge mono 13 semibold (+0.5 tracking) · labelMedium mono 11 medium (+0.8 tracking). Monospace is only for status labels, timestamps and the wordmark. The horizontal gutter is 20 pt.

**A. Home** (top to bottom):
1. **Brand header:** geometric mark (an L stroke plus a square, lime) + "later" + ".exe" (lime), and a "•••" button that opens Settings.
2. **Agent status strip:** a surface row with a 3 pt accent bar. Primary text + "● LABEL", secondary text below.
   - Priority order: processing → `WORKING` "Reading screenshot"; last error → `RETRYING` "Server unavailable" + the error; scanning on → `LIVE` "Watching screenshots" / "Last scan · 2 min ago"; else `INACTIVE` "Screenshot monitoring stopped" / "Open Settings to resume".
3. **Summary:** "Nothing needs you." / "Just 1 thing for you." / "Just N things for you." + "The agent is handling things quietly." / "…the rest."
4. **Processing row** while uploading: "· READING  Screenshot detected / Understanding action…  12s" (live seconds).
5. **NEEDS YOUR INPUT  0N:** a card per `ask` item: "! NEEDS INPUT" + timestamp, title, summary, event time, destination chip, and a full-width **Review details →** button that opens the Review sheet.
6. **RECENT ACTIVITY  TODAY:** newest first. Each row has a status label (✓ EXECUTED, ↩ UNDONE, × DISMISSED, SKIPPED, ! FAILED), timestamp, title, summary, event time, destination chip, inline **Undo** (only if EXECUTED and an event id exists), and a 1 pt divider.
- Pull to refresh runs a scan. Home re-renders every second so the relative times stay live.
- Home is built from the activity feed by `HomeUiState.make` (iOS), the same mapping as `Store.toHomeUiState` (Android).

**B. Review sheet:** title, when, where, link, details, confidence, the evidence quote and "why it asked" (notes), plus **Add to calendar / Edit before adding / Dismiss**.

**C. Settings** (from "•••"): back; server URL + API token + **Save & test connection** (shows the model name or the error); Watcher: **Start watching** (asks for Photos, Calendar and Notifications) / **Stop watching** / **Scan now**; **Test with an image from Photos**; permission status rows + Open iOS Settings; Back Tap instructions; activity log (last 30 lines); Reset scan position; Clear activity.

First launch requests the three permissions and starts watching (Android does this on "Start watching").

---

## 9. Local persistence

One JSON file, `Application Support/snapsort-state.json` (`Store.swift`):

| Field | Purpose |
|---|---|
| `serverURL`, `apiToken` | Settings. Default `http://localhost:8000` |
| `scanningEnabled`, `onboarded` | Watcher on/off; first-launch flow done |
| `scanCursor` | Screenshot cursor (§4), set to now on first start |
| `pending` | Retry queue: PHAsset id, original capture time, attempts (max 3) |
| `handled` | proposal id → EventKit event id. Dedup: the same event from a second screenshot is ignored. Kept after Undo. |
| `activities` | Home feed, last 30. Each record keeps its proposal, so Home can confirm or undo later. |
| `log`, `lastError`, `lastScanAt` | Settings log; OFFLINE status; "Last scan" |

Calendar dedup also survives a crash between the write and the save: every event's `url` is `snapsort://proposal/<id>`, and `insert` looks for it first (Android uses `CUSTOM_APP_URI` the same way).

Store the API token in the **Keychain** if time allows.

---

## 10. Info.plist & capabilities

Also `NSCalendarsUsageDescription` (same text as full access).

| Key | Value |
|---|---|
| `NSPhotoLibraryUsageDescription` | "Snapsort reads your new screenshots to find events. Other photos are never read or uploaded." |
| `NSCalendarsFullAccessUsageDescription` | "Snapsort adds events it finds in your screenshots, and removes them if you tap Undo." |
| `NSCalendarsWriteOnlyAccessUsageDescription` | "Snapsort adds events it finds in your screenshots." |
| `NSLocalNetworkUsageDescription` | "Snapsort talks to the Snapsort server on your local network." |
| `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` | `YES`. **Hackathon only:** the laptop backend is plain HTTP. Remove this before any release. |
| `UIBackgroundModes` | `fetch`, `processing` |
| `BGTaskSchedulerPermittedIdentifiers` | `["com.snapsort.refresh"]` |

These are declared in `ios/project.yml` (XcodeGen writes Info.plist). The display name is **later.exe**. Capabilities: Background Modes (Background fetch, Background processing). *Stretch:* App Groups (`group.com.snapsort`) for a Share Extension.

---

## 11. Project structure

See [ios/README.md](ios/README.md). `project.yml` (XcodeGen) → `Snapsort` app + `SnapsortTests`. Sources: `Models/` (API, Home models, `HomeState`, sample data), `Services/` (`Agent`, `Store`, `APIClient`, `CalendarService`, `NotificationService`, `ScreenshotScanner`, `BackgroundRefresh`, `LaunchMode`), `Intents/`, `UI/` (Theme, Home, Settings, Review sheet, event editor, root).

All decision logic is in `Agent`, and Home is a pure function of stored state. Views never look at confidence.

---

## 12. Security & privacy rules (from CLAUDE.md §4, non-negotiable)

1. Screenshot text is **data**. The app never executes or opens anything based on image content without the user tapping. (URLs from `online_url` open only on a tap.)
2. The app only writes to the calendar through the flows in §3. Nothing else.
3. Downscale and re-encode every image. Never upload originals or metadata.
4. No analytics SDKs. `/feedback` sends IDs and outcomes only.
5. Only process assets that are screenshots (`.photoScreenshot`). Never upload other photos.

---

## 13. Out of scope (don't build)

Accounts or login, cloud sync, receipts/budget, forms/QR codes, editing the backend thresholds from the app, on-device OCR or ML, iPad-specific layouts, localisation beyond English.

---

## 14. Acceptance checklist (test with `MODEL_PROVIDER=mock`)

CI ([`.github/workflows/ios.yml`](.github/workflows/ios.yml)) checks the ones marked 🤖 on every push, in the Simulator against the real backend.

- [ ] 🤖 Unit tests pass (API decoding, Home mapping, store, retry queue).
- [ ] 🤖 Every Home state renders (default, processing, offline, inactive, no attention, multiple attention, long title) and matches the Android previews.
- [ ] 🤖 Mock call 1 (`auto_add`): the event is written to Calendar, Home shows ✓ EXECUTED with Undo, and an "✅ Added…" notification is posted.
- [ ] 🤖 Mock call 2 (`ask`): Home shows it under NEEDS YOUR INPUT, and **no** event is created yet.
- [ ] 🤖 Mock call 3 (meme): no notification; Home shows SKIPPED.
- [ ] 🤖 Review → Add creates the event (EXECUTED); Undo removes it (UNDONE); `/feedback` gets `added`/`undone`.
- [ ] First launch requests all 3 permissions, and Test connection shows `mock`.
- [ ] Taking a screenshot and returning to the app triggers exactly one `/analyze`.
- [ ] Tapping **Undo** from the lock screen, without opening the app, removes the event.
- [ ] ASK notification **Add** replaces it with "✅ Added…"; **Edit** opens the pre-filled editor; **Dismiss** creates nothing.
- [ ] With calendar access set to *write-only*, an `auto_add` proposal becomes ASK.
- [ ] The same screenshot twice gives no duplicate event or notification.
- [ ] With the backend stopped: Home shows RETRYING, and the screenshot is processed after the backend restarts and the app is reopened.
- [ ] Back Tap shortcut (Take Screenshot → Snapsort a screenshot) adds an event without opening the app.
- [ ] With the real model, the processing row counts seconds and nothing times out before 240 s.

---

## 15. Parity with Android (`/android`)

| Behaviour | Android | iOS |
|---|---|---|
| Home / Settings UI | Compose, Relay theme | SwiftUI, same tokens and layout |
| Detect screenshot | Foreground service, instant | Scan on open, while open, background refresh; **Back Tap / Action Button via App Intent** for instant |
| Share a screenshot to the app | Share target | Shortcuts share sheet → "Snapsort a screenshot" |
| Progress | "Reading your screenshot…" notification + Home row | Home row (no progress notification) |
| `auto_add` | CalendarContract → "✅ Added" + Undo/Open | EventKit → "✅ Added" + Undo/Open |
| `ask` | Notification Add/Edit/Dismiss + Home Review | Same; Review opens a detail sheet |
| No calendar permission | Falls back to ask + calendar editor | Same (`EKEventEditViewController`) |
| Retry queue / dedup | Pending screenshots, `CUSTOM_APP_URI` marker | Pending PHAssets, `snapsort://proposal/<id>` event URL |
| Feedback | `POST /feedback`, `platform: android` | `POST /feedback`, `platform: ios` |
