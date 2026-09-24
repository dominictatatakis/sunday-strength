import SwiftUI

/// The four questions the website asks at signup. A provider sign-in brings
/// who someone is but not how they train, and without these there is no plan
/// to show -- so the account is made only once they are answered.
struct OnboardingView: View {
    let onboarding: Onboarding

    @State private var days = 3
    @State private var experience = "beginner"
    @State private var equipment = "full"
    @State private var includeRun = false
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Days per week", selection: $days) {
                        ForEach(onboarding.options.daysPerWeek, id: \.self) { n in
                            Text("\(n)").tag(n)
                        }
                    }
                    Picker("Experience", selection: $experience) {
                        ForEach(onboarding.options.experience, id: \.self) { level in
                            Text(level.capitalized).tag(level)
                        }
                    }
                    Toggle("Include a run day", isOn: $includeRun)
                } header: {
                    Text("Your week")
                } footer: {
                    Text("You can change any of these later in Settings.")
                }

                Section("Equipment") {
                    Picker("Equipment", selection: $equipment) {
                        ForEach(onboarding.options.equipment) { option in
                            Text(option.name).tag(option.value)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }

                Section {
                    Button("Build my plan") {
                        Task {
                            await model.finishOnboarding(OnboardingPrefs(
                                days: days, experience: experience,
                                run: includeRun, equipment: equipment))
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .accessibilityIdentifier("finishOnboarding")
                }
            }
            .navigationTitle("How do you train?")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { model.cancelOnboarding() }
                }
            }
            .onAppear {
                // Start on values the server accepts, whatever it offers.
                let o = onboarding.options
                if !o.daysPerWeek.contains(days), let first = o.daysPerWeek.first {
                    days = first
                }
                if !o.experience.contains(experience), let first = o.experience.first {
                    experience = first
                }
                if !o.equipment.map(\.value).contains(equipment),
                   let first = o.equipment.last?.value ?? o.equipment.first?.value {
                    equipment = first
                }
            }
        }
    }
}
