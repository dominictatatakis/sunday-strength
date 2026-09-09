import Foundation
import Observation

@MainActor
@Observable
final class AppModel {
    enum Phase: Equatable {
        case loading
        case signedOut(String?)     // optional error message
        case signedIn
    }

    private(set) var phase: Phase = .loading
    private(set) var me: Me?
    private(set) var plan: Plan?
    private(set) var isOffline = false

    private let api: APIClient

    init(api: APIClient = APIClient()) {
        self.api = api
    }

    /// Called on launch: sign in again from stored credentials, so the app
    /// opens on the plan rather than a login screen.
    func restore() async {
        guard let stored = Keychain.load() else {
            phase = .signedOut(nil)
            return
        }
        do {
            try await api.login(email: stored.email, password: stored.password)
            me = try await api.me()
            phase = .signedIn
            await loadPlan()
        } catch APIError.badCredentials {
            Keychain.clear()
            phase = .signedOut("Your password has changed. Please sign in again.")
        } catch {
            // Offline: trust the stored credentials and let the plan cache show.
            phase = .signedIn
            isOffline = true
            await loadPlan()
        }
    }

    func signIn(email: String, password: String) async {
        phase = .loading
        do {
            try await api.login(email: email, password: password)
            me = try await api.me()
            Keychain.save(.init(email: email, password: password))
            phase = .signedIn
            await loadPlan()
        } catch APIError.badCredentials {
            phase = .signedOut("That email and password didn't match an account.")
        } catch APIError.offline {
            phase = .signedOut("Can't reach Sunday Strength. Check your connection.")
        } catch {
            phase = .signedOut("Something went wrong. Please try again.")
        }
    }

    func signOut() {
        Keychain.clear()
        me = nil
        plan = nil
        phase = .signedOut(nil)
    }

    func loadPlan() async {
        do {
            plan = try await api.plan(week: nil)
            isOffline = false
        } catch APIError.notAuthorised {
            await restore()
        } catch {
            isOffline = true
        }
    }
}
