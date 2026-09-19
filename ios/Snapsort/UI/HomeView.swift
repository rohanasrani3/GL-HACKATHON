import SwiftUI

/// later.exe Home, "Relay" direction. Port of android/.../ui/home/HomeScreen.kt.
/// Receives already-decided presentation state and emits user intents through callbacks.
struct HomeView: View {
    let state: HomeUiState
    var onUndo: (String) -> Void = { _ in }
    var onReview: (String) -> Void = { _ in }
    var onOverflow: () -> Void = {}
    var onRefresh: (() async -> Void)? = nil

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                BrandHeader(onOverflow: onOverflow)
                Spacer().frame(height: 18)
                AgentStatusStrip(status: state.agentStatus)
                Spacer().frame(height: 28)
                AttentionSummary(count: state.needsAttention.count)

                if let processing = state.processingItem {
                    Spacer().frame(height: 18)
                    ProcessingRow(item: processing)
                }

                if !state.needsAttention.isEmpty {
                    Spacer().frame(height: 30)
                    SectionHeader(title: "NEEDS YOUR INPUT", trailing: String(format: "%02d", state.needsAttention.count))
                    Spacer().frame(height: 10)
                    ForEach(state.needsAttention) { item in
                        NeedsInputCard(item: item, onReview: { onReview(item.id) })
                        Spacer().frame(height: 12)
                    }
                }

                if !state.recentActivity.isEmpty {
                    Spacer().frame(height: 22)
                    SectionHeader(title: "RECENT ACTIVITY", trailing: "TODAY")
                    ForEach(state.recentActivity) { item in
                        ActivityReceipt(item: item, onUndo: { onUndo(item.id) })
                    }
                }
            }
            .padding(.top, 18)
            .padding(.bottom, 32)
        }
        .scrollIndicators(.hidden)
        .refreshable { await onRefresh?() }
        .background(Relay.background.ignoresSafeArea())
    }
}

// MARK: - Components

private struct BrandHeader: View {
    let onOverflow: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            BrandMark()
            Spacer().frame(width: 11)
            Text("later").font(RelayFont.brand).foregroundStyle(Relay.textPrimary)
            Text(".exe").font(RelayFont.brand).foregroundStyle(Relay.lime)
            Spacer()
            Button(action: onOverflow) {
                Text("•••").font(RelayFont.labelLarge).foregroundStyle(Relay.textMuted)
                    .frame(width: 48, height: 48)
            }
            .accessibilityLabel("Open settings and agent controls")
        }
        .padding(.horizontal, Relay.gutter)
    }
}

/// Geometric later.exe mark: an "L" stroke plus a small square.
struct BrandMark: View {
    var body: some View {
        Canvas { ctx, size in
            let stroke = min(size.width, size.height) * 0.19
            var path = Path()
            path.move(to: CGPoint(x: stroke / 2, y: stroke / 2))
            path.addLine(to: CGPoint(x: stroke / 2, y: size.height - stroke / 2))
            path.addLine(to: CGPoint(x: size.width * 0.6, y: size.height - stroke / 2))
            ctx.stroke(path, with: .color(Relay.lime), style: StrokeStyle(lineWidth: stroke, lineCap: .square, lineJoin: .miter))
            ctx.fill(
                Path(CGRect(x: size.width * 0.68, y: size.height * 0.12, width: size.width * 0.28, height: size.height * 0.28)),
                with: .color(Relay.lime)
            )
        }
        .frame(width: 24, height: 24)
        .accessibilityLabel("later.exe")
    }
}

private struct AgentStatusStrip: View {
    let status: AgentStatus

    private var presentation: (label: String, color: Color) {
        switch status.kind {
        case .active: return ("LIVE", Relay.green)
        case .processing: return ("WORKING", Relay.green)
        case .offline: return ("RETRYING", Relay.amber)
        case .inactive: return ("INACTIVE", Relay.border)
        }
    }

    var body: some View {
        let p = presentation
        HStack(spacing: 0) {
            Rectangle().fill(p.color).frame(width: 3)
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .center) {
                    Text(status.primaryText)
                        .font(RelayFont.bodyMediumStrong)
                        .foregroundStyle(Relay.textPrimary)
                    Spacer(minLength: 8)
                    Text("● \(p.label)").relayLabel(p.color)
                }
                Text(status.secondaryText)
                    .font(RelayFont.bodyMedium)
                    .foregroundStyle(Relay.textMuted)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .frame(minHeight: 58, alignment: .leading)
        }
        .fixedSize(horizontal: false, vertical: true)
        .background(Relay.surface)
        .padding(.horizontal, Relay.gutter)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(p.label). \(status.primaryText). \(status.secondaryText)")
    }
}

private struct AttentionSummary: View {
    let count: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(count == 0 ? "Nothing needs you." : count == 1 ? "Just 1 thing for you." : "Just \(count) things for you.")
                .font(RelayFont.headline)
                .foregroundStyle(Relay.textPrimary)
            Text(count == 0 ? "The agent is handling things quietly." : "The agent is handling the rest.")
                .font(RelayFont.bodyMedium)
                .foregroundStyle(Relay.textMuted)
        }
        .padding(.horizontal, Relay.gutter)
    }
}

