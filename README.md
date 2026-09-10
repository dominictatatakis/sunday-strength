# Sunday Strength

Your gym week, in your inbox, every Sunday night. Subscribers pick days per
week (2–5), experience level, what equipment they have, and an optional run
day; a deterministic engine (grown from the personal
`../weight-loss/gym_plan.py`) generates their week, and a Sunday job emails it.
£5/month or £12/quarter via Stripe.

*"Sunday Strength" is a placeholder name — everything referencing it is in
`app.py`, the templates, and `scripts/stripe_setup.py`.*

## How it fits together

```
landing page (app.py /)         Stripe Checkout            weekly cron
  signup form ──POST /subscribe──> £5/mo or £12/qtr ──webhook──> subscriber
                                                        active      │
  /exercise/<slug> demo pages  <──links in email── send_weekly.py ──┘
  (public-domain images + instructions from free-exercise-db)
```

- `engine.py` — plan generation. Deterministic per (ISO week, days, level,
  equipment, run), rotating exercise pools per movement pattern. `python3
  engine.py --days 4 --level beginner --equipment bodyweight` to preview any
  combination.

  **Equipment** is one of `full` (machines, cables, barbells), `dumbbells`
  (home weights) or `bodyweight` (nothing) — cumulative, so a full gym also
  gets the dumbbell and bodyweight movements. Every exercise carries the
  minimum kit it needs, and each (pattern, level, tier) has at least one
  option, so a bodyweight subscriber gets the same week *shape*. Where two
  slots in a day would land on the same movement (bodyweight pools are
  narrow), the second slot is dropped rather than repeated.

  **Swaps** — `ALTERNATIVES` maps each movement to ranked substitutes,
  filtered to what the subscriber actually has. They appear under every
  exercise in the email, on the plan page, and on each `/exercise/<slug>`
  page: "machine taken? try these instead".
- `app.py` — FastAPI: 3-step signup wizard (journey → plan → account →
  payment), Stripe Checkout + webhook, accounts via email+password (stdlib
  scrypt) or Google SSO (`/login`, `/account` to change days/level/equipment/
  run, `/billing` for the Stripe portal), signed manage/cancel links in emails,
  exercise demo pages, terms.

  Google SSO is config-gated: create an OAuth client at
  console.cloud.google.com (APIs & Services → Credentials → OAuth client ID →
  Web application, authorised redirect URI `<APP_BASE_URL>/auth/google`), set
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, and the buttons appear on the
  wizard and login page. Google signups carry the chosen journey/plan through
  the OAuth `state` parameter (signed, 15-min expiry) and land straight in
  Stripe Checkout.
- `emails.py` — shared rendering + the welcome email: sent the moment a
  signup activates, with a thank-you and a sample plan for the current week.
- `send_weekly.py` — Sunday send job (Resend API; dry-runs without a key;
  idempotent per subscriber-week, safe to re-run).
- `db.py` — SQLite (`subscribers`, `sends`) + HMAC-signed email tokens. One
  connection per worker thread, reused across requests. `sends.week` is a
  year-scoped key (`2026-W30`), so the idempotency check can't collide with
  the same ISO week a year later. Schema and migrations run once per process;
  both back-ends add missing columns on boot, so deploying over an existing
  database needs no manual step.
- `scripts/stripe_setup.py` — one-time creation of the Stripe product/prices.
- `scripts/fetch_exercise_media.py` — pulls public-domain instructions and
  images for every exercise in the engine. `ALIASES` maps our slugs to
  free-exercise-db names; map a slug to `None` and add an `EXTRA` entry to
  write our own copy for a movement the dataset doesn't carry (the pike
  push-up). Check the `fuzzy:` lines it prints — a bad guess ships the wrong
  photos.

## Exercise content licensing (researched 18 Jul 2026)

The personal plan linked to StrengthLog guide pages. Plain hyperlinks are
legal, including in a paid product — but building a paid product on a
competitor's pages is fragile and unpolished, so this project serves **its own
exercise pages** instead:

