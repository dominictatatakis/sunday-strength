import SwiftUI

struct ExerciseRow: View {
    let exercise: PlanExercise
    let day: Int

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: exercise.done ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(exercise.done ? .green : .secondary)
                .font(.title3)

            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.name)
                    .font(.body.weight(.medium))
                Text(exercise.sets)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let logged = loggedLabel {
                    Text(logged)
                        .font(.caption)
                        .foregroundStyle(.green)
                }
            }
            Spacer()
        }
        .padding(.vertical, 6)
    }

    /// "3 × 10 @ 22.5kg", dropping whatever is missing. Mirrors _last_label
    /// in app.py so the phone and the website read the same.
    private var loggedLabel: String? {
        guard exercise.done else { return nil }
        var parts: [String] = []
        if let sets = exercise.setsDone, let reps = exercise.reps {
            parts.append("\(sets) × \(reps)")
        } else if let reps = exercise.reps {
            parts.append("\(reps)")
        }
        if let weight = exercise.weightKg {
            let trimmed = weight == weight.rounded()
                ? String(Int(weight)) : String(weight)
            parts.append("@ \(trimmed)kg")
        }
        return parts.isEmpty ? "Done" : parts.joined(separator: " ")
    }
}
