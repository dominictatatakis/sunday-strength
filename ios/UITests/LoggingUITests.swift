import XCTest

final class LoggingUITests: AppUITestCase {

    /// Logs a set through the sheet and checks the row shows it. Whether it
    /// reached the database is checked separately, against the API — an
    /// optimistic UI will happily tick a row that never saved.
    func testLogsASetAndShowsIt() {
        let app = launchSignedIn()

        // The first cell is the section header, which is not tappable; the
        // exercise row is the button inside a cell.
        let row = app.cells.buttons.firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        row.tap()

        let save = app.buttons["Save"]
        XCTAssertTrue(save.waitForExistence(timeout: 10),
                      "the log sheet did not open")

        // Default 3 sets, 10 reps; step reps once so the value is distinctive.
        app.steppers.element(boundBy: 1).buttons.element(boundBy: 1).tap()
        save.tap()

        XCTAssertTrue(app.staticTexts["3 × 11"].waitForExistence(timeout: 10),
                      "the row did not show the logged set")
    }
}
