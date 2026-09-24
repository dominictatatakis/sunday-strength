import CryptoKit
import XCTest
@testable import SundayStrength

@MainActor
final class ProviderSignInTests: XCTestCase {

    private let base = URL(string: "http://localhost:8123")!

    private func respond(_ status: Int, _ json: String) -> (HTTPURLResponse, Data) {
        (HTTPURLResponse(url: base, statusCode: status, httpVersion: nil,
                         headerFields: nil)!, Data(json.utf8))
    }

    private func client() -> APIClient {
        APIClient(baseURL: base, session: StubProtocol.session())
    }

    private let meJSON = """
    {"email":"a@b.com","status":"active","days_per_week":3,
     "experience":"beginner","equipment":"full","include_run":false,
     "options":{"days_per_week":[2,3],"experience":["beginner"],
                "equipment":[{"value":"full","name":"Full gym"}]}}
    """

    private let providersJSON = """
    {"google":true,"apple":true,
     "options":{"days_per_week":[2,3],"experience":["beginner"],
                "equipment":[{"value":"full","name":"Full gym"}]}}
    """

    override func setUp() {
        super.setUp()
        Keychain.clear()
    }

    override func tearDown() {
        StubProtocol.handler = nil
        Keychain.clear()
        super.tearDown()
    }

    // MARK: - Nonce

    /// Apple is sent the hash, the server the raw value; the server hashes
    /// what it receives and compares with the claim Apple signed.
    func testTheHashedNonceIsTheSHA256OfTheRaw() {
        let nonce = ProviderSignIn.makeNonce()
        let expected = SHA256.hash(data: Data(nonce.raw.utf8))
            .map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(nonce.hashed, expected)
        XCTAssertNotEqual(ProviderSignIn.makeNonce().raw, nonce.raw)
    }

    // MARK: - The Google callback

    func testTheCallbackIsReadForAHandoffOrOnboarding() throws {
        XCTAssertEqual(
            try ProviderSignIn.outcome(from: URL(string: "sundaystrength://auth?handoff=abc")!),
            .handoff("abc"))
        XCTAssertEqual(
            try ProviderSignIn.outcome(from: URL(
                string: "sundaystrength://auth?needs_onboarding=1&pending=p.q")!),
            .needsOnboarding(pending: "p.q"))
        XCTAssertThrowsError(try ProviderSignIn.outcome(
            from: URL(string: "sundaystrength://auth?error=1")!))
    }

    // MARK: - The client

