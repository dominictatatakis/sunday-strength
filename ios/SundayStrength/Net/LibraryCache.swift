import Foundation

/// The exercise library last served, so how-to steps and the picker work
/// with no signal.
enum LibraryCache {
    private static var url: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base,
                                                 withIntermediateDirectories: true)
        return base.appendingPathComponent("library.json")
    }

    static func save(_ exercises: [LibraryExercise]) {
        guard let data = try? JSON.encoder.encode(exercises) else { return }
        try? data.write(to: url, options: .atomic)
    }

    static func load() -> [LibraryExercise]? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSON.decoder.decode([LibraryExercise].self, from: data)
    }
}
