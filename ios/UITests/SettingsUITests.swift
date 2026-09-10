import XCTest

final class SettingsUITests: AppUITestCase {

    /// Changes days per week and checks the change sticks.
    ///
    /// Reads the current value from the picker and moves to a different one,
    /// so the test always makes a real change whatever the last run left. It
    /// deliberately does not count day headers in the plan list: only the
    /// headers currently on screen exist in the hierarchy, so counting them
    /// reports whatever happens to be scrolled into view.
    func testChangingDaysPerWeekSticks() {
        let app = launchSignedIn()
        openSettings(app)

        // The picker's label carries its current value ("Days per week, 4").
        let picker = app.buttons
            .matching(NSPredicate(format: "label BEGINSWITH 'Days per week'"))
            .firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 10), app.debugDescription)

        let before = Int(picker.label.filter(\.isNumber)) ?? 4
        let target = before == 4 ? 3 : 4

        picker.tap()
        let option = app.buttons["\(target)"]
        XCTAssertTrue(option.waitForExistence(timeout: 5),
                      "no option '\(target)' in the picker")
        option.tap()

        let save = app.buttons["Save changes"]
        XCTAssertTrue(save.waitForExistence(timeout: 5))
        XCTAssertTrue(wait(for: save, toBe: "isEnabled == true"),
                      "Save stayed disabled after changing \(before) to \(target)")
        save.tap()

        XCTAssertTrue(app.staticTexts["Saved. Your plan has been rebuilt."]
                        .waitForExistence(timeout: 15),
                      "no confirmation after saving")

        // Leave and come back: the form resyncs from the profile the PATCH
        // returned, so this only holds if the server actually accepted it.
        app.tabBars.buttons["Plan"].tap()
        openSettings(app)
        XCTAssertTrue(wait(for: picker, toBe: "label CONTAINS '\(target)'"),
                      "after saving, the picker reads \(picker.label)")
    }
}
