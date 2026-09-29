import SwiftUI

/// What a day's rows ask the plan screen to do.
enum DayAction {
    case log(PlanExercise)
    case howTo(PlanExercise)
    case swap(PlanExercise)
    case remove(PlanExercise)
    case add
    case reset
}

struct DayCard: View {
    let day: PlanDay
    let onAction: (DayAction) -> Void

    var body: some View {
        Section {
            ForEach(day.exercises) { exercise in
                ExerciseRow(exercise: exercise,
                            onTap: { onAction(.log(exercise)) },
                            onInfo: { onAction(.howTo(exercise)) })
                    .swipeActions(edge: .trailing) {
                        Button("Remove", role: .destructive) {
                            onAction(.remove(exercise))
                        }
                        Button("Swap") { onAction(.swap(exercise)) }
                            .tint(.blue)
                    }
            }
            Button { onAction(.add) } label: {
                Label("Add exercise", systemImage: "plus")
            }
            if day.edited {
                Button("Reset day to the original plan") { onAction(.reset) }
                    .foregroundStyle(.secondary)
            }
        } header: {
            HStack {
                Text(day.title)
                Spacer()
                Text("\(doneCount)/\(day.exercises.count)")
                    .foregroundStyle(isComplete ? .green : .secondary)
            }
        }
    }

    private var doneCount: Int {
        day.exercises.filter(\.done).count
    }

    /// An emptied day isn't a finished one.
    private var isComplete: Bool {
        !day.exercises.isEmpty && doneCount == day.exercises.count
    }
}
