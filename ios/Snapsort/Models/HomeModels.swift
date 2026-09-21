import Foundation

// Presentation models for Home. Port of android/.../home/HomeModels.kt: views receive
// already-decided state and never look at confidence or re-run the policy gate.

enum AgentStatusKind: Equatable {
    case active, processing, offline, inactive
}

struct AgentStatus: Equatable {
    var kind: AgentStatusKind
    var primaryText: String
    var secondaryText: String
}

enum ActivityStatus: String, Codable, CaseIterable {
    case processing = "PROCESSING"
    case executed = "EXECUTED"
    case needsAttention = "NEEDS_ATTENTION"
    case undone = "UNDONE"
    case dismissed = "DISMISSED"
    case skipped = "SKIPPED"
    case failed = "FAILED"
    case retrying = "RETRYING"

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ActivityStatus(rawValue: raw) ?? .executed
    }
}

struct ToolDestination: Equatable {
    var label: String
    var symbol: String
}

struct ActivityItem: Identifiable, Equatable {
    var id: String
    var title: String
    var status: ActivityStatus
    var destination: ToolDestination? = nil
    var summary: String
    var eventTime: String? = nil
    var activityTimestamp: String? = nil
    var canUndo: Bool = false
}

struct HomeUiState: Equatable {
    var agentStatus: AgentStatus
    var processingItem: ActivityItem? = nil
    var needsAttention: [ActivityItem] = []
    var recentActivity: [ActivityItem] = []
}
