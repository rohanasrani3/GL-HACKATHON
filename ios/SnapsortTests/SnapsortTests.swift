import CoreImage.CIFilterBuiltins
import UIKit
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

/// v3 forms: the /analyze `forms` shape from backend/snapsort/schema.py.
private let formJSON = """
{
  "proposals": [], "genre": "poster", "skipped_reason": null, "model": "mock", "latency_ms": 10,
  "links": [{"url": "https://forms.gle/x", "domain": "forms.gle", "title": null, "description": null, "is_form": true, "source": "qr"}],
  "forms": [{
    "id": "f1", "action": "form.prefill", "decision": "ask", "confidence": 0.9, "evidence": "forms.gle/x", "notes": [],
    "payload": {
      "form_url": "https://docs.google.com/forms/d/e/ABC/viewform?usp=sf_link",
      "title": "Talk signup", "domain": "docs.google.com", "prefill_style": "google_forms",
      "provider": "google_forms", "reasons": ["Google Forms link"],
      "fields": [
        {"entry_id": "entry.1", "question": "Your name", "profile_key": "full_name", "required": true, "type": "short_text", "options": [], "sensitive": false},
        {"entry_id": "entry.2", "question": "Email", "profile_key": "email", "required": true, "type": "short_text", "options": []},
        {"entry_id": "entry.3", "question": "Session", "profile_key": null, "required": false, "type": "multiple_choice", "options": ["AM", "PM"]},
        {"entry_id": "entry.4", "question": "Passport number", "profile_key": null, "sensitive": true}
      ]
    }
  }]
}
"""

@MainActor
final class FormTests: XCTestCase {
    private func form() throws -> FormProposal {
        try XCTUnwrap(JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(formJSON.utf8)).forms?.first)
    }

    func testDecodesFormsAndLinks() throws {
        let r = try JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(formJSON.utf8))
        XCTAssertEqual(r.links?.first?.isForm, true)
        let f = try form()
        XCTAssertEqual(f.payload.fields.map(\.entryId), ["entry.1", "entry.2", "entry.3", "entry.4"])
        XCTAssertTrue(f.payload.fields[3].isSensitive)
        XCTAssertFalse(f.payload.fields[1].isSensitive) // missing "sensitive" defaults to false
        XCTAssertTrue(f.canPrefill)
        XCTAssertEqual(f.destinationLabel, "Google Forms")
    }

    func testPrefillURLNeverContainsSensitiveFields() throws {
        let url = try XCTUnwrap(try form().prefillURL(values: [
            "entry.1": "Ada Lovelace", "entry.2": "ada+talk@example.com", "entry.3": "PM", "entry.4": "K1234567",
        ]))
        let s = url.absoluteString
        XCTAssertTrue(s.hasPrefix("https://docs.google.com/forms/d/e/ABC/viewform?usp=pp_url&entry.1=Ada%20Lovelace"))
        XCTAssertTrue(s.contains("entry.2=ada%2Btalk@example.com"))
        XCTAssertTrue(s.contains("entry.3=PM"))
        XCTAssertFalse(s.contains("entry.4"))
        XCTAssertFalse(s.contains("K1234567"))
        XCTAssertFalse(s.contains("sf_link")) // original query replaced, like Android's clearQuery()
    }

    func testNoPrefillStyleOpensTheOriginalLink() throws {
        let json = formJSON.replacingOccurrences(of: "\"prefill_style\": \"google_forms\"", with: "\"prefill_style\": \"none\"")
        let f = try XCTUnwrap(JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(json.utf8)).forms?.first)
        XCTAssertFalse(f.canPrefill)
        XCTAssertEqual(f.prefillURL(values: ["entry.1": "x"])?.absoluteString, f.payload.formUrl)
    }

    func testProfileSeedsKnownAnswersOnly() throws {
        let suite = "snapsort-tests-\(UUID().uuidString)"
        let profile = Profile(defaults: UserDefaults(suiteName: suite)!)
        defer { UserDefaults().removePersistentDomain(forName: suite) }
        profile.putAll(["full_name": "Ada", "email": "  ", "student_id": "3035"])
        let f = try form()
        XCTAssertEqual(f.seededValues(from: profile), ["entry.1": "Ada"])
        XCTAssertEqual(f.missingCount(profile: profile), 3) // email blank, session and passport have no key
    }

    func testFormRecordsShowFormDestination() throws {
        var s = PersistedState()
        s.activities = [try form().activity(.needsAttention, "2 answers needed")]
        let home = HomeUiState.make(from: s, processingSince: nil)
        XCTAssertEqual(home.needsAttention.first?.destination?.label, "Google Forms")
        XCTAssertEqual(home.needsAttention.first?.eventTime, "docs.google.com")
    }

    func testMultiDayAllDayRange() throws {
        let json = analyzeJSON
            .replacingOccurrences(of: "\"2026-09-25T16:00:00+08:00\"", with: "\"2026-10-12\"")
            .replacingOccurrences(of: "\"2026-09-25T17:30:00+08:00\"", with: "\"2026-10-17\"")
            .replacingOccurrences(of: "\"all_day\": false", with: "\"all_day\": true")
        let p = try JSONDecoder.api.decode(AnalyzeResponse.self, from: Data(json.utf8)).proposals[0]
        XCTAssertEqual(p.prettyWhen, "Mon 12 – Fri 16 Oct")
    }
}


final class QRDemoFormTests: XCTestCase {
    /// A phone-sized "poster" with the QR code in one corner, encoded as JPEG like the upload path.
    private func posterJPEG(qr text: String) throws -> Data {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        let code = try XCTUnwrap(filter.outputImage).transformed(by: CGAffineTransform(scaleX: 12, y: 12))
        let cg = try XCTUnwrap(CIContext().createCGImage(code, from: code.extent))
        let size = CGSize(width: 1080, height: 1600)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let poster = UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            UIImage(cgImage: cg).draw(in: CGRect(x: 600, y: 1100, width: 400, height: 400))
        }
        return try XCTUnwrap(ImagePrep.jpeg(from: poster))
    }

    func testDecodesTheHardcodedQRAndMatchesTheForm() throws {
        let urls = QRCodes.urls(in: try posterJPEG(qr: "https://qrto.org/fNWFrg"))
        XCTAssertEqual(urls, ["https://qrto.org/fNWFrg"])
        let forms = DemoForms.forms(forQR: urls)
        XCTAssertEqual(forms.map(\.id), ["9bfb46481379"]) // same id the backend would give it
        XCTAssertEqual(forms.first?.payload.fields.count, 7)
    }

    func testOtherQRCodesAreIgnored() throws {
        XCTAssertTrue(DemoForms.forms(forQR: QRCodes.urls(in: try posterJPEG(qr: "https://example.com/menu"))).isEmpty)
        XCTAssertTrue(QRCodes.urls(in: Data("not an image".utf8)).isEmpty)
    }

    func testNormalisesTrailingSlashAndCase() {
        XCTAssertEqual(DemoForms.normalise("http://QRTO.org/fNWFrg/"), "https://qrto.org/fNWFrg")
    }

    func testPrefilledLinkForTheDemoForm() {
        let url = DemoForms.revisionDojo.prefillURL(values: ["entry.1046611833": "Ada", "entry.590969671": "Veg"])
        XCTAssertEqual(url?.absoluteString,
                       "https://docs.google.com/forms/d/e/1FAIpQLSci6LIaE_RgnJT4es__YrJjFK74nX3MjeKlydf1540OcMPxdg/viewform?usp=pp_url&entry.1046611833=Ada&entry.590969671=Veg")
    }
}
