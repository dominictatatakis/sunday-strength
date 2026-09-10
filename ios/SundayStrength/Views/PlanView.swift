import SwiftUI

/// Which exercise the log sheet is for. Held by PlanView rather than by each
/// row: a row's own @State is tied to a view the list rebuilds whenever the
/// plan reloads, which loses the sheet mid-tap.
private struct LogTarget: Identifiable {
    let day: Int
    let exercise: PlanExercise

    var id: String { "\(day)|\(exercise.slug)" }
}

struct PlanView: View {
    @Environment(AppModel.self) private var model
    @State private var logging: LogTarget?

    var body: some View {
        NavigationStack {
            List {
                if let error = model.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
                if model.isOffline {
                    Text("Offline — showing your last saved plan.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let plan = model.plan {
                    ForEach(plan.days) { day in
                        DayCard(day: day) { exercise in
                            logging = LogTarget(day: day.day, exercise: exercise)
                        }
                    }
                    if let run = plan.run {
                        Section("Run") {
                            Text(run).font(.callout)
                        }
                    }
                } else {
                    Text("Loading your plan…")
                        .foregroundStyle(.secondary)
                }
            }
            .sheet(item: $logging) { target in
                LogSheet(exercise: target.exercise, day: target.day)
            }
            .navigationTitle(model.plan.map { "Week \($0.week)" } ?? "This week")
            .refreshable { await model.loadPlan() }
        }
    }
}
