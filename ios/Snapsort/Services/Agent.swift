import SwiftUI
import UIKit
import UserNotifications

struct ProcessOutcome {
    let ok: Bool
    let summary: String
}

/// The on-phone half of the agent: upload screenshots, follow the backend's `decision`, and
/// carry out what the user chose. Home, Settings, notifications and App Intents all go through here,
/// so every entry point behaves the same (port of ScreenshotWatcherService.process, ActionReceiver
/// and MainActivity's undo/confirm).
///
/// The backend's policy gate decides auto_add vs ask (CLAUDE.md §2.5). This class never re-scores.
@MainActor
final class Agent: ObservableObject {
    static let shared = Agent()

    let store: Store
    let calendar: CalendarService
    let notifier: NotificationService
    let scanner: ScreenshotScanner
    let profile: Profile

    /// Drives the pre-filled calendar editor (Edit, or Add without calendar access).
    @Published var editing: Proposal?
    /// Drives the form review screen (from Home's Review or the "form found" notification).
    @Published var reviewingForm: FormProposal?
    @Published var toast: String?

    private var scanning = false
    private var startedUp = false

    init(store: Store = .shared, calendar: CalendarService = .shared, notifier: NotificationService = .shared,
         scanner: ScreenshotScanner = .shared, profile: Profile = .shared) {
        self.store = store
        self.calendar = calendar
        self.notifier = notifier
        self.scanner = scanner
        self.profile = profile
    }

    private func api() throws -> APIClient {
        try APIClient(serverURL: store.state.serverURL, token: store.state.apiToken)
    }

