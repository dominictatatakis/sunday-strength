import Foundation

enum APIError: Error, Equatable {
    case badCredentials
    /// Too many sign-in attempts; the server wants a pause.
    case throttled
    case notAuthorised
    /// 400 from _apply_completion — the tick will never be accepted.
    case rejected(String)
    case offline
    case server(Int)
    /// A provider identity with no account yet: ask the four questions, then
    /// sign in again with the answers. Google's carries the signed identity.
    case needsOnboarding(pending: String?)
    /// Someone new while payments are on -- the app cannot create accounts.
    case noAccount
    /// Their provider's address already belongs to a password account.
    case emailInUse
}

/// The body of a refused provider sign-in: {"error": "...", "pending": "..."}.
private struct AuthProblem: Decodable {
    let error: String?
    let pending: String?
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
        // Every refusal sends the browser back to /login with a reason; only
        // success goes anywhere else. Matching on the reasons missed slow=1.
        guard (300..<400).contains(http.statusCode) else {
            throw APIError.badCredentials
        }
        if location.contains("/login") {
            throw location.contains("slow=1")
                ? APIError.throttled : APIError.badCredentials
        }
    }

    // MARK: - Provider sign-in

    func providers() async throws -> ProvidersInfo {
        try await get("api/v1/auth/providers", query: nil)
    }

    func signInWithApple(identityToken: String, nonce: String,
                         prefs: OnboardingPrefs?) async throws -> AuthResponse {
        struct Body: Encodable {
            let identityToken: String
            let nonce: String
            let prefs: OnboardingPrefs?
        }
        return try await postAuth("api/v1/auth/apple",
                                  Body(identityToken: identityToken,
                                       nonce: nonce, prefs: prefs))
    }

    func signInWithGoogle(handoff: String) async throws -> AuthResponse {
        try await postAuth("api/v1/auth/google", ["handoff": handoff])
    }

    func signInWithGoogle(pending: String,
                          prefs: OnboardingPrefs) async throws -> AuthResponse {
        struct Body: Encodable {
            let pending: String
            let prefs: OnboardingPrefs
        }
        return try await postAuth("api/v1/auth/google",
                                  Body(pending: pending, prefs: prefs))
    }

    /// Swaps the refresh token for a fresh ss_session cookie.
    func refresh(_ token: String) async throws -> AuthResponse {
        try await postAuth("api/v1/auth/refresh", ["refresh": token])
    }

    private func postAuth<B: Encodable>(_ path: String,
                                        _ body: B) async throws -> AuthResponse {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSON.encoder.encode(body)
        let (data, response) = try await perform(request, delegate: nil)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.server(0)
        }
        let problem = try? JSON.decoder.decode(AuthProblem.self, from: data)
        switch (http.statusCode, problem?.error) {
        case (200..<300, _):
            return try JSON.decoder.decode(AuthResponse.self, from: data)
        case (409, "needs_onboarding"):
            throw APIError.needsOnboarding(pending: problem?.pending)
        case (409, "email_in_use"):
            throw APIError.emailInUse
        case (403, "no_account"):
            throw APIError.noAccount
        case (401, _):
            throw APIError.notAuthorised
        case (400, _):
            throw APIError.rejected(Self.detail(from: data))
        default:
            throw APIError.server(http.statusCode)
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
