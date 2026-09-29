import Foundation

/// The order the exercise picker offers the library in: what suits the
/// moment first. Swapping a squat shows other squats, then the rest of legs;
/// adding to a leg day shows legs and core before anything else.
enum PickerOrder {
    struct Group: Equatable, Identifiable {
        let title: String
        let exercises: [LibraryExercise]

        var id: String { title }
    }

    private static let partNames = ["legs": "Legs", "push": "Push",
                                    "pull": "Pull", "core": "Core"]

    /// - Parameters:
    ///   - day: the day being changed. Its exercises are never offered.
    ///   - replacing: the slug being swapped out, or nil when adding.
    ///   - search: keeps the names containing it, in the same groups.
    static func groups(library: [LibraryExercise], day: PlanDay,
                       replacing: String?, search: String = "") -> [Group] {
        let inDay = Set(day.exercises.map(\.slug))
        let bySlug = Dictionary(library.map { ($0.slug, $0) },
                                uniquingKeysWith: { first, _ in first })
        var remaining = library
            .filter { !inDay.contains($0.slug) }
            .sorted {
                $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            }
        var groups: [Group] = []

        func take(_ title: String, where matches: (LibraryExercise) -> Bool) {
            groups.append(Group(title: title, exercises: remaining.filter(matches)))
            remaining.removeAll(where: matches)
        }

        var dayParts: [String] = []
        for part in day.exercises.compactMap({ bySlug[$0.slug]?.part })
        where !dayParts.contains(part) {
            dayParts.append(part)
        }

        if let replacing, let old = bySlug[replacing] {
            let suggested = old.alternatives.compactMap { alt in
                remaining.first { $0.slug == alt.slug }
            }
            groups.append(Group(title: "Suggested", exercises: suggested))
            remaining.removeAll { option in
                suggested.contains { $0.slug == option.slug }
            }
            take("Same movement") { !Set($0.patterns).isDisjoint(with: old.patterns) }
            take(name(of: old.part)) { $0.part == old.part }
            for part in dayParts where part != old.part {
                take(name(of: part)) { $0.part == part }
            }
        } else {
            for part in dayParts {
                take(name(of: part)) { $0.part == part }
            }
        }
        take("Everything else") { _ in true }

        let query = search.trimmingCharacters(in: .whitespaces)
        return groups.compactMap { group in
            let shown = query.isEmpty ? group.exercises
                : group.exercises.filter {
                    $0.name.localizedCaseInsensitiveContains(query)
                }
            return shown.isEmpty ? nil : Group(title: group.title, exercises: shown)
        }
    }

    private static func name(of part: String) -> String {
        partNames[part] ?? part.capitalized
    }
}
