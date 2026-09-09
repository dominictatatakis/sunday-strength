import SwiftUI

struct DayCard: View {
    let day: PlanDay
    let onSelect: (PlanExercise) -> Void

    var body: some View {
        Section {
            ForEach(day.exercises) { exercise in
                ExerciseRow(exercise: exercise) { onSelect(exercise) }
            }
        } header: {
            HStack {
                Text(day.title)
                Spacer()
                Text("\(doneCount)/\(day.exercises.count)")
                    .foregroundStyle(doneCount == day.exercises.count
                                     ? .green : .secondary)
            }
        }
    }

    private var doneCount: Int {
        day.exercises.filter(\.done).count
    }
}
