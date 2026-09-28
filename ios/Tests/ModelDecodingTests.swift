import XCTest
@testable import SundayStrength

final class ModelDecodingTests: XCTestCase {

    func fixture(_ name: String) throws -> Data {
        let url = Bundle(for: Self.self)
            .url(forResource: name, withExtension: "json")!
        return try Data(contentsOf: url)
    }

    func testDecodesMe() throws {
        let me = try JSON.decoder.decode(Me.self, from: fixture("me"))
        XCTAssertEqual(me.email, "ios-test@example.com")
        XCTAssertEqual(me.daysPerWeek, 4)
        XCTAssertEqual(me.experience, "intermediate")
        XCTAssertTrue(me.includeRun)
    }

    func testDecodesPlan() throws {
        let plan = try JSON.decoder.decode(Plan.self, from: fixture("plan"))
        XCTAssertEqual(plan.days.count, 4)
        XCTAssertTrue(plan.weekKey.hasPrefix("2026-W"))
        let first = plan.days[0]
        XCTAssertEqual(first.day, 1)
        XCTAssertFalse(first.exercises.isEmpty)
    }

    /// `sets` is the prescription string, `sets_done` the count actually done.
    func testSetsIsAStringAndSetsDoneAnInt() throws {
        let plan = try JSON.decoder.decode(Plan.self, from: fixture("plan"))
        let ex = plan.days[0].exercises[0]
        XCTAssertFalse(ex.sets.isEmpty)
        XCTAssertNil(ex.setsDone)
        XCTAssertFalse(ex.done)
    }

    func testEncodesCompletionInSnakeCase() throws {
        let body = CompletionBody(slug: "goblet-squat", day: 1,
                                  week: "2026-W37", sets: 3, reps: 10,
                                  weightKg: 22.5, done: true)
        let json = try JSON.encoder.encode(body)
        let text = String(decoding: json, as: UTF8.self)
        XCTAssertTrue(text.contains("\"weight_kg\":22.5"))
        XCTAssertFalse(text.contains("weightKg"))
    }
}

extension ModelDecodingTests {
    func testDecodesTheOptionsServedWithTheProfile() throws {
        let me = try JSON.decoder.decode(Me.self, from: try fixture("me"))
        XCTAssertEqual(me.options.daysPerWeek, [2, 3, 4, 5])
        XCTAssertEqual(me.options.experience,
                       ["beginner", "intermediate", "advanced"])
        XCTAssertEqual(me.options.equipment.map(\.value),
                       ["bodyweight", "dumbbells", "full"])
        XCTAssertEqual(me.options.equipment.first?.name, "Bodyweight only")
    }

    /// nil means "leave it alone", so a nil field must not be sent at all —
    /// encoding it as null would blank the value server-side.
    func testPatchOmitsUnsetFields() throws {
        var patch = PrefsPatch()
        patch.daysPerWeek = 3
        let text = String(decoding: try JSON.encoder.encode(patch), as: UTF8.self)
        XCTAssertTrue(text.contains("\"days_per_week\":3"))
        XCTAssertFalse(text.contains("experience"))
        XCTAssertFalse(text.contains("equipment"))
        XCTAssertFalse(text.contains("include_run"))
    }
}

extension ModelDecodingTests {
    func testDecodesTheLibrary() throws {
        let library = try JSON.decoder.decode(Library.self, from: fixture("exercises"))
        let squat = library.exercises[0]
        XCTAssertTrue(squat.youtubeUrl.hasPrefix("https://www.youtube.com/"))
        XCTAssertEqual(squat.patterns, ["squat"])
        XCTAssertEqual(squat.images.count, 2)
        XCTAssertEqual(squat.alternatives.count, 3)
    }

    /// A swapped-in row carries two swaps, as the plan's own rows do.
    func testALibraryEntryBecomesAnUnloggedPlanRow() throws {
        let library = try JSON.decoder.decode(Library.self, from: fixture("exercises"))
        let row = library.exercises[0].planExercise
        XCTAssertEqual(row.slug, "goblet-squat")
        XCTAssertEqual(row.sets, "3 x 10-12")
        XCTAssertEqual(row.alts.map(\.slug), ["box-squat", "leg-press"])
        XCTAssertFalse(row.done)
    }

    /// Plans cached before days could be edited must still open offline.
    func testAPlanWithoutEditFlagsReadsAsUnedited() throws {
        let plan = try JSON.decoder.decode(Plan.self, from: fixture("plan"))
        XCTAssertFalse(plan.days[0].edited)
        XCTAssertNil(plan.days[0].original)
    }

    func testQueuedChangesSurviveARoundTrip() throws {
        let changes: [QueuedChange] = [
            .tick(.init(slug: "plank", day: 1, week: "2026-W40", sets: 3,
                        reps: nil, weightKg: nil, done: true)),
            .setDay(.init(week: "2026-W40", day: 1, slugs: ["plank"])),
            .resetDay(week: "2026-W40", day: 2),
        ]
        let data = try JSON.encoder.encode(changes)
        XCTAssertEqual(try JSON.decoder.decode([QueuedChange].self, from: data),
                       changes)
    }
}

final class AdoptingTests: XCTestCase {
    private func row(_ slug: String, done: Bool = false,
                     name: String? = nil) -> PlanExercise {
        PlanExercise(name: name ?? slug, slug: slug, sets: "3 x 10",
                     equipment: "full", alts: [], done: done,
                     setsDone: done ? 3 : nil, reps: nil, weightKg: nil)
    }

    private func day(_ rows: [PlanExercise]) -> PlanDay {
        PlanDay(day: 1, title: "Day 1", exercises: rows, edited: true,
                original: ["a", "b"])
    }

    /// A tick made while the swap was in flight is newer than the server's copy.
    func testRowsAlreadyShownKeepTheirLocalState() {
        let local = day([row("a", done: true), row("c")])
        let server = day([row("a", done: false), row("c", done: true, name: "C")])
        let merged = local.adopting(server, newcomers: ["c"])
        XCTAssertTrue(merged.exercises[0].done, "the local tick must survive")
        XCTAssertEqual(merged.exercises[1].name, "C",
                       "a newcomer takes the server's row")
        XCTAssertTrue(merged.exercises[1].done,
                      "and the log the server knows about")
    }

    func testADayChangedAgainMeanwhileStaysAsShown() {
        let local = day([row("a"), row("d")])
        let server = day([row("a"), row("c")])
        XCTAssertEqual(local.adopting(server, newcomers: ["c"]), local)
    }
}
