import XCTest

/// Drives the real app against a local server, because this repo's guidance is
/// that several of its bugs only ever showed up when the actual flow was run.
///
/// Needs a throwaway server on :8123 with the ios-test@example.com account —
/// see ios/README.md. Skips itself rather than failing when there is none, so
/// a plain `xcodebuild test` on a machine with no server stays green.
final class SignInUITests: XCTestCase {

    private let email = "ios-test@example.com"
    private let password = "testpass123"

    override func setUpWithError() throws {
        continueAfterFailure = false
        try XCTSkipUnless(Self.serverIsUp(), "no server on :8123")
    }

    private static func serverIsUp() -> Bool {
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

    /// Signs out first if a previous run left credentials in the Keychain.
    private func signOutIfNeeded(_ app: XCUIApplication) {
        let signOut = app.buttons["Sign out"]
        if signOut.waitForExistence(timeout: 5) {
            signOut.tap()
        }
    }

    private func signIn(_ app: XCUIApplication, password: String) {
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

    func testSignsInAndReachesThePlan() {
        let app = XCUIApplication()
        app.launch()
        signOutIfNeeded(app)
        signIn(app, password: password)

        XCTAssertTrue(app.staticTexts["Signed in as \(email)"]
                        .waitForExistence(timeout: 15),
                      "did not reach the signed-in screen")
    }

    /// The whole point of storing credentials: a 30-day cookie must not mean
    /// a password prompt on the second launch.
    func testStaysSignedInAcrossLaunches() {
        let app = XCUIApplication()
        app.launch()
        signOutIfNeeded(app)
        signIn(app, password: password)
        XCTAssertTrue(app.staticTexts["Signed in as \(email)"]
                        .waitForExistence(timeout: 15))

        app.terminate()
        app.launch()

        XCTAssertTrue(app.staticTexts["Signed in as \(email)"]
                        .waitForExistence(timeout: 15),
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
