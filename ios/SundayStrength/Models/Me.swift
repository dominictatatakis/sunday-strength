import Foundation

struct Me: Codable, Equatable {
    let email: String
    let status: String
    let daysPerWeek: Int
    let experience: String
    let equipment: String
    let includeRun: Bool
}
