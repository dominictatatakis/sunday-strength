# Sunday Strength — agent notes

Read `README.md` for what this is and how it is deployed. This file covers what will trip you up.
The Python app lives in `server/`; run the commands below from the repository root.

## Running things safely

`server/.env` holds live credentials. Before running anything that could send email, clear the providers
and use a throwaway database. Never point anything at `gymdigest.db`.

```bash
DB_PATH=/tmp/test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  .venv/bin/uvicorn --app-dir server app:app --port 8123
```

Tests: `.venv/bin/python -m unittest discover -s server/tests -t server`. They are safe to run (throwaway databases, email keys
cleared) but don't cover everything. Also run the app and drive the real flow: several bugs here only
showed up that way, such as a floated badge colliding with a row and a fuzzy match shipping photos of
the wrong exercise.

## Rules that are load-bearing

- **Plans are deterministic.** `generate_plan(week, days, level, run, equipment)` must return the same
  plan for the same inputs, forever. The email, the plan page and the completion log each regenerate
  it and must agree. No randomness, no "today", no database reads. Days a subscriber rearranges live
  in `day_plans` and go over the generated week in `app._plan_for`, which everything that shows or
  checks a plan must use. Only the Sunday email calls `generate_plan` directly.
- **New exercises that must not change existing plans go in `EXTRA_EXERCISES`**, not `POOLS`.
  Anything added to a pool shifts the rotation and changes every plan already generated, which
  orphans the sets logged against them.
- **Equipment tiers are cumulative:** `bodyweight < dumbbells < full`. Each exercise carries the
  minimum kit it needs, and every (pattern, level, tier) needs at least one option, or `generate_plan`
  raises. Adding a pattern or a level means checking all three tiers.
- **Week keys look like `2026-W30`:** year first, zero-padded, so string order is date order.
  `last_logged(before_week=...)` relies on that. A bare week number collides a year later, which was a
  real bug.
- **`/subscribe` refuses an email that already has an account.** Otherwise it would reset that
  account's password with nothing but the address.
- **`_resolve_identity` alone decides who a Google or Apple sign-in belongs to.** It links to an
  existing account only when the provider has verified the address and it is not a relay address.
- **Cancellation happens on POST, never GET.** Mail clients and security scanners follow links.
- **`SECRET_KEY` never gets a fixed default.** Unset means a random per-process key and a warning.
- **`_apply_completion` is the one place a tick is validated and written.** The JSON API, the browser
  and the no-JS form all go through it, which is why the API can't rot unnoticed.
- **The plan page works without JavaScript.** Each exercise is a real `<form>` posting to
  `/account/plan/log`. The script intercepts it and calls the API instead. Keep both paths working.
- **The Sunday job claims (subscriber, week) before sending** and releases the claim if the send fails,
  so a crash can't double-email and a provider outage can be retried.
- **Keep the Supabase Data API shut** (see README). Don't "fix" `rls_enabled_no_policy` by adding
  policies.

## Database

- `db.connect()` returns the thread's connection, reused across requests. Don't close it.
- Adding a column: append it to `SCHEMA` and `SCHEMA_PG`, and add an idempotent `ALTER` to
  `MIGRATIONS_SQLITE` and `MIGRATIONS_PG`. Existing databases only get the migration, which runs on
  boot.
- SQLite locally, Postgres when `DATABASE_URL` is set. `_PgConn` translates `?` placeholders and
  returns dict rows. **The Postgres path has never run locally.** Treat changes to `_PgConn`,
  `SCHEMA_PG` or `MIGRATIONS_PG` as unverified until they have run on Render, and check its boot log
  for `migration skipped:`.
- Read rows written before a column existed through the tolerant helpers: `db.sub_equipment(sub)`,
  not `sub["equipment"]`.

## Exercise media

After adding an exercise, run `server/scripts/fetch_exercise_media.py` and **read the `fuzzy:` lines**.
Fuzzy matching has offered "Pin Presses" for the pike push-up and served "Kettlebell Windmill" photos
for the kettlebell swing. With no good match, set the alias to `None` and add an `EXTRA` entry. Never
scrape StrengthLog, and never embed YouTube.

## Style

Stdlib over dependencies: passwords use stdlib `scrypt`, and there is no ORM, JWT library or JS
framework. Comments explain why, not what. British English in user-facing copy. Hand-written CSS using
the existing custom properties. Keep diffs minimal and idiomatic to the file you are in.
