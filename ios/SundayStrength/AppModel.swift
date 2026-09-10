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
    private(set) var isSaving = false
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
