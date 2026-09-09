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

    var id: Int { day }
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

struct Alt: Codable, Equatable {
    let name: String
    let slug: String
}
