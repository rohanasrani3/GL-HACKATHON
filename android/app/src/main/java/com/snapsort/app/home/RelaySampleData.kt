package com.snapsort.app.home

/**
 * Demo-only fixtures for previews and the first visual host.
 *
 * These values deliberately do not read production storage or platform services.
 */
object RelaySampleData {
    private val googleCalendar = CALENDAR   // the real chip, so previews can't drift from runtime

    private val activeAgent = AgentStatus(
        kind = AgentStatusKind.ACTIVE,
        primaryText = "Watching screenshots",
        secondaryText = "Last scan · just now",
    )

    private val processingScreenshot = ActivityItem(
        id = "processing-screenshot",
        title = "Screenshot detected",
        status = ActivityStatus.PROCESSING,
        summary = "Understanding action…",
        activityTimestamp = "8s",
    )

    private val assignmentNeedsInput = ActivityItem(
        id = "comp3230-assignment",
        title = "COMP3230 Assignment",
        status = ActivityStatus.NEEDS_ATTENTION,
        destination = googleCalendar,
        summary = "Deadline unclear",
    )

    private val buildNight = ActivityItem(
        id = "build-night",
        title = "Build Night",
        status = ActivityStatus.EXECUTED,
        destination = googleCalendar,
        summary = "Added to calendar",
        eventTime = "Sep 22 · 17:00–19:00",
        activityTimestamp = "Just now",
        canUndo = true,
    )

    private val orientationDay = ActivityItem(
        id = "dsa-orientation-day",
        title = "DSA Orientation Day",
        status = ActivityStatus.EXECUTED,
        destination = googleCalendar,
        summary = "Added to calendar",
        eventTime = "Sep 27 · 12:00",
        activityTimestamp = "2 min ago",
        canUndo = true,
    )

    private val longHealthcareEvent = ActivityItem(
        id = "generative-ai-healthcare",
        title = "Generative AI in Healthcare: Building Safe Clinical Systems",
        status = ActivityStatus.EXECUTED,
        destination = googleCalendar,
        summary = "Added to calendar",
        eventTime = "Oct 3 · 18:30–20:00",
        activityTimestamp = "5 min ago",
        canUndo = true,
    )

    val defaultState = HomeUiState(
        agentStatus = activeAgent,
        processingItem = processingScreenshot,
        needsAttention = listOf(assignmentNeedsInput),
        recentActivity = listOf(buildNight, orientationDay, longHealthcareEvent),
    )

    val processing = defaultState.copy(
        agentStatus = AgentStatus(
            kind = AgentStatusKind.PROCESSING,
            primaryText = "Reading screenshot",
            secondaryText = "Understanding actionable information",
        ),
    )

    val offlineRetrying = defaultState.copy(
        agentStatus = AgentStatus(
            kind = AgentStatusKind.OFFLINE,
            primaryText = "Server unavailable",
            secondaryText = "Will retry automatically",
        ),
        processingItem = ActivityItem(
            id = "retrying-upload",
            title = "Screenshot upload failed",
            status = ActivityStatus.RETRYING,
            summary = "Will retry automatically",
        ),
    )

    val inactive = defaultState.copy(
        agentStatus = AgentStatus(
            kind = AgentStatusKind.INACTIVE,
            primaryText = "Screenshot monitoring stopped",
            secondaryText = "Open Settings to resume",
        ),
        processingItem = null,
    )

    val noAttention = defaultState.copy(needsAttention = emptyList())

    val multipleAttention = defaultState.copy(
        needsAttention = listOf(
            assignmentNeedsInput,
            ActivityItem(
                id = "registration-form",
                title = "Conference registration form",
                status = ActivityStatus.NEEDS_ATTENTION,
                destination = ToolDestination(label = "Browser", symbol = "↗"),
                summary = "Two required fields need your input",
            ),
        ),
    )

    val longTitle = defaultState.copy(
        processingItem = null,
        needsAttention = emptyList(),
        recentActivity = listOf(longHealthcareEvent, buildNight, orientationDay),
    )
}
