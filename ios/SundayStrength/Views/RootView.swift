import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.phase {
        case .loading:
            ProgressView()
        case .signedOut(let error):
            LoginView(error: error)
        case .signedIn:
            TabView {
                PlanView()
                    .tabItem { Label("Plan", systemImage: "list.bullet") }
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
            }
        }
    }
}
