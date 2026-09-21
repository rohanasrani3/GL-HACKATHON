import Foundation

// Builds Home from real storage. Port of android/.../home/HomeState.kt, so both apps
// derive the same screen from the same activity records.

extension HomeUiState {
    static let calendarDestination = ToolDestination(label: "Calendar", symbol: "C")

    static func make(from s: PersistedState, processingSince: Date?, now: Date = Date()) -> HomeUiState {
        let processingItem = processingSince.map {
            ActivityItem(
                id: "processing",
                title: "Screenshot detected",
                status: .processing,
                summary: "Understanding action…",
                activityTimestamp: elapsedLabel(now.timeIntervalSince($0))
            )
        }
        return HomeUiState(
            agentStatus: agentStatus(s, processing: processingSince != nil, now: now),
            processingItem: processingItem,
            needsAttention: s.activities.filter { $0.status == .needsAttention }.map { item($0, now: now) },
            recentActivity: s.activities.filter { $0.status != .needsAttention }.map { item($0, now: now) }
        )
    }

    static func agentStatus(_ s: PersistedState, processing: Bool, now: Date) -> AgentStatus {
        if processing {
            return AgentStatus(kind: .processing, primaryText: "Reading screenshot", secondaryText: "Understanding actionable information")
        }
        if let error = s.lastError {
            return AgentStatus(kind: .offline, primaryText: "Server unavailable", secondaryText: String(error.prefix(80)))
        }
        if s.scanningEnabled {
            let secondary = s.lastScanAt.map { "Last scan · \(relativeLabel(now.timeIntervalSince($0)))" } ?? "Waiting for the first scan"
            return AgentStatus(kind: .active, primaryText: "Watching screenshots", secondaryText: secondary)
        }
        return AgentStatus(kind: .inactive, primaryText: "Screenshot monitoring stopped", secondaryText: "Open Settings to resume")
    }

    static func item(_ r: ActivityRecord, now: Date) -> ActivityItem {
        ActivityItem(
            id: r.id,
            title: r.title,
            status: r.status,
            destination: r.form.map { ToolDestination(label: $0.destinationLabel, symbol: "≡") }
                ?? ((r.status == .executed || r.status == .needsAttention) ? calendarDestination : nil),
            summary: r.summary,
            eventTime: r.eventTime,
            activityTimestamp: relativeLabel(now.timeIntervalSince(r.timestamp)),
            // Undo needs the calendar event we wrote; without an eventId there is nothing to reverse.
            canUndo: r.status == .executed && r.eventId != nil
        )
    }

    static func relativeLabel(_ seconds: TimeInterval) -> String {
        let mins = Int(seconds / 60)
        switch mins {
        case ..<1: return "Just now"
        case ..<60: return "\(mins) min ago"
        case ..<1440: return "\(mins / 60) h ago"
        default: return "\(mins / 1440) d ago"
        }
    }

    static func elapsedLabel(_ seconds: TimeInterval) -> String { "\(max(0, Int(seconds)))s" }
}
