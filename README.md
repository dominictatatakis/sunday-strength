# Sunday Strength

Your gym week in your inbox every Sunday evening. Subscribers choose 2–5 training days, their
experience level, their equipment (full gym, dumbbells or bodyweight) and an optional run day. A
deterministic engine builds the week and a Sunday job emails it. Subscribers can also log sets on a
plan page, through a JSON API, or in the iPhone app.

FastAPI, Jinja templates and hand-written CSS, with no JavaScript build step. SQLite locally,
Postgres (Supabase) in production.

## Files

| File | What it does |
|---|---|
| `engine.py` | Exercise pools, plan generation and swaps. Preview any plan with `python3 engine.py --days 4 --level beginner --equipment bodyweight` |
| `app.py` | Every route: signup, Stripe, accounts and sign-in, the plan page, exercise pages, the JSON API |
| `db.py` | Schema, migrations, queries, signed tokens, password and API-key hashing |
| `providers.py` | Checks Google and Apple sign-in tokens |
| `ratelimit.py` | Limits sign-in and signup attempts |
| `emails.py`, `send_weekly.py`, `mailer.py` | Render, schedule and deliver the emails |
| `progress.py` | Progress maths (estimated one-rep max, trends). Not shown in the app yet |
| `scripts/` | Stripe product setup; fetching exercise photos and instructions |
| `ios/` | The iPhone app. See [`ios/README.md`](ios/README.md) |

## Run it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_exercise_media.py   # exercise photos and instructions
DB_PATH=/tmp/test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  .venv/bin/uvicorn app:app --reload --port 8000
```

Clear the email keys as shown whenever a `.env` is present: it holds live credentials, and the app
would otherwise email real subscribers. Without Stripe keys, signups activate straight away without
payment. `.venv/bin/python send_weekly.py --dry-run` prints this week's emails instead of sending them.

## Tests

```bash
.venv/bin/python -m unittest discover
```

The tests use throwaway databases and never send email. For the iOS tests, see `ios/README.md`.

## Billing

Stripe, at £5/month or £12/quarter. Billing stays off, and signups are free ("Free while in beta"),
unless `STRIPE_SECRET_KEY` is set and `BILLING_ENABLED` is not `0`. `scripts/stripe_setup.py` creates
the product and prices. The webhook endpoint is `/stripe/webhook`, for `checkout.session.completed`,
`customer.subscription.deleted` and `invoice.payment_failed`.

## Deploy

- **Render** runs the app on its free tier: New → Blueprint → this repo, which reads `render.yaml`.
  Free instances sleep after about 15 minutes idle, so the first request after that takes about 30
  seconds.
- **Supabase** holds the data. Set `DATABASE_URL` to the session pooler connection string and `db.py`
  switches from SQLite to Postgres. Migrations run on boot.
- **GitHub Actions** triggers the send every Sunday at 17:00 UTC
  (`.github/workflows/sunday-send.yml`) by POSTing to `/admin/send-weekly`. It needs two repository
  secrets: `APP_URL`, the Render URL, and `ADMIN_TOKEN`, copied from the Render service's environment.
- **Email** goes through the first provider configured: Brevo (the beta route, 300 a day), Gmail SMTP
  (blocked on Render's free tier), then Resend (needs a verified domain before it will email anyone
  but the account owner). With none set, emails print to the terminal.
- **Google sign-in** on the website appears once `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set.
  The redirect URI is `<APP_BASE_URL>/auth/google`. Apple sign-in, in the iPhone app, uses
  `APPLE_BUNDLE_ID`.

`.env.example` lists the main settings.

## JSON API

Authenticate with the session cookie, or with `Authorization: Bearer ss_...` using a key created on
`/account`. Only a hash of the key is stored, and creating a new key revokes the old one.

```
GET   /api/v1/me                     preferences, status and the valid options
PATCH /api/v1/me                     change any subset of preferences
GET   /api/v1/plan[?week=2026-W30]   the week's plan, with what has been logged
POST  /api/v1/completions            {"day":1,"slug":"bench-press","sets":3,"reps":8,"weight_kg":60}
                                     ("done": false removes the entry)
GET   /api/v1/completions?limit=200  logged sets, newest first
```

The iPhone app also uses the `/api/v1/auth/*` sign-in routes. `/docs` is off unless `DEV_DOCS=1`.

## Security

- Don't give another app the Supabase `DATABASE_URL`. It connects as the owner, bypassing row-level
  security, so it can read and write every subscriber. Give it an API key instead.
- The Supabase Data API is shut on purpose. Every table has row-level security on with no policies,
  and the `anon` and `authenticated` grants are revoked; `db.py` reapplies this on every boot. Supabase's
  advisor reporting `rls_enabled_no_policy` is the intended state.

## Exercise content

Photos and instructions come from [free-exercise-db](https://github.com/yuhonas/free-exercise-db),
which is public domain. Exercise pages link out to a YouTube search rather than embedding videos,
since embedding them in a paid product goes against YouTube's terms. StrengthLog's content is
copyrighted and not used.

## Not built yet

- Password reset (for now, subscribers reply to any email)
- A progress page, using `progress.py`
- Superset pairing, and progression hints for advanced lifters
- A free two-week trial through Stripe's `trial_period_days`
