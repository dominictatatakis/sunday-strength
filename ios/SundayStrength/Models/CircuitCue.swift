import Foundation

/// A sound the abs circuit makes. Stop and start differ in pitch and rhythm,
/// so you know which it is mid-plank without looking at the phone.
enum CircuitCue: CaseIterable {
    /// Work begins: two quick high beeps.
    case start
    /// Work ends, rest now: one long low beep.
    case stop
    /// One of the last three seconds of work or rest: a short soft beep.
    case countdown
    /// The circuit is over: three rising notes.
    case finish

    /// (frequency in Hz, seconds); 0 Hz is a gap. Nothing below 800 Hz:
    /// phone speakers are weak down there, and the first version's 440 Hz
    /// stop was hard to hear in a gym.
    var notes: [(Double, Double)] {
        switch self {
        case .start: [(1320, 0.25), (0, 0.1), (1760, 0.35)]
        case .stop: [(880, 1.0)]
        case .countdown: [(1100, 0.15)]
        case .finish: [(1320, 0.2), (1760, 0.2), (2640, 0.6)]
        }
    }

    /// The countdown is a little quieter so the stop and start stand out.
    var volume: Float {
        self == .countdown ? 0.8 : 1
    }

    /// What to play as the timer moves from one position to the next: nil
    /// for most ticks, which stay in the same second or above three.
    static func between(_ old: CircuitTimer.Position?,
                        _ new: CircuitTimer.Position?) -> CircuitCue? {
        guard let new else { return old == nil ? nil : .finish }
        guard let old else { return nil }
        if old.move != new.move || old.phase != new.phase {
            return new.phase == .work ? .start : .stop
        }
        if old.remaining != new.remaining, new.remaining <= 3 {
            return .countdown
        }
        return nil
    }
}
