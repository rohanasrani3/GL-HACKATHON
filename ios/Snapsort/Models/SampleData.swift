import Foundation

/// Demo-only fixtures (port of RelaySampleData.kt). Used by #Preview and by the
/// `-demoState <name>` launch argument; never read by the real pipeline.
enum SampleData {
    static let calendar = ToolDestination(label: "Calendar", symbol: "C")

    static let activeAgent = AgentStatus(kind: .active, primaryText: "Watching screenshots", secondaryText: "Last scan · just now")

    static let processingScreenshot = ActivityItem(
        id: "processing-screenshot", title: "Screenshot detected", status: .processing,
        summary: "Understanding action…", activityTimestamp: "8s"
    )
    static let assignmentNeedsInput = ActivityItem(
        id: "comp3230-assignment", title: "COMP3230 Assignment", status: .needsAttention,
        destination: calendar, summary: "Deadline unclear"
    )
    static let buildNight = ActivityItem(
        id: "build-night", title: "Build Night", status: .executed, destination: calendar,
        summary: "Added to calendar", eventTime: "Sep 22 · 17:00–19:00", activityTimestamp: "Just now", canUndo: true
    )
    static let orientationDay = ActivityItem(
        id: "dsa-orientation-day", title: "DSA Orientation Day", status: .executed, destination: calendar,
        summary: "Added to calendar", eventTime: "Sep 27 · 12:00", activityTimestamp: "2 min ago", canUndo: true
    )
    static let longHealthcareEvent = ActivityItem(
        id: "generative-ai-healthcare", title: "Generative AI in Healthcare: Building Safe Clinical Systems",
        status: .executed, destination: calendar, summary: "Added to calendar",
        eventTime: "Oct 3 · 18:30–20:00", activityTimestamp: "5 min ago", canUndo: true
    )

    static let defaultState = HomeUiState(
        agentStatus: activeAgent,
        processingItem: processingScreenshot,
        needsAttention: [assignmentNeedsInput],
        recentActivity: [buildNight, orientationDay, longHealthcareEvent]
    )

    static func state(named name: String) -> HomeUiState {
        var s = defaultState
        switch name {
        case "active":
            s.processingItem = nil
        case "processing":
            s.agentStatus = AgentStatus(kind: .processing, primaryText: "Reading screenshot", secondaryText: "Understanding actionable information")
        case "offline":
            s.agentStatus = AgentStatus(kind: .offline, primaryText: "Server unavailable", secondaryText: "Will retry automatically")
            s.processingItem = ActivityItem(id: "retrying-upload", title: "Screenshot upload failed", status: .retrying, summary: "Will retry automatically")
        case "inactive":
            s.agentStatus = AgentStatus(kind: .inactive, primaryText: "Screenshot monitoring stopped", secondaryText: "Open Settings to resume")
            s.processingItem = nil
        case "noAttention":
            s.needsAttention = []
        case "multipleAttention":
            s.needsAttention = [
                assignmentNeedsInput,
                ActivityItem(id: "registration-form", title: "Conference registration form", status: .needsAttention,
                             destination: ToolDestination(label: "Browser", symbol: "↗"), summary: "Two required fields need your input"),
            ]
        case "longTitle":
            s.processingItem = nil
            s.needsAttention = []
            s.recentActivity = [longHealthcareEvent, buildNight, orientationDay]
        default:
            break
        }
        return s
    }
}