private struct ProcessingRow: View {
    let item: ActivityItem

    var body: some View {
        let p = statusPresentation(item.status)
        HStack(spacing: 10) {
            Text(p.label).relayLabel(p.color)
            VStack(alignment: .leading, spacing: 0) {
                Text(item.title).font(RelayFont.bodyMediumStrong).foregroundStyle(Relay.textPrimary)
                Text(item.summary).font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
            }
            Spacer(minLength: 0)
            if let t = item.activityTimestamp { Text(t).relayLabel() }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Relay.surface)
        .padding(.horizontal, Relay.gutter)
        .accessibilityElement(children: .combine)
    }
}

private struct SectionHeader: View {
    let title: String
    let trailing: String

    var body: some View {
        HStack {
            Text(title).relayLabel()
            Spacer()
            Text(trailing).relayLabel()
        }
        .padding(.horizontal, Relay.gutter)
        .padding(.vertical, 10)
    }
}

private struct NeedsInputCard: View {
    let item: ActivityItem
    let onReview: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("! NEEDS INPUT").relayLabel(Relay.amber)
                Spacer()
                if let t = item.activityTimestamp { Text(t).relayLabel() }
            }
            Spacer().frame(height: 12)
            Text(item.title).font(RelayFont.titleLarge).foregroundStyle(Relay.textPrimary)
            Spacer().frame(height: 5)
            Text(item.summary).font(RelayFont.bodyLarge).foregroundStyle(Relay.textMuted)
            if let when = item.eventTime {
                Spacer().frame(height: 4)
                Text(when).font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
            }
            if let destination = item.destination {
                Spacer().frame(height: 14)
                DestinationLabel(destination: destination)
            }
            Spacer().frame(height: 16)
            Button("Review details  →", action: onReview)
                .buttonStyle(RelayFilledButtonStyle())
                .accessibilityLabel("Review \(item.title)")
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Relay.surface)
        .overlay(RoundedRectangle(cornerRadius: 3).stroke(Relay.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 3))
        .padding(.horizontal, Relay.gutter)
    }
}

private struct ActivityReceipt: View {
    let item: ActivityItem
    let onUndo: () -> Void

    var body: some View {
        let p = statusPresentation(item.status)
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(p.label).relayLabel(p.color)
                Spacer()
                if let t = item.activityTimestamp { Text(t).relayLabel() }
            }
            Spacer().frame(height: 8)
            Text(item.title).font(RelayFont.titleMedium).foregroundStyle(Relay.textPrimary)
            Spacer().frame(height: 3)
            Text(item.summary).font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
            if let when = item.eventTime {
                Spacer().frame(height: 3)
                Text(when).font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
            }
            Spacer().frame(height: 11)
            HStack {
                if let destination = item.destination { DestinationLabel(destination: destination) }
                Spacer()
                if item.canUndo {
                    Button(action: onUndo) {
                        Text("Undo").font(RelayFont.labelLarge).tracking(0.5).foregroundStyle(Relay.green)
                            .padding(.horizontal, 12)
                            .frame(minHeight: 48)
                    }
                    .accessibilityLabel("Undo \(item.title)")
                }
            }
            .frame(minHeight: item.canUndo ? 48 : 22)
        }
        .padding(.horizontal, Relay.gutter)
        .padding(.vertical, 17)
        .frame(maxWidth: .infinity, alignment: .leading)

        Rectangle().fill(Relay.border).frame(height: 1).padding(.horizontal, Relay.gutter)
    }
}

private struct DestinationLabel: View {
    let destination: ToolDestination

    var body: some View {
        HStack(spacing: 8) {
            Text(destination.symbol)
                .relayLabel()
                .frame(width: 22, height: 22)
                .overlay(RoundedRectangle(cornerRadius: 2).stroke(Relay.border, lineWidth: 1))
            Text(destination.label).font(RelayFont.bodyMedium).foregroundStyle(Relay.textMuted)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Destination: \(destination.label)")
    }
}

func statusPresentation(_ status: ActivityStatus) -> (label: String, color: Color) {
    switch status {
    case .processing: return ("· READING", Relay.green)
    case .executed: return ("✓ EXECUTED", Relay.green)
    case .needsAttention: return ("! NEEDS INPUT", Relay.amber)
    case .undone: return ("↩ UNDONE", Relay.textMuted)
    case .dismissed: return ("× DISMISSED", Relay.textMuted)
    case .skipped: return ("SKIPPED", Relay.textMuted)
    case .failed: return ("! FAILED", Relay.amber)
    case .retrying: return ("↻ RETRYING", Relay.amber)
    }
}

#Preview("Relay — default") { HomeView(state: SampleData.defaultState) }
#Preview("Relay — offline") { HomeView(state: SampleData.state(named: "offline")) }
#Preview("Relay — inactive") { HomeView(state: SampleData.state(named: "inactive")) }
#Preview("Relay — multiple attention") { HomeView(state: SampleData.state(named: "multipleAttention")) }
