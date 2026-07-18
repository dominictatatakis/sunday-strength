"""Sunday Strength — signup site, Stripe billing, and exercise pages.

Run locally:  uvicorn app:app --reload --port 8000

Without Stripe keys configured the app runs in DEV MODE: signups are
activated immediately (no payment) so the full flow is testable end to end.
"""

from __future__ import annotations

import envfile  # noqa: F401  (must load .env before the imports below)

import json
import os
import urllib.parse

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db
import emails
import engine

BASE_DIR = os.path.dirname(__file__)
MANAGE_LINK_MAX_AGE = 60 * 60 * 24 * 180   # links in emails: 180 days
LOGIN_LINK_MAX_AGE = 60 * 30               # magic sign-in links: 30 min
SESSION_MAX_AGE = 60 * 60 * 24 * 30        # login cookie: 30 days
SESSION_COOKIE = "ss_session"
OAUTH_STATE_MAX_AGE = 60 * 15              # Google round-trip: 15 min

# Google SSO — optional; the buttons appear once these are set.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
APP_BASE_URL = (os.environ.get("APP_BASE_URL")
                or os.environ.get("RENDER_EXTERNAL_URL")  # set by Render
                or "http://localhost:8000")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PRICE_IDS = {
    "monthly": os.environ.get("STRIPE_PRICE_MONTHLY", ""),
    "quarterly": os.environ.get("STRIPE_PRICE_QUARTERLY", ""),
}
DEV_MODE = not STRIPE_SECRET_KEY

if STRIPE_SECRET_KEY:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="Sunday Strength")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")),
          name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Exercise media fetched by scripts/fetch_exercise_media.py (may not exist yet)
_EXDB_PATH = os.path.join(BASE_DIR, "static", "exdb.json")
EXDB: dict = {}
if os.path.exists(_EXDB_PATH):
    with open(_EXDB_PATH) as f:
        EXDB = json.load(f)


def exercise_url(slug: str) -> str:
    return f"{APP_BASE_URL}/exercise/{slug}"


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, sso: str = ""):
    return templates.TemplateResponse(request, "landing.html", {
        "dev_mode": DEV_MODE, "google_enabled": GOOGLE_ENABLED,
        "sso_error": sso == "failed",
    })


def _send_welcome_safe(conn, email: str) -> None:
    """Welcome email with a sample plan; never lets email failure break signup."""
    try:
        sub = db.get_by_email(conn, email)
        if sub:
            emails.send_welcome(sub)
    except Exception as e:
        print(f"welcome email failed for {email}: {e}")


def _session_email(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    return db.verify_token(token, max_age=SESSION_MAX_AGE) if token else None


def _login_response(email: str, target: str) -> RedirectResponse:
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(SESSION_COOKIE, db.sign_email(email), httponly=True,
                    max_age=SESSION_MAX_AGE, samesite="lax")
    return resp


def _finish_signup(conn, email: str) -> RedirectResponse:
    """After the account exists: take payment (or activate in dev mode).

    Returns a redirect with the login cookie set, so the subscriber lands
    signed in when they come back from Stripe.
    """
    if DEV_MODE:
        db.set_status(conn, email, "active")
        _send_welcome_safe(conn, email)
        return _login_response(email, "/success?dev=1")
    sub = db.get_by_email(conn, email)
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": PRICE_IDS[sub["plan"]], "quantity": 1}],
        customer_email=email,
        success_url=f"{APP_BASE_URL}/success",
        cancel_url=f"{APP_BASE_URL}/?cancelled=1",
        metadata={"email": email},
    )
    return _login_response(email, session.url)


def _valid_prefs(days: int, experience: str, plan: str) -> bool:
    return (days in engine.SPLITS and experience in engine.LEVELS
            and plan in PRICE_IDS)


@app.post("/subscribe")
def subscribe(email: str = Form(...), password: str = Form(...),
              days: int = Form(...), experience: str = Form(...),
              include_run: bool = Form(False), plan: str = Form("monthly")):
    email = email.lower().strip()
    if "@" not in email or not _valid_prefs(days, experience, plan):
        raise HTTPException(400, "Invalid signup details.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    conn = db.connect()
    db.upsert_subscriber(conn, email, days, experience, include_run, plan)
    db.set_password(conn, email, password)
    return _finish_signup(conn, email)


# --- Google SSO -------------------------------------------------------------

def _google_redirect(state: dict) -> RedirectResponse:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{APP_BASE_URL}/auth/google",
        "response_type": "code",
        "scope": "openid email",
        "state": db.sign_data(state),
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}",
                            status_code=303)


