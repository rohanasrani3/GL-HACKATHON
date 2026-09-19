package com.snapsort.app.home

enum class AgentStatusKind {
    ACTIVE,
    PROCESSING,
    OFFLINE,
    INACTIVE,
}

data class AgentStatus(
    val kind: AgentStatusKind,
    val primaryText: String,
    val secondaryText: String,
)

enum class ActivityStatus {
    PROCESSING,
    EXECUTED,
    NEEDS_ATTENTION,
    UNDONE,
    DISMISSED,
    SKIPPED,
    FAILED,
    RETRYING,
}

data class ToolDestination(
    val label: String,
    val symbol: String,
)

data class ActivityItem(
    val id: String,
    val title: String,
    val status: ActivityStatus,
    val destination: ToolDestination? = null,
    val summary: String,
    val eventTime: String? = null,
    val activityTimestamp: String? = null,
    val canUndo: Boolean = false,
)

data class HomeUiState(
    val agentStatus: AgentStatus,
    val processingItem: ActivityItem? = null,
    val needsAttention: List<ActivityItem> = emptyList(),
    val recentActivity: List<ActivityItem> = emptyList(),
)
