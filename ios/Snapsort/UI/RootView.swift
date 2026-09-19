import SwiftUI

/// Hosts Home and Settings on top of the real pipeline (port of MainActivity).
struct RootView: View {
    @EnvironmentObject private var store: Store
    @EnvironmentObject private var agent: Agent

    @State private var showSettings = LaunchMode.demoScreen == "settings"
    @State private var reviewing: ActivityRecord?
    @State private var editAfterReview: Proposal?
    private let demoForm = LaunchMode.demoScreen == "form" ? SampleData.form : nil

    var body: some View {
        ZStack(alignment: .bottom) {
            Relay.background.ignoresSafeArea()

            if let form = agent.reviewingForm ?? demoForm {
                FormReviewView(
                    form: form,
                    onOpen: { values in agent.openForm(form, values: values) },
                    onDismiss: { agent.dismissForm(form) },
                    onBack: { agent.reviewingForm = nil }
                )
                .id(form.id)
            } else if showSettings {
                SettingsView(onBack: { showSettings = false })
            } else {
                // Re-render every second so "Reading screenshot… 12s" and "2 min ago" stay live.
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    HomeView(
                        state: homeState(now: context.date),
                        onUndo: { id in agent.undo(recordId: id) },
                        onReview: { id in
                            // Forms go to their own review screen; events to the Review sheet.
                            if let form = store.activity(id)?.form { agent.reviewingForm = form } else { reviewing = store.activity(id) }
                        },
                        onOverflow: { showSettings = true },
                        onRefresh: { await agent.scan() }
                    )
                }
            }

            if let toast = agent.toast {
                ToastView(text: toast)
                    .padding(.bottom, 12)
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: agent.toast)
        .sheet(item: $reviewing, onDismiss: {
            // Present the editor only after the review sheet has gone.
            if let p = editAfterReview {
                editAfterReview = nil
                agent.editing = p
            }
        }) { record in
            ReviewSheet(
                record: record,
                onAdd: {
                    reviewing = nil
                    Task { await agent.confirm(recordId: record.id) }
                },
                onEdit: {
                    editAfterReview = record.proposal
                    reviewing = nil
                },
                onDismiss: {
                    reviewing = nil
                    agent.dismiss(recordId: record.id)
                }
            )
        }
        .sheet(item: $agent.editing) { proposal in
            EventEditView(proposal: proposal) { saved, eventId in
                agent.finishedEditing(proposal, saved: saved, eventId: eventId)
            }
            .ignoresSafeArea()
        }
    }

    private func homeState(now: Date) -> HomeUiState {
        if let demo = LaunchMode.demoState { return SampleData.state(named: demo) }
        return HomeUiState.make(from: store.state, processingSince: store.processingSince, now: now)
    }
}