    func testSignInSendsSnakeCaseAndDecodesTheRefreshToken() async throws {
        StubProtocol.handler = { request in
            let body = String(decoding: request.httpBodyStreamData() ?? Data(),
                              as: UTF8.self)
            XCTAssertTrue(body.contains("\"identity_token\":\"tok\""), body)
            XCTAssertTrue(body.contains("\"nonce\":\"raw\""), body)
            XCTAssertFalse(body.contains("prefs"), "nil prefs must be omitted: \(body)")
            return self.respond(200, #"{"refresh":"r1","email":"a@b.com"}"#)
        }
        let response = try await client().signInWithApple(
            identityToken: "tok", nonce: "raw", prefs: nil)
        XCTAssertEqual(response.refresh, "r1")
    }

    func testTheServersRefusalsBecomeDistinctErrors() async {
        let cases: [(Int, String, APIError)] = [
            (409, #"{"error":"needs_onboarding","pending":"p1"}"#,
             .needsOnboarding(pending: "p1")),
            (409, #"{"error":"needs_onboarding"}"#, .needsOnboarding(pending: nil)),
            (409, #"{"error":"email_in_use"}"#, .emailInUse),
            (403, #"{"error":"no_account"}"#, .noAccount),
            (401, #"{"error":"unauthenticated"}"#, .notAuthorised),
        ]
        for (status, json, expected) in cases {
            StubProtocol.handler = { _ in self.respond(status, json) }
            do {
                _ = try await client().signInWithGoogle(handoff: "h")
                XCTFail("expected \(expected)")
            } catch let error as APIError {
                XCTAssertEqual(error, expected, json)
            } catch {
                XCTFail("unexpected \(error)")
            }
        }
    }

    // MARK: - The model

    /// The cookie lasts 30 days. Signing in again on every launch spends the
    /// server's sign-in allowance (8 per 15 minutes) and locked people out.
    func testRestoreReusesAWorkingCookieWithoutSigningInAgain() async {
        for store in [{ Keychain.saveRefresh("r1") },
                      { Keychain.save(.init(email: "a@b.com", password: "pw")) }] {
            store()
            let paths = LockedPaths()
            StubProtocol.handler = { request in
                paths.append(request.url!.path)
                return request.url!.path == "/api/v1/me"
                    ? self.respond(200, self.meJSON)
                    : self.respond(200, #"{"week":1,"week_key":"2026-W01","equipment":"full","run":null,"notes":[],"days":[]}"#)
            }
            let model = AppModel(api: client())
            await model.restore()
            XCTAssertEqual(model.phase, .signedIn)
            XCTAssertFalse(paths.values.contains("/login"), "\(paths.values)")
            XCTAssertFalse(paths.values.contains("/api/v1/auth/refresh"))
        }
    }

    /// A provider account has no password: once the cookie has expired,
    /// restoring uses the refresh token and never posts the login form.
    func testAnExpiredCookieIsRenewedWithTheRefreshToken() async {
        Keychain.saveRefresh("r1")
        let paths = LockedPaths()
        let refreshed = LockedPaths()
        StubProtocol.handler = { request in
            paths.append(request.url!.path)
            switch request.url!.path {
            case "/api/v1/auth/refresh":
                refreshed.append("yes")
                return self.respond(200, #"{"refresh":"r2","email":"a@b.com"}"#)
            case "/api/v1/me":
                return refreshed.values.isEmpty
                    ? self.respond(401, #"{"detail":"Sign in"}"#)
                    : self.respond(200, self.meJSON)
            default:
                return self.respond(500, "{}")
            }
        }
        let model = AppModel(api: client())
        await model.restore()
        XCTAssertEqual(model.phase, .signedIn)
        XCTAssertFalse(paths.values.contains("/login"))
        XCTAssertEqual(Keychain.loadRefresh(), "r2", "the new token replaces the old")
    }

    /// Being told to wait is not being offline, and not a wrong password.
    func testAThrottledRestoreSaysSoAndKeepsTheCredentials() async {
        Keychain.save(.init(email: "a@b.com", password: "pw"))
        StubProtocol.handler = { request in
            request.url!.path == "/login"
                ? (HTTPURLResponse(url: self.base, statusCode: 303, httpVersion: nil,
                                   headerFields: ["Location": "/login?slow=1"])!, Data())
                : self.respond(401, #"{"detail":"Sign in"}"#)
        }
        let model = AppModel(api: client())
        await model.restore()
        XCTAssertEqual(model.phase,
                       .signedOut("Too many attempts. Wait a few minutes and try again."))
        XCTAssertNotNil(Keychain.load(), "the password is still right")
    }

    func testARefusedRefreshTokenSignsOut() async {
        Keychain.saveRefresh("dead")
        StubProtocol.handler = { _ in self.respond(401, #"{"error":"unauthenticated"}"#) }  // me, then refresh
        let model = AppModel(api: client())
        await model.restore()
        XCTAssertEqual(model.phase, .signedOut("Please sign in again."))
        XCTAssertNil(Keychain.loadRefresh())
    }

    /// Someone new gets the four questions; the answers go back with the
    /// credential that was waiting, and only then is anyone signed in.
    func testSomeoneNewIsAskedTheQuestionsThenSignedIn() async {
        let sentPrefs = LockedPaths()
        StubProtocol.handler = { request in
            switch request.url!.path {
            case "/api/v1/auth/providers":
                return self.respond(200, self.providersJSON)
            case "/api/v1/auth/apple":
                let body = String(decoding: request.httpBodyStreamData() ?? Data(),
                                  as: UTF8.self)
                if body.contains("prefs") {
                    sentPrefs.append(body)
                    return self.respond(200, #"{"refresh":"r1","email":"a@b.com"}"#)
                }
                return self.respond(409, #"{"error":"needs_onboarding"}"#)
            case "/api/v1/me":
                return self.respond(200, self.meJSON)
            default:
                return self.respond(200, #"{"week":1,"week_key":"2026-W01","equipment":"full","run":null,"notes":[],"days":[]}"#)
            }
        }
        let model = AppModel(api: client())
        await model.signInWithApple(identityToken: "tok", nonce: "raw")
        guard case .onboarding(let onboarding) = model.phase else {
            return XCTFail("expected onboarding, got \(model.phase)")
        }
        XCTAssertEqual(onboarding.pending, .apple(identityToken: "tok", nonce: "raw"))

        await model.finishOnboarding(OnboardingPrefs(
            days: 3, experience: "beginner", run: true, equipment: "full"))
        XCTAssertEqual(model.phase, .signedIn)
        XCTAssertTrue(sentPrefs.values.first?.contains("\"run\":true") ?? false)
        XCTAssertEqual(Keychain.loadRefresh(), "r1")
    }

    func testNoAccountWhilePaymentsAreOnIsSaidPlainly() async {
        StubProtocol.handler = { _ in self.respond(403, #"{"error":"no_account"}"#) }
        let model = AppModel(api: client())
        await model.signInWithApple(identityToken: "tok", nonce: "raw")
        XCTAssertEqual(model.phase,
                       .signedOut("There's no Sunday Strength account for that sign-in."))
    }
}

/// Collects values from the stub's background thread.
final class LockedPaths: @unchecked Sendable {
    private let lock = NSLock()
    private var items: [String] = []
    func append(_ s: String) { lock.lock(); items.append(s); lock.unlock() }
    var values: [String] { lock.lock(); defer { lock.unlock() }; return items }
}
