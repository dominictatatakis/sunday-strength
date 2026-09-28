import Foundation

/// Body of PUT /api/v1/plan/days/{day}: the whole day, in order. The day is
/// in the path too; the server ignores it here.
struct DayBody: Codable, Equatable {
    let week: String
    let day: Int
    let slugs: [String]
}

/// Something done without signal, replayed in the order it was done.
enum QueuedChange: Codable, Equatable {
    case tick(CompletionBody)
    case setDay(DayBody)
    case resetDay(week: String, day: Int)
}