@app.post("/subscribe/google")
def subscribe_google(days: int = Form(...), experience: str = Form(...),
                     include_run: bool = Form(False),
                     plan: str = Form("monthly")):
    """Step 3 'Continue with Google': carry the journey through OAuth state."""
    if not GOOGLE_ENABLED:
        raise HTTPException(404, "Google sign-in is not configured.")
    if not _valid_prefs(days, experience, plan):
        raise HTTPException(400, "Invalid signup details.")
    return _google_redirect({"signup": True, "days": days,
                             "experience": experience,
                             "run": bool(include_run), "plan": plan})


@app.get("/login/google")
def login_google():
    if not GOOGLE_ENABLED:
        raise HTTPException(404, "Google sign-in is not configured.")
    return _google_redirect({"login": True})


@app.get("/auth/google")
def google_callback(code: str = "", state: str = "", error: str = ""):
    if not GOOGLE_ENABLED:
        raise HTTPException(404, "Google sign-in is not configured.")
    st = db.verify_data(state, max_age=OAUTH_STATE_MAX_AGE)
    if error or not code or st is None:
        return RedirectResponse("/?sso=failed", status_code=303)

    token = httpx.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": f"{APP_BASE_URL}/auth/google",
        "grant_type": "authorization_code",
    }, timeout=20).json()
    if "access_token" not in token:
        return RedirectResponse("/?sso=failed", status_code=303)
    info = httpx.get(GOOGLE_USERINFO_URL, headers={
        "Authorization": f"Bearer {token['access_token']}"}, timeout=20).json()
    email = (info.get("email") or "").lower().strip()
    if not email or not info.get("email_verified"):
        return RedirectResponse("/?sso=failed", status_code=303)

    conn = db.connect()
    if st.get("signup"):
        db.upsert_subscriber(conn, email, st["days"], st["experience"],
                             st["run"], st["plan"])
        return _finish_signup(conn, email)
    # plain login
    if not db.get_by_email(conn, email):
        return RedirectResponse("/?sso=failed", status_code=303)
    return _login_response(email, "/account")


@app.get("/success", response_class=HTMLResponse)
def success(request: Request, dev: int = 0):
    return templates.TemplateResponse(request, "success.html",
                                      {"dev_mode": bool(dev)})


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if DEV_MODE:
        raise HTTPException(400, "Stripe not configured.")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Bad signature.")

    conn = db.connect()
    obj = event["data"]["object"]
    if event["type"] == "checkout.session.completed":
        email = (obj.get("metadata") or {}).get("email") or obj.get("customer_email")
        if email:
            db.set_status(conn, email, "active",
                          customer_id=obj.get("customer"),
                          subscription_id=obj.get("subscription"))
            _send_welcome_safe(conn, email)
    elif event["type"] == "customer.subscription.deleted":
        email = _email_for_customer(obj.get("customer"))
        if email:
            db.set_status(conn, email, "cancelled")
    elif event["type"] == "invoice.payment_failed":
        email = _email_for_customer(obj.get("customer"))
        if email:
            db.set_status(conn, email, "past_due")
    return {"ok": True}


def _email_for_customer(customer_id: str | None) -> str | None:
    if not customer_id:
        return None
    conn = db.connect()
    row = conn.execute(
        "SELECT email FROM subscribers WHERE stripe_customer_id = ?",
        (customer_id,)).fetchone()
    return row["email"] if row else None


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: int = 0):
    return templates.TemplateResponse(request, "login.html", {
        "error": bool(error), "google_enabled": GOOGLE_ENABLED})


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)):
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub or not db.check_password(password, sub["password_hash"]):
        return RedirectResponse("/login?error=1", status_code=303)
    return _login_response(email, "/account")


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/account", response_class=HTMLResponse)
def account(request: Request, saved: int = 0):
    email = _session_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "account.html", {
        "sub": sub, "saved": bool(saved), "levels": engine.LEVELS,
        "day_options": sorted(engine.SPLITS), "dev_mode": DEV_MODE,
        "active": "settings",
    })


