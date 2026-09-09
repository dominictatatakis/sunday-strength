import SwiftUI

struct DayCard: View {
    let day: PlanDay

    var body: some View {
        Section {
            ForEach(day.exercises) { exercise in
                ExerciseRow(exercise: exercise, day: day.day)
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
