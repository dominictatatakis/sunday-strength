import XCTest
@testable import SundayStrength

@MainActor
final class AppModelTests: XCTestCase {

    private let base = URL(string: "http://localhost:8123")!

    private let planJSON = """
    {"week":37,"week_key":"2026-W37","equipment":"full","run":null,"notes":[],
     "days":[{"day":1,"title":"Day 1 - Upper",
              "exercises":[{"name":"Goblet squat","slug":"goblet-squat",
                            "sets":"3 x 10-12","equipment":"dumbbells","alts":[],
                            "done":false,"sets_done":null,"reps":null,
                            "weight_kg":null}]}]}
    """

    private func makeModel() -> AppModel {
        AppModel(api: APIClient(baseURL: base, session: StubProtocol.session()))
    }

    private func ok(_ data: Data) -> (HTTPURLResponse, Data) {
        (HTTPURLResponse(url: base, statusCode: 200,
                         httpVersion: nil, headerFields: nil)!, data)
    }

    override func tearDown() {
        StubProtocol.handler = nil
        super.tearDown()
    }

    func testLogTicksTheRowImmediately() async {
        StubProtocol.handler = { request in
            if request.url!.path.contains("completions") {
                return self.ok(Data(#"{"ok":true}"#.utf8))
            }
            return self.ok(Data(self.planJSON.utf8))
        }
        let model = makeModel()
        await model.loadPlan()
        await model.log(day: 1, slug: "goblet-squat",
                        sets: 3, reps: 10, weightKg: 22.5)

        let exercise = model.plan!.days[0].exercises[0]
        XCTAssertTrue(exercise.done)
        XCTAssertEqual(exercise.setsDone, 3)
        XCTAssertEqual(exercise.weightKg, 22.5)
    }

    /// A 400 means the plan drifted and this tick will never be accepted, so
    /// the optimistic change has to come back off rather than linger as a lie.
    func testRejectedTickRevertsTheRow() async {
        StubProtocol.handler = { request in
            if request.url!.path.contains("completions") {
                let detail = Data(#"{"detail":"That exercise isn't in that day's plan."}"#.utf8)
                return (HTTPURLResponse(url: self.base, statusCode: 400,
                                        httpVersion: nil,
                                        headerFields: nil)!, detail)
            }
            return self.ok(Data(self.planJSON.utf8))
        }
        let model = makeModel()
        await model.loadPlan()
        await model.log(day: 1, slug: "goblet-squat",
                        sets: 3, reps: 10, weightKg: 22.5)

        let exercise = model.plan!.days[0].exercises[0]
        XCTAssertFalse(exercise.done, "a rejected tick must not stay ticked")
        XCTAssertNil(exercise.setsDone)
        XCTAssertEqual(model.errorMessage,
                       "That exercise isn't in that day's plan.")
    }

    /// A tick made with no signal must stay on screen: the set was done, and
    /// telling someone mid-workout that it wasn't is worse than being wrong later.
    func testNetworkFailureKeepsTheOptimisticTick() async {
        StubProtocol.handler = { request in
            if request.url!.path.contains("completions") {
                throw URLError(.notConnectedToInternet)
            }
            return self.ok(Data(self.planJSON.utf8))
        }
        let model = makeModel()
        await model.loadPlan()
        await model.log(day: 1, slug: "goblet-squat",
                        sets: 3, reps: 10, weightKg: 22.5)

        XCTAssertTrue(model.plan!.days[0].exercises[0].done)
        XCTAssertTrue(model.isOffline)
    }
}

extension AppModelTests {

    /// Login answers a 303 to /account; anything else is read as a failure,
    /// so a stub that returns 200 for everything never signs in.
    private func loginRedirect() -> (HTTPURLResponse, Data) {
        (HTTPURLResponse(url: base, statusCode: 303, httpVersion: nil,
                         headerFields: ["Location": "/account"])!, Data())
    }

    private var meJSON: String {
        """
        {"email":"a@b.com","status":"active","days_per_week":4,
         "experience":"intermediate","equipment":"full","include_run":true,
         "options":{"days_per_week":[2,3,4,5],
                    "experience":["beginner","intermediate","advanced"],
                    "equipment":[{"value":"full","name":"Full gym"}]}}
        """
    }

    /// Only the field that actually differs may be sent: the profile could be
    /// an hour old, and resending all four would revert anything changed on
    /// the website in the meantime.
    func testSaveSettingsSendsOnlyWhatChanged() async {
        let body = LockedBox()
        StubProtocol.handler = { request in
            if request.url!.path.hasSuffix("/login") { return self.loginRedirect() }
            if request.httpMethod == "PATCH" {
                body.value = request.httpBodyStreamData()
                    .map { String(decoding: $0, as: UTF8.self) }
            }
            if request.url!.path.contains("plan") {
                return self.ok(Data(self.planJSON.utf8))
            }
            return self.ok(Data(self.meJSON.utf8))
        }
        let model = makeModel()
        await model.signIn(email: "a@b.com", password: "x")
        XCTAssertNotNil(model.me, "the test never signed in")

        await model.saveSettings(daysPerWeek: 3, experience: "intermediate",
                                 equipment: "full", includeRun: true)

        let sent = body.value ?? ""
        XCTAssertTrue(sent.contains("days_per_week"), "sent: \(sent)")
        XCTAssertFalse(sent.contains("experience"), "sent: \(sent)")
        XCTAssertFalse(sent.contains("equipment"), "sent: \(sent)")
    }

    func testSaveSettingsSendsNothingWhenNothingChanged() async {
        let calls = LockedBox()
        StubProtocol.handler = { request in
            if request.url!.path.hasSuffix("/login") { return self.loginRedirect() }
            if request.httpMethod == "PATCH" { calls.value = "patched" }
            if request.url!.path.contains("plan") {
                return self.ok(Data(self.planJSON.utf8))
            }
            return self.ok(Data(self.meJSON.utf8))
        }
        let model = makeModel()
        await model.signIn(email: "a@b.com", password: "x")
        XCTAssertNotNil(model.me, "the test never signed in")

        let changed = await model.saveSettings(
            daysPerWeek: 4, experience: "intermediate",
            equipment: "full", includeRun: true)

        XCTAssertFalse(changed)
        XCTAssertNil(calls.value, "an unchanged form must not call the API")
    }
}

/// Somewhere for the stub's closure to hand a value back.
final class LockedBox: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: String?

    var value: String? {
        get { lock.withLock { stored } }
        set { lock.withLock { stored = newValue } }
    }
}
