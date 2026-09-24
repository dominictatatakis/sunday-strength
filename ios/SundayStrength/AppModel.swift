import Foundation
import Observation

@MainActor
@Observable
final class AppModel {
    enum Phase: Equatable {
        case loading
        case signedOut(String?)     // optional error message
        /// A provider sign-in with no account yet: the four questions.
        case onboarding(Onboarding)
        case signedIn
    }

    private(set) var phase: Phase = .loading
    private(set) var me: Me?
    private(set) var plan: Plan?
    private(set) var isOffline = false
    private(set) var isSaving = false
    /// Which sign-in buttons to offer. Nil until the server has said, and a
    /// provider it does not advertise gets no button at all.
    private(set) var providers: ProvidersInfo?
    var errorMessage: String?
    var settingsError: String?

    private let api: APIClient
    private let queue: OfflineQueue

    init(api: APIClient = APIClient(), queue: OfflineQueue = OfflineQueue()) {
        self.api = api
        self.queue = queue
    }

    /// Called on launch: sign in again from stored credentials, so the app
    /// opens on the plan rather than a login screen.
    func restore() async {
        let refresh = Keychain.loadRefresh()
        let stored = refresh == nil ? Keychain.load() : nil
        guard refresh != nil || stored != nil else {
            phase = .signedOut(nil)
            return
        }
        // The session cookie lasts 30 days, so try it first. Signing in again
        // on every launch spent the server's sign-in allowance (8 per 15
        // minutes) and locked out anyone who opened the app often.
        do {
            me = try await api.me()
            phase = .signedIn
            await loadPlan()
            return
        } catch APIError.notAuthorised {
            // Expired: sign in again below.
        } catch {
            // Offline: trust the stored credentials and let the plan cache show.
            phase = .signedIn
            isOffline = true
            await loadPlan()
            return
        }
        if let refresh {
            await restore(refresh: refresh)
            return
        }
        guard let stored else { return }
        do {
            try await api.login(email: stored.email, password: stored.password)
            me = try await api.me()
            phase = .signedIn
            await loadPlan()
        } catch APIError.badCredentials {
            Keychain.clear()
            phase = .signedOut("Your password has changed. Please sign in again.")
        } catch APIError.throttled {
            // The password is still right; the server just wants a pause.
            phase = .signedOut("Too many attempts. Wait a few minutes and try again.")
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
        } catch APIError.throttled {
            phase = .signedOut("Too many attempts. Wait a few minutes and try again.")
        } catch APIError.offline {
            phase = .signedOut("Can't reach Sunday Strength. Check your connection.")
        } catch {
            phase = .signedOut("Something went wrong. Please try again.")
        }
    }

    /// An Apple or Google account: no password, so the refresh token.
    private func restore(refresh: String) async {
        do {
            let response = try await api.refresh(refresh)
            Keychain.saveRefresh(response.refresh)
            me = try await api.me()
            phase = .signedIn
            await loadPlan()
        } catch APIError.notAuthorised {
            Keychain.clear()
            phase = .signedOut("Please sign in again.")
        } catch {
            // Offline: trust the stored token and let the plan cache show.
            phase = .signedIn
            isOffline = true
            await loadPlan()
        }
    }

    // MARK: - Apple and Google

    func loadProviders() async {
        providers = try? await api.providers()
    }

    func signInWithApple(identityToken: String, nonce: String) async {
        await providerSignIn(.apple(identityToken: identityToken, nonce: nonce)) {
            try await self.api.signInWithApple(identityToken: identityToken,
                                               nonce: nonce, prefs: nil)
        }
    }

    func signInWithGoogle() async {
        let outcome: ProviderSignIn.GoogleOutcome
        do {
            outcome = try await ProviderSignIn.google(baseURL: AppConfig.baseURL)
        } catch ProviderSignIn.Failure.cancelled {
            return
        } catch {
            phase = .signedOut("Signing in with Google didn't work. Try again.")
            return
        }
        switch outcome {
        case .handoff(let handoff):
            await providerSignIn(nil) {
                try await self.api.signInWithGoogle(handoff: handoff)
            }
        case .needsOnboarding(let pending):
            await askOnboarding(.google(pending: pending))
        }
    }

    /// Sends the four answers with the credential that is waiting on them.
    func finishOnboarding(_ prefs: OnboardingPrefs) async {
        guard case .onboarding(let onboarding) = phase else { return }
        await providerSignIn(nil) {
            switch onboarding.pending {
            case .apple(let token, let nonce):
                return try await self.api.signInWithApple(
                    identityToken: token, nonce: nonce, prefs: prefs)
            case .google(let pending):
                return try await self.api.signInWithGoogle(
                    pending: pending, prefs: prefs)
            }
        }
    }

    func cancelOnboarding() {
        phase = .signedOut(nil)
    }

    /// `resume` is what to come back to if the server wants the four
    /// questions answered first.
    private func providerSignIn(_ resume: PendingSignIn?,
                                _ call: () async throws -> AuthResponse) async {
        phase = .loading
        do {
            let response = try await call()
            Keychain.saveRefresh(response.refresh)
            me = try await api.me()
            phase = .signedIn
            await loadPlan()
        } catch APIError.needsOnboarding(let pending) {
            if let pending {
                await askOnboarding(.google(pending: pending))
            } else if let resume {
                await askOnboarding(resume)
            } else {
                phase = .signedOut("Something went wrong. Please try again.")
            }
        } catch APIError.noAccount {
            phase = .signedOut("There's no Sunday Strength account for that sign-in.")
        } catch APIError.emailInUse {
            phase = .signedOut("That email already has an account. Sign in with your password.")
        } catch APIError.notAuthorised {
            // Apple's token lasts ten minutes; a long pause on the questions
            // outlives it.
            phase = .signedOut("That sign-in didn't work. Please try again.")
        } catch APIError.offline {
            phase = .signedOut("Can't reach Sunday Strength. Check your connection.")
        } catch {
            phase = .signedOut("Something went wrong. Please try again.")
        }
    }

