import XCTest

/* Captures the App Store screenshots from the real app.

   Driven by scripts/screenshots.sh, which sets the simulator appearance from
   outside: -AppleInterfaceStyle as a launch argument is ignored, so a test
   that sets it there renders light and reports dark. Needs the throwaway
   server on :8123, same as every other UI test here. */
final class ScreenshotTests: AppUITestCase {

    private func save(_ name: String, _ app: XCUIApplication) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testCaptureMainScreens() {
        // Sign out first so the sign-in screen is one of the shots.
        let signedOut = XCUIApplication()
        signedOut.launch()
        signOutIfNeeded(signedOut)
        XCTAssertTrue(signedOut.textFields["Email"].waitForExistence(timeout: 10),
                      "expected the sign-in screen after signing out")
        save("A-signin", signedOut)

        // launchSignedIn relaunches after signing in through the form. Doing
        // it by hand leaves the keyboard dismissing over the list, and the
        // first row stays untappable -- which is what the base class is for.
        let app = launchSignedIn()
        save("B-plan", app)

        // The log sheet is the thing people actually use mid-set.
        let row = app.cells.element(boundBy: 1)
        XCTAssertTrue(wait(for: row, toBe: "isHittable == true"),
                      "the first exercise row never became tappable")
        row.tap()
        XCTAssertTrue(app.buttons["Save"].waitForExistence(timeout: 10),
                      "the log sheet did not open")
        save("C-log", app)
        app.buttons["Save"].tap()

        openSettings(app)
        XCTAssertTrue(app.buttons["Sign out"].waitForExistence(timeout: 10))
        save("D-settings", app)
    }
}
