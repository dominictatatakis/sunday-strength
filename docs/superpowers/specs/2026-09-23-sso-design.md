# Signing in with Google and Apple

Sunday Strength already signs people in with Google on the website. This
finishes the job: Sign in with Apple as well, both providers in the iOS app,
and an identity model that does not hand someone a second, empty account.

The sibling project `../friend-management-system` (Kith) is doing the same
work against the same design. The identity rules below are shared with it
deliberately; the implementations are separate because the two ship
independently.

## Why Apple as well

App Review guideline 4.8 requires Sign in with Apple once an app offers any
other third-party login. The iOS app is on TestFlight and already has a
Google-backed account system behind it, so Apple is not optional — the two
arrive together.

## Identity

An account stops being identified by its email address alone.

```sql
CREATE TABLE IF NOT EXISTS auth_identities (
    id            SERIAL PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    provider      TEXT NOT NULL,       -- 'google' | 'apple'
    subject_id    TEXT NOT NULL,       -- the provider's stable `sub`
    email         TEXT,                -- as provided; may be a relay
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, subject_id)
);
```

Added to both schema variants, Postgres and SQLite.

`subject_id`, not email, is the key. Sign in with Apple offers **Hide My
Email**, which hands over a per-app relay address like
`a1b2c3@privaterelay.appleid.com`. Keying on email would give someone who
signed up that way a second account the next time they used a different
button — an empty plan, no logged sets, and nothing in the interface to
explain where their training went. Apple's `sub` is stable even when the
relay address is not.

`subscribers.password_hash` is already nullable, which is what the existing
Google flow relies on. No change there.

### Linking rules

Given a verified `(provider, subject_id, email, email_verified)`:

1. An identity row exists → sign that subscriber in.
2. No identity row, but `email_verified` and the address is **not** a relay
   and a subscriber already holds it → write the identity row, then sign in.
3. Otherwise → the new-account path below.

Two rules are load-bearing:

**Never link on an unverified email.** A provider that will assert an
address it has not verified is an account takeover primitive. The existing
`/auth/google` callback already refuses when `email_verified` is false; that
check moves into the shared path rather than being reimplemented.

**Never auto-link a relay address.** It is per-app by construction and says
nothing about who the person is anywhere else.

The email column is stored for support and display. Nothing authenticates
against it.

## New accounts need preferences

Signing up here is not just credentials. `/subscribe` takes days per week,
experience, equipment and whether to include a run, and without them there
is no plan to show. The website carries those through OAuth state; a phone
tapping "Sign in with Apple" supplies none of them.

So when a provider credential resolves to no existing subscriber and the
request carries no preferences, the server writes nothing and answers `409`
with `needs_onboarding`. The app shows the same four questions the website
asks, then posts again; the subscriber row and the first week are created
together.

Creating the row first and asking afterwards would leave accounts with no
plan, reachable only by a screen the person can skip.

## Endpoints

```
GET  /auth/{provider}/start      redirect with signed state + PKCE
GET  /auth/{provider}/callback   exchange, link or create, set the cookie
POST /api/v1/auth/{provider}     the phone's way in; sets ss_session
```

The existing `/login/google`, `/subscribe/google` and `/auth/google` keep
working. Their body moves into the shared verification path so there is one
place that decides who a provider response belongs to, not two that drift.

### Verifying Apple

The client sends the identity token. The server checks:

- the signature, against Apple's published JWKS (fetched and cached; a
  fetch failure is a `503`, never a pass)
- `iss` is `https://appleid.apple.com`
- `exp` is in the future
- `nonce` matches the one the client generated for this attempt
- `aud` is **either** the bundle identifier (iOS) **or** the Services ID
  (web) — these differ, and accepting only one breaks the other surface

Apple returns the person's name **only on the first authorisation, ever**.
Persist it then or lose it.

### Verifying Google

The phone runs PKCE and sends `code` plus `code_verifier`; the server
exchanges them, keeping the client secret off the device. The website keeps
the server-side exchange it already has.

## The iOS app

A native `SignInWithAppleButton`, and a "Continue with Google" button that
opens `ASWebAuthenticationSession`. No third-party SDK — this app has no
dependencies and Google's SDK would buy nothing over
`ASWebAuthenticationSession`.

`POST /api/v1/auth/{provider}` sets the same `ss_session` cookie the login
form sets, so everything past sign-in is unchanged: `APIClient` keeps
working as it does today, and the offline queue and plan cache are untouched.

A button appears only when the server advertises that provider, so an
unconfigured credential shows nothing rather than a button that fails.
`GOOGLE_ENABLED` already works this way and `APPLE_ENABLED` joins it.

## Testing

Provider responses are stubbed. No test reaches Google or Apple.

The cases worth writing before the code:

- an unverified email does not link, and does not create
- a relay address does not link to an existing subscriber with the same name
- a token signed by the wrong key is refused
- a replayed token with a stale nonce is refused
- `aud` of the bundle ID and of the Services ID both pass
- no preferences means no subscriber row — nothing is written
- signing in twice with the same provider does not create a second identity
- an existing password account links on first Google sign-in and keeps its
  logged sets

The UI tests already drive the real app against a local server on `:8123`;
the sign-in screen gains coverage for both buttons there. Note that the
simulator resolves `localhost` to `::1`, so that server must bind
dual-stack or the app cannot reach it.

## Rolling it out

Apple capability, Services ID and key first; then the server behind flags;
then the app. Each step is inert until the one before it is live, so a
half-finished rollout shows the current sign-in screen rather than a broken
new one.