@app.post("/account")
def account_update(request: Request, days: int = Form(...),
                   experience: str = Form(...),
                   include_run: bool = Form(False)):
    email = _session_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    if days not in engine.SPLITS or experience not in engine.LEVELS:
        raise HTTPException(400, "Invalid preferences.")
    conn = db.connect()
    db.update_prefs(conn, email, days, experience, include_run)
    return RedirectResponse("/account?saved=1", status_code=303)


@app.get("/billing")
def billing(request: Request):
    """Logged-in shortcut to the Stripe billing portal."""
    email = _session_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    if DEV_MODE or not sub["stripe_customer_id"]:
        return HTMLResponse("<p>Dev mode — no billing to manage. "
                            '<a href="/account">Back</a></p>')
    session = stripe.billing_portal.Session.create(
        customer=sub["stripe_customer_id"],
        return_url=f"{APP_BASE_URL}/account")
    return RedirectResponse(session.url, status_code=303)


@app.get("/manage")
def manage(token: str):
    """Signed link from the weekly email -> Stripe billing portal."""
    email = db.verify_token(token, max_age=MANAGE_LINK_MAX_AGE)
    if not email:
        raise HTTPException(403, "Invalid or expired link.")
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        raise HTTPException(404, "No subscription found.")
    if DEV_MODE or not sub["stripe_customer_id"]:
        db.set_status(conn, email, "cancelled")
        return HTMLResponse("<p>Subscription cancelled (dev mode). "
                            "You won't receive further emails.</p>")
    session = stripe.billing_portal.Session.create(
        customer=sub["stripe_customer_id"], return_url=APP_BASE_URL)
    return RedirectResponse(session.url, status_code=303)


def _current_sub(request: Request):
    email = _session_email(request)
    if not email:
        return None
    return db.get_by_email(db.connect(), email)


def _this_week_plan(sub) -> tuple[int, dict]:
    import datetime
    week = datetime.date.today().isocalendar()[1]
    return week, engine.generate_plan(week, sub["days_per_week"],
                                      sub["experience"],
                                      bool(sub["include_run"]))


@app.get("/exercises", response_class=HTMLResponse)
def exercise_library(request: Request):
    """Members-only exercise library."""
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    week, plan = _this_week_plan(sub)
    return templates.TemplateResponse(request, "exercises.html", {
        "exercises": engine.flat_library(), "parts": engine.PART_NAMES,
        "part_order": engine.PART_ORDER, "levels": engine.LEVELS,
        "member": True, "sub": sub, "default_level": sub["experience"],
        "week": week, "active": "exercises",
        "this_week": {ex["slug"] for day in plan["days"]
                      for ex in day["exercises"]},
    })


@app.get("/account/exercises")
def my_exercises():
    return RedirectResponse("/exercises", status_code=303)


@app.get("/account/plan", response_class=HTMLResponse)
def my_plan(request: Request):
    """This week's plan, in the browser."""
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    week, plan = _this_week_plan(sub)
    return templates.TemplateResponse(request, "plan.html", {
        "sub": sub, "plan": plan, "week": week, "active": "plan"})


@app.get("/exercise/{slug}", response_class=HTMLResponse)
def exercise_page(request: Request, slug: str):
    if slug not in engine.all_slugs():
        raise HTTPException(404, "Unknown exercise.")
    meta = EXDB.get(slug, {})
    name = meta.get("name") or slug.replace("-", " ").capitalize()
    yt = ("https://www.youtube.com/results?search_query="
          + urllib.parse.quote_plus(f"{name} form how to"))
    return templates.TemplateResponse(request, "exercise.html", {
        "name": name,
        "instructions": meta.get("instructions", []),
        "images": meta.get("images", []),
        "youtube_url": yt,
    })


@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})


@app.post("/admin/send-weekly")
def admin_send_weekly(request: Request):
    """Triggered by the Sunday GitHub Action. Idempotent, so a retry after a
    partial failure only emails whoever hasn't been sent this week's plan."""
    import hmac as _hmac
    token = request.headers.get("x-admin-token", "")
    if not ADMIN_TOKEN or not _hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(403, "Bad admin token.")
    import send_weekly
    return send_weekly.run()
