import XCTest

/// Swap, add, remove and reset against a local server. Each test puts day 1
/// back first and last, so runs don't pile edits on one another.
final class EditingUITests: AppUITestCase {

    /// The ⓘ on the first exercise row. Its label, "How to do <name>", is the
    /// steadiest handle on the row: the row is a button, so its texts are
    /// exposed as buttons rather than static texts.
    private func firstInfo(_ app: XCUIApplication) -> XCUIElement {
        // Cell 0 is the section header; cell 1 the first exercise.
        app.cells.element(boundBy: 1)
            .buttons.matching(identifier: "howto").firstMatch
    }

    /// Plan rows showing an exercise, whatever element type holds its name.
    private func rows(named name: String, in app: XCUIApplication) -> XCUIElementQuery {
        app.cells.containing(NSPredicate(format: "label == %@", name))
    }

    private func resetIfEdited(_ app: XCUIApplication) {
        let reset = app.buttons["Reset day to the original plan"].firstMatch
        if reset.waitForExistence(timeout: 3) {
            reset.tap()
            XCTAssertTrue(wait(for: reset, toBe: "exists == false"))
        }
    }

    func testSwapsFromTheHowToScreen() {
        let app = launchSignedIn()
        resetIfEdited(app)
        let info = firstInfo(app)
        XCTAssertTrue(info.waitForExistence(timeout: 10))
        let label = info.label

        info.tap()
        XCTAssertTrue(app.buttons["Done"].waitForExistence(timeout: 10),
                      "the how-to did not open")
        XCTAssertFalse(app.buttons["Save"].exists, "ⓘ must not open the log sheet too")
        // The swaps sit below the steps, and a list only builds the rows it
        // has scrolled to.
        let swap = app.buttons.matching(identifier: "swap").firstMatch
        for _ in 0..<4 where !swap.exists {
            app.swipeUp()
        }
        XCTAssertTrue(swap.waitForExistence(timeout: 5), "no swaps offered")
        swap.tap()

        XCTAssertTrue(wait(for: firstInfo(app),
                           toBe: NSPredicate(format: "label != %@", label).predicateFormat),
                      "the first row is still \(label)")
        resetIfEdited(app)
        XCTAssertTrue(wait(for: firstInfo(app),
                           toBe: NSPredicate(format: "label == %@", label).predicateFormat),
                      "reset did not bring it back")
    }

    func testAddsThenRemovesAnExercise() {
        let app = launchSignedIn()
        resetIfEdited(app)

        // Learn what the picker offers first, then count that name on the
        // plan with the picker closed: open, it would count its own row too.
        let add = app.buttons["Add exercise"].firstMatch
        let pick = app.buttons.matching(identifier: "pick").firstMatch
        add.tap()
        XCTAssertTrue(pick.waitForExistence(timeout: 10), "the picker did not open")
        let name = pick.staticTexts.firstMatch.label
        app.buttons["Cancel"].tap()
        XCTAssertTrue(wait(for: pick, toBe: "exists == false"))
        let named = rows(named: name, in: app)
        let before = named.count

        add.tap()
        XCTAssertTrue(pick.waitForExistence(timeout: 10))
        XCTAssertEqual(pick.staticTexts.firstMatch.label, name)
        pick.tap()
        XCTAssertTrue(wait(for: pick, toBe: "exists == false"))

        XCTAssertTrue(wait(for: named.element(boundBy: before), toBe: "exists == true"),
                      "\(name) was not added\n" + app.debugDescription)
        named.element(boundBy: 0).swipeLeft()
        app.buttons["Remove"].tap()
        XCTAssertTrue(wait(for: named.element(boundBy: before), toBe: "exists == false"),
                      "\(name) was not removed")
        resetIfEdited(app)
    }
}
