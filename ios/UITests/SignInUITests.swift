import XCTest

final class SignInUITests: AppUITestCase {

    func testSignsInAndReachesThePlan() {
        let app = XCUIApplication()
        app.launch()
        signOutIfNeeded(app)
        signIn(app, password: password)

        XCTAssertTrue(planIsShowing(app), "did not reach the plan screen")
    }

    /// The whole point of storing credentials: a 30-day cookie must not mean
    /// a password prompt on the second launch.
    func testStaysSignedInAcrossLaunches() {
        let app = XCUIApplication()
        app.launch()
        signOutIfNeeded(app)
        signIn(app, password: password)
        XCTAssertTrue(planIsShowing(app))

        app.terminate()
        app.launch()

        XCTAssertTrue(planIsShowing(app),
                      "the app asked for a password again after a relaunch")
    }

    /// The branch that distinguishes the two 303s. Easy to get silently wrong,
    /// because a wrong password redirects with the same status as a right one.
    func testWrongPasswordShowsAnError() {
        let app = XCUIApplication()
        app.launch()
        signOutIfNeeded(app)
        signIn(app, password: "definitely-wrong")

        XCTAssertTrue(app.staticTexts["That email and password didn't match an account."]
                        .waitForExistence(timeout: 15),
                      "a wrong password must not sign in")
    }
}
