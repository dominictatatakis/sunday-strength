import SwiftUI
import UIKit

/// A day's 5-minute abs circuit: its moves with how-tos, then a guided timer
/// that ticks the circuit off when it finishes.
struct CircuitView: View {
    let day: Int
    let close: () -> Void

    @Environment(AppModel.self) private var model
    @State private var run: CircuitRun?
    @State private var preview: Alt?

    var body: some View {
        Group {
            if let circuit {
                if let run {
                    CircuitTimerView(circuit: circuit, run: run,
                                     onFinish: finish, onStop: { self.run = nil })
                } else {
                    overview(circuit)
                }
            } else {
                Text("This day has no abs circuit.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("5-minute abs")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Done", action: close)
            }
        }
        .navigationDestination(item: $preview) { move in
            ExerciseDetailView(slug: move.slug, day: day, role: .info, close: close)
        }
    }

    private var circuit: Circuit? {
        model.plan?.days.first { $0.day == day }?.circuit
    }

    private func overview(_ circuit: Circuit) -> some View {
        let timer = CircuitTimer(work: circuit.work, rest: circuit.rest,
                                 moves: circuit.moves.count)
        return List {
            Section {
                ForEach(Array(circuit.moves.enumerated()), id: \.offset) { i, move in
                    HStack(spacing: 10) {
                        Text("\(i + 1).")
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                        Text(move.name)
                        Spacer()
                        Button { preview = move } label: {
                            Image(systemName: "info.circle").font(.title3)
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("How to do \(move.name)")
                    }
                }
            } header: {
                Text("\(circuit.moves.count) moves · \(circuit.work) s on, \(circuit.rest) s rest · "
                     + String(format: "%d:%02d", timer.total / 60, timer.total % 60))
            } footer: {
                Text("One round, with no rest after the last move. The screen stays on while it runs.")
            }

            Section {
                Button {
                    run = CircuitRun(timer: timer)
                } label: {
                    Label("Start", systemImage: "play.fill")
                        .font(.headline)
                }
                .accessibilityIdentifier("startCircuit")

                if circuit.done {
                    Label("Done today", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Button("Mark as not done") {
                        let d = day
                        Task { await model.setCircuitDone(day: d, false) }
                    }
                } else {
                    Button("Mark as done") {
                        let d = day
                        Task { await model.setCircuitDone(day: d, true) }
                    }
                }
            }
        }
    }

    private func finish() {
        let d = day
        Task { await model.setCircuitDone(day: d, true) }
    }
}

/// The countdown. It reads the time from the run every fifth of a second, so
/// it shows the right move and seconds after a pause or a locked phone.
private struct CircuitTimerView: View {
    let circuit: Circuit
    let run: CircuitRun
    let onFinish: () -> Void
    let onStop: () -> Void

    @State private var finished = false
    @State private var sounds = CircuitSounds()

    var body: some View {
        TimelineView(.periodic(from: .now, by: 0.2)) { context in
            let position = run.timer.position(at: run.elapsed(at: context.date))
            content(position)
                .onChange(of: position) { old, new in
                    guard let cue = CircuitCue.between(old, new) else { return }
                    play(cue)
                }
        }
        .onAppear {
            // Kept awake: auto-lock mid-plank would leave the timer silent.
            UIApplication.shared.isIdleTimerDisabled = true
            play(.start)
        }
        .onDisappear { UIApplication.shared.isIdleTimerDisabled = false }
    }

    @ViewBuilder
    private func content(_ position: CircuitTimer.Position?) -> some View {
        if let position {
            VStack(spacing: 20) {
                Spacer()
                Text("Move \(position.move + 1) of \(circuit.moves.count)")
                    .font(.headline)
                    .foregroundStyle(.secondary)
                Text(position.phase == .work ? circuit.moves[position.move].name : "Rest")
                    .font(.largeTitle.weight(.bold))
                    .multilineTextAlignment(.center)
                Text("\(position.remaining)")
                    .font(.system(size: 120, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(position.phase == .work ? Color.accentColor : .secondary)
                    .accessibilityLabel("\(position.remaining) seconds left")
                Text(position.phase == .work ? "Work" : "Rest")
                    .font(.title3.weight(.semibold))
                if let next = next(after: position) {
                    Text("Next: \(next)")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                HStack(spacing: 12) {
                    Button(run.isPaused ? "Resume" : "Pause") {
                        run.isPaused ? run.resume(at: .now) : run.pause(at: .now)
                    }
                    Button("Skip") { run.skip(at: .now) }
                        .accessibilityIdentifier("skip")
                    Button("Stop", role: .destructive, action: onStop)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            .padding()
        } else {
            VStack(spacing: 16) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 72))
                    .foregroundStyle(.green)
                Text("Circuit done")
                    .font(.title.weight(.bold))
                Text("Ticked off for today.")
                    .foregroundStyle(.secondary)
                Button("Back to the moves", action: onStop)
                    .buttonStyle(.bordered)
            }
            .padding()
        }
    }

    /// During work, the move after this one; during rest, the one coming up.
    private func next(after position: CircuitTimer.Position) -> String? {
        let upcoming = position.move + 1
        return upcoming < circuit.moves.count ? circuit.moves[upcoming].name : nil
    }

    /// A sound and a buzz. On finishing, also ticks the circuit off once.
    private func play(_ cue: CircuitCue) {
        if cue == .finish {
            guard !finished else { return }
            finished = true
            onFinish()
        }
        sounds.play(cue)
        switch cue {
        case .start, .stop:
            UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
        case .countdown:
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        case .finish:
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        }
    }
}
