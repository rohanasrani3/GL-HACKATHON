package com.snapsort.app.ui.home

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.snapsort.app.home.ActivityItem
import com.snapsort.app.home.ActivityStatus
import com.snapsort.app.home.AgentStatus
import com.snapsort.app.home.AgentStatusKind
import com.snapsort.app.home.HomeUiState
import com.snapsort.app.home.RelaySampleData
import com.snapsort.app.home.ToolDestination
import com.snapsort.app.ui.theme.LaterRelayTheme

private val HomeHorizontalPadding = 20.dp

private data class StatusPresentation(val label: String, val color: Color)

@Composable
fun HomeScreen(
    state: HomeUiState,
    onUndo: (String) -> Unit,
    onReview: (String) -> Unit,
    onOverflow: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Vertical)),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                top = 18.dp,
                bottom = 32.dp,
            ),
        ) {
            item(key = "brand") {
                BrandHeader(onOverflow = onOverflow)
                Spacer(Modifier.height(18.dp))
                AgentStatusStrip(state.agentStatus)
                Spacer(Modifier.height(28.dp))
                AttentionSummary(state.needsAttention.size)
            }

            state.processingItem?.let { processing ->
                item(key = "processing-${processing.id}") {
                    Spacer(Modifier.height(18.dp))
                    ProcessingRow(processing)
                }
            }

            if (state.needsAttention.isNotEmpty()) {
                item(key = "attention-heading") {
                    Spacer(Modifier.height(30.dp))
                    SectionHeader(
                        title = "NEEDS YOUR INPUT",
                        trailing = state.needsAttention.size.toString().padStart(2, '0'),
                    )
                    Spacer(Modifier.height(10.dp))
                }
                items(state.needsAttention, key = { "attention-${it.id}" }) { item ->
                    NeedsInputItem(item = item, onReview = { onReview(item.id) })
                    Spacer(Modifier.height(12.dp))
                }
            }

            if (state.recentActivity.isNotEmpty()) {
                item(key = "recent-heading") {
                    Spacer(Modifier.height(22.dp))
                    SectionHeader(title = "RECENT ACTIVITY", trailing = "TODAY")
                }
                items(state.recentActivity, key = { "recent-${it.id}" }) { item ->
                    ActivityReceipt(item = item, onUndo = { onUndo(item.id) })
                }
            }
        }
    }
}

@Composable
private fun BrandHeader(onOverflow: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = HomeHorizontalPadding),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BrandMark()
        Spacer(Modifier.width(11.dp))
        Text(
            text = "later",
            color = MaterialTheme.colorScheme.onBackground,
            style = MaterialTheme.typography.titleMedium.copy(
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
            ),
        )
        Text(
            text = ".exe",
            color = MaterialTheme.colorScheme.secondary,
            style = MaterialTheme.typography.titleMedium.copy(
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
            ),
        )
        Spacer(Modifier.weight(1f))
        TextButton(
            onClick = onOverflow,
            modifier = Modifier
                .size(48.dp)
                .semantics { contentDescription = "Open settings and agent controls" },
            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
        ) {
            Text(
                text = "•••",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelLarge,
            )
        }
    }
}

@Composable
private fun BrandMark() {
    val color = MaterialTheme.colorScheme.secondary
    Canvas(
        modifier = Modifier
            .size(24.dp)
            .semantics { contentDescription = "later.exe" },
    ) {
        val stroke = size.minDimension * 0.19f
        drawLine(
            color = color,
            start = Offset(stroke / 2, stroke / 2),
            end = Offset(stroke / 2, size.height - stroke / 2),
            strokeWidth = stroke,
            cap = StrokeCap.Square,
        )
        drawLine(
            color = color,
            start = Offset(stroke / 2, size.height - stroke / 2),
            end = Offset(size.width * 0.6f, size.height - stroke / 2),
            strokeWidth = stroke,
            cap = StrokeCap.Square,
        )
        drawRect(
            color = color,
            topLeft = Offset(size.width * 0.68f, size.height * 0.12f),
            size = androidx.compose.ui.geometry.Size(size.width * 0.28f, size.height * 0.28f),
        )
    }
}

