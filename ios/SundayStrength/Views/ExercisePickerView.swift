import SwiftUI

/// The library, ordered by what suits the swap or the day, to swap in or add.
/// Tapping a name chooses it; ⓘ shows its how-to first.
struct ExercisePickerView: View {
    let day: Int
    let replacing: String?
    let close: () -> Void

    @Environment(AppModel.self) private var model
    @State private var search = ""
    @State private var preview: LibraryExercise?

    var body: some View {
        List {
            if model.library.isEmpty {
                Text("The exercise list hasn't downloaded yet. Pull down on the plan to refresh when you have signal.")
                    .foregroundStyle(.secondary)
            }
            ForEach(groups) { group in
                Section(group.title) {
                    ForEach(group.exercises) { option in
                        HStack {
                            Button { choose(option) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(option.name)
                                    Text(option.sets)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .contentShape(Rectangle())
                            }
                            // Plain, not borderless: a name, not a link. Either
                            // keeps the ⓘ beside it a separate tap target.
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("pick")

                            Button { preview = option } label: {
                                Image(systemName: "info.circle").font(.title3)
                            }
                            .buttonStyle(.borderless)
                            .accessibilityLabel("How to do \(option.name)")
                        }
                    }
                }
            }
        }
        .searchable(text: $search, prompt: "Search exercises")
        .navigationTitle(replacing == nil ? "Add to day \(day)" : "Swap for…")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel", action: close)
            }
        }
        .navigationDestination(item: $preview) { option in
            ExerciseDetailView(slug: option.slug, day: day,
                               role: .candidate(replacing: replacing), close: close)
        }
    }

    private var groups: [PickerOrder.Group] {
        guard let planDay = model.plan?.days.first(where: { $0.day == day }) else {
            return []
        }
        return PickerOrder.groups(library: model.library, day: planDay,
                                  replacing: replacing, search: search)
    }

    private func choose(_ option: LibraryExercise) {
        let d = day, s = option.slug
        if let replacing {
            Task { await model.swap(day: d, replacing: replacing, with: s) }
        } else {
            Task { await model.add(day: d, slug: s) }
        }
        close()
    }
}
