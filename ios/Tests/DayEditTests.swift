import XCTest
@testable import SundayStrength

/// Swapping, adding, removing and resetting, against a stubbed server.
@MainActor
final class DayEditTests: XCTestCase {

    private let base = URL(string: "http://localhost:8123")!
    private var queueURL: URL!
    private var legacyURL: URL!

    override func setUp() {
        super.setUp()
        let tmp = FileManager.default.temporaryDirectory
        queueURL = tmp.appendingPathComponent("changes-\(UUID().uuidString).json")
        legacyURL = tmp.appendingPathComponent("ticks-\(UUID().uuidString).json")
    }

    override func tearDown() {
        StubProtocol.handler = nil
        try? FileManager.default.removeItem(at: queueURL)
        super.tearDown()
    }

    /// Never the default legacy path: that is the app's real file.
    private func queue() -> OfflineQueue {
        OfflineQueue(fileURL: queueURL, legacyURL: legacyURL)
    }

    private func row(_ slug: String, _ name: String, done: Bool = false) -> String {
        """
        {"name":"\(name)","slug":"\(slug)","sets":"3 x 10","equipment":"full","alts":[],
         "done":\(done),"sets_done":\(done ? "3" : "null"),"reps":null,"weight_kg":null}
        """
    }

    private func plan(_ rows: [String], edited: Bool = false) -> Data {
        Data("""
        {"week":40,"week_key":"2026-W40","equipment":"full","run":null,"notes":[],
         "days":[{"day":1,"title":"Day 1 - Legs","edited":\(edited),
                  "original":["goblet-squat","plank"],
                  "exercises":[\(rows.joined(separator: ","))]}]}
        """.utf8)
    }

    private var generated: Data {
        plan([row("goblet-squat", "Goblet squat", done: true), row("plank", "Plank")])
    }

    private let library = Data("""
    {"exercises":[
     {"slug":"goblet-squat","name":"Goblet squat","sets":"3 x 10-12","equipment":"dumbbells",
      "part":"legs","patterns":["squat"],"instructions":[],"images":[],"youtube_url":"",
      "alternatives":[]},
     {"slug":"leg-press","name":"Leg press","sets":"3 x 10-12","equipment":"full",
      "part":"legs","patterns":["squat"],"instructions":[],"images":[],"youtube_url":"",
      "alternatives":[]},
     {"slug":"dead-bug","name":"Dead bug","sets":"3 x 10","equipment":"bodyweight",
      "part":"core","patterns":["core"],"instructions":[],"images":[],"youtube_url":"",
      "alternatives":[]}]}
    """.utf8)

    private func ok(_ data: Data) -> (HTTPURLResponse, Data) {
        (HTTPURLResponse(url: base, statusCode: 200, httpVersion: nil,
                         headerFields: nil)!, data)
    }

