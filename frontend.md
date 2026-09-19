# frontend.md: iOS app spec (Swift / SwiftUI)

> **For the coding agent (OpenAI Codex or similar) building the iPhone app.** This file is self-contained. It has everything the iOS app must do and every backend call it must make. Build exactly this. Anything marked *Stretch* is only for when the core checklist in §14 passes.
>
> Background reading (optional): [README.md](README.md) (product), [CLAUDE.md](CLAUDE.md) (architecture and rules). The Android app in `/android` implements the same behaviour in Kotlin and can be used as a reference.

---

## 0. TL;DR

Snapsort watches the user's **screenshots**. For each new screenshot the app:

1. Sends the image to our backend: `POST /analyze`.
2. Gets back zero or more **proposals** (calendar events), each with a `decision`:
   - `"auto_add"`: the backend is confident. **Add it to the calendar immediately, then send a notification** "✅ Added to your calendar: …" with an **Undo** button.
   - `"ask"`: the event is unclear. **Send a notification asking first**: "Add '…' to calendar?" with **Add / Edit / Dismiss**. Only add if the user taps Add.
3. Reports what the user did: `POST /feedback`.

The **backend decides** `auto_add` vs `ask`. The app never re-scores confidence. It just follows `decision`, with one exception: if the app can't auto-add (no full calendar access), it falls back to `ask`.

**Target:** iOS 17+, Swift 5.9+, SwiftUI, async/await, **no third-party dependencies**.

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

`ProposalHandler.handle(_ proposal: Proposal)`:

```
if already handled (proposal.id in HandledStore)       → skip (log "duplicate")
if proposal.decision == "auto_add" AND calendar access == .fullAccess:
    eventId = CalendarService.add(proposal)
    if success → notify ADDED(proposal, eventId); feedback(added); log "✅ Added"
    else       → notify ASK(proposal); log "❓ Asked (auto-add failed)"
else:
    notify ASK(proposal); log "❓ Asked"
mark proposal.id handled
```

Notification button handlers:

| Notification | Button | Action |
|---|---|---|
| ADDED | **Undo** (destructive) | `CalendarService.remove(eventId)`, remove the notification, feedback `undone`, log "↩ Undone" |
| ADDED | **Open** (foreground) | Open the Calendar app at the event's start: `calshow:<start.timeIntervalSinceReferenceDate>` |
| ASK | **Add** | `CalendarService.add(proposal)`. On success, **post an ADDED notification** (with Undo) and send feedback `added`. On failure, post the "Couldn't add" notification (§7) and send feedback `failed`. |
| ASK | **Edit** (foreground) | Open the app → present `EKEventEditViewController` pre-filled. If saved, feedback `edited`. |
| ASK | **Dismiss** (destructive), or the notification is cleared | Feedback `dismissed`, log "✖ Dismissed" |
| Any | Tap on the body | Open the app's Activity screen, scrolled to that item |

**Rule: after anything is added to the calendar, the user always gets a notification saying so, with Undo.**

---

## 4. Getting screenshots on iOS

iOS has **no** API to run code when a screenshot is taken, and **no** "screenshots folder" permission. See the README platform notes. Implement these paths, in priority order:

1. **Scan on foreground (core).** When the app becomes active (`scenePhase == .active`) and at launch, fetch new screenshots:
   ```swift
   let opts = PHFetchOptions()
   opts.predicate = NSPredicate(format: "(mediaSubtypes & %d) != 0 AND creationDate > %@",
                                PHAssetMediaSubtype.photoScreenshot.rawValue, lastScanDate as NSDate)
   opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
   let assets = PHAsset.fetchAssets(with: .image, options: opts)
   ```
   Process them **sequentially**. On first run set `lastScanDate = now`, so the user's existing backlog is **not** processed. Advance `lastScanDate` to each asset's `creationDate` only after its request completes, and send failures to the retry queue.
2. **Live while open (core).** Register a `PHPhotoLibraryChangeObserver`. When the library changes while the app is running, run the same scan. This is the smoothest demo: screenshot, switch back to Snapsort, and the notifications appear.
3. **Background refresh (core).** Register `BGAppRefreshTask` id `com.snapsort.refresh`, schedule it with `earliestBeginDate = now + 15 min` after every run, and run the same scan inside. iOS decides when it actually runs (it may be hours). The ~30 s budget is too short for the real model, so in background mode **upload at most 1 screenshot per run**, and call `setTaskCompleted` before expiry.
4. **Manual pick (core).** A "Check a screenshot" button with `PhotosPicker` (filter `.screenshots`). Uses `captured_at` = the asset's creation date if available, else now. Also needed for the demo fallback.
5. *Stretch:* **Share Extension**, so the user can share from the screenshot preview. It writes the image and date into an App Group container; the main app processes it on next launch.
6. *Stretch:* **App Intent** "Check latest screenshot", usable from Shortcuts or Back Tap.

**Photos permission:** request `.readWrite` via `PHPhotoLibrary.requestAuthorization(for: .readWrite)`. If the result is `.limited`, show a blocking explanation card: *"Snapsort needs Full Access to see new screenshots. It only reads screenshots, never your other photos."* with a button to Settings (`UIApplication.openSettingsURLString`).

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

## 8. Screens (SwiftUI)

Keep it simple: 3 screens in a `TabView`, or a `NavigationStack` with a settings sheet.

**A. Onboarding** (first launch, 4 steps, each with one explanation sentence and one button):
1. Photos: Full Access (§4)
2. Calendar: Full Access (§6)
3. Notifications (§7)
4. Server: base URL + token fields + **Test connection** (calls `/health` and shows the model name or the error)

