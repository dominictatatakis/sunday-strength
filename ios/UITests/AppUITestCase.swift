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

    /// The plan screen is identified by its Sign out control plus at least one
    /// exercise row, rather than by any particular exercise: which movements
    /// appear depends on the week, and these tests should not break every Monday.
    func planIsShowing(_ app: XCUIApplication) -> Bool {
        guard app.buttons["Sign out"].waitForExistence(timeout: 15) else {
            return false
        }
        return app.cells.firstMatch.waitForExistence(timeout: 5)
    }

    /// Signs out first if a previous run left credentials in the Keychain.
    func signOutIfNeeded(_ app: XCUIApplication) {
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

    /// Launches signed in, whatever state the previous test left behind.
    func launchSignedIn() -> XCUIApplication {
        let app = XCUIApplication()
        app.launch()
        if !app.buttons["Sign out"].waitForExistence(timeout: 8) {
            signIn(app, password: password)
        }
        XCTAssertTrue(planIsShowing(app), "could not reach the plan screen")
        return app
    }
}
