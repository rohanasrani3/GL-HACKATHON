import Foundation

enum APIError: LocalizedError {
    case badURL(String)
    case noResponse
    case http(Int, String)

    var errorDescription: String? {
        switch self {
        case .badURL(let url): return "Bad server URL: \(url)"
        case .noResponse: return "No response from server"
        case .http(401, _): return "HTTP 401: check the API token"
        case .http(let code, let body): return "HTTP \(code): \(body.prefix(200))"
        }
    }
}

/// Talks to the Snapsort backend (backend/snapsort/main.py). Port of Uploader.kt.
struct APIClient {
    let baseURL: URL
    let token: String

    /// The real model can take a while, especially on the first call: tolerate 240 s.
    static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 240
        c.timeoutIntervalForResource = 300
        return URLSession(configuration: c)
    }()

    init(serverURL: String, token: String) throws {
        guard let url = URL(string: serverURL), url.scheme != nil, url.host != nil else {
            throw APIError.badURL(serverURL)
        }
        baseURL = url
        self.token = token
    }

    private func request(_ path: String, timeout: TimeInterval = 240) -> URLRequest {
        var r = URLRequest(url: baseURL.appendingPathComponent(path))
        r.timeoutInterval = timeout
        if !token.isEmpty { r.setValue(token, forHTTPHeaderField: "X-Api-Token") }
        return r
    }

    private func check(_ data: Data, _ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.noResponse }
        guard http.statusCode == 200 else {
            throw APIError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
    }

    func health() async throws -> HealthResponse {
        let (data, response) = try await Self.session.data(for: request("health", timeout: 10))
        try check(data, response)
        return try JSONDecoder.api.decode(HealthResponse.self, from: data)
    }

    /// POST /analyze. `jpeg` must already be downscaled and re-encoded (ImagePrep), so no EXIF/GPS leaves the phone.
    func analyze(jpeg: Data, capturedAt: Date, timeZone: TimeZone = .current, locale: Locale = .current) async throws -> AnalyzeResponse {
        let boundary = "snapsort-\(UUID().uuidString)"
        var req = request("analyze")
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        let fields = [
            "captured_at": ProposalDates.isoWithOffset(capturedAt, timeZone: timeZone),
            "timezone": timeZone.identifier,
            "locale": locale.identifier(.bcp47),
        ]
        var body = Data()
        for (key, value) in fields {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"screenshot.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(jpeg)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        let (data, response) = try await Self.session.upload(for: req, from: body)
        try check(data, response)
        return try JSONDecoder.api.decode(AnalyzeResponse.self, from: data)
    }

    /// What the user did (ids + outcome only). Best-effort: never throws.
    func feedback(_ proposal: Proposal, outcome: String) async {
        var req = request("feedback", timeout: 15)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONEncoder.api.encode(
            FeedbackRequest(proposalId: proposal.id, decision: proposal.decision, outcome: outcome)
        )
        _ = try? await Self.session.data(for: req)
    }
}
