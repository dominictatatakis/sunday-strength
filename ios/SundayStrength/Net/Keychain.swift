import Foundation
import Security

/// The password is stored, not just the session cookie, because the API has no
/// refresh token: when the 30-day ss_session cookie expires the client signs in
/// again silently rather than interrupting someone mid-set.
enum Keychain {
    private static let service = "com.sundaystrength.app.credentials"

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
            // Readable while locked, so a background refresh works — but only
            // after the phone has been unlocked once since boot.
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
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

    static func clear() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