    private func askOnboarding(_ pending: PendingSignIn) async {
        if providers == nil { await loadProviders() }
        guard let options = providers?.options else {
            phase = .signedOut("Can't reach Sunday Strength. Check your connection.")
            return
        }
        phase = .onboarding(Onboarding(pending: pending, options: options))
    }

    func signOut() {
        Keychain.clear()
        me = nil
        plan = nil
        phase = .signedOut(nil)
    }

    /// Saves only what differs from the profile we hold, so a value changed on
    /// the website since launch is not silently reverted.
    ///
    /// Returns true if anything was sent and accepted.
    @discardableResult
    func saveSettings(daysPerWeek: Int, experience: String,
                      equipment: String, includeRun: Bool) async -> Bool {
        guard let current = me else { return false }

        var patch = PrefsPatch()
        if daysPerWeek != current.daysPerWeek { patch.daysPerWeek = daysPerWeek }
        if experience != current.experience { patch.experience = experience }
        if equipment != current.equipment { patch.equipment = equipment }
        if includeRun != current.includeRun { patch.includeRun = includeRun }
        guard patch != PrefsPatch() else { return false }

        isSaving = true
        defer { isSaving = false }
        do {
            me = try await api.updateMe(patch)
            settingsError = nil
            // These preferences are what generate_plan is given, so the week
            // has just changed underneath the plan tab.
            await loadPlan()
            return true
        } catch APIError.rejected(let detail) {
            settingsError = detail
        } catch APIError.notAuthorised {
            await restore()
        } catch APIError.offline {
            settingsError = "Can't reach Sunday Strength. Your settings weren't saved."
        } catch {
            settingsError = "Something went wrong. Your settings weren't saved."
        }
        return false
    }

    /// Optimistic: the row changes immediately, because waiting for a round
    /// trip between every set is unusable in a gym.
    func log(day: Int, slug: String, sets: Int?, reps: Int?,
             weightKg: Double?) async {
        let previous = exercise(day: day, slug: slug)
        update(day: day, slug: slug) {
            $0.done = true
            $0.setsDone = sets
            $0.reps = reps
            $0.weightKg = weightKg
        }
        await push(.init(slug: slug, day: day, week: weekKey, sets: sets,
                         reps: reps, weightKg: weightKg, done: true),
                   revertTo: previous)
    }

    func untick(day: Int, slug: String) async {
        let previous = exercise(day: day, slug: slug)
        update(day: day, slug: slug) {
            $0.done = false
            $0.setsDone = nil
            $0.reps = nil
            $0.weightKg = nil
        }
        await push(.init(slug: slug, day: day, week: weekKey, sets: nil,
                         reps: nil, weightKg: nil, done: false),
                   revertTo: previous)
    }

    private func push(_ body: CompletionBody,
                      revertTo previous: PlanExercise?) async {
        do {
            try await api.setCompletion(body)
            errorMessage = nil
            isOffline = false
        } catch APIError.rejected(let detail) {
            // The plan drifted: this tick will never be accepted, so put the
            // row back and refetch rather than retrying forever.
            if let previous { revert(day: body.day, to: previous) }
            errorMessage = detail
            await loadPlan()
        } catch APIError.notAuthorised {
            await restore()
        } catch {
            // Network failure: keep the optimistic state and replay later.
            await queue.enqueue(body)
            isOffline = true
        }
    }

    private var weekKey: String {
        plan?.weekKey ?? ""
    }

    private func exercise(day: Int, slug: String) -> PlanExercise? {
        plan?.days.first { $0.day == day }?
            .exercises.first { $0.slug == slug }
    }

    private func update(day: Int, slug: String,
                        transform: (inout PlanExercise) -> Void) {
        guard var plan else { return }
        guard let d = plan.days.firstIndex(where: { $0.day == day }),
              let e = plan.days[d].exercises.firstIndex(where: { $0.slug == slug })
        else { return }
        transform(&plan.days[d].exercises[e])
        self.plan = plan
    }

    /// Named `revert`, not `restore`, so it cannot be confused with the
    /// sign-in `restore()` above.
    private func revert(day: Int, to exercise: PlanExercise) {
        update(day: day, slug: exercise.slug) { $0 = exercise }
    }

    func loadPlan() async {
        do {
            let fetched = try await api.plan(week: nil)
            plan = fetched
            PlanCache.save(fetched)
            isOffline = false
            await flushQueue()
        } catch APIError.notAuthorised {
            await restore()
        } catch {
            if plan == nil { plan = PlanCache.load() }
            isOffline = true
        }
    }

    /// Replay queued ticks. A 400 means the server will never accept this one,
    /// so drop it — otherwise it retries forever.
    func flushQueue() async {
        for entry in await queue.pending() {
            do {
                try await api.setCompletion(entry)
                await queue.remove(entry)
            } catch APIError.rejected {
                await queue.remove(entry)
            } catch {
                break          // still offline; keep the rest for next time
            }
        }
    }
}
