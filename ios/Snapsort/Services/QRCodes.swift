import CoreImage
import Foundation
import Vision

/// On-device QR decoding. A QR code carries the exact link, while reading a printed URL off a
/// poster is error-prone, and the backend only sees a downscaled copy.
enum QRCodes {
    /// Every http(s) link encoded in a QR code in the image. Never throws; [] if none or unreadable.
    static func urls(in imageData: Data) -> [String] {
        guard let image = CIImage(data: imageData) else { return [] }
        // CoreImage's detector needs no Neural Engine, so it also works in the Simulator (CI).
        // Vision is the fallback: it copes better with small or skewed codes on a real phone.
        var payloads = coreImage(image)
        if payloads.isEmpty { payloads = vision(image) }
        var seen = Set<String>()
        return payloads
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.lowercased().hasPrefix("http://") || $0.lowercased().hasPrefix("https://") }
            .filter { seen.insert($0).inserted }
    }

    private static func coreImage(_ image: CIImage) -> [String] {
        let detector = CIDetector(ofType: CIDetectorTypeQRCode, context: nil,
                                  options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])
        return (detector?.features(in: image) ?? []).compactMap { ($0 as? CIQRCodeFeature)?.messageString }
    }

    private static func vision(_ image: CIImage) -> [String] {
        let request = VNDetectBarcodesRequest()
        request.symbologies = [.qr]
        guard (try? VNImageRequestHandler(ciImage: image, options: [:]).perform([request])) != nil else { return [] }
        return (request.results ?? []).compactMap(\.payloadStringValue)
    }
}

/// TEMPORARY demo hardcode: QR codes on our own posters whose form we already know.
///
/// If Vision decodes one of these QR codes, the form is offered even when the backend found no form
/// (its QR decoder can miss on a downscaled screenshot). The ids match the backend's
/// (sha1(form_url)[:12]), so when the backend also finds it, it is the same form, not a duplicate.
/// Remove once the backend reliably decodes these posters.
enum DemoForms {
    static let byQR: [String: FormProposal] = [
        "https://qrto.org/fNWFrg": revisionDojo,
    ]

    static func forms(forQR urls: [String]) -> [FormProposal] {
        urls.compactMap { byQR[normalise($0)] }
    }

    static func normalise(_ url: String) -> String {
        var s = url.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix("/") { s.removeLast() }
        guard var c = URLComponents(string: s) else { return s }
        c.scheme = "https"
        c.host = c.host?.lowercased()
        return c.string ?? s
    }

    /// Read from the live form on 2026-09-20 (backend/snapsort/forms.py resolve_google_form).
    static let revisionDojo = FormProposal(
        id: "9bfb46481379",
        action: "form.prefill",
        decision: "ask",
        payload: FormPayload(
            formUrl: "https://docs.google.com/forms/d/e/1FAIpQLSci6LIaE_RgnJT4es__YrJjFK74nX3MjeKlydf1540OcMPxdg/viewform",
            title: "Revision Dojo Blah Blah",
            domain: "docs.google.com",
            fields: [
                FormField(entryId: "entry.1046611833", question: "Name?", profileKey: "full_name", required: false, type: "short_text", options: nil, sensitive: false),
                FormField(entryId: "entry.1731345188", question: "Age?", profileKey: "age", required: false, type: "short_text", options: nil, sensitive: false),
                FormField(entryId: "entry.121842724", question: "Phone Number?", profileKey: "phone", required: false, type: "short_text", options: nil, sensitive: false),
                FormField(entryId: "entry.373191682", question: "Email?", profileKey: "email", required: false, type: "short_text", options: nil, sensitive: false),
                FormField(entryId: "entry.843302050", question: "Location?", profileKey: "location", required: false, type: "short_text", options: nil, sensitive: false),
                FormField(entryId: "entry.610050749", question: "Gender", profileKey: nil, required: false, type: "multiple_choice", options: ["Male", "Female"], sensitive: false),
                FormField(entryId: "entry.590969671", question: "Dietary Preference", profileKey: "dietary", required: false, type: "multiple_choice", options: ["Veg", "Non-veg"], sensitive: false),
            ],
            prefillStyle: "google_forms",
            provider: "google_forms",
            reasons: ["QR code on the poster (qrto.org/fNWFrg) leads to this Google Form", "7 questions read from the form"]
        ),
        confidence: 0.95,
        evidence: "https://qrto.org/fNWFrg",
        notes: ["source:qr", "hardcoded_demo"]
    )
}
