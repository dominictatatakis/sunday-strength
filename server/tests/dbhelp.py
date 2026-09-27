"""A throwaway SQLite database per test. Never gymdigest.db."""
import os
import tempfile

# Before db is imported anywhere: it reads these at import time, and the app
# would otherwise open the real database and the live mail providers.
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ["DATABASE_URL"] = ""
for var in ("BREVO_API_KEY", "RESEND_API_KEY", "GMAIL_USER", "STRIPE_SECRET_KEY"):
    os.environ[var] = ""
os.environ.setdefault("SECRET_KEY", "test-secret")

import db  # noqa: E402


def fresh_db():
    """Point db at a new empty file and return a connection to it."""
    conn = getattr(db._local, "conn", None)
    if conn is not None:
        db.close(conn)
        db._local.conn = None
    db.DB_PATH = os.path.join(tempfile.mkdtemp(), "test.db")
    db._schema_ready = False
    return db.connect()
