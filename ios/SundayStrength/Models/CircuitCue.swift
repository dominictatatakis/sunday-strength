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

    /// (frequency in Hz, seconds); 0 Hz is a gap.
    var notes: [(Double, Double)] {
        switch self {
        case .start: [(880, 0.12), (0, 0.06), (1320, 0.2)]
        case .stop: [(440, 0.7)]
        case .countdown: [(660, 0.09)]
        case .finish: [(660, 0.15), (880, 0.15), (1320, 0.45)]
        }
    }

    /// The countdown is quieter so the stop and start stand out.
    var volume: Float {
        self == .countdown ? 0.5 : 1
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
