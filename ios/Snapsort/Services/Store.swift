import Foundation

/// One entry in the Home activity feed (port of ActivityRecord in android/.../Store.kt).
/// Written at the same points the pipeline logs, so the feed and the notifications agree.
struct ActivityRecord: Codable, Identifiable, Equatable {
    var id: String
    var title: String
    var status: ActivityStatus
    var summary: String
    var eventTime: String? = nil
    var timestamp: Date = Date()
    var eventId: String? = nil // EventKit eventIdentifier, for Undo
    var proposal: Proposal? = nil // kept so Home can confirm or undo later without the backend
    /// Set for registration forms (kind "form"); Review then opens the form screen instead of adding.
    var form: FormProposal? = nil

    var isForm: Bool { form != nil }
}

struct LogLine: Codable, Equatable, Identifiable {
    var id = UUID()
    var t: Date
    var msg: String
}

/// A screenshot we found but haven't finished processing (retry queue).
struct PendingShot: Codable, Equatable {
    var assetId: String
    var capturedAt: Date
    var attempts: Int = 0
}

struct PersistedState: Codable, Equatable {
    var serverURL = "https://gl-hackathon.onrender.com" // same default as Android
    var apiToken = ""
    var onboarded = false
    var scanningEnabled = false
    var lastError: String? = nil
    var lastScanAt: Date? = nil
    /// Screenshot cursor: only screenshots created after this are processed. Set to "now" on first
    /// start so the existing backlog is skipped.
    var scanCursor: Date? = nil
    var activities: [ActivityRecord] = []
    var log: [LogLine] = []
    /// proposal id → EventKit eventIdentifier. Kept after Undo: retries must not recreate the event.
    var handled: [String: String] = [:]
    var pending: [PendingShot] = []
}

/// Settings + activity feed + retry queue, persisted as one JSON file. Hackathon-grade persistence.
@MainActor
final class Store: ObservableObject {
    static let shared = Store(fileURL: Store.defaultURL)
    static let maxActivity = 30
    static let maxLog = 30
    static let maxAttempts = 3

    @Published private(set) var state: PersistedState
    /// When the in-flight analysis started, or nil. Drives the "Reading screenshot" row.
    @Published var processingSince: Date?

    private let fileURL: URL?

    /// `fileURL: nil` keeps everything in memory (tests).
    init(fileURL: URL?) {
        self.fileURL = fileURL
        if let url = fileURL, let data = try? Data(contentsOf: url),
           let saved = try? Store.decoder.decode(PersistedState.self, from: data) {
            state = saved
        } else {
            state = PersistedState()
        }
    }

    static var defaultURL: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("snapsort-state.json")
    }

    private static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        e.outputFormatting = [.prettyPrinted, .sortedKeys]
        return e
    }()

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    func update(_ change: (inout PersistedState) -> Void) {
        change(&state)
        save()
    }

    private func save() {
        guard let url = fileURL, let data = try? Store.encoder.encode(state) else { return }
        try? data.write(to: url, options: .atomic)
    }

    // MARK: Settings

    var serverURL: String {
        get { state.serverURL }
        set {
            var v = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
            while v.hasSuffix("/") { v.removeLast() }
            update { $0.serverURL = v }
        }
    }

    var apiToken: String {
        get { state.apiToken }
        set { update { $0.apiToken = newValue.trimmingCharacters(in: .whitespacesAndNewlines) } }
    }

    // MARK: Activity feed

    /// Newest first. Replaces any earlier entry with the same id.
    func recordActivity(_ record: ActivityRecord) {
        update { s in
            s.activities.removeAll { $0.id == record.id }
            s.activities.insert(record, at: 0)
            if s.activities.count > Store.maxActivity {
                s.activities.removeLast(s.activities.count - Store.maxActivity)
            }
        }
    }

    func activity(_ id: String) -> ActivityRecord? {
        state.activities.first { $0.id == id }
    }

    func log(_ message: String) {
        update { s in
            s.log.insert(LogLine(t: Date(), msg: message), at: 0)
            if s.log.count > Store.maxLog { s.log.removeLast(s.log.count - Store.maxLog) }
        }
    }

    func clearActivity() {
        update { $0.activities = []; $0.log = [] }
    }

    // MARK: Dedup receipts

    func handledEventId(_ proposalId: String) -> String? { state.handled[proposalId] }

    func markHandled(_ proposalId: String, eventId: String) {
        update { $0.handled[proposalId] = eventId }
    }

    // MARK: Retry queue

    /// Adds a screenshot to pending work. Returns the original capture time if it was already queued.
    @discardableResult
    func enqueue(assetId: String, capturedAt: Date) -> Date {
        if let existing = state.pending.first(where: { $0.assetId == assetId }) { return existing.capturedAt }
        update { $0.pending.append(PendingShot(assetId: assetId, capturedAt: capturedAt)) }
        return capturedAt
    }

    func completePending(_ assetId: String) {
        update { $0.pending.removeAll { $0.assetId == assetId } }
    }

    /// Counts a failed attempt. Returns true when the screenshot was dropped after too many tries.
    @discardableResult
    func failPending(_ assetId: String) -> Bool {
        var dropped = false
        update { s in
            guard let i = s.pending.firstIndex(where: { $0.assetId == assetId }) else { return }
            s.pending[i].attempts += 1
            if s.pending[i].attempts >= Store.maxAttempts {
                s.pending.remove(at: i)
                dropped = true
            }
        }
        return dropped
    }
}

extension FormProposal {
    func activity(_ status: ActivityStatus, _ summary: String) -> ActivityRecord {
        ActivityRecord(id: id, title: title, status: status, summary: summary, eventTime: payload.domain, form: self)
    }
}

extension Proposal {
    /// Feed entry for this proposal (port of Proposal.toActivity in Uploader.kt).
    func activity(_ status: ActivityStatus, _ summary: String, eventId: String? = nil) -> ActivityRecord {
        ActivityRecord(id: id, title: payload.title, status: status, summary: summary,
                       eventTime: prettyWhen, eventId: eventId, proposal: self)
    }
}
