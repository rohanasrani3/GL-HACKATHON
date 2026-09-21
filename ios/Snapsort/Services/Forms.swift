import Foundation

/// What Snapsort knows about you, for filling in registration forms (port of Profile.kt).
///
/// Local only (CLAUDE.md §2.8): values never go to the backend. The backend names which profile
/// key answers each question, and the phone supplies the value (§4.3, minimal egress).
/// Stored in the app's private container. §2.8 wants this encrypted at rest before a real release.
@MainActor
final class Profile: ObservableObject {
    static let shared = Profile(defaults: .standard)

    /// Must match PROFILE_KEYS in backend/snapsort/schema.py.
    static let keys = ["full_name", "email", "phone", "age", "location", "organisation", "student_id", "dietary", "website"]

    static let labels: [String: String] = [
        "full_name": "Full name",
        "email": "Email",
        "phone": "Phone",
        "age": "Age",
        "location": "Location",
        "organisation": "University / organisation",
        "student_id": "Student ID",
        "dietary": "Dietary requirements",
        "website": "Website / LinkedIn",
    ]

    static func label(_ key: String) -> String {
        labels[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }

    @Published private(set) var values: [String: String]
    private let defaults: UserDefaults
    private static let storageKey = "snapsort_profile"

    init(defaults: UserDefaults) {
        self.defaults = defaults
        values = defaults.dictionary(forKey: Profile.storageKey) as? [String: String] ?? [:]
    }

    subscript(key: String) -> String? {
        get { values[key].flatMap { $0.isEmpty ? nil : $0 } }
        set { putAll([key: newValue ?? ""]) }
    }

    func putAll(_ new: [String: String]) {
        for (k, v) in new {
            let trimmed = v.trimmingCharacters(in: .whitespacesAndNewlines)
            values[k] = trimmed.isEmpty ? nil : trimmed
        }
        defaults.set(values, forKey: Profile.storageKey)
    }

    func clear() {
        values = [:]
        defaults.removeObject(forKey: Profile.storageKey)
    }
}

extension FormProposal {
    /// Answers we already know, keyed by entry id. Sensitive fields are never seeded.
    @MainActor
    func seededValues(from profile: Profile) -> [String: String] {
        var out: [String: String] = [:]
        for field in payload.fields where !field.isSensitive {
            if let key = field.profileKey, let value = profile[key] { out[field.entryId] = value }
        }
        return out
    }

    /// Questions the profile can't answer yet (shown as "N need you").
    @MainActor
    func missingCount(profile: Profile) -> Int {
        payload.fields.filter { f in f.profileKey.map { profile[$0] == nil } ?? true }.count
    }

    /// The link that opens the form with answers already typed in (port of buildPrefillUrl).
    /// Google Forms: ?usp=pp_url&entry.N=value · other GET forms: ?name=value · otherwise untouched.
    /// Whatever the style, the form only ever *opens*; Snapsort never submits it (CLAUDE.md §4.6),
    /// and sensitive fields never go into the URL.
    func prefillURL(values: [String: String]) -> URL? {
        guard style != PrefillStyle.none, var components = URLComponents(string: payload.formUrl) else {
            return URL(string: payload.formUrl)
        }
        let sensitive = Set(payload.fields.filter(\.isSensitive).map(\.entryId))
        var items: [URLQueryItem] = style == PrefillStyle.googleForms ? [URLQueryItem(name: "usp", value: "pp_url")] : []
        // Keep the backend's field order so the URL is stable and readable.
        for field in payload.fields where !sensitive.contains(field.entryId) {
            if let value = values[field.entryId], !value.trimmingCharacters(in: .whitespaces).isEmpty {
                items.append(URLQueryItem(name: field.entryId, value: value))
            }
        }
        components.queryItems = items.isEmpty ? nil : items
        // URLComponents leaves "+" alone, which forms read as a space: encode it explicitly.
        components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        return components.url
    }
}
