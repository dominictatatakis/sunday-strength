# Sunday Strength for iOS — design

_9 September 2026. Status: approved, step 1 not yet planned._

A native SwiftUI iPhone app in a new `ios/` folder, signing into the same
account as the website and showing the same week. Built in three steps:

| Step | Adds | Server change |
|---|---|---|
| 1 | Login, this week's plan, ticking sets | **none** |
| 2 | Progress tab | `GET /api/v1/progress` |
| 3 | Settings tab | `PATCH /api/v1/me` |

This document specifies step 1 in full and sketches 2 and 3. Each later step
gets its own design before any code.

## Why step 1 needs no server changes

The first instinct is that a phone needs a token endpoint, because the only
documented way to get an API key is copying one from `/account` in a browser.
That is wrong. `_api_sub` (`app.py:578`) tries the `Authorization: Bearer`
header first and **falls back to the `ss_session` cookie** (`app.py:583`), and
`POST /login` (`app.py:292`) sets that cookie from an ordinary form post.

So the app signs in the way the website does — form-encoded `email` and
`password` to `/login` — and `URLSession` carries the resulting cookie to every
`/api/v1/*` call. No token endpoint, no API-key paste, and critically no new
password-guessing surface: the app hits exactly the login route that is already
public.

Everything else already exists too. `api_plan` (`app.py:613`) returns the week's
days with `done`, `sets_done`, `reps` and `weight_kg` already merged in, so the
plan screen is one request. `api_set_completion` (`app.py:667`) writes ticks
through `_apply_completion` (`app.py:636`), the same validator the browser fetch
and the no-JS form use.

## Session lifetime

