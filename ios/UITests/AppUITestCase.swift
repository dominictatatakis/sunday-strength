import XCTest

/// Shared setup for tests that drive the real app against a local server.
///
/// Needs a throwaway server on :8123 with the ios-test@example.com account —
/// see ios/README.md. Skips rather than fails when there is none, so a plain
/// `xcodebuild test` stays green on a machine without one.
class AppUITestCase: XCTestCase {

    let email = "ios-test@example.com"
    let password = "testpass123"

    override func setUpWithError() throws {
        continueAfterFailure = false
        try XCTSkipUnless(Self.serverIsUp(), "no server on :8123")
    }

    static func serverIsUp() -> Bool {
        let url = URL(string: "http://localhost:8123/health")!
        var reachable = false
        let done = DispatchSemaphore(value: 0)
        URLSession(configuration: .ephemeral).dataTask(with: url) { _, response, _ in
            reachable = (response as? HTTPURLResponse)?.statusCode == 200
            done.signal()
        }.resume()
        _ = done.wait(timeout: .now() + 5)
        return reachable
    }

    /// Signed in is identified by the tab bar plus at least one exercise row,
    /// rather than by any particular exercise: which movements appear depends
    /// on the week, and these tests should not break every Monday.
    func planIsShowing(_ app: XCUIApplication) -> Bool {
        guard app.tabBars.buttons["Plan"].waitForExistence(timeout: 15) else {
            return false
        }
        return app.cells.firstMatch.waitForExistence(timeout: 5)
    }

    func openSettings(_ app: XCUIApplication) {
        let tab = app.tabBars.buttons["Settings"]
        XCTAssertTrue(tab.waitForExistence(timeout: 10), "no Settings tab")
        tab.tap()
    }

    /// Signs out first if a previous run left credentials in the Keychain.
    /// Sign out lives in Settings, so this has to go there to reach it.
    func signOutIfNeeded(_ app: XCUIApplication) {
        guard app.tabBars.buttons["Settings"].waitForExistence(timeout: 5) else {
            return          // already signed out
        }
        openSettings(app)
        let signOut = app.buttons["Sign out"]
        if signOut.waitForExistence(timeout: 5) {
            signOut.tap()
        }
    }

    func signIn(_ app: XCUIApplication, password: String) {
        let emailField = app.textFields["Email"]
        XCTAssertTrue(emailField.waitForExistence(timeout: 10),
                      "login screen never appeared")
        emailField.tap()
        emailField.typeText(email)

        let passwordField = app.secureTextFields["Password"]
        passwordField.tap()
        passwordField.typeText(password)

        app.buttons["Sign in"].tap()
    }

    /// Waits for a condition on an element — existence is not the same as
    /// being ready to tap.
    @discardableResult
    func wait(for element: XCUIElement, toBe predicate: String,
              timeout: TimeInterval = 15) -> Bool {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: predicate), object: element)
        return XCTWaiter().wait(for: [expectation], timeout: timeout) == .completed
    }

    /// Launches signed in, whatever state the previous test left behind.
    ///
    /// Waits for the keyboard to go before returning. When this signs in via
    /// the form rather than restoring, the keyboard is still dismissing over
    /// the plan list, and a tap aimed at the first row lands on nothing — an
    /// intermittent failure that only appeared when a previous test had
    /// signed out.
    func launchSignedIn() -> XCUIApplication {
        let app = XCUIApplication()
        app.launch()
        if !app.tabBars.buttons["Plan"].waitForExistence(timeout: 8) {
            signIn(app, password: password)
            XCTAssertTrue(planIsShowing(app), "could not sign in")
            // Relaunch so the session is restored from the Keychain instead.
            // On the form path the keyboard is still dismissing over the list
            // and the first row stays untappable — a failure that only ever
            // appeared when a previous test had signed out.
            app.terminate()
            app.launch()
        }
        XCTAssertTrue(planIsShowing(app), "could not reach the plan screen")
        return app
    }
}
