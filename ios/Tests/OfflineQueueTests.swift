import XCTest
@testable import SundayStrength

final class OfflineQueueTests: XCTestCase {

    private var url: URL!
    private var legacyURL: URL!

    override func setUp() {
        super.setUp()
        let tmp = FileManager.default.temporaryDirectory
        url = tmp.appendingPathComponent("queue-\(UUID().uuidString).json")
        legacyURL = tmp.appendingPathComponent("ticks-\(UUID().uuidString).json")
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: url)
        try? FileManager.default.removeItem(at: legacyURL)
        super.tearDown()
    }

    /// Never the default legacy path: that is the app's real file.
    private func makeQueue() -> OfflineQueue {
        OfflineQueue(fileURL: url, legacyURL: legacyURL)
    }

    private func tick(_ slug: String, sets: Int?, done: Bool = true) -> QueuedChange {
        .tick(.init(slug: slug, day: 1, week: "2026-W37", sets: sets,
                    reps: 10, weightKg: 20, done: done))
    }

    private func setDay(_ slugs: [String]) -> QueuedChange {
        .setDay(.init(week: "2026-W37", day: 1, slugs: slugs))
    }

    func testStartsEmpty() async {
        let pending = await makeQueue().pending()
        XCTAssertTrue(pending.isEmpty)
    }

    /// Two ticks on the same slot are one intention, not two. Keeping both
    /// would replay a stale value over a newer one.
    func testNewestTickWinsPerSlot() async {
        let queue = makeQueue()
        await queue.enqueue(tick("goblet-squat", sets: 3))
        await queue.enqueue(tick("goblet-squat", sets: 5))
        let pending = await queue.pending()
        XCTAssertEqual(pending, [tick("goblet-squat", sets: 5)])
    }

    func testDifferentSlotsBothKept() async {
        let queue = makeQueue()
        await queue.enqueue(tick("goblet-squat", sets: 3))
        await queue.enqueue(tick("bench-press", sets: 3))
        let pending = await queue.pending()
        XCTAssertEqual(pending.count, 2)
    }

    func testUntickReplacesTick() async {
        let queue = makeQueue()
        await queue.enqueue(tick("goblet-squat", sets: 3))
        await queue.enqueue(tick("goblet-squat", sets: nil, done: false))
        let pending = await queue.pending()
        XCTAssertEqual(pending, [tick("goblet-squat", sets: nil, done: false)])
    }

    /// A tick on a swapped-in exercise is refused until the swap has landed,
    /// so the order things were done in is the order they are sent in.
    func testEditsAndTicksKeepTheirOrder() async {
        let queue = makeQueue()
        await queue.enqueue(setDay(["leg-press"]))
        await queue.enqueue(tick("leg-press", sets: 3))
        await queue.enqueue(setDay(["leg-press", "plank"]))
        let pending = await queue.pending()
        XCTAssertEqual(pending, [setDay(["leg-press"]), tick("leg-press", sets: 3),
                                 setDay(["leg-press", "plank"])])
    }

    func testRemoveDropsOnlyThatEntry() async {
        let queue = makeQueue()
        await queue.enqueue(setDay(["a"]))
        await queue.enqueue(tick("a", sets: 3))
        await queue.remove(setDay(["a"]))
        let pending = await queue.pending()
        XCTAssertEqual(pending, [tick("a", sets: 3)])
    }

    func testSurvivesRelaunch() async {
        await makeQueue().enqueue(setDay(["a"]))
        let pending = await makeQueue().pending()
        XCTAssertEqual(pending, [setDay(["a"])])
    }

    /// Ticks queued by the build before this one were a bare list of bodies.
    func testUpgradesTicksQueuedByTheOldBuild() async throws {
        let old = CompletionBody(slug: "plank", day: 2, week: "2026-W37",
                                 sets: 3, reps: 10, weightKg: nil, done: true)
        try JSON.encoder.encode([old]).write(to: legacyURL)
        let pending = await makeQueue().pending()
        XCTAssertEqual(pending, [.tick(old)])
        XCTAssertFalse(FileManager.default.fileExists(atPath: legacyURL.path))
        let again = await makeQueue().pending()
        XCTAssertEqual(again, [.tick(old)], "the upgrade must have been saved")
    }
}
