import SwiftUI

/// How to do one exercise: photos, steps, and what to do instead if the kit
/// is taken. `inPlan` is an exercise already in the day; `candidate` one
/// being looked at before it goes in; `info` just the how-to, as the abs
/// circuit shows it.
struct ExerciseDetailView: View {
    enum Role: Hashable {
        case inPlan
        case candidate(replacing: String?)
        case info
    }

    let slug: String
    let day: Int
    let role: Role
    let close: () -> Void
    var logSets: ((PlanExercise) -> Void)?

    @Environment(AppModel.self) private var model
    @State private var preview: LibraryExercise?

    var body: some View {
        List {
            if let entry {
                if !entry.images.isEmpty {
                    Section {
                        HStack(spacing: 8) {
                            ForEach(entry.images, id: \.self) { ExercisePhoto(path: $0) }
                        }
                    }
                }
                steps(entry)
                if role == .inPlan { swaps(entry) }
            } else {
                Text("The how-to hasn't downloaded yet. Pull down on the plan to refresh when you have signal.")
                    .foregroundStyle(.secondary)
            }
            if role != .info { actions }
        }
        .navigationTitle(entry?.name ?? planRow?.name ?? "Exercise")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Done", action: close)
            }
        }
        .navigationDestination(item: $preview) { option in
            ExerciseDetailView(slug: option.slug, day: day,
                               role: .candidate(replacing: slug), close: close)
        }
    }

    private var entry: LibraryExercise? { model.libraryEntry(slug) }

    private var planDay: PlanDay? { model.plan?.days.first { $0.day == day } }

    private var planRow: PlanExercise? {
        planDay?.exercises.first { $0.slug == slug }
    }

    private func steps(_ entry: LibraryExercise) -> some View {
        Section {
            ForEach(Array(entry.instructions.enumerated()), id: \.offset) { i, step in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text("\(i + 1).")
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                    Text(step)
                }
            }
            if entry.instructions.isEmpty {
                Text("No written steps for this one yet. The video search below shows it done.")
                    .foregroundStyle(.secondary)
            }
            if let url = URL(string: entry.youtubeUrl) {
                Link(destination: url) {
                    Label("Search YouTube for form videos", systemImage: "play.rectangle")
                }
            }
        } header: {
            Text("How to do it")
        } footer: {
            Text("Prescribed: \(planRow?.sets ?? entry.sets)")
        }
    }

    private func swaps(_ entry: LibraryExercise) -> some View {
        let inDay = Set(planDay?.exercises.map(\.slug) ?? [])
        let options = entry.alternatives
            .filter { !inDay.contains($0.slug) }
            .compactMap { model.libraryEntry($0.slug) }
        return Section("Taken? Swap for:") {
            ForEach(options) { option in
                HStack {
                    // Both borderless: two buttons in one row otherwise fire
                    // together.
                    Button(option.name) { preview = option }
                        .buttonStyle(.borderless)
                        .foregroundStyle(.primary)
                    Spacer()
                    Button("Swap") {
                        let d = day, old = slug
                        Task { await model.swap(day: d, replacing: old, with: option.slug) }
                        close()
                    }
                    .buttonStyle(.borderless)
                    .accessibilityIdentifier("swap")
                }
            }
            NavigationLink("Choose another…") {
                ExercisePickerView(day: day, replacing: slug, close: close)
            }
        }
    }

    @ViewBuilder
    private var actions: some View {
        Section {
            switch role {
            case .inPlan:
                if let row = planRow, let logSets {
                    Button("Log sets") { logSets(row) }
                }
                Button("Remove from today", role: .destructive) {
                    let d = day, s = slug
                    Task { await model.remove(day: d, slug: s) }
                    close()
                }
            case .candidate(let replacing):
                if let replacing {
                    Button("Swap in") {
                        let d = day, s = slug
                        Task { await model.swap(day: d, replacing: replacing, with: s) }
                        close()
                    }
                } else {
                    Button("Add to day \(day)") {
                        let d = day, s = slug
                        Task { await model.add(day: d, slug: s) }
                        close()
                    }
                }
            case .info:
                EmptyView()
            }
        }
    }
}
