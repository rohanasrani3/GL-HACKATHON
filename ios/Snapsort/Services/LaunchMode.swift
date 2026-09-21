import Foundation
import UIKit

/// Launch arguments used by CI and demos (`-name value` lands in UserDefaults' argument domain):
///   -demoState default|active|processing|offline|inactive|noAttention|multipleAttention|longTitle
///   -demoScreen settings|form
///   -serverURL http://127.0.0.1:8000
///   -selfTest analyze,analyze,analyze,confirm,undo,form,openForm
enum LaunchMode {
    static var isRunningTests: Bool { ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil }
    static var demoState: String? { UserDefaults.standard.string(forKey: "demoState") }
    static var demoScreen: String? { UserDefaults.standard.string(forKey: "demoScreen") }
    static var serverURLOverride: String? { UserDefaults.standard.string(forKey: "serverURL") }
    static var selfTest: String? { UserDefaults.standard.string(forKey: "selfTest") }
    /// Automated runs never show permission prompts (they would cover the screenshots).
    static var isAutomated: Bool { isRunningTests || demoState != nil || demoScreen != nil || selfTest != nil }
}

/// End-to-end check against a running backend (CI uses MODEL_PROVIDER=mock). Runs the real pipeline
/// on a bundled sample screenshot, then writes a report to Documents/selftest.txt.
@MainActor
enum SelfTest {
    static func run(_ steps: String, agent: Agent) async {
        var report: [String] = []
        let sample = Bundle.main.url(forResource: "sample_screenshot", withExtension: "png")
            .flatMap { try? Data(contentsOf: $0) }
            .flatMap { ImagePrep.jpeg(from: $0) }

        for step in steps.split(separator: ",").map({ $0.trimmingCharacters(in: .whitespaces) }) {
            switch step {
            case "analyze":
                guard let sample else { report.append("analyze: FAILED missing sample image"); continue }
                let out = await agent.processImage(sample)
                report.append("analyze: ok=\(out.ok) \(out.summary.replacingOccurrences(of: "\n", with: " | "))")
            case "confirm":
                if let r = agent.store.state.activities.first(where: { $0.status == .needsAttention }) {
                    await agent.confirm(recordId: r.id)
                    report.append("confirm: \(r.title) -> \(agent.store.activity(r.id)?.status.rawValue ?? "?")")
                } else {
                    report.append("confirm: nothing needs input")
                }
            case "undo":
                if let r = agent.store.state.activities.first(where: { $0.status == .executed && $0.eventId != nil }) {
                    agent.undo(recordId: r.id)
                    report.append("undo: \(r.title) -> \(agent.store.activity(r.id)?.status.rawValue ?? "?")")
                } else {
                    report.append("undo: nothing to undo")
                }
            case "form":
                // Forms need a live Google Form page, which the mock backend can't provide, so this
                // feeds the backend's FormProposal shape straight into the same code path.
                let lines = agent.receive(forms: [SampleData.form])
                report.append("form: \(lines.first ?? "nothing") -> \(agent.store.activity(SampleData.form.id)?.status.rawValue ?? "?")")
            case "openForm":
                agent.profile.putAll(["full_name": "Test User", "email": "test@example.com"])
                let values = SampleData.form.seededValues(from: agent.profile)
                    .merging(["entry.1004": "Afternoon", "entry.1005": "A123456(7)"]) { a, _ in a }
                let url = agent.openForm(SampleData.form, values: values)
                report.append("openForm: \(url?.absoluteString ?? "nil") -> \(agent.store.activity(SampleData.form.id)?.status.rawValue ?? "?")")
            case "reset":
                agent.store.clearActivity()
                report.append("reset")
            default:
                report.append("\(step): unknown step")
            }
        }
        report.append("calendar: \(agent.calendar.statusText)")
        report.append("statuses: " + agent.store.state.activities.map { "\($0.title)=\($0.status.rawValue)" }.joined(separator: ", "))
        agent.store.log("Self-test finished (\(report.count) lines)")

        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        try? report.joined(separator: "\n").write(to: docs.appendingPathComponent("selftest.txt"), atomically: true, encoding: .utf8)
    }
}
