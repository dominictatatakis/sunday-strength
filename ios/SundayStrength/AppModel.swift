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
    /// True while the saved plan is on screen and the server's is on its way.
    /// After a quiet spell the free server takes up to a minute to wake, and
    /// the plan screen says so rather than looking stuck.
    private(set) var isUpdating = false
    /// Which sign-in buttons to offer. Nil until the server has said, and a
    /// provider it does not advertise gets no button at all.
    private(set) var providers: ProvidersInfo?
    /// Every exercise the kit allows, for how-to screens, the picker, and
    /// building a swapped-in row without waiting for the server.
    private(set) var library: [LibraryExercise] = []
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
        // Open on the plan saved on the phone rather than a spinner: the
        // server can take up to a minute to wake, and the saved plan is what
        // is needed at the gym. Everything below then updates it.
        if plan == nil, let cached = PlanCache.load() {
            plan = cached
            library = LibraryCache.load() ?? []
            phase = .signedIn
        }
        isUpdating = true
        defer { isUpdating = false }
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
        library = []
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

    /// Saved as soon as it's switched: it doesn't touch the plan, so it needs
    /// neither the Save button nor a rebuild. The switch moves at once and
    /// goes back if the server says no.
    func setWeeklyEmail(_ on: Bool) async {
        guard let previous = me?.weeklyEmail, previous != on else { return }
        me?.weeklyEmail = on
        do {
            me = try await api.updateMe(PrefsPatch(weeklyEmail: on))
            settingsError = nil
            return
        } catch APIError.rejected(let detail) {
            settingsError = detail
        } catch APIError.notAuthorised {
            await restore()
        } catch APIError.offline {
            settingsError = "Can't reach Sunday Strength. The Sunday email wasn't changed."
        } catch {
            settingsError = "Something went wrong. The Sunday email wasn't changed."
        }
        me?.weeklyEmail = previous
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

    /// What a finished abs circuit is ticked off as: engine.CIRCUIT_SLUG.
    static let circuitSlug = "abs-circuit"

    /// Ticks the day's abs circuit, or clears it. Shown at once and sent like
    /// any tick, so it queues without signal.
    func setCircuitDone(day: Int, _ done: Bool) async {
        guard var plan, let d = plan.days.firstIndex(where: { $0.day == day }),
              plan.days[d].circuit != nil else { return }
        plan.days[d].circuit?.done = done
        self.plan = plan
        PlanCache.save(plan)
        await push(.init(slug: Self.circuitSlug, day: day, week: weekKey,
                         sets: nil, reps: nil, weightKg: nil, done: done),
                   revertTo: nil)
    }

    func libraryEntry(_ slug: String) -> LibraryExercise? {
        library.first { $0.slug == slug }
    }

    func swap(day: Int, replacing old: String, with new: String) async {
        await changeDay(day) { slugs in
            guard let i = slugs.firstIndex(of: old), !slugs.contains(new) else {
                return
            }
            slugs[i] = new
        }
    }

    func add(day: Int, slug: String) async {
        await changeDay(day) { slugs in
            if !slugs.contains(slug) { slugs.append(slug) }
        }
    }

    func remove(day: Int, slug: String) async {
        await changeDay(day) { $0.removeAll { $0 == slug } }
    }

    /// Back to the generated day. Works offline: the plan carries the
    /// generated slugs, and the library the rows for any no longer shown.
    func resetDay(_ day: Int) async {
        guard let current = plan?.days.first(where: { $0.day == day }),
              current.edited, let original = current.original,
              let shown = show(day: day, slugs: original, edited: false)
        else { return }
        await sendDayChange(.resetDay(week: weekKey, day: day),
                            previous: shown.previous, newcomers: shown.newcomers)
    }

    private func changeDay(_ day: Int, _ change: (inout [String]) -> Void) async {
        guard let current = plan?.days.first(where: { $0.day == day }) else {
            return
        }
        var slugs = current.exercises.map(\.slug)
        change(&slugs)
        guard slugs != current.exercises.map(\.slug),
              let shown = show(day: day, slugs: slugs, edited: true)
        else { return }
        await sendDayChange(.setDay(DayBody(week: weekKey, day: day, slugs: slugs)),
                            previous: shown.previous, newcomers: shown.newcomers)
    }

    /// Puts a day's new list on screen before the server has it. Rows already
    /// there are kept, logs and all; only newcomers are built, from the
    /// library. Changes nothing, and returns nil, if one isn't in it.
    private func show(day: Int, slugs: [String], edited: Bool)
        -> (previous: PlanDay, newcomers: Set<String>)? {
        guard var plan, let d = plan.days.firstIndex(where: { $0.day == day })
        else { return nil }
        let previous = plan.days[d]
        let existing = Dictionary(previous.exercises.map { ($0.slug, $0) },
                                  uniquingKeysWith: { first, _ in first })
        let rows = slugs.compactMap { existing[$0] ?? libraryEntry($0)?.planExercise }
        guard rows.count == slugs.count else { return nil }
        plan.days[d].exercises = rows
        plan.days[d].edited = edited
        if plan.days[d].original == nil && !previous.edited {
            plan.days[d].original = previous.exercises.map(\.slug)
        }
        self.plan = plan
        // Saved now, so a relaunch with no signal still shows the change the
        // queue is holding.
        PlanCache.save(plan)
        return (previous, Set(slugs).subtracting(existing.keys))
    }

    private func sendDayChange(_ change: QueuedChange, previous: PlanDay,
                               newcomers: Set<String>) async {
        do {
            if let server = try await apply(change)?.days
                .first(where: { $0.day == previous.day }) {
                adopt(server, newcomers: newcomers)
            }
            errorMessage = nil
            isOffline = false
        } catch APIError.rejected(let detail) {
            // Never going to be accepted: put the day back and refetch.
            put(previous)
            errorMessage = detail
            await loadPlan()
        } catch APIError.notAuthorised {
            // Kept for after signing in again, which replays the queue.
            await queue.enqueue(change)
            await restore()
        } catch {
            await queue.enqueue(change)
            isOffline = true
        }
    }

    /// Takes the server's copy of a day just changed; see PlanDay.adopting.
    private func adopt(_ server: PlanDay, newcomers: Set<String>) {
        guard var plan, let d = plan.days.firstIndex(where: { $0.day == server.day })
        else { return }
        plan.days[d] = plan.days[d].adopting(server, newcomers: newcomers)
        self.plan = plan
        PlanCache.save(plan)
    }

    private func put(_ day: PlanDay) {
        guard var plan, let d = plan.days.firstIndex(where: { $0.day == day.day })
        else { return }
        plan.days[d] = day
        self.plan = plan
        PlanCache.save(plan)
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
            await queue.enqueue(.tick(body))
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
        // Changes made offline go first, so the plan fetched after them
        // already shows them.
        await flushQueue()
        do {
            let fetched = try await api.plan(week: nil)
            plan = fetched
            PlanCache.save(fetched)
            isOffline = false
        } catch APIError.notAuthorised {
            await restore()
            return
        } catch {
            if plan == nil { plan = PlanCache.load() }
            isOffline = true
        }
        await loadLibrary()
    }

    /// Replays queued changes in the order they were made. A 400 means the
    /// server will never accept that one, so drop it rather than retry forever.
    func flushQueue() async {
        for change in await queue.pending() {
            do {
                _ = try await apply(change)
                await queue.remove(change)
            } catch APIError.rejected {
                await queue.remove(change)
            } catch {
                break          // still offline; keep the rest for next time
            }
        }
    }

    /// Sends one change. Day edits answer with the week.
    private func apply(_ change: QueuedChange) async throws -> Plan? {
        switch change {
        case .tick(let body):
            try await api.setCompletion(body)
            return nil
        case .setDay(let body):
            return try await api.setDay(body)
        case .resetDay(let week, let day):
            return try await api.resetDay(week: week, day: day)
        }
    }

    private func loadLibrary() async {
        do {
            let fetched = try await api.exercises()
            library = fetched
            LibraryCache.save(fetched)
        } catch {
            if library.isEmpty { library = LibraryCache.load() ?? [] }
        }
        prefetchPhotos()
    }

    /// This week's photos, fetched now so the how-to shows them without signal.
    private func prefetchPhotos() {
        guard let plan else { return }
        let slugs = Set(plan.days.flatMap {
            $0.exercises.map(\.slug) + ($0.circuit?.moves.map(\.slug) ?? [])
        })
        let paths = library.filter { slugs.contains($0.slug) }.flatMap(\.images)
        guard !paths.isEmpty else { return }
        Task.detached(priority: .background) {
            await PhotoCache.shared.prefetch(paths)
        }
    }
}