    private func refused(_ detail: String) -> (HTTPURLResponse, Data) {
        (HTTPURLResponse(url: base, statusCode: 400, httpVersion: nil,
                         headerFields: nil)!,
         Data(#"{"detail":"\#(detail)"}"#.utf8))
    }

    private func makeModel() -> AppModel {
        AppModel(api: APIClient(baseURL: base, session: StubProtocol.session()),
                 queue: queue())
    }

    /// Serves the plan and library; `edit` answers PUT and DELETE.
    private func serve(edit: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) {
        StubProtocol.handler = { request in
            let path = request.url!.path
            if path.contains("/plan/days/") { return try edit(request) }
            if path.hasSuffix("/exercises") { return self.ok(self.library) }
            if path.hasSuffix("/completions") {
                return self.ok(Data(#"{"ok":true}"#.utf8))
            }
            return self.ok(self.generated)
        }
    }

    private func slugs(_ model: AppModel) -> [String] {
        model.plan!.days[0].exercises.map(\.slug)
    }

    func testSwapReplacesTheRowInPlaceAndSendsTheDay() async {
        let body = LockedBox()
        serve { request in
            body.value = String(decoding: request.httpBodyStreamData() ?? Data(),
                                as: UTF8.self)
            return self.ok(self.plan([self.row("leg-press", "Leg press"),
                                      self.row("plank", "Plank")], edited: true))
        }
        let model = makeModel()
        await model.loadPlan()
        await model.swap(day: 1, replacing: "goblet-squat", with: "leg-press")

        XCTAssertEqual(slugs(model), ["leg-press", "plank"])
        XCTAssertTrue(model.plan!.days[0].edited)
        XCTAssertTrue(body.value?.contains(#""slugs":["leg-press","plank"]"#) ?? false,
                      body.value ?? "nothing sent")
    }

    func testAKeptRowKeepsItsLog() async {
        serve { _ in
            self.ok(self.plan([self.row("goblet-squat", "Goblet squat", done: true),
                               self.row("plank", "Plank"),
                               self.row("dead-bug", "Dead bug")], edited: true))
        }
        let model = makeModel()
        await model.loadPlan()
        await model.add(day: 1, slug: "dead-bug")

        XCTAssertEqual(slugs(model), ["goblet-squat", "plank", "dead-bug"])
        XCTAssertTrue(model.plan!.days[0].exercises[0].done)
    }

    func testRemoveTakesTheRowOut() async {
        serve { _ in self.ok(self.plan([self.row("plank", "Plank")], edited: true)) }
        let model = makeModel()
        await model.loadPlan()
        await model.remove(day: 1, slug: "goblet-squat")
        XCTAssertEqual(slugs(model), ["plank"])
    }

    /// A 400 will never be accepted, so the day goes back as it was.
    func testARefusedEditPutsTheDayBack() async {
        serve { _ in
            self.refused("Leg press needs more equipment than your settings allow.")
        }
        let model = makeModel()
        await model.loadPlan()
        await model.swap(day: 1, replacing: "goblet-squat", with: "leg-press")

        XCTAssertEqual(slugs(model), ["goblet-squat", "plank"])
        XCTAssertEqual(model.errorMessage,
                       "Leg press needs more equipment than your settings allow.")
    }

    func testAnEditWithoutSignalShowsAndQueues() async {
        serve { _ in throw URLError(.notConnectedToInternet) }
        let model = makeModel()
        await model.loadPlan()
        await model.swap(day: 1, replacing: "goblet-squat", with: "leg-press")

        XCTAssertEqual(slugs(model), ["leg-press", "plank"])
        XCTAssertTrue(model.isOffline)
        let pending = await queue().pending()
        XCTAssertEqual(pending, [.setDay(.init(week: "2026-W40", day: 1,
                                               slugs: ["leg-press", "plank"]))])
    }

    /// Queued changes go before the plan is fetched, in the order they were
    /// made, so the fetched plan already includes them.
    func testQueuedChangesReplayInOrderBeforeThePlanLoads() async {
        let waiting = queue()
        await waiting.enqueue(.setDay(.init(week: "2026-W40", day: 1,
                                            slugs: ["leg-press"])))
        await waiting.enqueue(.tick(.init(slug: "leg-press", day: 1, week: "2026-W40",
                                          sets: 3, reps: nil, weightKg: nil,
                                          done: true)))
        let order = LockedBox()
        StubProtocol.handler = { request in
            let line = "\(request.httpMethod!) \(request.url!.path)"
            order.value = (order.value.map { $0 + "\n" } ?? "") + line
            if request.url!.path.hasSuffix("/exercises") { return self.ok(self.library) }
            if request.url!.path.hasSuffix("/completions") {
                return self.ok(Data(#"{"ok":true}"#.utf8))
            }
            return self.ok(self.generated)
        }
        let model = makeModel()
        await model.loadPlan()

        let lines = (order.value ?? "").split(separator: "\n").map(String.init)
        XCTAssertEqual(Array(lines.prefix(3)), ["PUT /api/v1/plan/days/1",
                                                "POST /api/v1/completions",
                                                "GET /api/v1/plan"])
        let left = await queue().pending()
        XCTAssertTrue(left.isEmpty)
    }

    func testResetPutsTheOriginalBackWithoutSignal() async {
        StubProtocol.handler = { request in
            let path = request.url!.path
            if path.contains("/plan/days/") { throw URLError(.notConnectedToInternet) }
            if path.hasSuffix("/exercises") { return self.ok(self.library) }
            return self.ok(self.plan([self.row("leg-press", "Leg press"),
                                      self.row("plank", "Plank")], edited: true))
        }
        let model = makeModel()
        await model.loadPlan()
        await model.resetDay(1)

        XCTAssertEqual(slugs(model), ["goblet-squat", "plank"])
        XCTAssertFalse(model.plan!.days[0].edited)
        let pending = await queue().pending()
        XCTAssertEqual(pending, [.resetDay(week: "2026-W40", day: 1)])
    }

    /// Before the library has ever downloaded there is nothing to build the
    /// row from, so nothing changes and nothing is sent.
    func testAnExerciseMissingFromTheLibraryChangesNothing() async {
        let sent = LockedBox()
        serve { _ in
            sent.value = "sent"
            return self.ok(self.generated)
        }
        let model = makeModel()
        await model.loadPlan()
        await model.add(day: 1, slug: "moon-squat")
        XCTAssertEqual(slugs(model), ["goblet-squat", "plank"])
        XCTAssertNil(sent.value)
    }
}