`SESSION_MAX_AGE` is 30 days (`app.py:33`). A gym app that logs you out monthly
mid-session is a bad gym app, so credentials go into the Keychain
(`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, so a background refresh
works while the phone is locked provided it has been unlocked once since boot,
and the password stays out of device backups) and the client
re-authenticates silently on the first 401, retrying the original request once.
A silent login that is *rejected* means the password genuinely changed, so the
Keychain is cleared and the login screen shown. A silent login that merely
*fails to connect* means no such thing, so the app stays signed in on its
cached plan. Conflating the two would sign people out every time they walked
into a basement gym.

The password is stored, not just the cookie, because there is no refresh token
to store instead. This is the standard shape for an app talking to a
session-cookie backend, and it is why step 1 does not need a token endpoint —
but it is also the strongest argument for adding one later, since a token can be
revoked per-device and a password cannot.

## Layout

```
ios/
  project.yml                    xcodegen source — the project as a readable diff
  SundayStrength.xcodeproj/      generated once, committed, so Xcode needs no tooling
  SundayStrength/
    SundayStrengthApp.swift
    Net/     APIClient.swift  Keychain.swift  OfflineQueue.swift
    Models/  Me.swift  Plan.swift  Completion.swift
    Views/   LoginView.swift  PlanView.swift  DayView.swift  LogSheet.swift
    Info.plist  Assets.xcassets
  Tests/     APIClientTests.swift  OfflineQueueTests.swift
  README.md                      how to run it against a local server
```

Deployment target iOS 17. **No third-party dependencies** — `URLSession`,
`Codable`, the Security framework for the Keychain, and Swift Charts when step 2
arrives. That is the Swift reading of this repo's "stdlib over dependencies, no
bundler" rule, and it means the app has no supply chain to audit.

`xcodegen` generates the project from `project.yml`; the generated
`.xcodeproj` is committed so a clone opens in Xcode without installing anything.
`project.yml` is what gets reviewed when the project structure changes.

`.gitignore` gains `ios/build/` and `xcuserdata/`. That is the only existing
file step 1 touches.

## Architecture

Three layers, no more:

- **`APIClient`** — an `actor` wrapping one `URLSession` with a shared
  `HTTPCookieStorage`. Owns login, the 401 retry, and typed `Codable` calls.
- **`AppModel`** — an `@Observable` holding auth state, the current plan and the
  offline queue's depth. One instance, injected through the environment.
- **Views** — SwiftUI, no logic beyond formatting.

Base URL is a build setting: `http://localhost:8000` in Debug,
`APP_BASE_URL`'s production value in Release. Debug builds need
`NSAllowsLocalNetworking` in `Info.plist`, because App Transport Security blocks
cleartext HTTP outright; the Release build carries no ATS exception at all.

### Ticking a set

Optimistic, because the alternative is a spinner between every set:

1. The row updates immediately and the tick appends to the offline queue.
2. `POST /api/v1/completions` fires.
3. On success the queue entry is dropped.
4. On a network failure it stays queued and the row keeps its new state.
5. On a **400** the plan has drifted — `_apply_completion` rejects slugs that
   are not in that week's plan — so the row reverts, the queue entry is dropped,
   and the plan refetches.

Distinguishing 4 from 5 matters. A queued tick that the server will never accept
would otherwise retry forever.

## Offline

This runs in a gym, where signal is bad by default rather than exceptionally.

The last successful `/api/v1/plan` response is cached to disk as raw JSON and
rendered with an "offline" banner when a refetch fails. Ticks append to a small
JSON file keyed by `(week, day, slug)`, newest wins, flushed on foreground and
after a successful request.

Replaying a queue hours late is safe, and the reason is a rule this repo already
enforces: `generate_plan` (`engine.py:537`) is deterministic, so the plan the
phone cached is the plan the server will validate against, and completions are
idempotent per slot rather than incremental. Nothing about a late tick is
ambiguous.

## Verification

Unit tests via `xcodebuild test`: `Codable` decoding against JSON fixtures
captured from the real endpoints, and the queue's merge, replay and
drop-on-400 logic.

Then the real flow, because this repo's own guidance is that several of its bugs
only ever showed up that way:

```bash
DB_PATH=/tmp/ios-test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  .venv/bin/uvicorn app:app --port 8123
```

Provider vars cleared so nothing can email a real subscriber, `DB_PATH` on a
throwaway file so `gymdigest.db` is never touched. A test account is created
through `/subscribe`, which activates instantly in `DEV_MODE` when
`STRIPE_SECRET_KEY` is unset. Then: boot the simulator, log in, tick a set,
and confirm it appears on the website's plan page for the same account.

## Deliberately not in step 1

Signup, billing and cancellation stay on the web. Stripe in-app is painful, and
Apple takes a cut of in-app purchases for anything that looks like digital
content — a fight not worth having for a product whose signup already works in
Safari. The app assumes an account exists and links out for anything else.

No push notifications. The Sunday email is the delivery mechanism and already
works; adding a second one before the app has any users is speculation.

No watch app, no iPad layout, no widgets.

## Steps 2 and 3, sketched

**`GET /api/v1/progress`** would be the first thing ever to serve `progress.py`.
That module is 345 lines of tested pure functions — `strength_index`,
`relative_strength`, `consistency`, `tonnage`, `pattern_trends` — that nothing
imports: there is no progress route in `app.py` and no progress page on the
website. So step 2 is not "expose an existing feature", it is shipping that
feature server-side with the phone as its first consumer, and the endpoint
should be designed for the website too.

One shape constraint is already visible: `sparkline()` returns SVG path geometry,
which is web-shaped. The endpoint should return the underlying values and let
each client draw them, or the phone will be parsing SVG to render a chart.

**`PATCH /api/v1/me`** is smaller than it looks. `POST /account` already lets
people change days per week, experience, equipment and run day mid-week, so the
endpoint mirrors semantics that exist rather than inventing any. The one thing
to get right is that changing settings changes the generated plan, which can
strand completions logged against exercises that are no longer in the week — the
same thing the website already does, and worth confirming is intended before
making it easier to trigger.
