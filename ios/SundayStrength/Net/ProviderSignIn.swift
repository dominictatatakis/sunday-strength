import AuthenticationServices
import CryptoKit
import Foundation

/// Getting a credential from Apple or Google.
///
/// Neither provider's SDK is used. Apple's sheet is a system control, and
/// Google is an authorisation code collected through the system browser, so
/// both are Apple frameworks only -- which is what the rest of this app is.
///
/// Nothing here decides anything. It hands the server a credential; who that
/// credential belongs to, and whether they may have an account, is the
/// server's to answer.
enum ProviderSignIn {

    enum Failure: Error, Equatable {
        /// The person dismissed the sheet. Not worth showing an error for.
        case cancelled
        case failed
    }

    // MARK: - Apple

    /// A random nonce, and the SHA-256 of it.
    ///
    /// Apple is sent the hash and echoes it inside the signed token; the
    /// server is sent the raw value and compares. That is what makes a token
    /// captured once useless the second time. Sending the raw value to Apple
    /// and the hash to the server type-checks, compiles, and silently removes
    /// the replay protection entirely, so the two are produced together here
    /// rather than at the call site.
    static func makeNonce() -> (raw: String, hashed: String) {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let raw = Data(bytes).base64EncodedString()
        let hashed = SHA256.hash(data: Data(raw.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return (raw, hashed)
    }

    /// The name Apple gives, formatted, or nil.
    ///
    /// Apple returns this on the FIRST authorisation only, ever. It is not
    /// retrievable afterwards by any call, so a caller that does not keep it
    /// now cannot ask again.
    static func displayName(from components: PersonNameComponents?) -> String? {
        guard let components else { return nil }
        let formatted = PersonNameComponentsFormatter.localizedString(
            from: components, style: .default)
        return formatted.isEmpty ? nil : formatted
    }

    /// Pulls the identity token out of an Apple credential.
    static func identityToken(
        from credential: ASAuthorizationAppleIDCredential) throws -> String {
        guard let data = credential.identityToken,
              let token = String(data: data, encoding: .utf8), !token.isEmpty
        else { throw Failure.failed }
        return token
    }

}

/// Presents the browser sheet over the app's own window.
@MainActor
private final class AnchorProvider: NSObject,
    ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession)
        -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
        let scene = scenes.first { $0.activationState == .foregroundActive }
            ?? scenes.first
        // A window built for the scene, rather than a bare UIWindow(): the
        // parameterless initialiser is deprecated on iOS 26, and a window with
        // no scene has nothing to present over in any case.
        if let scene {
            return scene.keyWindow ?? UIWindow(windowScene: scene)
        }
        return UIWindow()
    }
}

extension ProviderSignIn {

    /// What the server sends the app back with.
    enum GoogleOutcome: Equatable {
        /// Signed in. Exchange this for a session; it expires in a minute.
        case handoff(String)
        /// Verified, but new here: ask the four questions first. The identity
        /// is signed, so it survives the round trip without the app being
        /// able to alter who it is.
        case needsOnboarding(pending: String)
    }

    /// Runs Google sign-in through the system browser.
    ///
    /// Opens our own start URL, not Google's: the exchange then happens on the
    /// server, the client secret never reaches this device, and Google needs
    /// only one web client rather than a second native one.
    @MainActor
    static func google(baseURL: URL,
                       callbackScheme: String = "sundaystrength") async throws -> GoogleOutcome {
        let start = baseURL.appendingPathComponent("login/google")
        var components = URLComponents(url: start, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "app", value: "1")]

        let anchor = AnchorProvider()
        let url: URL = try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: components.url!, callbackURLScheme: callbackScheme) { url, error in
                if let url {
                    continuation.resume(returning: url)
                } else if let error = error as? ASWebAuthenticationSessionError,
                          error.code == .canceledLogin {
                    continuation.resume(throwing: Failure.cancelled)
                } else {
                    continuation.resume(throwing: Failure.failed)
                }
            }
            session.presentationContextProvider = anchor
            // Not ephemeral: someone already signed in to Google in Safari
            // should not have to type a password again to use this button.
            session.prefersEphemeralWebBrowserSession = false
            if !session.start() {
                continuation.resume(throwing: Failure.failed)
            }
        }
        return try outcome(from: url)
    }

    /// Reads what the callback URL carries. Separated from the browser work so
    /// it can be tested without one.
    static func outcome(from url: URL) throws -> GoogleOutcome {
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?
            .queryItems ?? []
        func value(_ name: String) -> String? {
            let found = items.first { $0.name == name }?.value
            return (found?.isEmpty == false) ? found : nil
        }
        if let handoff = value("handoff") { return .handoff(handoff) }
        if let pending = value("pending"), value("needs_onboarding") != nil {
            return .needsOnboarding(pending: pending)
        }
        throw Failure.failed
    }
}
