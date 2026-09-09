import SwiftUI

struct LogSheet: View {
    let exercise: PlanExercise
    let day: Int

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    @State private var sets: Int
    @State private var reps: Int
    @State private var weight: Double

    init(exercise: PlanExercise, day: Int) {
        self.exercise = exercise
        self.day = day
        _sets = State(initialValue: exercise.setsDone ?? 3)
        _reps = State(initialValue: exercise.reps ?? 10)
        _weight = State(initialValue: exercise.weightKg ?? 0)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Stepper("Sets: \(sets)", value: $sets, in: 1...10)
                    Stepper("Reps: \(reps)", value: $reps, in: 1...50)
                    HStack {
                        Text("Weight")
                        Spacer()
                        TextField("kg", value: $weight,
                                  format: .number.precision(.fractionLength(0...1)))
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 80)
                        Text("kg").foregroundStyle(.secondary)
                    }
                } header: {
                    Text(exercise.name)
                } footer: {
                    Text("Prescribed: \(exercise.sets). Weight is per dumbbell, not the pair.")
                }

                if exercise.done {
                    Button("Clear this log", role: .destructive) {
                        Task {
                            await model.untick(day: day, slug: exercise.slug)
                            dismiss()
                        }
                    }
                }
            }
            .navigationTitle("Log set")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            await model.log(day: day, slug: exercise.slug,
                                            sets: sets, reps: reps,
                                            weightKg: weight > 0 ? weight : nil)
                            dismiss()
                        }
                    }
                }
            }
        }
    }
}
