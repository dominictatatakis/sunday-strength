import SwiftUI

/// What the plan screen has open over it. Held here rather than by each row:
/// a row's own @State is tied to a view the list rebuilds whenever the plan
/// reloads, which loses the sheet mid-tap. One sheet at a time, so moving
/// from a how-to to the log sheet swaps one for the other.
enum PlanSheet: Identifiable {
    case log(day: Int, exercise: PlanExercise)
    case howTo(day: Int, slug: String)
    case pick(day: Int, replacing: String?)
    case circuit(day: Int)

    var id: String {
        switch self {
        case .log(let day, let exercise): "log|\(day)|\(exercise.slug)"
        case .howTo(let day, let slug): "howto|\(day)|\(slug)"
        case .pick(let day, let replacing): "pick|\(day)|\(replacing ?? "")"
        case .circuit(let day): "circuit|\(day)"
        }
    }
}

struct PlanView: View {
    @Environment(AppModel.self) private var model
    @State private var sheet: PlanSheet?

    var body: some View {
        NavigationStack {
            List {
                if let error = model.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
                if model.isUpdating {
                    WakingNote()
                }
                if model.isOffline {
                    Text("Offline — showing your last saved plan.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let plan = model.plan {
                    ForEach(plan.days) { day in
                        DayCard(day: day) { handle($0, on: day.day) }
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
            .sheet(item: $sheet) { content(for: $0) }
            .navigationTitle(model.plan.map { "Week \($0.week)" } ?? "This week")
            .refreshable { await model.loadPlan() }
        }
    }

    private func handle(_ action: DayAction, on day: Int) {
        switch action {
        case .log(let exercise):
            sheet = .log(day: day, exercise: exercise)
        case .howTo(let exercise):
            sheet = .howTo(day: day, slug: exercise.slug)
        case .swap(let exercise):
            sheet = .pick(day: day, replacing: exercise.slug)
        case .remove(let exercise):
            Task { await model.remove(day: day, slug: exercise.slug) }
        case .add:
            sheet = .pick(day: day, replacing: nil)
        case .reset:
            Task { await model.resetDay(day) }
        case .circuit:
            sheet = .circuit(day: day)
        }
    }

    @ViewBuilder
    private func content(for sheet: PlanSheet) -> some View {
        switch sheet {
        case .log(let day, let exercise):
            LogSheet(exercise: exercise, day: day)
        case .howTo(let day, let slug):
            NavigationStack {
                ExerciseDetailView(slug: slug, day: day, role: .inPlan,
                                   close: { self.sheet = nil },
                                   logSets: { self.sheet = .log(day: day, exercise: $0) })
            }
        case .pick(let day, let replacing):
            NavigationStack {
                ExercisePickerView(day: day, replacing: replacing,
                                   close: { self.sheet = nil })
            }
        case .circuit(let day):
            NavigationStack {
                CircuitView(day: day, close: { self.sheet = nil })
            }
        }
    }
}
