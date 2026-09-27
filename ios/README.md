# Sunday Strength for iOS

A SwiftUI iPhone app for the same account as the website. It shows this week's plan, logs sets, edits
preferences, and keeps working with no signal. The progress tab is not built yet. No third-party
dependencies.

## Run it

Debug builds talk to a local server. From the repository root, start one on a throwaway database
with the email providers cleared, so nothing can reach a real subscriber:

```bash
DB_PATH=/tmp/ios-test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  STRIPE_SECRET_KEY= .venv/bin/uvicorn --app-dir server app:app --port 8123
```

Create an account to sign in with. The field is `days`, not `days_per_week`:

```bash
curl -X POST http://localhost:8123/subscribe \
  -d "email=ios-test@example.com" -d "password=testpass123" \
  -d "days=4" -d "experience=intermediate" -d "equipment=full"
```

Then `cd ios && xcodegen generate && open SundayStrength.xcodeproj`. To use a different server, set
`SS_BASE_URL` in the scheme's environment.

## Tests

```bash
cd ios && xcodebuild -project SundayStrength.xcodeproj -scheme SundayStrength \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/ss-ios-build test
```

- **`-derivedDataPath` must be outside the repo.** The checkout is in a synced folder that stamps
  Finder information onto build output, and `codesign` then rejects the bundle.
- **Don't add `-sdk iphonesimulator`.** Alongside `-destination` it matches nothing.
- **Run `xcodegen generate` after adding any file**, and edit `project.yml`, not the `.xcodeproj`. A
  file missing from the project is not compiled, and the run still reports `TEST SUCCEEDED`.
- UI tests skip themselves when the local server isn't running, except `OfflineUITests`, which needs it
  stopped.

## Sign-in

- **Password:** the app posts to `/login` as the website's form does, and the `ss_session` cookie it
  gets back (valid 30 days) authenticates every `/api/v1` call. Right and wrong passwords both return
  `303`, so the app reads the `Location` header. The password is kept in the Keychain
  (`AfterFirstUnlockThisDeviceOnly`, so it stays out of backups) to sign in again silently when the
  cookie expires.
- **Apple or Google:** `/api/v1/auth/apple` and `/api/v1/auth/google` return the same cookie plus a
  refresh token (valid a year), which is kept instead of a password and exchanged at
  `/api/v1/auth/refresh`. The phone never holds a Google credential. `/api/v1/auth/providers` says
  which buttons to show.

## Preferences

`PATCH /api/v1/me` takes any subset of `days_per_week`, `experience`, `equipment` and `include_run`,
validated as `POST /account` does. The app sends only the fields that changed, so a profile an hour
old can't undo an edit made on the website. Saving rebuilds the week.

## Structure

| Path | What it owns |
|---|---|
| `project.yml` | The project definition |
| `Net/APIClient.swift` | Every network call, and the error types |
| `Net/Keychain.swift` | Stored password or refresh token |
| `Net/OfflineQueue.swift` | Ticks made without signal |
| `Net/PlanCache.swift` | The last plan seen, for offline launches |
| `Net/ProviderSignIn.swift` | Apple and Google sign-in |
| `AppModel.swift` | Sign-in state, the current plan, optimistic updates |
| `Views/` | SwiftUI, with no logic beyond formatting |
