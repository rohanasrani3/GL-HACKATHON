import SwiftUI

/// Home → "Review details": what the agent found and why it asked, then Add / Edit / Dismiss
/// (the same choices as the ASK notification).
struct ReviewSheet: View {
    let record: ActivityRecord
    let onAdd: () -> Void
    let onEdit: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("! NEEDS INPUT").relayLabel(Relay.amber)
                Spacer().frame(height: 12)
                Text(record.title).font(RelayFont.titleLarge).foregroundStyle(Relay.textPrimary)

                if let p = record.proposal {
                    Spacer().frame(height: 16)
                    Detail(label: "WHEN", value: p.prettyWhen)
                    if let place = p.payload.location.name { Detail(label: "WHERE", value: place) }
                    if let link = p.payload.location.onlineUrl { Detail(label: "LINK", value: link) }
                    if let about = p.payload.description { Detail(label: "DETAILS", value: about) }
                    Detail(label: "CONFIDENCE", value: "\(Int((p.confidence * 100).rounded()))%")
                    Detail(label: "FROM THE SCREENSHOT", value: "“\(p.evidence)”")
                    if let notes = p.notes, !notes.isEmpty {
                        Detail(label: "WHY IT ASKED", value: notes.joined(separator: " · "))
                    }
                } else {
                    Text(record.summary).font(RelayFont.bodyLarge).foregroundStyle(Relay.textMuted)
                }

                Spacer().frame(height: 24)
                VStack(spacing: 10) {
                    Button("Add to calendar", action: onAdd).buttonStyle(RelayFilledButtonStyle())
                    Button("Edit before adding", action: onEdit).buttonStyle(RelayOutlineButtonStyle())
                    Button(action: onDismiss) {
                        Text("Dismiss").font(RelayFont.labelLarge).foregroundStyle(Relay.textMuted).frame(maxWidth: .infinity, minHeight: 48)
                    }
                }
                .disabled(record.proposal == nil)
            }
            .padding(Relay.gutter)
        }
        .background(Relay.surface.ignoresSafeArea())
        .presentationDetents([.medium, .large])
        .presentationBackground(Relay.surface)
    }
}

private struct Detail: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).relayLabel()
            Text(value).font(RelayFont.bodyLarge).foregroundStyle(Relay.textPrimary)
        }
        .padding(.bottom, 12)
    }
}
