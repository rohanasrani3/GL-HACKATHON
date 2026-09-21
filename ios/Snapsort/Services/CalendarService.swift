import EventKit

/// Direct calendar writes for auto-add + Undo (port of CalendarWriter.kt).
/// Without full access the app never writes silently: every proposal becomes "ask" and Add opens the editor.
@MainActor
final class CalendarService {
    static let shared = CalendarService()
    let eventStore = EKEventStore()

    var hasFullAccess: Bool { EKEventStore.authorizationStatus(for: .event) == .fullAccess }

    var statusText: String {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .fullAccess: return "Full access"
        case .writeOnly: return "Add only (no auto-add / Undo)"
        case .denied, .restricted: return "Denied"
        case .notDetermined: return "Not asked yet"
        default: return "Unknown"
        }
    }

    var canAsk: Bool { EKEventStore.authorizationStatus(for: .event) == .notDetermined }

    func requestAccess() async -> Bool {
        (try? await eventStore.requestFullAccessToEvents()) ?? false
    }

    /// Returns the event identifier, or nil if it couldn't be written.
    func insert(_ p: Proposal, store: Store) -> String? {
        if let existing = store.handledEventId(p.id) { return existing }
        guard hasFullAccess, let calendar = eventStore.defaultCalendarForNewEvents,
              let start = p.startDate, let end = p.endDate else { return nil }

        // Recover a write if the app stopped before saving its local receipt.
        let marker = Self.marker(for: p)
        let window = eventStore.predicateForEvents(
            withStart: start.addingTimeInterval(-86_400), end: end.addingTimeInterval(86_400), calendars: nil
        )
        if let found = eventStore.events(matching: window).first(where: { $0.url == marker }),
           let id = found.eventIdentifier {
            store.markHandled(p.id, eventId: id)
            return id
        }

        let event = makeEvent(for: p)
        event.calendar = calendar
        do {
            try eventStore.save(event, span: .thisEvent, commit: true)
        } catch {
            return nil
        }
        guard let id = event.eventIdentifier else { return nil }
        store.markHandled(p.id, eventId: id)
        return id
    }

    /// Unsaved event pre-filled from a proposal (also used by the Edit screen).
    func makeEvent(for p: Proposal) -> EKEvent {
        let e = EKEvent(eventStore: eventStore)
        e.title = p.payload.title
        e.location = p.payload.location.name ?? p.payload.location.onlineUrl
        e.notes = [p.payload.description, p.payload.location.onlineUrl, "Added by Snapsort from a screenshot"]
            .compactMap { $0 }
            .joined(separator: "\n")
        e.url = Self.marker(for: p)
        e.calendar = eventStore.defaultCalendarForNewEvents
        if p.payload.allDay {
            let start = p.startDate ?? Calendar.current.startOfDay(for: Date())
            e.isAllDay = true
            e.startDate = start
            // The backend's all-day end is exclusive (next day); EventKit's is inclusive.
            e.endDate = max(start, (p.endDate ?? start).addingTimeInterval(-1))
        } else {
            e.timeZone = TimeZone(identifier: p.payload.timezone)
            e.startDate = p.startDate ?? Date()
            e.endDate = p.endDate ?? e.startDate.addingTimeInterval(3600)
        }
        return e
    }

    func delete(eventId: String) -> Bool {
        guard hasFullAccess, let event = eventStore.event(withIdentifier: eventId) else { return false }
        do {
            try eventStore.remove(event, span: .thisEvent, commit: true)
            return true
        } catch {
            return false
        }
    }

    static func marker(for p: Proposal) -> URL? { URL(string: "snapsort://proposal/\(p.id)") }
}
