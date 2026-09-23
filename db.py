"""SQLite storage + signed tokens for manage/unsubscribe links."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "gymdigest.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")  # Postgres in production

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    # Never fall back to a shared constant: anyone who knows it can forge a
    # session cookie for any account. A per-process key is safe; it just means
    # logins and manage links don't survive a restart.
    SECRET_KEY = secrets.token_hex(32)
    print("WARNING: SECRET_KEY is not set — using a random one for this "
          "process. Sign-ins and email manage links will stop working on "
          "restart. Set SECRET_KEY (openssl rand -hex 32) in .env.")

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS subscribers (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    days_per_week INTEGER NOT NULL,
    experience TEXT NOT NULL,
    include_run INTEGER NOT NULL DEFAULT 0,
    equipment TEXT NOT NULL DEFAULT 'full',
    plan TEXT NOT NULL DEFAULT 'monthly',
    password_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sends (
    id SERIAL PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    week TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subscriber_id, week)
);
CREATE TABLE IF NOT EXISTS completions (
    id SERIAL PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    week TEXT NOT NULL,
    day INTEGER NOT NULL,
    slug TEXT NOT NULL,
    sets INTEGER,
    weight_kg DOUBLE PRECISION,
    reps INTEGER,
    done_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subscriber_id, week, day, slug)
);
"""

# Applied once per process, after SCHEMA_PG. Each must be safe to re-run.
MIGRATIONS_PG = [
    "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS password_hash TEXT",
    "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS equipment TEXT "
    "NOT NULL DEFAULT 'full'",
    "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS api_key_hash TEXT",
    "ALTER TABLE completions ADD COLUMN IF NOT EXISTS sets INTEGER",
    # sends.week used to be an INTEGER ISO week number, which collides one year
    # later and silently skips everyone. It now holds '2026-W30'.
    """DO $$ BEGIN
         IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'sends' AND column_name = 'week'
                      AND data_type <> 'text')
         THEN ALTER TABLE sends ALTER COLUMN week TYPE TEXT; END IF;
       END $$""",
    # Supabase exposes every table in `public` through PostgREST, and its
    # default grants hand anon/authenticated full read/write. Without RLS that
    # made the whole subscriber table readable by anyone holding the anon key,
    # which is public by design. Nothing here talks to the Data API — the app
    # connects as the owning role, which bypasses RLS — so the fix is to deny
    # everything: RLS on with no policies, grants revoked, and default
    # privileges revoked so tables added later start locked too.
    # No format('%I'): every statement goes through psycopg2 with a params
    # tuple, which reads a bare % as a placeholder and fails the block.
    """DO $$
         DECLARE t text;
         BEGIN
           IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
           THEN RETURN; END IF;          -- plain Postgres, no Data API
           FOR t IN SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public' AND tableowner = current_user
           LOOP
             EXECUTE 'ALTER TABLE public.' || quote_ident(t)
                     || ' ENABLE ROW LEVEL SECURITY';
             EXECUTE 'REVOKE ALL ON public.' || quote_ident(t)
                     || ' FROM anon, authenticated';
           END LOOP;
           EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                   'REVOKE ALL ON TABLES FROM anon, authenticated';
         END $$""",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    days_per_week INTEGER NOT NULL,
    experience TEXT NOT NULL,
    include_run INTEGER NOT NULL DEFAULT 0,
    equipment TEXT NOT NULL DEFAULT 'full',  -- bodyweight | dumbbells | full
    plan TEXT NOT NULL DEFAULT 'monthly',           -- monthly | quarterly
    password_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',         -- pending | active | past_due | cancelled
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS sends (
    id INTEGER PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    week TEXT NOT NULL,                             -- '2026-W30'
    sent_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (subscriber_id, week)
);
-- What the subscriber actually did. The plan itself is reproducible from
-- (week, prefs), so a completion only needs to name the slot it fills.
CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    week TEXT NOT NULL,                             -- '2026-W30'
    day INTEGER NOT NULL,                           -- 1-based day in that week
    slug TEXT NOT NULL,
    sets INTEGER,                                   -- all three optional: a
    weight_kg REAL,                                 -- bare tick is a valid
    reps INTEGER,                                   -- log. reps are per set,
                                                    -- weight is per dumbbell
    done_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (subscriber_id, week, day, slug)
);
"""

# SQLite is dynamically typed, so the sends.week int -> text change needs no
# migration; only columns added after a database was created do.
MIGRATIONS_SQLITE = [
    "ALTER TABLE subscribers ADD COLUMN password_hash TEXT",
    "ALTER TABLE subscribers ADD COLUMN equipment TEXT NOT NULL DEFAULT 'full'",
    "ALTER TABLE subscribers ADD COLUMN api_key_hash TEXT",
    "ALTER TABLE completions ADD COLUMN sets INTEGER",
]


class _PgConn:
    """Thin wrapper so the sqlite3-style call sites work on Postgres too:
    translates `?` placeholders and returns dict rows."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        try:
            cur.execute(sql.replace("?", "%s"), params)
        except Exception:
            # Leave the connection usable for the next caller: without this a
            # failed statement poisons every later one on a reused connection.
            self._raw.rollback()
            raise
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()

    @property
    def closed(self) -> bool:
        return bool(self._raw.closed)


