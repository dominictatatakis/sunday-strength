import XCTest
@testable import SundayStrength

final class APIClientTests: XCTestCase {

    private let base = URL(string: "http://localhost:8123")!

    private func client() -> APIClient {
        APIClient(baseURL: base, session: StubProtocol.session())
    }

    private func response(_ status: Int,
                          headers: [String: String] = [:]) -> HTTPURLResponse {
        HTTPURLResponse(url: base, statusCode: status,
                        httpVersion: nil, headerFields: headers)!
    }

    override func tearDown() {
        StubProtocol.handler = nil
        super.tearDown()
    }

    /// A good login is a 303 to /account. A bad one is a 303 to
    /// /login?error=1 — same status, so only the Location tells them apart.
    func testLoginSucceedsOnRedirectToAccount() async throws {
        StubProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            return (self.response(303, headers: ["Location": "/account"]), Data())
        }
        try await client().login(email: "a@b.com", password: "hunter22")
    }

    func testLoginFailsOnRedirectToError() async {
        StubProtocol.handler = { _ in
            (self.response(303, headers: ["Location": "/login?error=1"]), Data())
        }
        do {
            try await client().login(email: "a@b.com", password: "wrong")
            XCTFail("expected badCredentials")
        } catch let error as APIError {
            XCTAssertEqual(error, .badCredentials)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    /// Throttled sign-ins redirect to /login?slow=1. Checking only for
    /// error=1 read that as success.
    func testAThrottledLoginIsNotASuccess() async {
        StubProtocol.handler = { _ in
            (self.response(303, headers: ["Location": "/login?slow=1"]), Data())
        }
        do {
            try await client().login(email: "a@b.com", password: "x")
            XCTFail("expected throttled")
        } catch let error as APIError {
            XCTAssertEqual(error, .throttled)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testLoginFormEncodesTheBody() async throws {
        StubProtocol.handler = { request in
            let body = request.httpBodyStreamData() ?? Data()
            let text = String(decoding: body, as: UTF8.self)
            XCTAssertTrue(text.contains("email=a%40b.com"))
            XCTAssertTrue(text.contains("password=hunter22"))
            return (self.response(303, headers: ["Location": "/account"]), Data())
        }
        try await client().login(email: "a@b.com", password: "hunter22")
    }

    func testPlanDecodes() async throws {
        let json = Data("""
        {"week":37,"week_key":"2026-W37","equipment":"full","run":null,
         "notes":[],"days":[{"day":1,"title":"Day 1 - Upper","exercises":[]}]}
        """.utf8)
        StubProtocol.handler = { _ in (self.response(200), json) }
        let plan = try await client().plan(week: nil)
        XCTAssertEqual(plan.weekKey, "2026-W37")
        XCTAssertNil(plan.run)
    }

    func testPlanPassesTheWeekQuery() async throws {
        StubProtocol.handler = { request in
            XCTAssertEqual(request.url?.query, "week=2026-W30")
            let json = Data("""
            {"week":30,"week_key":"2026-W30","equipment":"full","run":null,
             "notes":[],"days":[]}
            """.utf8)
            return (self.response(200), json)
        }
        _ = try await client().plan(week: "2026-W30")
    }

    func test401IsNotAuthorised() async {
        StubProtocol.handler = { _ in (self.response(401), Data()) }
        do {
            _ = try await client().me()
            XCTFail("expected notAuthorised")
        } catch let error as APIError {
            XCTAssertEqual(error, .notAuthorised)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    /// _apply_completion returns 400 with a FastAPI {"detail": "..."} body
    /// when the slug is not in that week's plan.
    func test400CarriesTheServerDetail() async {
        let body = Data(#"{"detail":"That exercise isn't in that day's plan."}"#.utf8)
        StubProtocol.handler = { _ in (self.response(400), body) }
        do {
            try await client().setCompletion(
                .init(slug: "nope", day: 1, week: "2026-W37",
                      sets: nil, reps: nil, weightKg: nil, done: true))
            XCTFail("expected rejected")
        } catch let error as APIError {
            XCTAssertEqual(error, .rejected("That exercise isn't in that day's plan."))
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testNetworkFailureIsOffline() async {
        StubProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }
        do {
            _ = try await client().plan(week: nil)
            XCTFail("expected offline")
        } catch let error as APIError {
            XCTAssertEqual(error, .offline)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }
}
