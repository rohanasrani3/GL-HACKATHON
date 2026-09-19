import EventKitUI
import SwiftUI

/// The system event editor, pre-filled from a proposal (Edit, or Add without full calendar access).
/// Works even with write-only access: the editor saves out of process.
struct EventEditView: UIViewControllerRepresentable {
    let proposal: Proposal
    /// (saved, eventIdentifier if we can read it back)
    let onFinish: (Bool, String?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onFinish: onFinish) }

    func makeUIViewController(context: Context) -> EKEventEditViewController {
        let vc = EKEventEditViewController()
        vc.eventStore = CalendarService.shared.eventStore
        vc.event = CalendarService.shared.makeEvent(for: proposal)
        vc.editViewDelegate = context.coordinator
        return vc
    }

    func updateUIViewController(_ controller: EKEventEditViewController, context: Context) {}

    final class Coordinator: NSObject, EKEventEditViewDelegate {
        let onFinish: (Bool, String?) -> Void

        init(onFinish: @escaping (Bool, String?) -> Void) {
            self.onFinish = onFinish
        }

        func eventEditViewController(_ controller: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) {
            let saved = action == .saved
            onFinish(saved, saved ? controller.event?.eventIdentifier : nil)
        }
    }
}