_local = threading.local()
_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema(conn) -> None:
    """Create tables and run migrations once per process, not per connection."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        if DATABASE_URL:
            for stmt in SCHEMA_PG.split(";"):
                if stmt.strip():
                    conn.execute(stmt)
            for stmt in MIGRATIONS_PG:
                try:
                    conn.execute(stmt)
                except Exception as e:      # already applied, or not permitted
                    print(f"migration skipped: {e}")
        else:
            conn.executescript(SCHEMA)
            for stmt in MIGRATIONS_SQLITE:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass                    # column already exists
        conn.commit()
        _schema_ready = True


def _new_connection():
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        raw = psycopg2.connect(
            DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        # Every call site commits per statement anyway; autocommit stops idle
        # transactions holding a snapshot open on a long-lived connection.
        raw.autocommit = True
        return _PgConn(raw)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _usable(conn) -> bool:
    try:
        conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def connect():
    """A connection for this thread, reused across requests.

    FastAPI runs the sync routes in a bounded thread pool, so this caps us at
    one database connection per worker thread instead of opening (and never
    closing) one per request.
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        if _usable(conn):
            return conn
        close(conn)                 # server hung up; replace it
        _local.conn = None
    conn = _new_connection()
    _ensure_schema(conn)
    _local.conn = conn
    return conn


def close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def upsert_subscriber(conn, email: str, days: int, experience: str,
                      include_run: bool, plan: str,
                      equipment: str = "full") -> int:
    conn.execute(
        """INSERT INTO subscribers (email, days_per_week, experience, include_run, plan, equipment)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(email) DO UPDATE SET
             days_per_week=excluded.days_per_week,
             experience=excluded.experience,
             include_run=excluded.include_run,
             plan=excluded.plan,
             equipment=excluded.equipment,
             updated_at=CURRENT_TIMESTAMP""",
        (email.lower().strip(), days, experience, int(include_run), plan,
         equipment))
    conn.commit()
    return conn.execute("SELECT id FROM subscribers WHERE email = ?",
                        (email.lower().strip(),)).fetchone()["id"]


def set_status(conn, email: str, status: str, customer_id: str | None = None,
               subscription_id: str | None = None) -> None:
    conn.execute(
        """UPDATE subscribers SET status = ?,
             stripe_customer_id = COALESCE(?, stripe_customer_id),
             stripe_subscription_id = COALESCE(?, stripe_subscription_id),
             updated_at = CURRENT_TIMESTAMP
           WHERE email = ?""",
        (status, customer_id, subscription_id, email.lower().strip()))
    conn.commit()


def active_subscribers(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM subscribers WHERE status = 'active' ORDER BY id").fetchall()


def get_by_email(conn, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM subscribers WHERE email = ?",
                        (email.lower().strip(),)).fetchone()


def sub_equipment(sub) -> str:
    """A subscriber's equipment, tolerating rows written before the column."""
    try:
        return sub["equipment"] or "full"
    except (KeyError, IndexError):
        return "full"


def week_key(year: int, week: int) -> str:
    """The idempotency key for one send: '2026-W30'.

    Includes the year — an ISO week number alone repeats every 52-53 weeks, so
    a bare week would make the send job skip everyone from year two onwards.
    """
    return f"{year}-W{week:02d}"


def record_send(conn, subscriber_id: int, week: str) -> bool:
    """Claim this subscriber-week. False if they already got this week's email."""
    try:
        conn.execute("INSERT INTO sends (subscriber_id, week) VALUES (?, ?)",
                     (subscriber_id, week))
        conn.commit()
        return True
    except Exception:  # unique violation (sqlite3 or psycopg2)
        if hasattr(conn, "rollback"):
            conn.rollback()
        return False


def unrecord_send(conn, subscriber_id: int, week: str) -> None:
    """Release a claim whose email failed to send, so a re-run retries it."""
    conn.execute("DELETE FROM sends WHERE subscriber_id = ? AND week = ?",
                 (subscriber_id, week))
    conn.commit()


# --- completions: what actually got done -----------------------------------

def set_completion(conn, subscriber_id: int, week: str, day: int, slug: str,
                   weight_kg: float | None = None,
                   reps: int | None = None,
                   sets: int | None = None) -> None:
    """Mark one exercise done, with optional load. Re-ticking updates it."""
    conn.execute(
        """INSERT INTO completions
             (subscriber_id, week, day, slug, sets, weight_kg, reps)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(subscriber_id, week, day, slug) DO UPDATE SET
             sets = excluded.sets,
             weight_kg = excluded.weight_kg,
             reps = excluded.reps,
             done_at = CURRENT_TIMESTAMP""",
        (subscriber_id, week, day, slug, sets, weight_kg, reps))
    conn.commit()


def clear_completion(conn, subscriber_id: int, week: str, day: int,
                     slug: str) -> None:
    conn.execute(
        "DELETE FROM completions WHERE subscriber_id = ? AND week = ? "
        "AND day = ? AND slug = ?", (subscriber_id, week, day, slug))
    conn.commit()


def completions_for_week(conn, subscriber_id: int, week: str) -> dict:
    """{'<day>|<slug>': row} for the plan page and the API's done-flags."""
    rows = conn.execute(
        "SELECT * FROM completions WHERE subscriber_id = ? AND week = ?",
        (subscriber_id, week)).fetchall()
    return {f"{r['day']}|{r['slug']}": dict(r) for r in rows}


def recent_completions(conn, subscriber_id: int, limit: int = 200) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM completions WHERE subscriber_id = ? "
        "ORDER BY id DESC LIMIT ?", (subscriber_id, limit)).fetchall()]


