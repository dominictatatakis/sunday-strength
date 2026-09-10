import Foundation

struct Me: Codable, Equatable {
    let email: String
    let status: String
    let daysPerWeek: Int
    let experience: String
    let equipment: String
    let includeRun: Bool
    /// What the preferences are allowed to be. Served with the profile so the
    /// app doesn't hard-code the splits and levels and drift from engine.py.
    let options: PrefOptions
}

struct PrefOptions: Codable, Equatable {
    let daysPerWeek: [Int]
    let experience: [String]
    let equipment: [EquipmentOption]
}

struct EquipmentOption: Codable, Equatable, Identifiable {
    let value: String
    let name: String

    var id: String { value }
}

/// Body of PATCH /api/v1/me. Every field optional: nil leaves it alone.
struct PrefsPatch: Codable, Equatable {
    var daysPerWeek: Int?
    var experience: String?
    var equipment: String?
    var includeRun: Bool?
}
