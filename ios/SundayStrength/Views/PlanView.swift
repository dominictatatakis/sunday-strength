import SwiftUI

struct PlanView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 12) {
            Text("Signed in as \(model.me?.email ?? "—")")
            Text("\(model.plan?.days.count ?? 0) days this week")
            Button("Sign out") { model.signOut() }
        }
    }
}
