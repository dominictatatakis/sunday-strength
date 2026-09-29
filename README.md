# Sunday Strength

I built this as a side project to get myself back to the gym without having to think about which
exercises to do. Every Sunday evening, the coming week's workouts arrive by email.

Subscribers choose 2–5 training days, their experience level, their equipment (full gym, dumbbells
or bodyweight) and an optional run day, and a deterministic engine builds the week from those. They
can also log sets on a plan page, through a JSON API, or in the iPhone app.

FastAPI, Jinja templates and hand-written CSS, with no JavaScript build step. SQLite locally,
Postgres (Supabase) in production.

## Layout

```
server/        the website, JSON API and emails (Python, runs on Render)
ios/           the iPhone app (see ios/README.md)
.github/       the job that triggers the Sunday send
render.yaml    Render's deploy settings
```

| In `server/` | What it does |
|---|---|
| `engine.py` | Exercise pools, plan generation and swaps |
| `app.py` | Every route: signup, accounts and sign-in, the plan page, exercise pages, the JSON API |
| `db.py` | Schema, migrations, queries, signed tokens, password and API-key hashing |
| `providers.py` | Checks Google and Apple sign-in tokens |
| `ratelimit.py` | Limits sign-in and signup attempts |
| `emails.py`, `send_weekly.py`, `mailer.py` | Render, schedule and deliver the emails |
| `progress.py` | Progress maths (estimated one-rep max, trends). Not shown in the app yet |
| `envfile.py` | Loads `server/.env` |
| `templates/`, `static/` | Pages and emails; CSS and exercise media |
| `scripts/` | One-off scripts, such as fetching exercise photos and instructions |
| `tests/` | The Python tests |

## Run it locally

From the repository root:

```bash
python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt
.venv/bin/python server/scripts/fetch_exercise_media.py   # exercise photos and instructions
DB_PATH=/tmp/test.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  .venv/bin/uvicorn --app-dir server app:app --reload --port 8000
```

Settings go in `server/.env` (start from `server/.env.example`). Clear the email keys as shown
whenever that file exists: it holds live credentials, and the app would otherwise email real
subscribers.

- `.venv/bin/python server/send_weekly.py --dry-run` prints this week's emails instead of sending them.
- `python3 server/engine.py --days 4 --level beginner --equipment bodyweight` previews a plan.

## Tests

```bash
.venv/bin/python -m unittest discover -s server/tests -t server
```

The tests use throwaway databases and never send email. For the iOS tests, see `ios/README.md`.

## Deploy

- **Render** runs the app on its free tier: New → Blueprint → this repo, which reads `render.yaml`.
  That file points Render at `server/`. Free instances sleep after about 15 minutes idle, so the
  first request after that takes about 30 seconds.
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

`server/.env.example` lists the main settings.

## JSON API

Authenticate with the session cookie, or with `Authorization: Bearer ss_...` using a key created on
`/account`. Only a hash of the key is stored, and creating a new key revokes the old one.

```
GET    /api/v1/me                     preferences, status and the valid options
PATCH  /api/v1/me                     change any subset of preferences
GET    /api/v1/plan[?week=2026-W30]   the week's plan, with what has been logged
POST   /api/v1/completions            {"day":1,"slug":"bench-press","sets":3,"reps":8,"weight_kg":60}
                                      ("done": false removes the entry)
GET    /api/v1/completions?limit=200  logged sets, newest first
PUT    /api/v1/plan/days/{day}        {"slugs":["goblet-squat","plank"]}: that day's exercises, in
                                      order, for this week (or "week"); returns the plan
DELETE /api/v1/plan/days/{day}        puts the day back as generated
GET    /api/v1/exercises              the library your kit allows, with steps and photo paths
```

Each day in a plan also carries `circuit`: that day's 5-minute abs circuit (`work` and `rest` in
seconds, five `moves`, and `done`). It is ticked like an exercise, with the slug `abs-circuit`.

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
to stay within YouTube's terms. StrengthLog's content is copyrighted and not used.

## Not built yet

- Password reset (for now, subscribers reply to any email)
- A progress page, using `server/progress.py`
- Superset pairing, and progression hints for advanced lifters
