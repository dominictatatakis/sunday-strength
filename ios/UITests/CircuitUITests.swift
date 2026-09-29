import XCTest

/// Runs a day's abs circuit through against a local server, skipping each
/// move, and checks it ends ticked off. Leaves it not done afterwards.
final class CircuitUITests: AppUITestCase {

    func testRunsTheCircuitAndTicksItOff() {
        let app = launchSignedIn()
        let row = app.buttons.matching(identifier: "circuit").firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), "no abs circuit row")
        if !row.isHittable { app.swipeUp() }
        row.tap()

        let start = app.buttons["startCircuit"]
        XCTAssertTrue(start.waitForExistence(timeout: 10), "the circuit page did not open")
        let undo = app.buttons["Mark as not done"]
        if undo.exists {
            undo.tap()
            XCTAssertTrue(app.buttons["Mark as done"].waitForExistence(timeout: 5))
        }

        start.tap()
        XCTAssertTrue(app.staticTexts["Move 1 of 5"].waitForExistence(timeout: 5))
        let skip = app.buttons["skip"]
        for _ in 0..<5 {
            skip.tap()
        }
        XCTAssertTrue(app.staticTexts["Circuit done"].waitForExistence(timeout: 5),
                      "skipping every move should finish the circuit")

        app.buttons["Back to the moves"].tap()
        XCTAssertTrue(app.staticTexts["Done today"].waitForExistence(timeout: 5),
                      "finishing should tick the circuit off")
        app.buttons["Mark as not done"].tap()
        XCTAssertTrue(app.buttons["Mark as done"].waitForExistence(timeout: 5))
    }
}
