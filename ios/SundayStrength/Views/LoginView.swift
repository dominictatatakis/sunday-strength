import AuthenticationServices
import SwiftUI

struct LoginView: View {
    let error: String?

    private enum Field { case email, password }

    @State private var email = ""
    @State private var password = ""
    @FocusState private var focused: Field?
    /// Made when the Apple sheet opens: Apple is given the hash, the server
    /// the raw value, so the two must come from the same call.
    @State private var appleNonce: (raw: String, hashed: String)?
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 20) {
            Text("Sunday Strength")
                .font(.largeTitle.weight(.semibold))

            Text("Sign in with your Sunday Strength account.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            VStack(spacing: 12) {
                TextField("Email", text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focused, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focused = .password }
                SecureField("Password", text: $password)
                    .textContentType(.password)
                    .focused($focused, equals: .password)
                    .submitLabel(.go)
                    .onSubmit { submit() }
            }
            .textFieldStyle(.roundedBorder)

            if let error {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            }

            Button("Sign in") { submit() }
                .buttonStyle(.borderedProminent)
                .disabled(email.isEmpty || password.isEmpty)

            if let providers = model.providers, providers.apple || providers.google {
                VStack(spacing: 12) {
                    if providers.apple {
                        SignInWithAppleButton(.continue) { request in
                            let nonce = ProviderSignIn.makeNonce()
                            appleNonce = nonce
                            request.requestedScopes = [.email]
                            request.nonce = nonce.hashed
                        } onCompletion: { result in
                            handleApple(result)
                        }
                        .signInWithAppleButtonStyle(.black)
                        .frame(height: 48)
                        .accessibilityIdentifier("appleSignIn")
                    }
                    if providers.google {
                        Button {
                            Task { await model.signInWithGoogle() }
                        } label: {
                            Text("Continue with Google")
                                .frame(maxWidth: .infinity, minHeight: 36)
                        }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("googleSignIn")
                    }
                }
            }

            Text("No account yet? Sign up at sunday-strength.onrender.com.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(28)
        .onAppear { focused = .email }
        .task { await model.loadProviders() }
    }

    private func handleApple(_ result: Result<ASAuthorization, Error>) {
        guard case .success(let authorisation) = result,
              let credential = authorisation.credential
                as? ASAuthorizationAppleIDCredential,
              let token = try? ProviderSignIn.identityToken(from: credential),
              let nonce = appleNonce
        else {
            // A dismissed sheet is not an error worth a red label, and any
            // other failure leaves the form usable to try again.
            return
        }
        Task { await model.signInWithApple(identityToken: token, nonce: nonce.raw) }
    }

    private func submit() {
        guard !email.isEmpty, !password.isEmpty else { return }
        focused = nil
        Task { await model.signIn(email: email, password: password) }
    }
}