@Composable
private fun AgentStatusStrip(status: AgentStatus) {
    val presentation = when (status.kind) {
        AgentStatusKind.ACTIVE -> StatusPresentation("LIVE", MaterialTheme.colorScheme.primary)
        AgentStatusKind.PROCESSING -> StatusPresentation("WORKING", MaterialTheme.colorScheme.primary)
        AgentStatusKind.OFFLINE -> StatusPresentation("RETRYING", MaterialTheme.colorScheme.tertiary)
        AgentStatusKind.INACTIVE -> StatusPresentation("INACTIVE", MaterialTheme.colorScheme.outline)
    }
    val accent = presentation.color
    val stateLabel = presentation.label
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = HomeHorizontalPadding)
            .background(MaterialTheme.colorScheme.surface)
            .semantics {
                contentDescription = "$stateLabel. ${status.primaryText}. ${status.secondaryText}"
            },
    ) {
        Box(
            modifier = Modifier
                .width(3.dp)
                .height(58.dp)
                .background(accent),
        )
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(horizontal = 14.dp, vertical = 9.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = status.primaryText,
                    modifier = Modifier.weight(1f),
                    color = MaterialTheme.colorScheme.onSurface,
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
                )
                Text(
                    text = "● $stateLabel",
                    color = accent,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            Text(
                text = status.secondaryText,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun AttentionSummary(count: Int) {
    Column(modifier = Modifier.padding(horizontal = HomeHorizontalPadding)) {
        Text(
            text = when (count) {
                0 -> "Nothing needs you."
                1 -> "Just 1 thing for you."
                else -> "Just $count things for you."
            },
            color = MaterialTheme.colorScheme.onBackground,
            style = MaterialTheme.typography.headlineMedium,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = if (count == 0) {
                "The agent is handling things quietly."
            } else {
                "The agent is handling the rest."
            },
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun ProcessingRow(item: ActivityItem) {
    val presentation = activityStatusPresentation(item.status)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = HomeHorizontalPadding)
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .semantics {
                contentDescription = "${presentation.label}. ${item.title}. ${item.summary}. ${item.activityTimestamp.orEmpty()}"
            },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = presentation.label,
            color = presentation.color,
            style = MaterialTheme.typography.labelMedium,
        )
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = item.title,
                color = MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
            )
            Text(
                text = item.summary,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        item.activityTimestamp?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelMedium,
            )
        }
    }
}

@Composable
private fun SectionHeader(title: String, trailing: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = HomeHorizontalPadding, vertical = 10.dp),
    ) {
        Text(
            text = title,
            modifier = Modifier.weight(1f),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.labelMedium,
        )
        Text(
            text = trailing,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.labelMedium,
        )
    }
}

