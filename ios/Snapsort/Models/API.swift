import Foundation

// Backend contract v1 (frontend.md §2). Decode with JSONDecoder.api (snake_case keys).

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
    /// Additive fields (v3): absent on older backends, so optional.
    let forms: [FormProposal]?
    let links: [LinkContext]?
}

// MARK: - v3: registration forms found via links / QR codes in the screenshot

/// One question on the form, with the prefill parameter the backend read off the live page.
struct FormField: Codable, Hashable {
    let entryId: String // "entry.1046611833" on Google Forms, otherwise the input's name
    let question: String
    let profileKey: String? // which profile field answers this; nil = ask the user
    let required: Bool?
    let type: String?
    let options: [String]?
    /// Passwords, card numbers, government IDs. CLAUDE.md §4.6: never pre-filled, ever.
    let sensitive: Bool?

    var isRequired: Bool { required ?? false }
    var isSensitive: Bool { sensitive ?? false }
}

enum PrefillStyle {
    static let googleForms = "google_forms" // ?usp=pp_url&entry.N=value
    static let query = "query" // ?<input name>=value
    static let none = "none" // no URL prefill; open it and show the values to copy
}

struct FormPayload: Codable, Hashable {
    let formUrl: String
    let title: String?
    let domain: String // shown before anything opens (CLAUDE.md §4.7)
    let fields: [FormField]
    let prefillStyle: String?
    let provider: String?
    let reasons: [String]? // why the backend thinks this is a form
}

/// A form Snapsort can pre-fill. Always `decision: "ask"`: Snapsort never submits (CLAUDE.md §4.6).
struct FormProposal: Codable, Identifiable, Hashable {
    let id: String
    let action: String
    let decision: String
    let payload: FormPayload
    let confidence: Double
    let evidence: String
    let notes: [String]?

    var title: String { payload.title?.isEmpty == false ? payload.title! : "Registration form" }
    var style: String { payload.prefillStyle ?? PrefillStyle.none }
    var canPrefill: Bool { style != PrefillStyle.none && payload.fields.contains { !$0.isSensitive } }
    var destinationLabel: String { payload.provider == "google_forms" ? "Google Forms" : payload.domain }
}

/// What a link in the screenshot points at (context for the user).
struct LinkContext: Codable, Hashable {
    let url: String
    let domain: String
    let title: String?
    let description: String?
    let isForm: Bool?
    let source: String? // qr | ocr
}

struct Proposal: Codable, Identifiable, Hashable {
    let id: String
    let action: String
    let decision: String // "auto_add" | "ask"; anything unknown is treated as "ask"
    let payload: CalendarPayload
    let confidence: Double
    let evidence: String
    let notes: [String]?

    var isAutoAdd: Bool { decision == "auto_add" }
}

struct CalendarPayload: Codable, Hashable {
    let title: String
    let start: String // ISO 8601 with offset, or YYYY-MM-DD when allDay
    let end: String // exclusive next day when allDay
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
    let outcome: String // added | dismissed | undone | edited | failed
    var platform = "ios"
}

extension JSONDecoder {
    static var api: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}

extension JSONEncoder {
    static var api: JSONEncoder {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }
}

// MARK: - Dates and display (mirrors Notifier.prettyWhen on Android)

enum ProposalDates {
    static func parse(_ value: String, allDay: Bool) -> Date? {
        if allDay {
            let f = DateFormatter()
            f.calendar = Calendar(identifier: .gregorian)
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = .current
            f.dateFormat = "yyyy-MM-dd"
            return f.date(from: value)
        }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        if let d = f.date(from: value) { return d }
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: value)
    }

    /// `captured_at` for /analyze: always an explicit offset (+08:00, never "Z").
    static func isoWithOffset(_ date: Date, timeZone: TimeZone = .current) -> String {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ssxxxxx"
        return f.string(from: date)
    }
}

extension Proposal {
    var startDate: Date? { ProposalDates.parse(payload.start, allDay: payload.allDay) }
    var endDate: Date? { ProposalDates.parse(payload.end, allDay: payload.allDay) }

    /// "Fri 25 Sep, 16:00" or "Fri 25 Sep (all day)", in the event's own time zone.
    var prettyWhen: String {
        guard let start = startDate else { return payload.start }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        if payload.allDay {
            f.timeZone = .current
            f.dateFormat = "EEE d MMM"
            // Multi-day: "Mon 12 – Fri 16 Oct" (the backend's end date is exclusive).
            if let end = endDate, let last = Calendar.current.date(byAdding: .day, value: -1, to: end), last > start {
                let sameMonth = Calendar.current.isDate(start, equalTo: last, toGranularity: .month)
                let first = DateFormatter()
                first.locale = f.locale
                first.timeZone = f.timeZone
                first.dateFormat = sameMonth ? "EEE d" : "EEE d MMM"
                return "\(first.string(from: start)) – \(f.string(from: last))"
            }
            return f.string(from: start) + " (all day)"
        }
        f.timeZone = TimeZone(identifier: payload.timezone) ?? .current
        f.dateFormat = "EEE d MMM, HH:mm"
        return f.string(from: start)
    }

    var subtitle: String {
        [prettyWhen, payload.location.name].compactMap { $0 }.joined(separator: " · ")
    }

    var jsonString: String? {
        (try? JSONEncoder.api.encode(self)).flatMap { String(data: $0, encoding: .utf8) }
    }

    static func fromJSONString(_ s: String) -> Proposal? {
        s.data(using: .utf8).flatMap { try? JSONDecoder.api.decode(Proposal.self, from: $0) }
    }
}
