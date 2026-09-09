import SwiftUI

struct LoginView: View {
    let error: String?

    private enum Field { case email, password }

    @State private var email = ""
    @State private var password = ""
    @FocusState private var focused: Field?
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

            Text("No account yet? Sign up at sundaystrength.com.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(28)
        .onAppear { focused = .email }
    }

    private func submit() {
        guard !email.isEmpty, !password.isEmpty else { return }
        focused = nil
        Task { await model.signIn(email: email, password: password) }
    }
}
