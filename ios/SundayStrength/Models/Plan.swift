import Foundation

struct Plan: Codable, Equatable {
    let week: Int
    let weekKey: String
    let equipment: String
    let run: String?
    let notes: [String]
    var days: [PlanDay]
}

struct PlanDay: Codable, Equatable, Identifiable {
    let day: Int
    let title: String
    var exercises: [PlanExercise]
    /// Rearranged by the subscriber rather than as generated.
    var edited: Bool
    /// The generated day's slugs: what Reset puts back, even without signal.
    var original: [String]?

    var id: Int { day }
}

extension PlanDay {
    /// A plan cached before days could be edited has neither field, and must
    /// still open in a gym with no signal.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        day = try c.decode(Int.self, forKey: .day)
        title = try c.decode(String.self, forKey: .title)
        exercises = try c.decode([PlanExercise].self, forKey: .exercises)
        edited = try c.decodeIfPresent(Bool.self, forKey: .edited) ?? false
        original = try c.decodeIfPresent([String].self, forKey: .original)
    }

    /// The server's copy of a day the phone has just changed.
    ///
    /// Rows already on screen keep the phone's state: a set logged while the
    /// change was in flight is newer than the server's answer. Rows the
    /// change brought in take the server's, which knows about a log hidden
    /// while that exercise was out of the day. If the day has changed again
    /// since, what the phone shows stands.
    func adopting(_ server: PlanDay, newcomers: Set<String>) -> PlanDay {
        guard server.exercises.map(\.slug) == exercises.map(\.slug) else {
            return self
        }
        var day = server
        day.exercises = zip(exercises, server.exercises).map { local, remote in
            newcomers.contains(local.slug) ? remote : local
        }
        return day
    }
}

struct PlanExercise: Codable, Equatable, Identifiable {
    let name: String
    let slug: String
    /// The prescription, e.g. "3 x 10-12" — a string, not a count.
    let sets: String
    let equipment: String
    let alts: [Alt]
    var done: Bool
    var setsDone: Int?
    var reps: Int?
    var weightKg: Double?

    var id: String { slug }
}

struct Alt: Codable, Equatable, Hashable {
    let name: String
    let slug: String
}
