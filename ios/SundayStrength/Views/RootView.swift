import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.phase {
        case .loading:
            ProgressView()
        case .signedOut(let error):
            LoginView(error: error)
        case .onboarding(let onboarding):
            OnboardingView(onboarding: onboarding)
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
