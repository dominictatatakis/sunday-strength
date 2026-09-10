import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model

    @State private var daysPerWeek = 4
    @State private var experience = "intermediate"
    @State private var equipment = "full"
    @State private var includeRun = false
    @State private var saved = false
    @State private var loaded = false

    var body: some View {
        NavigationStack {
            Form {
                if let me = model.me {
                    Section {
                        Picker("Days per week", selection: $daysPerWeek) {
                            ForEach(me.options.daysPerWeek, id: \.self) { days in
                                Text("\(days)").tag(days)
                            }
                        }
                        Picker("Experience", selection: $experience) {
                            ForEach(me.options.experience, id: \.self) { level in
                                Text(level.capitalized).tag(level)
                            }
                        }
                        Toggle("Include a run day", isOn: $includeRun)
                    } header: {
                        Text("Your week")
                    } footer: {
                        Text("Changing these rebuilds this week's plan. Sets you have already logged against exercises that drop out stop being shown.")
                    }

                    Section("Equipment") {
                        Picker("Equipment", selection: $equipment) {
                            ForEach(me.options.equipment) { option in
                                Text(option.name).tag(option.value)
                            }
                        }
                        .pickerStyle(.inline)
                        .labelsHidden()
                    }

                    if let error = model.settingsError {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }

                    Section {
                        Button {
                            Task {
                                saved = await model.saveSettings(
                                    daysPerWeek: daysPerWeek,
                                    experience: experience,
                                    equipment: equipment,
                                    includeRun: includeRun)
                            }
                        } label: {
                            if model.isSaving {
                                ProgressView()
                            } else {
                                Text("Save changes")
                            }
                        }
                        .disabled(model.isSaving || !hasChanges)

                        if saved && !hasChanges {
                            Text("Saved. Your plan has been rebuilt.")
                                .font(.footnote)
                                .foregroundStyle(.green)
                        }
                    }

                    Section {
                        Text(me.email)
                            .foregroundStyle(.secondary)
                        Text("Billing and cancellation live on the website.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        Button("Sign out") { model.signOut() }
                    } header: {
                        Text("Account")
                    }
                } else {
                    Text("Loading your settings…")
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            // Only on first appearance: onAppear fires again when a picker
            // menu dismisses, and resetting there would discard the selection
            // the user just made. A change to `me` is the server's answer, so
            // that does resync.
            .onAppear { if !loaded { reset(); loaded = true } }
            .onChange(of: model.me) { _, _ in reset() }
        }
    }

    private var hasChanges: Bool {
        guard let me = model.me else { return false }
        return daysPerWeek != me.daysPerWeek || experience != me.experience
            || equipment != me.equipment || includeRun != me.includeRun
    }

    /// Pull the form back in line with the server's answer, so a rejected or
    /// partial save never leaves the screen showing something untrue.
    private func reset() {
        guard let me = model.me else { return }
        daysPerWeek = me.daysPerWeek
        experience = me.experience
        equipment = me.equipment
        includeRun = me.includeRun
    }
}
