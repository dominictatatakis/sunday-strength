import Foundation
import Security

/// The password is stored, not just the session cookie, because the API has no
/// refresh token: when the 30-day ss_session cookie expires the client signs in
/// again silently rather than interrupting someone mid-set.
///
/// An account made with Apple or Google has no password, so for those the
/// server's refresh token is stored instead. Only one of the two is ever
/// held: saving either clears both first.
enum Keychain {
    private static let service = "com.sundaystrength.app.credentials"
    private static let refreshService = "com.sundaystrength.app.refresh"

    struct Credentials: Equatable {
        let email: String
        let password: String
    }

    /// Returns the OSStatus so a failed save is never silent: losing the
    /// credentials means a silent logout 30 days later, which is exactly the
    /// thing storing them was meant to prevent.
    @discardableResult
    static func save(_ credentials: Credentials) -> OSStatus {
        clear()
        let attributes: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: credentials.email,
            kSecValueData as String: Data(credentials.password.utf8),
            // Readable while locked (after one unlock since boot) so a
            // background refresh works. ThisDeviceOnly keeps the password out
            // of iCloud and iTunes backups: it is re-derivable by signing in
            // again, so there is nothing to gain by letting it be restored
            // onto another device.
            kSecAttrAccessible as String:
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        return SecItemAdd(attributes as CFDictionary, nil)
    }

    static func load() -> Credentials? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecReturnAttributes as String: true,
            kSecReturnData as String: true,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let row = item as? [String: Any],
              let email = row[kSecAttrAccount as String] as? String,
              let data = row[kSecValueData as String] as? Data
        else { return nil }
        return Credentials(email: email,
                           password: String(decoding: data, as: UTF8.self))
    }

    @discardableResult
    static func saveRefresh(_ token: String) -> OSStatus {
        clear()
        let attributes: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: refreshService,
            kSecAttrAccount as String: "refresh",
            kSecValueData as String: Data(token.utf8),
            // As for the password: readable after first unlock for background
            // refresh, and never restored onto another device.
            kSecAttrAccessible as String:
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        return SecItemAdd(attributes as CFDictionary, nil)
    }

    static func loadRefresh() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: refreshService,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecReturnData as String: true,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data, !data.isEmpty
        else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    static func clear() {
        for svc in [service, refreshService] {
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: svc,
            ]
            SecItemDelete(query as CFDictionary)
        }
    }
}
