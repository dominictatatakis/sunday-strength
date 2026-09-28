import Foundation

/// Ticks and day edits made without a connection, replayed in order when
/// there is one.
///
/// Replaying late is safe because each entry is a whole state, not an
/// increment: a tick sets one slot and a day edit sets the whole day, so a
/// repeat is a no-op. Order matters, though: a tick on a swapped-in exercise
/// is refused until the swap has landed, so nothing jumps ahead of an edit
/// made before it.
actor OfflineQueue {
    private let fileURL: URL
    private var entries: [QueuedChange]

    init(fileURL: URL = OfflineQueue.defaultURL,
         legacyURL: URL = OfflineQueue.legacyURL) {
        self.fileURL = fileURL
        if let data = try? Data(contentsOf: fileURL) {
            entries = (try? JSON.decoder.decode([QueuedChange].self,
                                                from: data)) ?? []
        } else {
            // Ticks queued by the build before day edits, as bare bodies.
            let data = (try? Data(contentsOf: legacyURL)) ?? Data()
            let ticks = (try? JSON.decoder.decode([CompletionBody].self,
                                                  from: data)) ?? []
            entries = ticks.map(QueuedChange.tick)
            if !ticks.isEmpty { Self.write(entries, to: fileURL) }
            try? FileManager.default.removeItem(at: legacyURL)
        }
    }

    static var defaultURL: URL {
        directory.appendingPathComponent("offline-changes.json")
    }

    static var legacyURL: URL {
        directory.appendingPathComponent("offline-ticks.json")
    }

    private static var directory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base,
                                                 withIntermediateDirectories: true)
        return base
    }

    func pending() -> [QueuedChange] { entries }

    func enqueue(_ change: QueuedChange) {
        // A second tick on a slot replaces the first and joins the end: it
        // was made after everything already queued, so that is its place.
        if case .tick(let body) = change {
            entries.removeAll {
                guard case .tick(let queued) = $0 else { return false }
                return queued.week == body.week && queued.day == body.day
                    && queued.slug == body.slug
            }
        }
        entries.append(change)
        Self.write(entries, to: fileURL)
    }

    /// Drops the entry just sent, and only that one: a newer tick on the same
    /// slot, queued while this one was in flight, must stay.
    func remove(_ change: QueuedChange) {
        guard let i = entries.firstIndex(of: change) else { return }
        entries.remove(at: i)
        Self.write(entries, to: fileURL)
    }

    private static func write(_ entries: [QueuedChange], to url: URL) {
        guard let data = try? JSON.encoder.encode(entries) else { return }
        try? data.write(to: url, options: .atomic)
    }
}
