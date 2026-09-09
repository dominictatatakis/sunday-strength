import XCTest

/// Deliberately runs with the server down, so it does not inherit
/// AppUITestCase's skip. Assumes a previous run left the app signed in with a
/// cached plan — which is the real situation: you sign in at home, then walk
/// into a basement gym.
final class OfflineUITests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
        // The inverse of every other UI test: this one needs the server *down*.
        // Skipping keeps a normal `xcodebuild test` green; run it deliberately
        // with the server stopped, as ios/README.md describes.
        try XCTSkipIf(AppUITestCase.serverIsUp(),
                      "stop the server on :8123 to run the offline test")
    }

    func testTicksASetWithNoConnection() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.buttons["Sign out"].waitForExistence(timeout: 15),
                      "offline launch should show the cached plan, not a login screen")
        XCTAssertTrue(app.staticTexts["Offline — showing your last saved plan."]
                        .waitForExistence(timeout: 10),
                      "no offline banner")

        // Cell 0 is the section header, cell 1 the first exercise (already
        // logged by the online test), so cell 2 is the one to tick here.
        let row = app.cells.element(boundBy: 2)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()

        let save = app.buttons["Save"]
        XCTAssertTrue(save.waitForExistence(timeout: 10), "log sheet did not open")
        let reps = app.steppers.element(boundBy: 1).buttons.element(boundBy: 1)
        reps.tap()
        reps.tap()
        save.tap()

        let logged = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS %@", "3 × 12"))
            .firstMatch
        XCTAssertTrue(logged.waitForExistence(timeout: 10),
                      "a tick made offline must stay on screen")
    }
}
