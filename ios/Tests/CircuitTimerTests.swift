import XCTest
@testable import SundayStrength

final class CircuitTimerTests: XCTestCase {

    /// 5 moves of 40 s with 20 s between: 5 × 40 + 4 × 20 = 280 s.
    private let timer = CircuitTimer(work: 40, rest: 20, moves: 5)

    func testTheTotalLeavesOutTheLastRest() {
        XCTAssertEqual(timer.total, 280)
    }

    func testItStartsOnTheFirstMovesWork() {
        XCTAssertEqual(timer.position(at: 0), .init(move: 0, phase: .work, remaining: 40))
    }

    /// "1" shows for the whole last second, never "0" while still working.
    func testTheCountdownRoundsUp() {
        XCTAssertEqual(timer.position(at: 0.2)?.remaining, 40)
        XCTAssertEqual(timer.position(at: 39.5)?.remaining, 1)
    }

    func testRestFollowsWorkThenTheNextMove() {
        XCTAssertEqual(timer.position(at: 40), .init(move: 0, phase: .rest, remaining: 20))
        XCTAssertEqual(timer.position(at: 60), .init(move: 1, phase: .work, remaining: 40))
    }

    func testThereIsNoRestAfterTheLastMove() {
        XCTAssertEqual(timer.position(at: 279), .init(move: 4, phase: .work, remaining: 1))
        XCTAssertNil(timer.position(at: 280))
    }

    /// A side plank's 40 s is 20 s a side, each counted down from 20, so the
    /// last three seconds before switching tick like any other.
    func testASidedMoveCountsDownEachSide() {
        let timer = CircuitTimer(work: 40, rest: 20, moves: 5, sided: [1])
        XCTAssertEqual(timer.position(at: 60), .init(move: 1, phase: .work, remaining: 20, side: .first))
        XCTAssertEqual(timer.position(at: 79.5), .init(move: 1, phase: .work, remaining: 1, side: .first))
        XCTAssertEqual(timer.position(at: 80), .init(move: 1, phase: .work, remaining: 20, side: .second))
        XCTAssertEqual(timer.position(at: 99.5), .init(move: 1, phase: .work, remaining: 1, side: .second))
        XCTAssertEqual(timer.position(at: 100), .init(move: 1, phase: .rest, remaining: 20))
    }

    func testOtherMovesHaveNoSide() {
        let timer = CircuitTimer(work: 40, rest: 20, moves: 5, sided: [1])
        XCTAssertNil(timer.position(at: 30)?.side)
        XCTAssertNil(timer.position(at: 130)?.side)
    }

    /// 45 s splits into 22.5 s a side rather than giving one side more.
    func testAnOddWorkTimeSplitsEvenly() {
        let timer = CircuitTimer(work: 45, rest: 15, moves: 5, sided: [0])
        XCTAssertEqual(timer.position(at: 22.4)?.side, .first)
        XCTAssertEqual(timer.position(at: 22.5)?.side, .second)
        XCTAssertEqual(timer.position(at: 22.5)?.remaining, 23)
    }

    func testSidesDoNotChangeTheTotal() {
        XCTAssertEqual(CircuitTimer(work: 40, rest: 20, moves: 5, sided: [2]).total, 280)
    }
}

final class CircuitRunTests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_000_000)

    private func makeRun() -> CircuitRun {
        CircuitRun(timer: CircuitTimer(work: 40, rest: 20, moves: 5), startedAt: t0)
    }

    func testElapsedFollowsTheClock() {
        XCTAssertEqual(makeRun().elapsed(at: t0 + 30), 30)
    }

    /// Time is worked out from dates, so a locked phone or a pause neither
    /// loses nor adds any.
    func testPauseFreezesItAndResumeCarriesOn() {
        let run = makeRun()
        run.pause(at: t0 + 30)
        XCTAssertTrue(run.isPaused)
        XCTAssertEqual(run.elapsed(at: t0 + 90), 30)
        run.resume(at: t0 + 90)
        XCTAssertFalse(run.isPaused)
        XCTAssertEqual(run.elapsed(at: t0 + 100), 40)
    }

    func testSkipGoesToTheNextMovesWork() {
        let run = makeRun()
        run.skip(at: t0 + 10)
        XCTAssertEqual(run.timer.position(at: run.elapsed(at: t0 + 10)),
                       .init(move: 1, phase: .work, remaining: 40))
    }

    func testSkippingTheLastMoveFinishes() {
        let run = makeRun()
        run.skip(at: t0 + 250)
        XCTAssertNil(run.timer.position(at: run.elapsed(at: t0 + 250)))
    }
}