@Composable
private fun NeedsInputItem(
    item: ActivityItem,
    onReview: () -> Unit,
) {
    val shape = RoundedCornerShape(3.dp)
    Column(
        modifier = Modifier
            .padding(horizontal = HomeHorizontalPadding)
            .fillMaxWidth()
            .clip(shape)
            .border(1.dp, MaterialTheme.colorScheme.outline, shape)
            .background(MaterialTheme.colorScheme.surface)
            .padding(16.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = "! NEEDS INPUT",
                modifier = Modifier.weight(1f),
                color = MaterialTheme.colorScheme.tertiary,
                style = MaterialTheme.typography.labelMedium,
            )
            item.activityTimestamp?.let {
                Text(
                    text = it,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            text = item.title,
            color = MaterialTheme.colorScheme.onSurface,
            style = MaterialTheme.typography.titleLarge,
        )
        Spacer(Modifier.height(5.dp))
        Text(
            text = item.summary,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
        )
        item.eventTime?.let {
            Spacer(Modifier.height(4.dp))
            Text(
                text = it,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        item.destination?.let {
            Spacer(Modifier.height(14.dp))
            DestinationLabel(it)
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = onReview,
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp)
                .semantics { contentDescription = "Review ${item.title}" },
            colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.onSurface,
                contentColor = MaterialTheme.colorScheme.background,
            ),
            shape = RoundedCornerShape(2.dp),
        ) {
            Text(text = "Review details  →", style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun ActivityReceipt(
    item: ActivityItem,
    onUndo: () -> Unit,
) {
    val presentation = activityStatusPresentation(item.status)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = HomeHorizontalPadding, vertical = 17.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = presentation.label,
                modifier = Modifier.weight(1f),
                color = presentation.color,
                style = MaterialTheme.typography.labelMedium,
            )
            item.activityTimestamp?.let {
                Text(
                    text = it,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(
            text = item.title,
            color = MaterialTheme.colorScheme.onSurface,
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(Modifier.height(3.dp))
        Text(
            text = item.summary,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium,
        )
        item.eventTime?.let {
            Spacer(Modifier.height(3.dp))
            Text(
                text = it,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Spacer(Modifier.height(11.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            item.destination?.let {
                Box(modifier = Modifier.weight(1f)) { DestinationLabel(it) }
            } ?: Spacer(Modifier.weight(1f))
            if (item.canUndo) {
                TextButton(
                    onClick = onUndo,
                    modifier = Modifier
                        .height(48.dp)
                        .semantics { contentDescription = "Undo ${item.title}" },
                ) {
                    Text(
                        text = "Undo",
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }
        }
    }
    Box(
        modifier = Modifier
            .padding(horizontal = HomeHorizontalPadding)
            .fillMaxWidth()
            .height(1.dp)
            .background(MaterialTheme.colorScheme.outline),
    )
}

@Composable
private fun activityStatusPresentation(status: ActivityStatus): StatusPresentation = when (status) {
    ActivityStatus.PROCESSING -> StatusPresentation("· READING", MaterialTheme.colorScheme.primary)
    ActivityStatus.EXECUTED -> StatusPresentation("✓ EXECUTED", MaterialTheme.colorScheme.primary)
    ActivityStatus.NEEDS_ATTENTION -> StatusPresentation("! NEEDS INPUT", MaterialTheme.colorScheme.tertiary)
    ActivityStatus.UNDONE -> StatusPresentation("↩ UNDONE", MaterialTheme.colorScheme.onSurfaceVariant)
    ActivityStatus.DISMISSED -> StatusPresentation("× DISMISSED", MaterialTheme.colorScheme.onSurfaceVariant)
    ActivityStatus.SKIPPED -> StatusPresentation("SKIPPED", MaterialTheme.colorScheme.onSurfaceVariant)
    ActivityStatus.FAILED -> StatusPresentation("! FAILED", MaterialTheme.colorScheme.tertiary)
    ActivityStatus.RETRYING -> StatusPresentation("↻ RETRYING", MaterialTheme.colorScheme.tertiary)
}

@Composable
private fun DestinationLabel(destination: ToolDestination) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.semantics {
            contentDescription = "Destination: ${destination.label}"
        },
    ) {
        Box(
            modifier = Modifier
                .size(22.dp)
                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(2.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = destination.symbol,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelMedium,
            )
        }
        Spacer(Modifier.width(8.dp))
        Text(
            text = destination.label,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Preview(name = "Relay — default", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun DefaultHomePreview() = PreviewHome(RelaySampleData.defaultState)

@Preview(name = "Relay — processing", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun ProcessingHomePreview() = PreviewHome(RelaySampleData.processing)

@Preview(name = "Relay — offline", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun OfflineHomePreview() = PreviewHome(RelaySampleData.offlineRetrying)

@Preview(name = "Relay — inactive", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun InactiveHomePreview() = PreviewHome(RelaySampleData.inactive)

@Preview(name = "Relay — no attention", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun NoAttentionHomePreview() = PreviewHome(RelaySampleData.noAttention)

@Preview(name = "Relay — multiple attention", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun MultipleAttentionHomePreview() = PreviewHome(RelaySampleData.multipleAttention)

@Preview(name = "Relay — long title", showBackground = true, widthDp = 320, heightDp = 760, fontScale = 1.3f)
@Composable
private fun LongTitleHomePreview() = PreviewHome(RelaySampleData.longTitle)

@Composable
private fun PreviewHome(state: HomeUiState) {
    LaterRelayTheme {
        HomeScreen(
            state = state,
            onUndo = {},
            onReview = {},
            onOverflow = {},
        )
    }
}
