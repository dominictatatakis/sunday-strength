import SwiftUI

/// What a day's rows ask the plan screen to do.
enum DayAction {
    case log(PlanExercise)
    case howTo(PlanExercise)
    case swap(PlanExercise)
    case remove(PlanExercise)
    case add
    case reset
    case circuit
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
            if let circuit = day.circuit {
                CircuitRow(circuit: circuit) { onAction(.circuit) }
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

/// The abs circuit at the end of a day. An add-on, so it isn't part of the
/// day's done count.
private struct CircuitRow: View {
    let circuit: Circuit
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                Image(systemName: circuit.done ? "checkmark.circle.fill"
                                               : "figure.core.training")
                    .foregroundStyle(circuit.done ? Color.green : Color.accentColor)
                    .font(.title3)
                VStack(alignment: .leading, spacing: 2) {
                    Text("5-minute abs")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.primary)
                    Text("\(circuit.moves.count) moves · \(circuit.work) s on, \(circuit.rest) s rest")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        // Plain, so it reads as an item like the exercises above it rather
        // than a blue link; contentShape keeps the whole row tappable.
        .buttonStyle(.plain)
        .accessibilityIdentifier("circuit")
    }
}