- **[free-exercise-db](https://github.com/yuhonas/free-exercise-db)** —
  **Unlicense (public domain)**. 800+ exercises with step-by-step instructions
  and demo photos. Free for commercial use, no attribution required. This is
  what `fetch_exercise_media.py` uses. ✅ primary source
- **[wger](https://wger.readthedocs.io/)** exercise database — CC-BY-SA 4.0.
  Commercial use OK **with attribution and share-alike**. Fine as a backup;
  share-alike makes it slightly stickier than free-exercise-db. ⚠️ fallback
- **YouTube embeds** — embedding inside a *paid* product without approval sits
  against YouTube's ToS (no selling access to their content), so we never
  embed. Exercise pages *link out* to a YouTube search instead, which is fine
  (and emails can't play video anyway).
- **StrengthLog** — linking stays legal, but their text/images/videos are
  copyright; never scrape or re-host them. Not used here.

## Run it locally (no accounts needed)

```bash
cd gym-digest
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_exercise_media.py   # public-domain demo content
.venv/bin/uvicorn app:app --reload --port 8000     # http://localhost:8000
```

Without Stripe keys the app runs in **DEV MODE**: signups activate instantly,
so you can test the full loop:

```bash
# after signing up on the landing page:
.venv/bin/python send_weekly.py --dry-run          # prints the email
.venv/bin/python send_weekly.py                    # sends (or dry-runs without RESEND_API_KEY)
```

## Deploy (free tier: Render + Supabase + GitHub Actions)

The app runs on Render (free web service), subscriber data lives in Supabase
Postgres (free, survives restarts — set `DATABASE_URL` and `db.py` switches
from SQLite automatically), and a GitHub Action triggers the Sunday send by
POSTing to `/admin/send-weekly` with the `ADMIN_TOKEN`.

1. **Render**: dashboard → New → Blueprint → pick this repo. `render.yaml`
   configures everything; paste `DATABASE_URL` (Supabase → Connect → Session
   pooler URI, with the database password) and `RESEND_API_KEY` when asked.
2. **Supabase**: project `sunday-strength` (zlutmcnemdbmgjnfrwmx), schema
   already migrated. Reset the database password in Project Settings →
   Database if you don't have it.
3. **GitHub Actions**: repo → Settings → Secrets → Actions → add `APP_URL`
   (the onrender.com URL) and `ADMIN_TOKEN` (copy from the Render service's
   environment tab). Test with Actions → Sunday send → Run workflow.
4. **Email to strangers** needs a verified domain in Resend (free): buy a
   domain, add the two DNS records Resend shows, set `EMAIL_FROM` to
   `Sunday Strength <plan@yourdomain.com>`. Until then only the Resend
   account owner's inbox receives mail.

Note: Render free instances sleep after ~15 min idle; the first request after
that takes ~30s. Fine for a beta; £7/mo removes it later.

## Going live — checklist

1. **Validate first.** Deploy the landing page and buy a domain before
   polishing anything. If ~50 visitors produce 0 paying signups, stop.
2. Domain + deploy: any small host (Fly.io, Railway, a £4 VPS). SQLite is
   fine well past 1,000 subscribers.
3. Stripe: create account → `python3 scripts/stripe_setup.py` (test keys,
   then live) → put price IDs in `.env` → add webhook endpoint
   `https://yourdomain/stripe/webhook` (events: `checkout.session.completed`,
   `customer.subscription.deleted`, `invoice.payment_failed`) → copy the
   webhook signing secret. Enable the customer billing portal in the Stripe
   dashboard (Settings → Billing → Customer portal).
4. Resend: verify your domain (SPF/DKIM) so plans don't land in spam. Free to
   3,000 emails/month ≈ 690 weekly subscribers.
5. Cron the Sunday send, e.g. `0 18 * * 0 cd .../gym-digest && .venv/bin/python
   send_weekly.py` (18:00 Sunday; plans are for the week starting Monday).
6. Replace the placeholder `/terms` with reviewed terms; keep the health
   disclaimer. Register with the ICO (UK, ~£40/yr) as you're storing emails;
   add a privacy page covering Stripe + Resend as processors.
7. VAT: digital services; you're under the UK threshold until ~£90k — revisit
   then.

## Workout log + JSON API

Exercises get ticked off on `/account/plan`, with optional sets, reps and
weight. Logging those turns on a "last: 3 × 8 @ 60kg" hint under the same
exercise next time it comes round.

The three boxes read as one sentence — `[3] sets × [8] reps @ [60] kg` —
because the units are the whole answer to "is that per set or the total?".
**Reps are per set, and weight is per dumbbell, not the pair.** The sets box
is prefilled from the prescription (`3 x 10-12` → 3) so it only needs touching
on the days you deviate; the other two start empty.

The plan is reproducible from `(week, prefs)`, so a `completions` row only
names the slot it fills: `(subscriber_id, week, day, slug, sets, reps,
weight_kg)`, unique per slot. Week keys are the same `2026-W30` format as `sends`, and
because they're zero-padded a string compare orders them chronologically —
that's how `last_logged(before_week=...)` excludes the week in progress.

The same endpoints serve the plan page (session cookie) and anything else you
point at them (`Authorization: Bearer ss_...`, key from `/account`). Keeping
the browser on the API means it can't quietly rot: if ticking a box works, the
API works.

```
GET  /api/v1/me                     prefs and status
GET  /api/v1/plan[?week=2026-W30]   the week's plan, each exercise carrying
                                    done / sets_done / reps / weight_kg
                                    (`sets` there is the prescription text)
POST /api/v1/completions            {"day":1,"slug":"bench-press",
                                     "sets":3,"reps":8,"weight_kg":60}
                                    "done":false deletes the entry
GET  /api/v1/completions?limit=200  raw history, newest first
```

The plan page degrades cleanly: every exercise is a real form posting to
`/account/plan/log`, and the script intercepts the submit to call the API
instead (hiding the Save buttons via `html.js .savebtn`). With JavaScript off
you get a Save button per exercise and a normal page reload; both routes end up
in the same `_apply_completion`.

Writes are validated against that week's generated plan, so the table can't
fill with exercises the subscriber was never given. Only the SHA-256 of an API
key is stored — issuing a new one immediately revokes the old, and the key
itself is shown exactly once.

**Don't hand another app the Supabase `DATABASE_URL`.** The app connects as the
owner role, which bypasses row-level security, so that's unscoped, unrevokable
read/write over every subscriber. An API key is per-subscriber and rotatable.

**The Supabase Data API is deliberately shut.** Supabase publishes every table
in the `public` schema through PostgREST and grants `anon` full read/write by
default — meaning anyone holding the anon key (public by design) could read and
delete the subscriber table. Nothing here uses that API, so every table has RLS
enabled with no policies, the `anon`/`authenticated` grants are revoked, and
the schema's default privileges are revoked so new tables start locked. A
migration in `db.py` re-applies this on every boot; keep it. Supabase's
security advisor should report only `rls_enabled_no_policy` at INFO — that is
the intended end state here, not something to "fix" by adding policies.

## iOS app

`ios/` holds a native SwiftUI client for iPhone — this week's plan, set
logging and preferences, against the same account the website uses. Sign-in
needs nothing new: it posts to `/login` like the web form does and rides the
session cookie, because `_api_sub` falls back to that cookie when there is no
Bearer header.

Ticks made on the phone go through `_apply_completion` like every other path,
so they show up on `/account/plan` immediately. It keeps working with no
signal — the last plan is cached and ticks queue until there is a connection.

It added one route, `PATCH /api/v1/me`, which changes preferences under the
same validation `POST /account` uses. It applies only the fields it is sent, so
a phone holding an hour-old profile can't revert something changed on the
website. `GET /api/v1/me` now returns the valid options alongside the current
values, so clients don't hard-code the splits and levels.

See `ios/README.md` to run it. Nothing in `ios/` is installed or served by the
Python app, so it is inert to deploys.

## Things that will bite if you change them

- `SECRET_KEY` unset means a random key per process: sessions and email
  manage links break on every restart. It is never a fixed default — that
  would let anyone forge a session cookie for any account.
- `/subscribe` refuses an email that already has an account (it would
  otherwise reset that account's password with nothing but the address). The
  Google path *may* update an existing row, because Google has proved the
  address belongs to them.
- Cancellation happens on `POST /manage/cancel`, never on the `GET` — mail
  clients and security scanners follow links in emails.
- The Sunday job claims `(subscriber, week)` *before* sending and releases the
  claim if the send fails, so a crash can't double-email and a provider outage
  is still retryable.

## Roadmap (not built yet)

- Superset pairing (the personal plan's curated same-station supersets) —
  port from `gym_plan.py` once the split templates stabilise.
- Password reset flow (currently: reply to any email; fine pre-launch, not after).
- Progression hints for advanced ("add 2.5kg when you hit the top of the
  range").
- Free 2-week trial via Stripe `trial_period_days` — probably the single
  biggest conversion lever for this kind of product.
