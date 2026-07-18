# Sunday Strength

Your gym week, in your inbox, every Sunday night. Subscribers pick days per
week (2–5), experience level, and an optional run day; a deterministic engine
(grown from the personal `../weight-loss/gym_plan.py`) generates their week,
and a Sunday job emails it. £5/month or £12/quarter via Stripe.

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
  run), rotating exercise pools per movement pattern. `python3 engine.py
  --days 4 --level beginner` to preview any combination.
- `app.py` — FastAPI: 3-step signup wizard (journey → plan → account →
  payment), Stripe Checkout + webhook, accounts via email+password (stdlib
  scrypt) or Google SSO (`/login`, `/account` to change days/level/run,
  `/billing` for the Stripe portal), signed manage/cancel links in emails,
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
- `db.py` — SQLite (`subscribers`, `sends`) + HMAC-signed email tokens.
- `scripts/stripe_setup.py` — one-time creation of the Stripe product/prices.
- `scripts/fetch_exercise_media.py` — pulls public-domain instructions and
  images for every exercise in the engine.

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

## Roadmap (not built yet)

- Superset pairing (the personal plan's curated same-station supersets) —
  port from `gym_plan.py` once the split templates stabilise.
- Password reset flow (currently: reply to any email; fine pre-launch, not after).
- Progression hints for advanced ("add 2.5kg when you hit the top of the
  range").
- Free 2-week trial via Stripe `trial_period_days` — probably the single
  biggest conversion lever for this kind of product.
