import Foundation

/// An exercise the subscriber's kit allows, with its how-to: one entry of
/// GET /api/v1/exercises. Kept on disk for the gym.
struct LibraryExercise: Codable, Equatable, Hashable, Identifiable {
    let slug: String
    let name: String
    /// The prescription at the subscriber's level, e.g. "3 x 10-12".
    let sets: String
    let equipment: String
    /// "legs", "push", "pull" or "core".
    let part: String
    /// Movement patterns such as "hinge": what counts as the same movement.
    let patterns: [String]
    let instructions: [String]
    /// Paths on the server, e.g. "/static/exercises/plank-0.jpg".
    let images: [String]
    let youtubeUrl: String
    let alternatives: [Alt]

    var id: String { slug }

    /// The row a swap or add puts in the plan before the server confirms it,
    /// with two swaps as the plan's own rows carry.
    var planExercise: PlanExercise {
        PlanExercise(name: name, slug: slug, sets: sets, equipment: equipment,
                     alts: Array(alternatives.prefix(2)), done: false,
                     setsDone: nil, reps: nil, weightKg: nil)
    }
}

struct Library: Codable {
    let exercises: [LibraryExercise]
}
