import AVFoundation

/// Plays the circuit's beeps.
///
/// The playback category ignores the silent switch: you started the timer,
/// so it should be heard, as a workout timer is. The audio session is only
/// active while a beep sounds, so music dips under each beep and comes back
/// up between them rather than staying quiet for five minutes.
@MainActor
final class CircuitSounds: NSObject, AVAudioPlayerDelegate {
    private var players: [CircuitCue: AVAudioPlayer] = [:]
    private var sounding: Set<ObjectIdentifier> = []

    override init() {
        super.init()
        try? AVAudioSession.sharedInstance().setCategory(.playback,
                                                         options: [.duckOthers])
        for cue in CircuitCue.allCases {
            guard let player = try? AVAudioPlayer(data: Tone.wav(cue.notes)) else {
                continue
            }
            player.volume = cue.volume
            player.delegate = self
            player.prepareToPlay()
            players[cue] = player
        }
    }

    func play(_ cue: CircuitCue) {
        guard let player = players[cue] else { return }
        try? AVAudioSession.sharedInstance().setActive(true)
        player.currentTime = 0
        if player.play() {
            sounding.insert(ObjectIdentifier(player))
        }
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer,
                                                 successfully flag: Bool) {
        let id = ObjectIdentifier(player)
        Task { @MainActor in self.finished(id) }
    }

    /// Hands the audio back once nothing is sounding, so music returns to
    /// full volume.
    private func finished(_ id: ObjectIdentifier) {
        sounding.remove(id)
        guard sounding.isEmpty else { return }
        try? AVAudioSession.sharedInstance()
            .setActive(false, options: .notifyOthersOnDeactivation)
    }
}
