import Foundation

/// The last plan the server sent, so the app opens to something useful in a
/// basement gym with no signal.
enum PlanCache {
    private static var url: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base,
                                                 withIntermediateDirectories: true)
        return base.appendingPathComponent("plan.json")
    }

    static func save(_ plan: Plan) {
        guard let data = try? JSON.encoder.encode(plan) else { return }
        try? data.write(to: url, options: .atomic)
    }

    static func load() -> Plan? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSON.decoder.decode(Plan.self, from: data)
    }
}
