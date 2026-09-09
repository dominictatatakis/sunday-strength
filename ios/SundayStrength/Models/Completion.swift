import Foundation

/// Body of POST /api/v1/completions. `done: false` deletes the entry.
struct CompletionBody: Codable, Equatable {
    let slug: String
    let day: Int
    let week: String
    let sets: Int?
    let reps: Int?
    let weightKg: Double?
    let done: Bool
}
