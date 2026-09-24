import Foundation

/// GET /api/v1/auth/providers: which sign-in buttons to show, and the values
/// the onboarding questions may take -- someone new has no profile yet to
/// carry them.
struct ProvidersInfo: Codable, Equatable {
    let google: Bool
    let apple: Bool
    let options: PrefOptions
}

/// The four questions a first-time provider sign-in answers before any
/// account exists.
struct OnboardingPrefs: Codable, Equatable {
    var days: Int
    var experience: String
    var run: Bool
    var equipment: String
}

/// A provider sign-in succeeded. The ss_session cookie arrived with it; the
/// refresh token is what brings a session back once that cookie expires,
/// because a provider account has no password to replay.
struct AuthResponse: Codable, Equatable {
    let refresh: String
    let email: String
}

/// How to resume a provider sign-in once the onboarding answers are in.
enum PendingSignIn: Equatable {
    /// Apple's identity token and the raw nonce it was issued against.
    case apple(identityToken: String, nonce: String)
    /// The signed identity the server handed back from Google.
    case google(pending: String)
}

struct Onboarding: Equatable {
    let pending: PendingSignIn
    let options: PrefOptions
}
