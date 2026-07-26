# Sunday Strength — agent notes

Paid weekly gym-plan email service. Subscribers pick days/week, experience,
equipment and an optional run day; a deterministic engine builds their week and
a Sunday job emails it. FastAPI + Jinja templates + SQLite (Postgres in prod).
No build step, no framework beyond FastAPI, no JS bundler.

Read `README.md` first for the product and deploy story. This file is the
things that will trip you up.

## Run it

```bash
.venv/bin/uvicorn app:app --reload --port 8000     # app
.venv/bin/python engine.py --days 4 --level beginner --equipment bodyweight
.venv/bin/python send_weekly.py --dry-run          # never sends
```

There is no test suite. Verify by running the app and driving the real flow —
several bugs in this codebase only showed up that way (a floated badge
colliding with a row, a fuzzy match shipping photos of the wrong exercise).

**Before running anything that sends email**, clear the provider vars or you
will email real people from the live Brevo account:

```bash
DB_PATH=/tmp/test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  .venv/bin/uvicorn app:app --port 8123
```

`.env` holds live credentials and is gitignored. Never run tests against
`gymdigest.db` — pass `DB_PATH` to a throwaway file.

## Shape of it

| File | What it owns |
|---|---|
| `engine.py` | Exercise pools, plan generation, swaps. Pure data + functions, no I/O. |
| `app.py` | All routes: signup, Stripe, accounts, plan page, JSON API. |
| `db.py` | Schema, migrations, queries, signed tokens, password + API-key hashing. |
| `emails.py` / `send_weekly.py` / `mailer.py` | Render, schedule, deliver. |
| `templates/`, `static/style.css` | Server-rendered HTML, hand-written CSS. |

## Rules that are load-bearing

**Plans are deterministic.** `generate_plan(week, days, level, run, equipment)`
must return the same thing for the same inputs, forever. Nothing else works if
this breaks: the weekly email, the plan page and the completion log all
regenerate the plan independently and expect to agree. No randomness, no
"today", no reading the database.

**Equipment tiers are cumulative.** `bodyweight < dumbbells < full`. Every
exercise carries the *minimum* kit it needs, and every (pattern, level, tier)
must have at least one option — otherwise `generate_plan` raises on a pool that
filtered to empty. If you add a movement pattern or a level, check all three
tiers. Adjacent slots that would land on the same movement drop the later slot
rather than repeat it.

**Week keys are `2026-W30`, zero-padded, year first.** Used by `sends` and
`completions`. The padding is deliberate: string comparison equals
chronological order, which `last_logged(before_week=...)` relies on. A bare ISO
week number collides a year later and silently skips everyone — that was a real
bug here.

**`/subscribe` must refuse an email that already has an account.** Otherwise it
resets that account's password with nothing but the address. The Google path
may update an existing row, because Google proved they own the address.

**Cancellation happens on POST, never GET.** Mail clients and security scanners
follow links in emails.

**`SECRET_KEY` never gets a fixed default.** Unset means a random per-process
key plus a warning. A shared constant lets anyone forge a session cookie.

**The plan page and the API share endpoints.** `_apply_completion` is the one
place that validates and writes a tick; the JSON API, the browser fetch, and
the no-JS form all go through it. Keep it that way — it is why the API can't
rot unnoticed.

**The plan page works without JavaScript.** Every exercise is a real `<form>`
posting to `/account/plan/log`. The script intercepts submit and calls the API
instead, and hides the Save buttons via `html.js .savebtn`. If you touch the
tick UI, keep both paths working.

## Database

One connection per worker thread, reused across requests (`db.connect()`
returns the thread's connection — don't close it). Schema and migrations run
once per process. Both back-ends add missing columns on boot, so deploys need
no manual migration step.

Adding a column: append to `SCHEMA` *and* `SCHEMA_PG`, and add an idempotent
`ALTER` to `MIGRATIONS_SQLITE` *and* `MIGRATIONS_PG`. Existing databases only
get the migration.

SQLite locally, Postgres when `DATABASE_URL` is set. `_PgConn` translates `?`
placeholders and returns dict rows, so call sites are written sqlite-style.
**The Postgres path has never been exercised locally** — no Postgres here.
Treat any change to `_PgConn`, `SCHEMA_PG` or `MIGRATIONS_PG` as unverified
until it has run on Render, and check the boot log for `migration skipped:`.

Rows written before a column existed: read them through the tolerant helpers
(`db.sub_equipment(sub)`, not `sub["equipment"]`).

## Exercise media

`scripts/fetch_exercise_media.py` pulls public-domain content from
free-exercise-db into `static/exdb.json` + `static/exercises/` (both gitignored,
refetched at build time on Render).

After adding an exercise, run it and **read the `fuzzy:` lines**. Fuzzy
matching happily returns a completely different movement — it offered "Pin
Presses" for the pike push-up and was serving "Kettlebell Windmill" photos for
the kettlebell swing. If the dataset has no good match, set the alias to `None`
and add an `EXTRA` entry with our own instructions.

Licensing is researched and written up in `README.md`. free-exercise-db is
Unlicense (public domain). Never scrape StrengthLog; never embed YouTube in the
paid product — link out to a search instead.

## Money and legals

Payments are **off** until `STRIPE_SECRET_KEY` is set (`DEV_MODE`), which
activates signups instantly without charging. `SCALING.md` holds the
pre-revenue checklist — entity, ICO registration, key rotation. Don't advise on
those beyond what is written there.

## Style

Match what is there: stdlib over dependencies (passwords are stdlib `scrypt`,
there is no ORM, no JS framework), comments that explain *why* rather than
what, British English in user-facing copy, plain hand-written CSS with the
existing custom properties. Keep diffs minimal and idiomatic to the file you
are in.