    func show(_ message: String) {
        toast = message
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            if toast == message { toast = nil }
        }
    }

    private func feedback(_ p: Proposal, _ outcome: String) {
        guard let client = try? api() else { return }
        Task.detached { await client.feedback(p, outcome: outcome) }
    }

    // MARK: Lifecycle

    /// Called whenever the app becomes active.
    func onForeground() async {
        if LaunchMode.isRunningTests { return }
        if !startedUp {
            startedUp = true
            if let url = LaunchMode.serverURLOverride { store.serverURL = url }
            if let steps = LaunchMode.selfTest {
                await SelfTest.run(steps, agent: self)
                return
            }
        }
        if LaunchMode.isAutomated { return }
        if !store.state.onboarded {
            store.update { $0.onboarded = true }
            await startWatching()
            return
        }
        if store.state.scanningEnabled {
            scanner.startObserving()
            BackgroundRefresh.schedule()
            await scan()
        }
    }

    // MARK: Watching (Settings → Start / Stop)

    func startWatching() async {
        guard await scanner.requestAccess() else {
            show("Photo access is needed to see new screenshots")
            return
        }
        if calendar.canAsk { _ = await calendar.requestAccess() }
        if !calendar.hasFullAccess { show("No full calendar access: Snapsort will ask before every event") }
        _ = await notifier.requestAuthorization()
        store.update {
            $0.scanningEnabled = true
            if $0.scanCursor == nil { $0.scanCursor = Date() } // don't process the existing backlog
        }
        store.log("Watcher started")
        scanner.startObserving()
        BackgroundRefresh.schedule()
        await scan()
    }

    func stopWatching() {
        store.update { $0.scanningEnabled = false }
        store.log("Watcher stopped")
    }

    func resetScanPosition() {
        store.update { $0.scanCursor = Date(); $0.pending = [] }
        store.log("Scan position reset to now")
    }

    // MARK: Scanning

    /// Finds new screenshots, queues them, then works through the queue oldest first.
    func scan(limit: Int = .max) async {
        guard !scanning, store.state.scanningEnabled, scanner.canRead else { return }
        scanning = true
        defer { scanning = false }

        store.update { $0.lastScanAt = Date() }
        if store.state.scanCursor == nil { store.update { $0.scanCursor = Date() } }
        for asset in scanner.screenshots(after: store.state.scanCursor ?? Date()) {
            let created = asset.creationDate ?? Date()
            store.enqueue(assetId: asset.localIdentifier, capturedAt: created)
            store.update { $0.scanCursor = max($0.scanCursor ?? created, created) }
        }

        var done = 0
        for shot in store.state.pending {
            if done >= limit || Task.isCancelled { break }
            done += 1
            guard let jpeg = await scanner.jpeg(assetId: shot.assetId) else {
                store.completePending(shot.assetId) // deleted from Photos
                continue
            }
            let outcome = await process(jpeg: jpeg, capturedAt: shot.capturedAt, sourceId: shot.assetId)
            if outcome.ok {
                store.completePending(shot.assetId)
            } else {
                if store.failPending(shot.assetId) {
                    store.log("❌ Gave up on a screenshot after \(Store.maxAttempts) tries")
                }
                break // server unreachable: keep the rest queued for the next scan
            }
        }
    }

    /// Settings → "Test with an image", and the App Intent that receives an image.
    @discardableResult
    func processImage(_ jpeg: Data, capturedAt: Date = Date()) async -> ProcessOutcome {
        await process(jpeg: jpeg, capturedAt: capturedAt, sourceId: "manual-\(UUID().uuidString.prefix(8))")
    }

    /// App Intent / Back Tap: process the newest screenshot right now.
    func processLatestScreenshot() async -> ProcessOutcome {
        if !scanner.canRead, !(await scanner.requestAccess()) {
            return ProcessOutcome(ok: false, summary: "later.exe needs Full Access to Photos to read screenshots.")
        }
        guard let asset = scanner.latestScreenshot(), let jpeg = await scanner.jpeg(assetId: asset.localIdentifier) else {
            return ProcessOutcome(ok: false, summary: "No screenshot found.")
        }
        let created = asset.creationDate ?? Date()
        let outcome = await process(jpeg: jpeg, capturedAt: created, sourceId: asset.localIdentifier)
        if outcome.ok {
            store.completePending(asset.localIdentifier)
            store.update { $0.scanCursor = max($0.scanCursor ?? created, created) }
        }
        return outcome
    }

    /// Upload one screenshot and act on every proposal. Shared by all entry points.
    func process(jpeg: Data, capturedAt: Date, sourceId: String) async -> ProcessOutcome {
        store.processingSince = Date()
        defer { store.processingSince = nil }
        do {
            let result = try await api().analyze(jpeg: jpeg, capturedAt: capturedAt)
            store.update { $0.lastError = nil } // a successful round-trip clears OFFLINE
            let secs = result.latencyMs / 1000

            let forms = result.forms ?? []
            if result.proposals.isEmpty && forms.isEmpty {
                let reason = result.skippedReason ?? "nothing found"
                store.log("⏭ Skipped: \(reason) · \(secs)s")
                store.recordActivity(ActivityRecord(id: "skipped-\(sourceId)", title: "Screenshot skipped", status: .skipped, summary: reason))
                return ProcessOutcome(ok: true, summary: "Nothing to add (\(reason)).")
            }

            var lines = receive(forms: forms)
            for p in result.proposals {
                if store.handledEventId(p.id) != nil {
                    lines.append("Already added: \(p.payload.title)")
                    continue
                }
                // Follow `decision`; without full calendar access we can't auto-add, so we ask.
                let eventId = p.isAutoAdd ? calendar.insert(p, store: store) : nil
                if let eventId {
                    notifier.postAdded(p, eventId: eventId)
                    store.log("✅ Added: \(p.payload.title) (\(p.prettyWhen)) · \(secs)s")
                    store.recordActivity(p.activity(.executed, "Added to calendar", eventId: eventId))
                    feedback(p, "added")
                    lines.append("Added \(p.payload.title), \(p.prettyWhen).")
                } else {
                    notifier.postAsk(p)
                    store.log("❓ Asked: \(p.payload.title) (\(p.prettyWhen)) · \(secs)s")
                    store.recordActivity(p.activity(.needsAttention, "Needs your confirmation"))
                    lines.append("Needs your OK: \(p.payload.title), \(p.prettyWhen).")
                }
            }
            return ProcessOutcome(ok: true, summary: lines.joined(separator: "\n"))
        } catch {
            let message = error.localizedDescription
            store.log("❌ \(message)")
            store.update { $0.lastError = message }
            store.recordActivity(ActivityRecord(id: "failed-\(sourceId)", title: "Screenshot upload failed", status: .failed, summary: message))
            notifier.postError(message)
            return ProcessOutcome(ok: false, summary: "Couldn't reach the Snapsort server: \(message)")
        }
    }

    // MARK: User decisions (Home, Review sheet, notifications)

    /// Home's Review → Add, and the notification's Add button.
    func confirm(_ p: Proposal, fromNotification: Bool = false) async {
        if store.handledEventId(p.id) != nil { return }
        if !calendar.hasFullAccess, calendar.canAsk { _ = await calendar.requestAccess() }
        if let eventId = calendar.insert(p, store: store) {
            notifier.postAdded(p, eventId: eventId) // replaces the ASK notification (same id)
            store.log("✅ Added (you confirmed): \(p.payload.title)")
            store.recordActivity(p.activity(.executed, "Added to calendar", eventId: eventId))
            feedback(p, "added")
            show("Added to calendar")
        } else if fromNotification {
            // Background action can't show UI: post a notification whose tap opens the editor.
            notifier.postCouldNotAdd(p)
            store.log("❌ Couldn't write \(p.payload.title): no full calendar access")
            feedback(p, "failed")
        } else {
            // No full calendar access: let the user save it through the system editor instead.
            editing = p
        }
    }

    func confirm(recordId: String) async {
        // Forms open the review screen instead of writing anything (CLAUDE.md §4.6).
        if let form = store.activity(recordId)?.form {
            reviewingForm = form
            return
        }
        guard let p = store.activity(recordId)?.proposal else {
            show("This item can no longer be confirmed")
            return
        }
        await confirm(p)
    }

    /// Undo on Home or on an ADDED notification: delete the event we wrote.
    func undo(_ p: Proposal, eventId: String) {
        let ok = calendar.delete(eventId: eventId)
        notifier.remove(p.id)
        if ok {
            store.log("↩ Undone: \(p.payload.title)")
            store.recordActivity(p.activity(.undone, "Action reversed"))
            feedback(p, "undone")
            show("Removed from calendar")
        } else {
            store.log("❌ Couldn't undo \(p.payload.title)")
            show("Couldn't undo that one")
        }
    }

    func undo(recordId: String) {
        guard let record = store.activity(recordId), let eventId = record.eventId, let p = record.proposal else {
            show("Nothing to undo for this item")
            return
        }
        undo(p, eventId: eventId)
    }

    func dismiss(_ p: Proposal) {
        notifier.remove(p.id)
        store.log("✖ Dismissed: \(p.payload.title)")
        store.recordActivity(p.activity(.dismissed, "Dismissed"))
        feedback(p, "dismissed")
    }

    func dismiss(recordId: String) {
        guard let p = store.activity(recordId)?.proposal else { return }
        dismiss(p)
    }

    /// The calendar editor closed. `saved` with a nil id happens without full access (the system saved it).
    func finishedEditing(_ p: Proposal, saved: Bool, eventId: String?) {
        editing = nil
        guard saved else { return }
        if let eventId { store.markHandled(p.id, eventId: eventId) }
        notifier.remove(p.id)
        store.log("✏️ Added after editing: \(p.payload.title)")
        store.recordActivity(p.activity(.executed, "Added to calendar (edited)", eventId: eventId))
        feedback(p, "edited")
        show("Added to calendar")
    }

    // MARK: Forms (v3)

    /// Record and announce forms found in a screenshot. Nothing is opened or filled here: the
    /// user reviews first and presses Submit themselves (CLAUDE.md §4.6).
    func receive(forms: [FormProposal]) -> [String] {
        var lines: [String] = []
        for f in forms {
            if store.activity(f.id)?.status == .executed { continue } // already opened this one
            let missing = f.missingCount(profile: profile)
            notifier.postForm(f, missing: missing)
            store.log("📝 Form found: \(f.payload.domain) · \(f.payload.fields.count) questions, \(missing) to fill")
            store.recordActivity(f.activity(.needsAttention, missing > 0 ? "\(missing) answers needed" : "Ready to pre-fill"))
            lines.append("Registration form found: \(f.title) (\(f.payload.domain)). Open later.exe to review it.")
        }
        return lines
    }

    /// Save any new answers to the profile, then open the pre-filled form in Safari.
    /// This is where Snapsort stops: the user presses Submit (CLAUDE.md §4.6).
    @discardableResult
    func openForm(_ form: FormProposal, values: [String: String]) -> URL? {
        var learned: [String: String] = [:]
        for field in form.payload.fields where !field.isSensitive {
            // Passwords, card numbers and ID numbers are never stored (§4.6).
            if let key = field.profileKey, let v = values[field.entryId], !v.trimmingCharacters(in: .whitespaces).isEmpty {
                learned[key] = v
            }
        }
        if !learned.isEmpty { profile.putAll(learned) }

        let url = form.prefillURL(values: values)
        let answered = values.values.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }.count
        store.log("📝 Opened pre-filled form: \(form.payload.domain) (\(answered) answers)")
        store.recordActivity(form.activity(.executed, "Pre-filled — submit it yourself"))
        notifier.remove(form.id)
        reviewingForm = nil
        if let url, !LaunchMode.isAutomated {
            UIApplication.shared.open(url)
        }
        return url
    }

    func dismissForm(_ form: FormProposal) {
        notifier.remove(form.id)
        store.log("✖ Dismissed form: \(form.payload.domain)")
        store.recordActivity(form.activity(.dismissed, "Dismissed"))
        reviewingForm = nil
    }

    func handleFormNotification(_ form: FormProposal) {
        reviewingForm = store.activity(form.id)?.form ?? form
    }

    func handleNotification(action: String, category: String, proposal p: Proposal, eventId: String?) async {
        switch action {
        case NotificationService.Action.undo:
            if let eventId { undo(p, eventId: eventId) }
        case NotificationService.Action.open:
            if let start = p.startDate, let url = URL(string: "calshow:\(start.timeIntervalSinceReferenceDate)") {
                await UIApplication.shared.open(url)
            }
        case NotificationService.Action.add:
            await confirm(p, fromNotification: true)
        case NotificationService.Action.edit:
            editing = p
        case NotificationService.Action.dismiss, UNNotificationDismissActionIdentifier:
            if category == NotificationService.Category.ask { dismiss(p) }
        case UNNotificationDefaultActionIdentifier:
            // Tapping "Couldn't add" opens the editor; other taps just open Home.
            if category == NotificationService.Category.couldNotAdd { editing = p }
        default:
            break
        }
    }

    // MARK: Settings

    func testConnection() async -> String {
        do {
            let client = try api()
            let health = try await client.health()
            try await client.checkToken()
            store.update { $0.lastError = nil }
            let warning = health.apiVersion == 1 ? "" : " (backend version mismatch)"
            return "Connected: \(health.model)\(warning)"
        } catch {
            store.update { $0.lastError = error.localizedDescription }
            return "Failed: \(error.localizedDescription)"
        }
    }
}
