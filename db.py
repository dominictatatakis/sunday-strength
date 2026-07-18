"""SQLite storage + signed tokens for manage/unsubscribe links."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "gymdigest.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")  # Postgres in production
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS subscribers (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    days_per_week INTEGER NOT NULL,
    experience TEXT NOT NULL,
    include_run INTEGER NOT NULL DEFAULT 0,
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
    week INTEGER NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subscriber_id, week)
);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    days_per_week INTEGER NOT NULL,
    experience TEXT NOT NULL,
    include_run INTEGER NOT NULL DEFAULT 0,
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
    week INTEGER NOT NULL,
    sent_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (subscriber_id, week)
);
"""


class _PgConn:
    """Thin wrapper so the sqlite3-style call sites work on Postgres too:
    translates `?` placeholders and returns dict rows."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()


def connect():
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        raw = psycopg2.connect(
            DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn = _PgConn(raw)
        for stmt in SCHEMA_PG.split(";"):
            if stmt.strip():
                conn.execute(stmt)
        conn.commit()
        return conn

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:  # migration for DBs created before accounts existed
        conn.execute("ALTER TABLE subscribers ADD COLUMN password_hash TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    return conn


def upsert_subscriber(conn, email: str, days: int, experience: str,
                      include_run: bool, plan: str) -> int:
    conn.execute(
        """INSERT INTO subscribers (email, days_per_week, experience, include_run, plan)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(email) DO UPDATE SET
             days_per_week=excluded.days_per_week,
             experience=excluded.experience,
             include_run=excluded.include_run,
             plan=excluded.plan,
             updated_at=CURRENT_TIMESTAMP""",
        (email.lower().strip(), days, experience, int(include_run), plan))
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


def record_send(conn, subscriber_id: int, week: int) -> bool:
    """Returns False if this subscriber already got this week's email."""
    try:
        conn.execute("INSERT INTO sends (subscriber_id, week) VALUES (?, ?)",
                     (subscriber_id, week))
        conn.commit()
        return True
    except Exception:  # unique violation (sqlite3 or psycopg2)
        if hasattr(conn, "rollback"):
            conn.rollback()
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
                 include_run: bool) -> None:
    conn.execute(
        """UPDATE subscribers SET days_per_week = ?, experience = ?,
             include_run = ?, updated_at = CURRENT_TIMESTAMP
           WHERE email = ?""",
        (days, experience, int(include_run), email.lower().strip()))
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
