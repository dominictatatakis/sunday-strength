import XCTest
@testable import SundayStrength

/// Opening the app while the free server is still waking up.
@MainActor
final class LaunchTests: XCTestCase {

    private let base = URL(string: "http://localhost:8123")!

    private let planJSON = """
    {"week":40,"week_key":"2026-W40","equipment":"full","run":null,"notes":[],
     "days":[{"day":1,"title":"Day 1 - Legs","exercises":[
       {"name":"Plank","slug":"plank","sets":"3 x 30s","equipment":"bodyweight",
        "alts":[],"done":false,"sets_done":null,"reps":null,"weight_kg":null}]}]}
    """

    private let meJSON = """
    {"email":"a@b.com","status":"active","days_per_week":4,
     "experience":"intermediate","equipment":"full","include_run":false,
     "options":{"days_per_week":[2,3,4,5],
                "experience":["beginner","intermediate","advanced"],
                "equipment":[{"value":"full","name":"Full gym"}]}}
    """

    override func tearDown() {
        StubProtocol.handler = nil
        Keychain.clear()
        super.tearDown()
    }

    private func waitUntil(_ condition: () -> Bool, seconds: Double = 3) async -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(20))
        }
        return condition()
    }

    /// The server can take a minute to wake. The plan saved on the phone is
    /// what's needed at the gym, so it shows at once and updates behind it.
    func testTheSavedPlanShowsBeforeTheServerAnswers() async throws {
        PlanCache.save(try JSON.decoder.decode(Plan.self, from: Data(planJSON.utf8)))
        Keychain.save(.init(email: "a@b.com", password: "x"))

        let serverAwake = DispatchSemaphore(value: 0)
        StubProtocol.handler = { request in
            serverAwake.wait()
            let body = request.url!.path.hasSuffix("/me") ? self.meJSON : self.planJSON
            return (HTTPURLResponse(url: self.base, statusCode: 200, httpVersion: nil,
                                    headerFields: nil)!, Data(body.utf8))
        }
        let model = AppModel(api: APIClient(baseURL: base, session: StubProtocol.session()),
                             queue: OfflineQueue(
                                fileURL: FileManager.default.temporaryDirectory
                                    .appendingPathComponent("q-\(UUID().uuidString).json"),
                                legacyURL: FileManager.default.temporaryDirectory
                                    .appendingPathComponent("l-\(UUID().uuidString).json")))

        let launch = Task { await model.restore() }
        let shown = await waitUntil { model.phase == .signedIn && model.plan != nil }
        XCTAssertTrue(shown, "the saved plan should show while the server is asleep")
        XCTAssertTrue(model.isUpdating, "and say it is still updating")

        for _ in 0..<10 { serverAwake.signal() }
        await launch.value
        XCTAssertFalse(model.isUpdating)
        XCTAssertNotNil(model.me)
    }
}
