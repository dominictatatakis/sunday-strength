import SwiftUI

struct PlanView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            List {
                if model.isOffline {
                    Text("Offline — showing your last saved plan.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let plan = model.plan {
                    ForEach(plan.days) { day in
                        DayCard(day: day)
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
            .navigationTitle(model.plan.map { "Week \($0.week)" } ?? "This week")
            .refreshable { await model.loadPlan() }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Sign out") { model.signOut() }
                }
            }
        }
    }
}
