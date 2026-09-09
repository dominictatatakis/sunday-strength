import Foundation

enum AppConfig {
    /// Debug talks to a local throwaway server; Release to production.
    /// Override in Debug with the SS_BASE_URL environment variable.
    static var baseURL: URL {
        #if DEBUG
        let raw = ProcessInfo.processInfo.environment["SS_BASE_URL"]
            ?? "http://localhost:8123"
        #else
        let raw = "https://sunday-strength.onrender.com"
        #endif
        return URL(string: raw)!
    }
}
