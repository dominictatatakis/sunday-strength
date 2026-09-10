import Foundation

enum APIError: Error, Equatable {
    case badCredentials
    case notAuthorised
    /// 400 from _apply_completion — the tick will never be accepted.
    case rejected(String)
    case offline
    case server(Int)
}

/// Refuses redirects so login can read the Location header. URLSession would
/// otherwise follow the 303 and render /account, hiding whether it worked.
private final class NoRedirect: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? {
        nil
    }
}

actor APIClient {
    private let baseURL: URL
    private let session: URLSession
    private let noRedirect = NoRedirect()

    init(baseURL: URL = AppConfig.baseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    // MARK: - Auth

    /// Posts the website's own login form. The ss_session cookie it sets is
    /// what authenticates every /api/v1 call afterwards (app.py:583).
    func login(email: String, password: String) async throws {
        var request = URLRequest(url: baseURL.appendingPathComponent("login"))
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded",
                         forHTTPHeaderField: "Content-Type")
        request.httpBody = Self.formEncode(["email": email, "password": password])

        let (_, response) = try await perform(request, delegate: noRedirect)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.server(0)
        }
        let location = http.value(forHTTPHeaderField: "Location") ?? ""
        guard (300..<400).contains(http.statusCode),
              !location.contains("error=1"),
              !location.contains("exists=1")
        else {
            throw APIError.badCredentials
        }
    }

    // MARK: - Reads

    func me() async throws -> Me {
        try await get("api/v1/me", query: nil)
    }

    func plan(week: String?) async throws -> Plan {
        try await get("api/v1/plan",
                      query: week.map { [URLQueryItem(name: "week", value: $0)] })
    }

    /// Changes preferences. Sends only what differs, so a stale profile
    /// cannot revert a change made on the website since launch.
    func updateMe(_ patch: PrefsPatch) async throws -> Me {
        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/v1/me"))
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSON.encoder.encode(patch)
        return try JSON.decoder.decode(Me.self, from: await send(request))
    }

    // MARK: - Writes

    func setCompletion(_ body: CompletionBody) async throws {
        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/v1/completions"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSON.encoder.encode(body)
        _ = try await send(request)
    }

    // MARK: - Plumbing

    private func get<T: Decodable>(_ path: String,
                                   query: [URLQueryItem]?) async throws -> T {
        var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false)!
        components.queryItems = query
        let data = try await send(URLRequest(url: components.url!))
        return try JSON.decoder.decode(T.self, from: data)
    }

    private func send(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await perform(request, delegate: nil)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.server(0)
        }
        switch http.statusCode {
        case 200..<300:
            return data
        case 401:
            throw APIError.notAuthorised
        case 400:
            throw APIError.rejected(Self.detail(from: data))
        default:
            throw APIError.server(http.statusCode)
        }
    }

    private func perform(_ request: URLRequest,
                         delegate: URLSessionTaskDelegate?)
        async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request, delegate: delegate)
        } catch let error as URLError {
            throw error.code == .cancelled
                ? APIError.server(0) : APIError.offline
        }
    }

    /// FastAPI's HTTPException body is {"detail": "..."}.
    private static func detail(from data: Data) -> String {
        struct Detail: Decodable { let detail: String }
        return (try? JSONDecoder().decode(Detail.self, from: data))?.detail
            ?? "That didn't work."
    }

    private static func formEncode(_ fields: [String: String]) -> Data {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        let pairs = fields.map { key, value in
            let encoded = value
                .addingPercentEncoding(withAllowedCharacters: allowed) ?? ""
            return "\(key)=\(encoded)"
        }
        return Data(pairs.joined(separator: "&").utf8)
    }
}
