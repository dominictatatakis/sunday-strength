import XCTest
@testable import SundayStrength

final class PickerOrderTests: XCTestCase {

    private func ex(_ slug: String, _ name: String, _ part: String,
                    _ patterns: [String], alts: [String] = []) -> LibraryExercise {
        LibraryExercise(slug: slug, name: name, sets: "3 x 10", equipment: "full",
                        part: part, patterns: patterns, instructions: [], images: [],
                        youtubeUrl: "",
                        alternatives: alts.map { Alt(name: $0, slug: $0) })
    }

    private var library: [LibraryExercise] {
        [ex("back-squat", "Back squat", "legs", ["squat"],
            alts: ["leg-press", "goblet-squat"]),
         ex("goblet-squat", "Goblet squat", "legs", ["squat"]),
         ex("leg-press", "Leg press", "legs", ["squat"]),
         ex("front-squat", "Front squat", "legs", ["squat"]),
         ex("walking-lunge", "Walking lunge", "legs", ["single_leg"]),
         ex("plank", "Plank", "core", ["core"]),
         ex("dead-bug", "Dead bug", "core", ["core"]),
         ex("bench-press", "Bench press", "push", ["h_push"]),
         ex("barbell-row", "Barbell row", "pull", ["row"])]
    }

    private var legDay: PlanDay {
        PlanDay(day: 1, title: "Day 1 - Legs",
                exercises: ["back-squat", "plank"].map {
                    PlanExercise(name: $0, slug: $0, sets: "3 x 10",
                                 equipment: "full", alts: [], done: false,
                                 setsDone: nil, reps: nil, weightKg: nil)
                },
                edited: false, original: nil)
    }

    private func shape(_ groups: [PickerOrder.Group]) -> [String] {
        groups.map { "\($0.title): " + $0.exercises.map(\.name).joined(separator: ", ") }
    }

    /// Swapping a squat: its suggestions, other squats, the rest of legs, the
    /// day's other body part, then everything else.
    func testSwappingPutsTheSameKindOfExerciseFirst() {
        let groups = PickerOrder.groups(library: library, day: legDay,
                                        replacing: "back-squat")
        XCTAssertEqual(shape(groups), [
            "Suggested: Leg press, Goblet squat",
            "Same movement: Front squat",
            "Legs: Walking lunge",
            "Core: Dead bug",
            "Everything else: Barbell row, Bench press",
        ])
    }

    func testAddingPutsTheDaysBodyPartsFirst() {
        let groups = PickerOrder.groups(library: library, day: legDay,
                                        replacing: nil)
        XCTAssertEqual(shape(groups), [
            "Legs: Front squat, Goblet squat, Leg press, Walking lunge",
            "Core: Dead bug",
            "Everything else: Barbell row, Bench press",
        ])
    }

    func testNothingAlreadyInTheDayIsOffered() {
        let offered = PickerOrder.groups(library: library, day: legDay,
                                         replacing: nil)
            .flatMap(\.exercises).map(\.slug)
        XCTAssertFalse(offered.contains("back-squat"))
        XCTAssertFalse(offered.contains("plank"))
    }

    func testSearchKeepsTheOrderAndHidesEmptyGroups() {
        let groups = PickerOrder.groups(library: library, day: legDay,
                                        replacing: "back-squat", search: "SQUAT")
        XCTAssertEqual(shape(groups), ["Suggested: Goblet squat",
                                       "Same movement: Front squat"])
    }
}
