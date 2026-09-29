import Foundation
import Observation

/// Where a running circuit is, given the seconds since it started. A pure
/// function of elapsed time, so a pause or a locked phone is just a
/// different number going in.
struct CircuitTimer: Equatable {
    let work: Int
    let rest: Int
    let moves: Int

    enum Phase: Equatable {
        case work, rest
    }

    struct Position: Equatable {
        /// 0-based.
        let move: Int
        let phase: Phase
        /// Whole seconds left in this stretch, rounded up: "1" shows for the
        /// whole last second rather than "0" while still going.
        let remaining: Int
    }

    /// No rest after the last move.
    var total: Int {
        moves * work + max(moves - 1, 0) * rest
    }

    /// Nil once the circuit is over.
    func position(at elapsed: TimeInterval) -> Position? {
        guard moves > 0, elapsed < Double(total) else { return nil }
        let elapsed = max(elapsed, 0)
        let block = Double(work + rest)
        let move = min(Int(elapsed / block), moves - 1)
        let into = elapsed - Double(move) * block
        if into < Double(work) {
            return Position(move: move, phase: .work,
                            remaining: Int((Double(work) - into).rounded(.up)))
        }
        return Position(move: move, phase: .rest,
                        remaining: Int((block - into).rounded(.up)))
    }

    /// When a move's work begins, for Skip.
    func start(of move: Int) -> TimeInterval {
        Double(move * (work + rest))
    }
}

/// One run of the circuit: the timer plus the clock times that drive it.
@Observable
final class CircuitRun {
    let timer: CircuitTimer
    /// Seconds run before the current stretch of running.
    private var banked: TimeInterval = 0
    /// When running last resumed; nil while paused.
    private var resumed: Date?

    init(timer: CircuitTimer, startedAt: Date = .now) {
        self.timer = timer
        self.resumed = startedAt
    }

    var isPaused: Bool { resumed == nil }

    func elapsed(at now: Date) -> TimeInterval {
        banked + (resumed.map { now.timeIntervalSince($0) } ?? 0)
    }

    func pause(at now: Date) {
        guard !isPaused else { return }
        banked = elapsed(at: now)
        resumed = nil
    }

    func resume(at now: Date) {
        guard isPaused else { return }
        resumed = now
    }

    /// Straight to the next move's work, or to the end from the last move.
    func skip(at now: Date) {
        let next = timer.position(at: elapsed(at: now)).map { $0.move + 1 }
        banked = next.map { $0 < timer.moves ? timer.start(of: $0) : Double(timer.total) }
            ?? Double(timer.total)
        if !isPaused { resumed = now }
    }
}
