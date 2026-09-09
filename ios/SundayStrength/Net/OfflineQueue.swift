import Foundation

/// Ticks made without a connection, replayed when there is one.
///
/// Replaying late is safe because generate_plan is deterministic
/// (engine.py:537) — the plan the server validates against is the plan the
/// phone was showing — and completions are idempotent per slot rather than
/// incremental, so a repeat is a no-op rather than a double count.
actor OfflineQueue {
    private let fileURL: URL
    private var entries: [CompletionBody]

    init(fileURL: URL = OfflineQueue.defaultURL) {
        self.fileURL = fileURL
        let data = (try? Data(contentsOf: fileURL)) ?? Data()
        self.entries = (try? JSON.decoder.decode([CompletionBody].self,
                                                 from: data)) ?? []
    }

    static var defaultURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base,
                                                 withIntermediateDirectories: true)
        return base.appendingPathComponent("offline-ticks.json")
    }

    func pending() -> [CompletionBody] { entries }

    func enqueue(_ entry: CompletionBody) {
        entries.removeAll { isSameSlot($0, entry) }
        entries.append(entry)
        persist()
    }

    func remove(_ entry: CompletionBody) {
        entries.removeAll { isSameSlot($0, entry) }
        persist()
    }

    private func isSameSlot(_ a: CompletionBody, _ b: CompletionBody) -> Bool {
        a.week == b.week && a.day == b.day && a.slug == b.slug
    }

    private func persist() {
        guard let data = try? JSON.encoder.encode(entries) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}
