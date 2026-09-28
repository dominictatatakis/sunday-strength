import Foundation

/// Exercise photos, kept on disk so a how-to opened in a basement gym still
/// shows them. Saved as files rather than left to URLCache, whose rules for
/// what it keeps are heuristics this can't rely on offline.
actor PhotoCache {
    static let shared = PhotoCache()

    private let baseURL: URL
    private let session: URLSession
    private let directory: URL

    init(baseURL: URL = AppConfig.baseURL, session: URLSession = .shared,
         directory: URL = PhotoCache.defaultDirectory) {
        self.baseURL = baseURL
        self.session = session
        self.directory = directory
        try? FileManager.default.createDirectory(at: directory,
                                                 withIntermediateDirectories: true)
    }

    static var defaultDirectory: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("exercise-photos")
    }

    /// The photo at a server path such as "/static/exercises/plank-0.jpg",
    /// from disk once fetched. Nil offline if it never has been.
    func data(for path: String) async -> Data? {
        let file = directory.appendingPathComponent(
            (path as NSString).lastPathComponent)
        if let saved = try? Data(contentsOf: file) { return saved }
        guard let url = URL(string: path, relativeTo: baseURL),
              let fetched = try? await session.data(from: url),
              (fetched.1 as? HTTPURLResponse)?.statusCode == 200
        else { return nil }
        try? fetched.0.write(to: file, options: .atomic)
        return fetched.0
    }

    func prefetch(_ paths: [String]) async {
        for path in paths { _ = await data(for: path) }
    }
}
