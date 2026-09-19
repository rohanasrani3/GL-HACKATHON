import SwiftUI

/// Review before anything opens (port of android/.../ui/form/FormScreen.kt).
///
/// CLAUDE.md §4.6: Snapsort pre-fills and hands back control; it never submits.
/// §4.7: the resolved domain is shown before the link is opened.
struct FormReviewView: View {
    let form: FormProposal
    let onOpen: ([String: String]) -> Void
    let onDismiss: () -> Void
    let onBack: () -> Void

    @EnvironmentObject private var profile: Profile
    @State private var values: [String: String] = [:]
    @State private var autofilled: Set<String> = []
    @State private var seeded = false

    private var missingRequired: Int {
        form.payload.fields.filter { $0.isRequired && (values[$0.entryId] ?? "").trimmingCharacters(in: .whitespaces).isEmpty }.count
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Button(action: onBack) {
                    Text("‹  Back").font(RelayFont.bodyMediumStrong).foregroundStyle(Relay.green).frame(minHeight: 44)
                }

                Text("! NEEDS INPUT").relayLabel(Relay.amber)
                Text(form.title).font(RelayFont.headline).foregroundStyle(Relay.textPrimary)

                // §4.7: the user sees where this actually goes before anything opens.
                VStack(alignment: .leading, spacing: 4) {
                    Text("OPENS AT").relayLabel()
                    Text(form.payload.domain).font(RelayFont.titleMedium).foregroundStyle(Relay.textPrimary)
                    Text(form.canPrefill
                         ? "Snapsort fills these answers in and opens the form. It never presses Submit — that stays with you."
                         : "This page can't take answers in its link, so Snapsort opens it as-is. Your saved details are below to copy in.")
                        .font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
                    if let reasons = form.payload.reasons, !reasons.isEmpty {
                        Text("Why Snapsort thinks this is a form: " + reasons.joined(separator: "; "))
                            .font(.system(size: 12)).foregroundStyle(Relay.textMuted)
                    }
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Relay.surface)
                .overlay(RoundedRectangle(cornerRadius: 3).stroke(Relay.border, lineWidth: 1))

                if form.payload.fields.isEmpty {
                    Text("QUESTIONS").relayLabel().padding(.top, 8)
                    Text("This form builds its questions in the page, so they can't be read in advance. Snapsort will open it for you to fill in.")
                        .font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
                } else {
                    Text("ANSWERS").relayLabel().padding(.top, 8)
                }

                ForEach(form.payload.fields, id: \.entryId) { field in
                    FieldRow(field: field, value: binding(for: field), hint: hint(for: field))
                }

                Button(form.canPrefill ? "Open pre-filled form  →" : "Open form  →") { onOpen(values) }
                    .buttonStyle(RelayFilledButtonStyle())
                    .padding(.top, 8)

                Text(missingRequired > 0
                     ? "\(missingRequired) required question(s) still blank — you can fill them on the form."
                     : "Answers you add here are saved to your profile on this phone, so the next form is one tap.")
                    .font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)

                Button(action: onDismiss) {
                    Text("Not interested").font(RelayFont.labelLarge).foregroundStyle(Relay.textMuted)
                        .frame(maxWidth: .infinity, minHeight: 48)
                }
            }
            .padding(.horizontal, Relay.gutter)
            .padding(.vertical, 16)
        }
        .background(Relay.background.ignoresSafeArea())
        .onAppear {
            guard !seeded else { return }
            seeded = true
            // Known answers come from the local profile; the rest start blank for the user (§2.8).
            values = form.seededValues(from: profile)
            autofilled = Set(values.keys)
        }
    }

    private func binding(for field: FormField) -> Binding<String> {
        Binding(
            get: { field.isSensitive ? "" : values[field.entryId, default: ""] },
            set: { newValue in
                guard !field.isSensitive else { return }
                values[field.entryId] = newValue
                autofilled.remove(field.entryId) // edited by hand now
            }
        )
    }

    private func hint(for field: FormField) -> String {
        if field.isSensitive { return "Snapsort never fills this in" }
        if autofilled.contains(field.entryId) { return "From your profile · \(Profile.label(field.profileKey ?? ""))" }
        if field.profileKey != nil { return "Saved to your profile for next time" }
        return "Not stored — specific to this form"
    }
}

private struct FieldRow: View {
    let field: FormField
    @Binding var value: String
    let hint: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(field.question + (field.isRequired ? " *" : ""))
                .font(RelayFont.bodyMediumStrong)
                .foregroundStyle(field.isSensitive ? Relay.textMuted : Relay.textPrimary)
            TextField("", text: $value, axis: field.type == "paragraph" ? .vertical : .horizontal)
                .font(RelayFont.bodyLarge)
                .foregroundStyle(Relay.textPrimary)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .disabled(field.isSensitive)
                .padding(.horizontal, 12)
                .padding(.vertical, 12)
                .background(field.isSensitive ? Relay.background : Relay.surface)
                .overlay(RoundedRectangle(cornerRadius: 2).stroke(Relay.border, lineWidth: 1))
            Text(hint).font(.system(size: 12)).foregroundStyle(field.isSensitive ? Relay.amber : Relay.textMuted)
            if let options = field.options, !options.isEmpty {
                Text("Options: " + options.joined(separator: " · ")).font(.system(size: 12)).foregroundStyle(Relay.textMuted)
            }
        }
        .padding(.vertical, 4)
    }
}

#Preview { FormReviewView(form: SampleData.form, onOpen: { _ in }, onDismiss: {}, onBack: {}).environmentObject(Profile.shared) }
