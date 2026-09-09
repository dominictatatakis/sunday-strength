import XCTest
@testable import SundayStrength

final class OfflineQueueTests: XCTestCase {

    private var url: URL!

    override func setUp() {
        super.setUp()
        url = FileManager.default.temporaryDirectory
            .appendingPathComponent("queue-\(UUID().uuidString).json")
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: url)
        super.tearDown()
    }

    private func tick(_ slug: String, sets: Int?, done: Bool = true) -> CompletionBody {
        .init(slug: slug, day: 1, week: "2026-W37", sets: sets,
              reps: 10, weightKg: 20, done: done)
    }

    func testStartsEmpty() async {
        let queue = OfflineQueue(fileURL: url)
        let pending = await queue.pending()
        XCTAssertTrue(pending.isEmpty)
    }

    func testEnqueueAndRead() async {
        let queue = OfflineQueue(fileURL: url)
        await queue.enqueue(tick("goblet-squat", sets: 3))
        let pending = await queue.pending()
        XCTAssertEqual(pending.count, 1)
        XCTAssertEqual(pending.first?.slug, "goblet-squat")
    }

    /// Two ticks on the same slot are one intention, not two. Keeping both
    /// would replay a stale value over a newer one.
    func testNewestWinsPerSlot() async {
        let queue = OfflineQueue(fileURL: url)
        await queue.enqueue(tick("goblet-squat", sets: 3))
        await queue.enqueue(tick("goblet-squat", sets: 5))
        let pending = await queue.pending()
        XCTAssertEqual(pending.count, 1)
        XCTAssertEqual(pending.first?.sets, 5)
    }

    func testDifferentSlotsBothKept() async {
        let queue = OfflineQueue(fileURL: url)
        await queue.enqueue(tick("goblet-squat", sets: 3))
        await queue.enqueue(tick("bench-press", sets: 3))
        let pending = await queue.pending()
        XCTAssertEqual(pending.count, 2)
    }

    func testUntickReplacesTick() async {
        let queue = OfflineQueue(fileURL: url)
        await queue.enqueue(tick("goblet-squat", sets: 3))
        await queue.enqueue(tick("goblet-squat", sets: nil, done: false))
        let pending = await queue.pending()
        XCTAssertEqual(pending.count, 1)
        XCTAssertEqual(pending.first?.done, false)
    }

    func testRemoveDropsOne() async {
        let queue = OfflineQueue(fileURL: url)
        let entry = tick("goblet-squat", sets: 3)
        await queue.enqueue(entry)
        await queue.remove(entry)
        let pending = await queue.pending()
        XCTAssertTrue(pending.isEmpty)
    }

    func testSurvivesRelaunch() async {
        let first = OfflineQueue(fileURL: url)
        await first.enqueue(tick("goblet-squat", sets: 3))
        let second = OfflineQueue(fileURL: url)
        let pending = await second.pending()
        XCTAssertEqual(pending.count, 1)
    }
}
