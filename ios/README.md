# Sunday Strength for iOS

A native SwiftUI client for the same account as the website. Shows this week's
plan, logs completed sets, and edits your preferences — working offline in a
gym.

Steps 1 and 3 of `docs/superpowers/specs/2026-09-09-ios-app-design.md`. Step 2,
the progress tab, is not built. Everything but the settings tab runs on
endpoints that already existed; settings added `PATCH /api/v1/me`.

## Running it

The app talks to a local server in Debug builds. Start one against a throwaway
database, with the email providers cleared so nothing can reach a real
subscriber:

```bash
DB_PATH=/tmp/ios-test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  STRIPE_SECRET_KEY= .venv/bin/uvicorn app:app --port 8123
```

Create an account to sign in with (instant, no payment, because
`STRIPE_SECRET_KEY` is unset and the app is in `DEV_MODE`):

```bash
curl -X POST http://localhost:8123/subscribe \
  -d "email=ios-test@example.com" -d "password=testpass123" \
  -d "days=4" -d "experience=intermediate" -d "equipment=full"
```

Note the field is `days`, not `days_per_week`.

Then:

```bash
cd ios
xcodegen generate          # after editing project.yml or adding any file
open SundayStrength.xcodeproj
```

Point the app somewhere else with the `SS_BASE_URL` environment variable in the
scheme's run arguments.

## Tests

```bash
cd ios && xcodebuild -project SundayStrength.xcodeproj -scheme SundayStrength \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/ss-ios-build test
```

Two things about that command are load-bearing:

- **`-derivedDataPath` must be outside the repo.** This checkout sits in a
  file-provider-synced folder, which stamps `com.apple.FinderInfo` onto build
  output; `codesign` then rejects the bundle as "resource fork, Finder
  information, or similar detritus not allowed".
- **No `-sdk iphonesimulator`.** Passing it alongside `-destination` empties
  the scheme's supported platforms and nothing will match.

Run `xcodegen generate` after adding any file. The project holds an explicit
file list, so a new test file is simply not compiled until you do — and the run
reports `TEST SUCCEEDED` while silently skipping it.

The UI tests need the local server; they skip themselves when there is none, so
a plain test run stays green without one. `OfflineUITests` is the exception: it
runs with the server deliberately stopped.

## Changing preferences

`PATCH /api/v1/me` takes any subset of `days_per_week`, `experience`,
`equipment` and `include_run`, and validates them exactly as `POST /account`
does. The app sends only the fields that differ from the profile it holds — it
may be an hour old, and resending all four would revert anything changed on the
website meanwhile.

Saving rebuilds the week, because those preferences are what `generate_plan` is
given. Sets already logged against exercises that drop out stop being shown,
which is what the account form already does.

## How sign-in works

There is no token endpoint. The app posts to `/login` exactly as the website's
form does, and the `ss_session` cookie it returns authenticates every
`/api/v1/*` call — `_api_sub` falls back to the cookie when there is no Bearer
header (`app.py:583`).

Both a right and a wrong password return `303`, so the client reads the
`Location` header rather than following the redirect.

The cookie lasts 30 days, so credentials are kept in the Keychain
(`AfterFirstUnlockThisDeviceOnly`, which keeps them out of device backups) and
the app signs in again silently on the first 401 rather than interrupting a
workout.

## Structure

| Path | What it owns |
|---|---|
| `project.yml` | Project definition. Edit this, not the `.xcodeproj`. |
| `Net/APIClient.swift` | Every network call, and the error taxonomy. |
| `Net/Keychain.swift` | Stored credentials. |
| `Net/OfflineQueue.swift` | Ticks made without signal. |
| `Net/PlanCache.swift` | Last plan seen, for offline launches. |
| `AppModel.swift` | Auth state, the current plan, optimistic updates. |
| `Views/SettingsView.swift` | Preferences. Sends only what changed. |
| `Views/` | SwiftUI, no logic beyond formatting. |

No third-party dependencies, matching the Python side's stdlib-first rule.
