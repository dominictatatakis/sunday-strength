import SwiftUI

@main
struct SundayStrengthApp: App {
    @State private var model = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task { await model.restore() }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        Task { await model.flushQueue() }
                    }
                }
        }
    }
}
