import UIKit
import UserNotifications

/// Actionable notifications (port of Notifier.kt + ActionReceiver.kt).
///   ADDED: "✅ Added to your calendar: …"  [Undo] [Open]
///   ASK:   "Add “…” to calendar?"         [Add] [Edit] [Dismiss]
///   FORM:  "Registration form found"      [Review] (opens the review screen, never the form)
/// The identifier is the proposal id, so ADDED replaces ASK for the same event after Add.
final class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationService()

    enum Category {
        static let added = "ADDED"
        static let ask = "ASK"
        static let couldNotAdd = "COULD_NOT_ADD"
        static let form = "FORM"
    }

    enum Action {
        static let undo = "UNDO"
        static let open = "OPEN"
        static let add = "ADD"
        static let edit = "EDIT"
        static let dismiss = "DISMISS"
        static let review = "REVIEW"
    }

    private var center: UNUserNotificationCenter { .current() }

    func registerCategories() {
        let added = UNNotificationCategory(
            identifier: Category.added,
            actions: [
                UNNotificationAction(identifier: Action.undo, title: "Undo", options: [.destructive]),
                UNNotificationAction(identifier: Action.open, title: "Open", options: [.foreground]),
            ],
            intentIdentifiers: []
        )
        let ask = UNNotificationCategory(
            identifier: Category.ask,
            actions: [
                UNNotificationAction(identifier: Action.add, title: "Add", options: []),
                UNNotificationAction(identifier: Action.edit, title: "Edit", options: [.foreground]),
                UNNotificationAction(identifier: Action.dismiss, title: "Dismiss", options: [.destructive]),
            ],
            intentIdentifiers: [],
            options: [.customDismissAction] // clearing the notification counts as Dismiss
        )
        let couldNotAdd = UNNotificationCategory(identifier: Category.couldNotAdd, actions: [], intentIdentifiers: [])
        // Opens later.exe's review screen, never the form itself: nothing is filled or opened until
        // the user has seen the domain and the answers (CLAUDE.md §4.6, §4.7).
        let form = UNNotificationCategory(
            identifier: Category.form,
            actions: [UNNotificationAction(identifier: Action.review, title: "Review", options: [.foreground])],
            intentIdentifiers: []
        )
        center.setNotificationCategories([added, ask, couldNotAdd, form])
    }

    func requestAuthorization() async -> Bool {
        (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    func statusText() async -> String {
        switch await center.notificationSettings().authorizationStatus {
        case .authorized, .provisional, .ephemeral: return "Allowed"
        case .denied: return "Denied"
        case .notDetermined: return "Not asked yet"
        @unknown default: return "Unknown"
        }
    }

    // MARK: Posting

    func postAdded(_ p: Proposal, eventId: String) {
        post(id: p.id, title: "✅ Added to your calendar: \(p.payload.title)", body: p.subtitle,
             category: Category.added, proposal: p, eventId: eventId)
    }

    func postAsk(_ p: Proposal) {
        post(id: p.id, title: "Add “\(p.payload.title)” to calendar?",
             body: "\(p.subtitle)\nNot 100% sure about this one. Add it?",
             category: Category.ask, proposal: p)
    }

    func postCouldNotAdd(_ p: Proposal) {
        post(id: p.id, title: "Couldn't add “\(p.payload.title)” automatically", body: "Tap to add it in Calendar",
             category: Category.couldNotAdd, proposal: p)
    }

    func postForm(_ f: FormProposal, missing: Int) {
        let count = f.payload.fields.count
        let body = missing > 0
            ? "\(count) questions · \(missing) need you · \(f.payload.domain)"
            : "\(count) questions · ready to pre-fill · \(f.payload.domain)"
        post(id: f.id, title: "Registration form found", body: body + "\nSnapsort fills it in — you press Submit.",
             category: Category.form, form: f)
    }

    /// At most one of these is shown at a time (same identifier).
    func postError(_ message: String) {
        post(id: "server-error", title: "Snapsort couldn't reach the server", body: message, category: "")
    }

    func remove(_ id: String) {
        center.removeDeliveredNotifications(withIdentifiers: [id])
        center.removePendingNotificationRequests(withIdentifiers: [id])
    }

    private func post(id: String, title: String, body: String, category: String, proposal: Proposal? = nil,
                      eventId: String? = nil, form: FormProposal? = nil) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        content.categoryIdentifier = category
        var info: [String: String] = [:]
        if let json = proposal?.jsonString { info["proposal"] = json }
        if let eventId { info["eventId"] = eventId }
        if let form, let data = try? JSONEncoder.api.encode(form) { info["form"] = String(data: data, encoding: .utf8) }
        content.userInfo = info
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: nil))
    }

    // MARK: UNUserNotificationCenterDelegate

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .list]) // show even while the app is open
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let content = response.notification.request.content
        let proposal = (content.userInfo["proposal"] as? String).flatMap(Proposal.fromJSONString)
        let eventId = content.userInfo["eventId"] as? String
        let action = response.actionIdentifier
        let category = content.categoryIdentifier
        let form = (content.userInfo["form"] as? String)
            .flatMap { $0.data(using: .utf8) }
            .flatMap { try? JSONDecoder.api.decode(FormProposal.self, from: $0) }
        Task { @MainActor in
            if let form, action != UNNotificationDismissActionIdentifier {
                Agent.shared.handleFormNotification(form)
            } else if let proposal {
                await Agent.shared.handleNotification(action: action, category: category, proposal: proposal, eventId: eventId)
            }
            completionHandler()
        }
    }
}