**B. Activity (home)**
- Top: status card showing "Watching screenshots ✓", the last scan time, the backend model name, and a **Scan now** button.
- A **Check a screenshot** button (`PhotosPicker`).
- An in-progress row while uploading: "Reading your screenshot… 23s", with a live timer, because the real model is slow.
- A list of the last 50 entries, newest first:
  - `✅ Added: {title} ({when})`, with an Undo swipe action if still undoable
  - `❓ Asked: {title} ({when})` with Add / Dismiss buttons inline, so pending asks can also be answered in the app
  - `✖ Dismissed`, `↩ Undone`, `⏭ Skipped: {skipped_reason}`, `❌ {error}`
  - Tap → detail: all payload fields, confidence, evidence and notes, plus latency

**C. Settings:** base URL, token, Test connection, permission status rows (each with a "Fix" button → Settings app), "Reset scan position to now", "Clear activity log".

Design: system fonts and colors, and support Dark Mode. No custom design system is needed.

---

## 9. Local persistence (UserDefaults / small JSON files)

| Key | Type | Purpose |
|---|---|---|
| `serverURL` | String | Default `http://localhost:8000` |
| `apiToken` | String | Default `""` |
| `lastScanDate` | Date | Screenshot cursor (§4). Set to now on first run. |
| `handledProposalIds` | [String] (keep the last 500) | Dedup: the same event from a second screenshot is ignored |
| `eventIdsByProposal` | [String: String] | For Undo |
| `retryQueue` | [String] (PHAsset localIdentifiers, max 20) | Screenshots whose upload failed. Retried on the next scan. Drop after 3 attempts. |
| `activityLog` | [ActivityEntry] (last 50) | For screen B |

Store the API token in the **Keychain** if time allows. UserDefaults is acceptable for the hackathon.

---

## 10. Info.plist & capabilities

| Key | Value |
|---|---|
| `NSPhotoLibraryUsageDescription` | "Snapsort reads your new screenshots to find events. Other photos are never read or uploaded." |
| `NSCalendarsFullAccessUsageDescription` | "Snapsort adds events it finds in your screenshots, and removes them if you tap Undo." |
| `NSCalendarsWriteOnlyAccessUsageDescription` | "Snapsort adds events it finds in your screenshots." |
| `NSLocalNetworkUsageDescription` | "Snapsort talks to the Snapsort server on your local network." |
| `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` | `YES`. **Hackathon only:** the laptop backend is plain HTTP. Remove this before any release. |
| `UIBackgroundModes` | `fetch`, `processing` |
| `BGTaskSchedulerPermittedIdentifiers` | `["com.snapsort.refresh"]` |

Capabilities: Background Modes (Background fetch, Background processing). *Stretch:* App Groups (`group.com.snapsort`) for the Share Extension.

---

## 11. Suggested project structure

```
ios/Snapsort/
  SnapsortApp.swift            // @main, registers BG task + notification categories, scenePhase → scan
  Models/API.swift             // §2.4 Codable models
  Services/APIClient.swift     // health(), analyze(), feedback()
  Services/ScreenshotScanner.swift  // PhotoKit fetch + change observer + image prep (§4, §5)
  Services/CalendarService.swift    // EventKit add/remove/edit (§6)
  Services/NotificationService.swift// categories, post ADDED/ASK, delegate handlers (§7)
  Services/ProposalHandler.swift    // decision logic (§3)
  Services/Store.swift              // persistence (§9)
  Views/OnboardingView.swift
  Views/ActivityView.swift
  Views/ActivityDetailView.swift
  Views/SettingsView.swift
  Views/EventEditorView.swift       // UIViewControllerRepresentable around EKEventEditViewController
```

Put all decision logic in `ProposalHandler` and keep it free of UIKit/SwiftUI so it can be unit-tested with a fake `CalendarService` and a fake `NotificationService`.

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

- [ ] Onboarding requests all 3 permissions, and Test connection shows `mock`.
- [ ] Taking a screenshot, then returning to the app, triggers exactly one `/analyze` for it.
- [ ] Mock call 1 (`auto_add`): the event appears in Calendar **and** an "✅ Added…" notification appears.
- [ ] Tapping **Undo** from the lock screen, without opening the app, removes the event, and the log shows ↩.
- [ ] Mock call 2 (`ask`): an "Add “Dinner with Sam”…?" notification appears and **no** event is created yet.
- [ ] Tapping **Add** creates the event and the notification is replaced by "✅ Added…" with Undo.
- [ ] Tapping **Edit** opens the pre-filled editor, and saving creates the event.
- [ ] Tapping **Dismiss** creates nothing, and the log shows ✖.
- [ ] Mock call 3 (meme): no notification; the log shows `⏭ Skipped: meme`.
- [ ] With calendar access set to *write-only*, an `auto_add` proposal becomes an ASK notification.
- [ ] Sending the same screenshot twice gives no duplicate event or notification (dedup by `id`).
- [ ] With the backend stopped, a screenshot is queued, and it's processed automatically after the backend restarts and the app is reopened.
- [ ] `/feedback` is called with the right `outcome` for each of the above (check the server log or `evals/results/feedback.jsonl`).
- [ ] With the real model, the progress row shows elapsed seconds and nothing times out before 240 s.

---

## 15. Parity with Android (`/android`)

| Behaviour | Android (done) | iOS (this spec) |
|---|---|---|
| Detect screenshot | Background service, instant | Scan on open / while open / background refresh |
| Progress | "Reading your screenshot…" notification | In-app progress row |
| `auto_add` | Writes via CalendarContract → "✅ Added" + Undo/Open | Writes via EventKit → "✅ Added" + Undo/Open |
| `ask` | "Add …?" + Add/Edit/Dismiss | Same |
| No calendar permission | Falls back to ask + calendar screen | Same |
| Feedback | `POST /feedback`, `platform: android` | `POST /feedback`, `platform: ios` |