def last_logged(conn, subscriber_id: int, before_week: str | None = None) -> dict:
    """Most recent load per exercise — the 'last: 3 × 8 @ 60kg' hint.

    Week keys are zero-padded ('2026-W07'), so a string compare orders them
    chronologically and `before_week` cleanly excludes the week in progress.
    """
    rows = conn.execute(
        "SELECT slug, sets, weight_kg, reps, week FROM completions "
        "WHERE subscriber_id = ? AND (weight_kg IS NOT NULL "
        "OR reps IS NOT NULL OR sets IS NOT NULL) "
        "ORDER BY id DESC", (subscriber_id,)).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        if before_week and r["week"] >= before_week:
            continue
        out.setdefault(r["slug"], dict(r))
    return out


# --- API keys (for the plan page's own fetches and future apps) ------------

def hash_api_key(key: str) -> str:
    # Keys are 256 bits of randomness, so a plain digest is enough — there is
    # nothing to brute-force, unlike a user-chosen password.
    return hashlib.sha256(key.encode()).hexdigest()


def issue_api_key(conn, email: str) -> str:
    """Generate, store the hash, and return the key. Shown to the user once."""
    key = "ss_" + secrets.token_urlsafe(32)
    conn.execute(
        "UPDATE subscribers SET api_key_hash = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE email = ?", (hash_api_key(key), email.lower().strip()))
    conn.commit()
    return key


def get_by_api_key(conn, key: str):
    if not key:
        return None
    return conn.execute("SELECT * FROM subscribers WHERE api_key_hash = ?",
                        (hash_api_key(key),)).fetchone()


def has_api_key(sub) -> bool:
    try:
        return bool(sub["api_key_hash"])
    except (KeyError, IndexError):
        return False


# --- passwords (stdlib scrypt, no extra dependency) ------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.scrypt(password.encode(), salt=salt.encode(),
                       n=2**14, r=8, p=1).hex()
    return f"scrypt${salt}${h}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, salt, h = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=salt.encode(),
                                   n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(candidate, h)
    except Exception:
        return False


def set_password(conn, email: str, password: str) -> None:
    conn.execute(
        "UPDATE subscribers SET password_hash = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE email = ?", (hash_password(password), email.lower().strip()))
    conn.commit()


def update_prefs(conn, email: str, days: int, experience: str,
                 include_run: bool, equipment: str = "full") -> None:
    conn.execute(
        """UPDATE subscribers SET days_per_week = ?, experience = ?,
             include_run = ?, equipment = ?, updated_at = CURRENT_TIMESTAMP
           WHERE email = ?""",
        (days, experience, int(include_run), equipment, email.lower().strip()))
    conn.commit()


# --- signed, timestamped tokens (manage links in emails, login sessions) ---

def sign_email(email: str) -> str:
    raw = f"{email.lower().strip()}|{int(time.time())}"
    payload = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def sign_data(data: dict) -> str:
    """Signed, timestamped dict — used as the OAuth `state` parameter."""
    raw = json.dumps({**data, "_ts": int(time.time())}, separators=(",", ":"))
    payload = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_data(token: str, max_age: int | None = None) -> dict | None:
    try:
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(),
                            hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if max_age is not None and time.time() - int(data.get("_ts", 0)) > max_age:
            return None
        return data
    except Exception:
        return None


def verify_token(token: str, max_age: int | None = None) -> str | None:
    """Returns the email if the token is valid (and young enough), else None."""
    try:
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(),
                            hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        padded = payload + "=" * (-len(payload) % 4)
        email, ts = base64.urlsafe_b64decode(padded).decode().rsplit("|", 1)
        if max_age is not None and time.time() - int(ts) > max_age:
            return None
        return email
    except Exception:
        return None
