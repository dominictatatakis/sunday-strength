import SwiftUI

/// What to say while waiting on the server. A few seconds in, it explains
/// that the free server is waking, so a slow first request reads as that
/// rather than as the app being stuck.
struct WakingNote: View {
    /// Shown straight away; nil shows nothing until the wait turns slow.
    var first: String? = "Updating…"

    @State private var slow = false

    var body: some View {
        Group {
            if slow {
                Text("Waking the server — this can take up to a minute.")
            } else if let first {
                Text(first)
            }
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.center)
        .task {
            try? await Task.sleep(for: .seconds(4))
            slow = true
        }
    }
}
