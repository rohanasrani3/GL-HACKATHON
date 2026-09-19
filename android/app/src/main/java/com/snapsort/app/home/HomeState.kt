package com.snapsort.app.home

import com.snapsort.app.ActivityRecord
import com.snapsort.app.Store

/**
 * Builds the Home state from real storage.
 *
 * [RelaySampleData] stays in place for @Preview only. Anything the user actually sees at runtime
 * comes through here, so the feed always matches the notifications the pipeline posted.
 */

private val CALENDAR = ToolDestination(label = "Google Calendar", symbol = "G")

/** Statuses that belong in the "needs input" section rather than the receipt list. */
private const val ATTENTION = ActivityRecord.NEEDS_ATTENTION

fun Store.toHomeUiState(now: Long = System.currentTimeMillis()): HomeUiState {
    val records = activities()
    val processingSince = this.processingSince

    val processingItem = if (processingSince > 0L) {
        ActivityItem(
            id = "processing",
            title = "Screenshot detected",
            status = ActivityStatus.PROCESSING,
            summary = "Understanding action…",
            activityTimestamp = elapsedLabel(now - processingSince),
        )
    } else {
        null
    }

    return HomeUiState(
        agentStatus = agentStatus(processingSince > 0L, now),
        processingItem = processingItem,
        needsAttention = records.filter { it.status == ATTENTION }.map { it.toItem(now) },
        recentActivity = records.filter { it.status != ATTENTION }.map { it.toItem(now) },
    )
}

private fun Store.agentStatus(processing: Boolean, now: Long): AgentStatus = when {
    processing -> AgentStatus(
        kind = AgentStatusKind.PROCESSING,
        primaryText = "Reading screenshot",
        secondaryText = "Understanding actionable information",
    )

    lastError != null -> AgentStatus(
        kind = AgentStatusKind.OFFLINE,
        primaryText = "Server unavailable",
        secondaryText = lastError?.take(80) ?: "Will retry automatically",
    )

    watcherRunning -> AgentStatus(
        kind = AgentStatusKind.ACTIVE,
        primaryText = "Watching screenshots",
        secondaryText = if (lastScanAt > 0L) "Last scan · ${relativeLabel(now - lastScanAt)}" else "Waiting for the first scan",
    )

    else -> AgentStatus(
        kind = AgentStatusKind.INACTIVE,
        primaryText = "Screenshot monitoring stopped",
        secondaryText = "Open Settings to resume",
    )
}

private fun ActivityRecord.toItem(now: Long) = ActivityItem(
    id = id,
    title = title,
    status = runCatching { ActivityStatus.valueOf(status) }.getOrDefault(ActivityStatus.EXECUTED),
    destination = if (status == ActivityRecord.EXECUTED || status == ActivityRecord.NEEDS_ATTENTION) CALENDAR else null,
    summary = summary,
    eventTime = eventTime,
    activityTimestamp = relativeLabel(now - timestamp),
    // Undo needs the calendar row we wrote; without an eventId there is nothing to reverse.
    canUndo = status == ActivityRecord.EXECUTED && eventId != null,
)

private fun relativeLabel(deltaMs: Long): String {
    val mins = deltaMs / 60_000
    return when {
        mins < 1 -> "Just now"
        mins < 60 -> "$mins min ago"
        mins < 1440 -> "${mins / 60} h ago"
        else -> "${mins / 1440} d ago"
    }
}

private fun elapsedLabel(deltaMs: Long): String = "${(deltaMs / 1000).coerceAtLeast(0)}s"
