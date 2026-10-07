import AVFoundation
import XCTest
@testable import SundayStrength

/// Which sound the circuit makes as the timer moves on.
final class CircuitCueTests: XCTestCase {

    private func at(_ move: Int, _ phase: CircuitTimer.Phase,
                    _ remaining: Int, _ side: CircuitTimer.Side? = nil) -> CircuitTimer.Position {
        .init(move: move, phase: phase, remaining: remaining, side: side)
    }

    func testTheEndOfWorkSaysStop() {
        XCTAssertEqual(CircuitCue.between(at(0, .work, 1), at(0, .rest, 20)), .stop)
    }

    func testTheEndOfRestSaysStart() {
        XCTAssertEqual(CircuitCue.between(at(0, .rest, 1), at(1, .work, 40)), .start)
    }

    func testTheLastThreeSecondsCountDown() {
        XCTAssertEqual(CircuitCue.between(at(0, .work, 4), at(0, .work, 3)), .countdown)
        XCTAssertEqual(CircuitCue.between(at(1, .rest, 2), at(1, .rest, 1)), .countdown)
    }

    func testOtherwiseItIsQuiet() {
        XCTAssertNil(CircuitCue.between(at(0, .work, 10), at(0, .work, 9)))
        XCTAssertNil(CircuitCue.between(at(0, .work, 3), at(0, .work, 3)))
    }

    func testSkippingToTheNextMoveSaysStart() {
        XCTAssertEqual(CircuitCue.between(at(0, .work, 30), at(1, .work, 40)), .start)
    }

    func testHalfwayThroughASidedMoveSaysSwitch() {
        XCTAssertEqual(CircuitCue.between(at(2, .work, 1, .first), at(2, .work, 20, .second)),
                       .switchSides)
    }

    func testTheLastSecondsBeforeSwitchingCountDown() {
        XCTAssertEqual(CircuitCue.between(at(2, .work, 4, .first), at(2, .work, 3, .first)),
                       .countdown)
    }

    /// The end of a sided move is still a stop, not a switch.
    func testTheEndOfASidedMoveSaysStop() {
        XCTAssertEqual(CircuitCue.between(at(2, .work, 1, .second), at(2, .rest, 20)), .stop)
    }

    func testTheEndSaysFinished() {
        XCTAssertEqual(CircuitCue.between(at(4, .work, 1), nil), .finish)
        XCTAssertNil(CircuitCue.between(nil, nil))
    }

    /// Every cue sounds different: stop and start must be told apart
    /// without looking at the phone.
    func testEachCueHasItsOwnSound() {
        let sounds = CircuitCue.allCases.map { Tone.wav($0.notes) }
        XCTAssertEqual(Set(sounds).count, CircuitCue.allCases.count)
    }
}

final class ToneTests: XCTestCase {

    /// A beep of 0.5 s at 44.1 kHz is 22 050 16-bit samples after a 44-byte
    /// header, and reads back as audio.
    func testMakesAPlayableWav() throws {
        let data = Tone.wav([(440, 0.5)])
        XCTAssertEqual(String(decoding: data.prefix(4), as: UTF8.self), "RIFF")
        XCTAssertEqual(String(decoding: data[8..<12], as: UTF8.self), "WAVE")
        XCTAssertEqual(data.count, 44 + 22_050 * 2)
        let player = try AVAudioPlayer(data: data)
        XCTAssertEqual(player.duration, 0.5, accuracy: 0.01)
    }

    func testAZeroFrequencyIsSilence() {
        let samples = Tone.wav([(0, 0.1)]).dropFirst(44)
        XCTAssertTrue(samples.allSatisfy { $0 == 0 })
    }
}

@MainActor
final class CircuitSoundsTests: XCTestCase {

    /// You started the timer, so it sounds even on silent, and music dips
    /// under the beeps rather than stopping.
    func testPlaysOnSilentAndDipsMusic() {
        _ = CircuitSounds()
        let session = AVAudioSession.sharedInstance()
        XCTAssertEqual(session.category, .playback)
        XCTAssertTrue(session.categoryOptions.contains(.duckOthers))
    }
}

/// Heard in a gym, over music, from a phone on the floor: long enough and
/// loud enough to notice mid-rep.
final class CircuitCueLoudnessTests: XCTestCase {

    private func seconds(_ cue: CircuitCue) -> Double {
        cue.notes.reduce(0) { $0 + $1.1 }
    }

    func testTheBeepsLastLongEnoughToHear() {
        XCTAssertGreaterThanOrEqual(seconds(.stop), 1.0)
        XCTAssertGreaterThanOrEqual(seconds(.start), 0.7)
        XCTAssertGreaterThanOrEqual(seconds(.countdown), 0.15)
        XCTAssertGreaterThanOrEqual(seconds(.finish), 1.0)
        XCTAssertGreaterThanOrEqual(seconds(.switchSides), 0.7)
    }

    /// Phone speakers are weak below about 800 Hz, so nothing sits there.
    func testTheyAreInThePhoneSpeakersRange() {
        for cue in CircuitCue.allCases {
            for (frequency, _) in cue.notes where frequency > 0 {
                XCTAssertGreaterThanOrEqual(frequency, 800, "\(cue)")
            }
        }
    }

    /// Stop stays lower than start, so the two can't be mixed up.
    func testStopIsLowerThanStart() {
        let stop = CircuitCue.stop.notes.map(\.0).max()!
        let start = CircuitCue.start.notes.map(\.0).filter { $0 > 0 }.min()!
        XCTAssertLessThan(stop, start)
    }

    func testTheyPlayNearFullVolume() {
        XCTAssertGreaterThanOrEqual(CircuitCue.countdown.volume, 0.8)
        let samples = Tone.wav([(1000, 0.1)]).dropFirst(44)
        var peak: Int16 = 0
        samples.withUnsafeBytes { raw in
            for value in raw.bindMemory(to: Int16.self) { peak = max(peak, abs(value)) }
        }
        XCTAssertGreaterThanOrEqual(Double(peak), 0.94 * Double(Int16.max))
    }
}
