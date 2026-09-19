import XCTest
@testable import Snapsort

/// The /analyze example from frontend.md §2.2.
private let analyzeJSON = """
{
  "proposals": [{
    "id": "3f9a1c0b7d2e", "action": "calendar.create", "decision": "auto_add",
    "payload": {
      "title": "Generative AI in Healthcare (talk)",
      "start": "2026-09-25T16:00:00+08:00", "end": "2026-09-25T17:30:00+08:00",
      "all_day": false, "timezone": "Asia/Hong_Kong",
      "location": { "name": "Main Building LG01, HKU", "online_url": null },
      "description": "Public lecture by Dr. Mei Chan",
      "some_future_field": 1
    },
    "confidence": 0.95, "evidence": "Fri 25 Sept · 4:00 – 5:30pm", "notes": ["parser_and_model_agree"]
  }],
  "genre": "poster", "skipped_reason": null, "model": "mock", "latency_ms": 8759
}
"""

final class APIContractTests: XCTestCase {
    func testDecodesAnalyzeResponse() throws {
        let r = try JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(analyzeJSON.utf8))
        XCTAssertEqual(r.latencyMs, 8759)
        let p = try XCTUnwrap(r.proposals.first)
        XCTAssertTrue(p.isAutoAdd)
        XCTAssertEqual(p.payload.location.name, "Main Building LG01, HKU")
        XCTAssertNil(p.payload.location.onlineUrl)
        XCTAssertEqual(p.prettyWhen, "Fri 25 Sep, 16:00")
        XCTAssertEqual(p.subtitle, "Fri 25 Sep, 16:00 · Main Building LG01, HKU")
        XCTAssertEqual(p.endDate!.timeIntervalSince(p.startDate!), 90 * 60)
    }

    func testUnknownDecisionIsNotAutoAdd() throws {
        let json = analyzeJSON.replacingOccurrences(of: "\"auto_add\"", with: "\"something_new\"")
        let r = try JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(json.utf8))
        XCTAssertFalse(r.proposals[0].isAutoAdd)
    }

    func testProposalRoundTripsThroughNotificationUserInfo() throws {
        let p = try JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(analyzeJSON.utf8)).proposals[0]
        XCTAssertEqual(Proposal.fromJSONString(try XCTUnwrap(p.jsonString)), p)
    }

    func testCapturedAtAlwaysHasExplicitOffset() {
        let date = Date(timeIntervalSince1970: 1_790_000_000)
        XCTAssertTrue(ProposalDates.isoWithOffset(date, timeZone: TimeZone(identifier: "UTC")!).hasSuffix("+00:00"))
        XCTAssertTrue(ProposalDates.isoWithOffset(date, timeZone: TimeZone(identifier: "Asia/Hong_Kong")!).hasSuffix("+08:00"))
    }

    func testAllDayDatesParse() {
        XCTAssertNotNil(ProposalDates.parse("2026-09-30", allDay: true))
        XCTAssertNil(ProposalDates.parse("not a date", allDay: false))
    }
}

@MainActor
final class HomeStateTests: XCTestCase {
    private func proposal(_ id: String) -> Proposal {
        Proposal(id: id, action: "calendar.create", decision: "ask",
                 payload: CalendarPayload(title: id, start: "2026-09-25T16:00:00+08:00", end: "2026-09-25T17:00:00+08:00",
                                          allDay: false, timezone: "Asia/Hong_Kong",
                                          location: EventLocation(name: nil, onlineUrl: nil), description: nil),
                 confidence: 0.6, evidence: "x", notes: nil)
    }

    func testSplitsNeedsInputFromRecentActivity() {
        var s = PersistedState()
        s.scanningEnabled = true
        s.activities = [
            proposal("ask").activity(.needsAttention, "Needs your confirmation"),
            proposal("done").activity(.executed, "Added to calendar", eventId: "E1"),
            proposal("gone").activity(.undone, "Action reversed"),
        ]
        let home = HomeUiState.make(from: s, processingSince: nil)
        XCTAssertEqual(home.needsAttention.map(\.id), ["ask"])
        XCTAssertEqual(home.recentActivity.map(\.id), ["done", "gone"])
        XCTAssertEqual(home.recentActivity.map(\.canUndo), [true, false])
        XCTAssertEqual(home.recentActivity[0].destination, HomeUiState.calendarDestination)
        XCTAssertNil(home.recentActivity[1].destination)
        XCTAssertEqual(home.agentStatus.kind, .active)
    }

    func testAgentStatusPriority() {
        var s = PersistedState()
        XCTAssertEqual(HomeUiState.make(from: s, processingSince: nil).agentStatus.kind, .inactive)
        s.scanningEnabled = true
        XCTAssertEqual(HomeUiState.make(from: s, processingSince: nil).agentStatus.kind, .active)
        s.lastError = "HTTP 502"
        XCTAssertEqual(HomeUiState.make(from: s, processingSince: nil).agentStatus.kind, .offline)
        let now = Date()
        let home = HomeUiState.make(from: s, processingSince: now.addingTimeInterval(-23), now: now)
        XCTAssertEqual(home.agentStatus.kind, .processing)
        XCTAssertEqual(home.processingItem?.activityTimestamp, "23s")
    }

    func testRelativeLabels() {
        XCTAssertEqual(HomeUiState.relativeLabel(10), "Just now")
        XCTAssertEqual(HomeUiState.relativeLabel(5 * 60), "5 min ago")
        XCTAssertEqual(HomeUiState.relativeLabel(3 * 3600), "3 h ago")
        XCTAssertEqual(HomeUiState.relativeLabel(2 * 86_400), "2 d ago")
    }

    func testStoreReplacesSameIdAndCapsFeed() {
        let store = Store(fileURL: nil)
        store.recordActivity(proposal("a").activity(.needsAttention, "x"))
        store.recordActivity(proposal("a").activity(.executed, "y", eventId: "E"))
        XCTAssertEqual(store.state.activities.count, 1)
        XCTAssertEqual(store.state.activities[0].status, .executed)
        for i in 0..<50 { store.recordActivity(proposal("p\(i)").activity(.skipped, "z")) }
        XCTAssertEqual(store.state.activities.count, Store.maxActivity)
        XCTAssertEqual(store.state.activities[0].id, "p49")
    }

    func testRetryQueueKeepsOriginalCaptureAndGivesUp() {
        let store = Store(fileURL: nil)
        let first = Date(timeIntervalSince1970: 1000)
        XCTAssertEqual(store.enqueue(assetId: "A", capturedAt: first), first)
        XCTAssertEqual(store.enqueue(assetId: "A", capturedAt: Date()), first)
        XCTAssertFalse(store.failPending("A"))
        XCTAssertFalse(store.failPending("A"))
        XCTAssertTrue(store.failPending("A"))
        XCTAssertTrue(store.state.pending.isEmpty)
    }

    func testServerURLIsTrimmed() {
        let store = Store(fileURL: nil)
        store.serverURL = "  http://192.168.1.5:8000/ "
        XCTAssertEqual(store.state.serverURL, "http://192.168.1.5:8000")
    }

    func testPersistsAcrossLaunches() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("snapsort-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: url) }
        let a = Store(fileURL: url)
        a.recordActivity(proposal("keep").activity(.executed, "Added", eventId: "E9"))
        a.markHandled("keep", eventId: "E9")
        let b = Store(fileURL: url)
        XCTAssertEqual(b.activity("keep")?.eventId, "E9")
        XCTAssertEqual(b.handledEventId("keep"), "E9")
        XCTAssertEqual(b.activity("keep")?.proposal?.id, "keep")
    }
}
