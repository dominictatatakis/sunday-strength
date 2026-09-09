import XCTest
@testable import SundayStrength

final class ModelDecodingTests: XCTestCase {

    private func fixture(_ name: String) throws -> Data {
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
