import Foundation

/// Beeps made in code rather than shipped as sound files: 16-bit mono WAV
/// data that AVAudioPlayer can play straight from memory.
enum Tone {
    static let sampleRate = 44_100

    /// The notes one after another: (frequency in Hz, seconds), 0 Hz for a
    /// gap. Each note fades in and out over 10 ms, which stops it clicking.
    static func wav(_ notes: [(Double, Double)]) -> Data {
        var samples: [Int16] = []
        for (frequency, seconds) in notes {
            let count = Int((seconds * Double(sampleRate)).rounded())
            let fade = min(Double(sampleRate) * 0.01, Double(count) / 2)
            for i in 0..<count {
                guard frequency > 0 else {
                    samples.append(0)
                    continue
                }
                let edge = min(Double(i), Double(count - 1 - i))
                let envelope = fade > 0 ? min(edge / fade, 1) : 1
                let value = sin(2 * .pi * frequency * Double(i) / Double(sampleRate))
                samples.append(Int16(value * envelope * 0.8 * Double(Int16.max)))
            }
        }

        var data = Data()
        func append<T: FixedWidthInteger>(_ value: T) {
            withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
        }
        let bytes = samples.count * 2
        data.append(contentsOf: Array("RIFF".utf8))
        append(UInt32(36 + bytes))
        data.append(contentsOf: Array("WAVEfmt ".utf8))
        append(UInt32(16))                  // fmt chunk size
        append(UInt16(1))                   // PCM
        append(UInt16(1))                   // mono
        append(UInt32(sampleRate))
        append(UInt32(sampleRate * 2))      // bytes per second
        append(UInt16(2))                   // bytes per sample frame
        append(UInt16(16))                  // bits per sample
        data.append(contentsOf: Array("data".utf8))
        append(UInt32(bytes))
        for sample in samples { append(sample) }
        return data
    }
}
