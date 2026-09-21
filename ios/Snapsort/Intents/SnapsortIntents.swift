import AppIntents

// iOS can't run code when a screenshot is taken. These intents are the closest substitute:
//   • Shortcut "Take Screenshot → Snapsort a screenshot", bound to Back Tap or the Action Button,
//     captures and processes in one gesture without opening the app.
//   • "Check latest screenshot" processes the newest screenshot (Siri, Shortcuts, Spotlight).
//   • "Snapsort a screenshot" also accepts images from the share sheet via Shortcuts
//     (the equivalent of Android's share-to-Snapsort).

struct SnapsortScreenshotIntent: AppIntent {
    static let title: LocalizedStringResource = "Snapsort a screenshot"
    static let description = IntentDescription("Reads a screenshot and adds any event it finds to your calendar.")
    static let openAppWhenRun = false

    @Parameter(title: "Screenshot", supportedTypeIdentifiers: ["public.image"])
    var screenshot: IntentFile

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let jpeg = ImagePrep.jpeg(from: screenshot.data) else {
            return .result(dialog: "That doesn't look like an image.")
        }
        let outcome = await Agent.shared.processImage(jpeg)
        return .result(dialog: IntentDialog(stringLiteral: outcome.summary))
    }
}

struct CheckLatestScreenshotIntent: AppIntent {
    static let title: LocalizedStringResource = "Check latest screenshot"
    static let description = IntentDescription("Finds events in your most recent screenshot.")
    static let openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let outcome = await Agent.shared.processLatestScreenshot()
        return .result(dialog: IntentDialog(stringLiteral: outcome.summary))
    }
}

struct SnapsortShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: CheckLatestScreenshotIntent(),
            phrases: [
                "Check my latest screenshot with \(.applicationName)",
                "\(.applicationName) my screenshot",
            ],
            shortTitle: "Check latest screenshot",
            systemImageName: "camera.viewfinder"
        )
    }
}
