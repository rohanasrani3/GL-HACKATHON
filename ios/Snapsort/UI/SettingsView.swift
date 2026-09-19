import PhotosUI
import SwiftUI

/// Everything Android's Settings exposes (server URL, token, watcher start/stop, manual test,
/// activity log) plus the iOS-only bits: permission status and the Back Tap shortcut.
struct SettingsView: View {
    @EnvironmentObject private var store: Store
    @EnvironmentObject private var agent: Agent
    let onBack: () -> Void

    @State private var serverURL = ""
    @State private var apiToken = ""
    @State private var testing = false
    @State private var picked: PhotosPickerItem?
    @State private var notificationStatus = "…"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Button(action: onBack) {
                    Text("‹  Back").font(RelayFont.bodyMediumStrong).foregroundStyle(Relay.green)
                        .frame(minHeight: 44)
                }

                Text("Settings").font(RelayFont.headline).foregroundStyle(Relay.textPrimary)
                Text("The phone talks to the Snapsort backend. In the Simulator http://localhost:8000 works; on an iPhone use your laptop's IP on the same Wi-Fi/hotspot, or its Tailscale name.")
                    .font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)

                RelayField(label: "Laptop server URL", text: $serverURL, keyboard: .URL)
                RelayField(label: "API token (optional)", text: $apiToken, keyboard: .default)

                Button(testing ? "Testing…" : "Save & test connection") { saveAndTest() }
                    .buttonStyle(RelayFilledButtonStyle(fill: Relay.green, height: 48))
                    .disabled(testing)

                SectionTitle("Watcher")
                Text(store.state.scanningEnabled
                     ? "Running. New screenshots are checked when you open later.exe, while it's open, and in background refresh."
                     : "Stopped. Screenshots are ignored until you start it.")
                    .font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)

                if store.state.scanningEnabled {
                    Button("■  Stop watching") { agent.stopWatching() }.buttonStyle(RelayOutlineButtonStyle())
                    Button("Scan now") { Task { await agent.scan() } }.buttonStyle(RelayOutlineButtonStyle())
                } else {
                    Button("▶  Start watching screenshots") {
                        saveFields()
                        Task { await agent.startWatching(); onBack() }
                    }
                    .buttonStyle(RelayFilledButtonStyle(fill: Relay.green, height: 48))
                }

                PhotosPicker(selection: $picked, matching: .images) {
                    Text("Test with an image from Photos")
                }
                .buttonStyle(RelayOutlineButtonStyle())

                SectionTitle("Permissions")
                PermissionRow(name: "Photos", status: agent.scanner.statusText)
                PermissionRow(name: "Calendar", status: agent.calendar.statusText)
                PermissionRow(name: "Notifications", status: notificationStatus)
                Button("Open iOS Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                }
                .buttonStyle(RelayOutlineButtonStyle())

                SectionTitle("Instant capture (Back Tap)")
                Text("iOS doesn't let apps react the moment you take a screenshot. For one-gesture capture: in Shortcuts, make a shortcut with “Take Screenshot” then “Snapsort a screenshot”, and assign it in Settings → Accessibility → Touch → Back Tap (or to the Action Button).")
                    .font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)

                SectionTitle("Activity log")
                if store.state.log.isEmpty {
                    Text("Nothing yet.").font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
                } else {
                    ForEach(store.state.log) { line in
                        Text("\(line.t.formatted(date: .omitted, time: .standard))  \(line.msg)")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(Relay.textMuted)
                    }
                }

                HStack(spacing: 12) {
                    Button("Reset scan position") { agent.resetScanPosition() }.buttonStyle(RelayOutlineButtonStyle())
                    Button("Clear activity") { store.clearActivity() }.buttonStyle(RelayOutlineButtonStyle())
                }
                .padding(.top, 8)
            }
            .padding(.horizontal, Relay.gutter)
            .padding(.vertical, 16)
        }
        .background(Relay.background.ignoresSafeArea())
        .onAppear {
            serverURL = store.state.serverURL
            apiToken = store.state.apiToken
        }
        .task { notificationStatus = await agent.notifier.statusText() }
        .onChange(of: picked) { _, item in
            guard let item else { return }
            saveFields()
            agent.show("Analyzing… (this can take a while)")
            Task {
                if let data = try? await item.loadTransferable(type: Data.self), let jpeg = ImagePrep.jpeg(from: data) {
                    await agent.processImage(jpeg)
                } else {
                    agent.show("Couldn't read that image")
                }
                picked = nil
            }
        }
    }

    private func saveFields() {
        store.serverURL = serverURL
        store.apiToken = apiToken
        serverURL = store.state.serverURL
    }

    private func saveAndTest() {
        saveFields()
        testing = true
        Task {
            let message = await agent.testConnection()
            testing = false
            agent.show(message)
        }
    }
}

private struct SectionTitle: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(RelayFont.titleMedium).foregroundStyle(Relay.textPrimary).padding(.top, 8)
    }
}

private struct RelayField: View {
    let label: String
    @Binding var text: String
    let keyboard: UIKeyboardType

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased()).relayLabel()
            TextField("", text: $text)
                .font(RelayFont.bodyLarge)
                .foregroundStyle(Relay.textPrimary)
                .keyboardType(keyboard)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(.horizontal, 12)
                .frame(minHeight: 48)
                .background(Relay.surface)
                .overlay(RoundedRectangle(cornerRadius: 2).stroke(Relay.border, lineWidth: 1))
        }
    }
}

private struct PermissionRow: View {
    let name: String
    let status: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(name).font(RelayFont.bodyMediumStrong).foregroundStyle(Relay.textPrimary)
            Spacer()
            Text(status).font(RelayFont.bodyMedium).multilineTextAlignment(.trailing)
                .foregroundStyle(status.hasPrefix("Full") || status == "Allowed" ? Relay.green : Relay.amber)
        }
    }
}
