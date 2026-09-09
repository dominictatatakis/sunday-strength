import XCTest

/// Deliberately runs with the server down, so it does not inherit
/// AppUITestCase's skip. Assumes a previous run left the app signed in with a
/// cached plan — which is the real situation: you sign in at home, then walk
/// into a basement gym.
final class OfflineUITests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testTicksASetWithNoConnection() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.buttons["Sign out"].waitForExistence(timeout: 15),
                      "offline launch should show the cached plan, not a login screen")
        XCTAssertTrue(app.staticTexts["Offline — showing your last saved plan."]
                        .waitForExistence(timeout: 10),
                      "no offline banner")

        // Second row: the first already has a log from the online test.
        let row = app.cells.buttons.element(boundBy: 1)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()

        let save = app.buttons["Save"]
        XCTAssertTrue(save.waitForExistence(timeout: 10), "log sheet did not open")
        let reps = app.steppers.element(boundBy: 1).buttons.element(boundBy: 1)
        reps.tap()
        reps.tap()
        save.tap()

        XCTAssertTrue(app.staticTexts["3 × 12"].waitForExistence(timeout: 10),
                      "a tick made offline must stay on screen")
    }
}
