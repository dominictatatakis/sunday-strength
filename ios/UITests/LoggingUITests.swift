import XCTest

final class LoggingUITests: AppUITestCase {

    /// Logs a set through the sheet and checks the row shows it. Whether it
    /// reached the database is checked separately, against the API — an
    /// optimistic UI will happily tick a row that never saved.
    ///
    /// Clears any existing log first so the run starts from a known state.
    /// Without that the test increments the same row's reps on every run and
    /// is really asserting on whatever the last run left behind.
    func testLogsASetAndShowsIt() {
        let app = launchSignedIn()

        // Cell 0 is the section header; cell 1 is the first exercise.
        let row = app.cells.element(boundBy: 1)
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(wait(for: row, toBe: "isHittable == true"),
                      "the row never became tappable")

        row.tap()
        let clear = app.buttons["Clear this log"]
        if clear.waitForExistence(timeout: 5) {
            clear.tap()
            XCTAssertTrue(wait(for: row, toBe: "isHittable == true"))
            row.tap()
        }

        let save = app.buttons["Save"]
        XCTAssertTrue(save.waitForExistence(timeout: 10),
                      "the log sheet did not open")

        // A cleared row defaults to 3 sets and 10 reps; step reps once.
        XCTAssertEqual(value(in: app, startingWith: "Sets: "), 3)
        XCTAssertEqual(value(in: app, startingWith: "Reps: "), 10)
        app.steppers.element(boundBy: 1).buttons.element(boundBy: 1).tap()
        save.tap()

        let logged = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS %@", "3 × 11"))
            .firstMatch
        XCTAssertTrue(logged.waitForExistence(timeout: 10),
                      "no element shows the logged set\n" + app.debugDescription)
    }

    private func value(in app: XCUIApplication, startingWith prefix: String) -> Int {
        let label = app.staticTexts
            .matching(NSPredicate(format: "label BEGINSWITH %@", prefix))
            .firstMatch
        XCTAssertTrue(label.waitForExistence(timeout: 5), "no '\(prefix)' label")
        return Int(label.label.replacingOccurrences(of: prefix, with: "")) ?? 0
    }
}
