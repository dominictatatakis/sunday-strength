"""Sunday Strength — signup site, Stripe billing, and exercise pages.

Run locally:  uvicorn app:app --reload --port 8000

Without Stripe keys configured the app runs in DEV MODE: signups are
activated immediately (no payment) so the full flow is testable end to end.
"""

from __future__ import annotations

import envfile  # noqa: F401  (must load .env before the imports below)

import datetime
import json
import os
import urllib.parse
from html import escape as html_escape

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

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
                    max_age=SESSION_MAX_AGE, samesite="lax",
                    secure=APP_BASE_URL.startswith("https"))
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
    if sub and sub["status"] == "active":
        # Already paying (e.g. signed up again through Google) — don't open a
        # second subscription, just sign them in.
        return _login_response(email, "/account")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": PRICE_IDS[sub["plan"]], "quantity": 1}],
        customer_email=email,
        success_url=f"{APP_BASE_URL}/success",
        cancel_url=f"{APP_BASE_URL}/?cancelled=1",
        metadata={"email": email},
    )
    return _login_response(email, session.url)


def _valid_prefs(days: int, experience: str, plan: str,
                 equipment: str = "full") -> bool:
    return (days in engine.SPLITS and experience in engine.LEVELS
            and plan in PRICE_IDS and equipment in engine.EQUIPMENT_RANK)


@app.post("/subscribe")
def subscribe(email: str = Form(...), password: str = Form(...),
              days: int = Form(...), experience: str = Form(...),
              include_run: bool = Form(False), plan: str = Form("monthly"),
              equipment: str = Form("full")):
    email = email.lower().strip()
    if "@" not in email or not _valid_prefs(days, experience, plan, equipment):
        raise HTTPException(400, "Invalid signup details.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    conn = db.connect()
    if db.get_by_email(conn, email):
        # Signing up over an existing account would reset its password with
        # nothing but the email address. Make them sign in instead.
        return RedirectResponse("/login?exists=1", status_code=303)
    db.upsert_subscriber(conn, email, days, experience, include_run, plan,
                         equipment)
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
                     plan: str = Form("monthly"),
                     equipment: str = Form("full")):
    """Step 3 'Continue with Google': carry the journey through OAuth state."""
    if not GOOGLE_ENABLED:
        raise HTTPException(404, "Google sign-in is not configured.")
    if not _valid_prefs(days, experience, plan, equipment):
        raise HTTPException(400, "Invalid signup details.")
    return _google_redirect({"signup": True, "days": days,
                             "experience": experience,
                             "run": bool(include_run), "plan": plan,
                             "equipment": equipment})


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
        # Google has proved they own this address, so updating an existing
        # row here is safe (unlike the email+password path).
        db.upsert_subscriber(conn, email, st["days"], st["experience"],
                             st["run"], st["plan"],
                             st.get("equipment", "full"))
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
def login_page(request: Request, error: int = 0, exists: int = 0):
    return templates.TemplateResponse(request, "login.html", {
        "error": bool(error), "exists": bool(exists),
        "google_enabled": GOOGLE_ENABLED})


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


def _account_context(sub, **extra) -> dict:
    return {"sub": sub, "levels": engine.LEVELS,
            "day_options": sorted(engine.SPLITS), "dev_mode": DEV_MODE,
            "active": "settings", "equipment_options": engine.EQUIPMENT,
            "equipment_names": engine.EQUIPMENT_NAMES,
            "equipment": db.sub_equipment(sub),
            "has_api_key": db.has_api_key(sub), **extra}


@app.get("/account", response_class=HTMLResponse)
def account(request: Request, saved: int = 0):
    email = _session_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "account.html",
                                      _account_context(sub, saved=bool(saved)))


@app.post("/account")
def account_update(request: Request, days: int = Form(...),
                   experience: str = Form(...),
                   include_run: bool = Form(False),
                   equipment: str = Form("full")):
    email = _session_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    if (days not in engine.SPLITS or experience not in engine.LEVELS
            or equipment not in engine.EQUIPMENT_RANK):
        raise HTTPException(400, "Invalid preferences.")
    conn = db.connect()
    db.update_prefs(conn, email, days, experience, include_run, equipment)
    return RedirectResponse("/account?saved=1", status_code=303)


@app.post("/account/api-key", response_class=HTMLResponse)
def account_api_key(request: Request):
    """Issue (or replace) the API key. Only the hash is stored, so this is the
    one and only time the key itself is shown."""
    email = _session_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    key = db.issue_api_key(conn, email)
    return templates.TemplateResponse(
        request, "account.html",
        _account_context(db.get_by_email(conn, email), new_api_key=key))


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


def _manage_sub(token: str):
    email = db.verify_token(token, max_age=MANAGE_LINK_MAX_AGE)
    if not email:
        raise HTTPException(403, "Invalid or expired link.")
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        raise HTTPException(404, "No subscription found.")
    return conn, email, sub


@app.get("/manage")
def manage(token: str):
    """Signed link from the weekly email -> Stripe billing portal."""
    conn, email, sub = _manage_sub(token)
    if DEV_MODE or not sub["stripe_customer_id"]:
        # Confirm on a POST: mail clients and link scanners follow GETs, and
        # a prefetch must never cancel someone's subscription.
        return HTMLResponse(
            '<p>Stop your Sunday emails for '
            f'{html_escape(email)}?</p>'
            '<form method="post" action="/manage/cancel">'
            f'<input type="hidden" name="token" value="{html_escape(token)}">'
            '<button type="submit">Yes, cancel my subscription</button>'
            '</form><p><a href="/">No, keep them coming</a></p>')
    session = stripe.billing_portal.Session.create(
        customer=sub["stripe_customer_id"], return_url=APP_BASE_URL)
    return RedirectResponse(session.url, status_code=303)


@app.post("/manage/cancel")
def manage_cancel(token: str = Form(...)):
    conn, email, sub = _manage_sub(token)
    if not (DEV_MODE or not sub["stripe_customer_id"]):
        raise HTTPException(400, "Cancel from the billing portal instead.")
    db.set_status(conn, email, "cancelled")
    return HTMLResponse("<p>Cancelled — you won't receive further emails.</p>")


def _current_sub(request: Request):
    email = _session_email(request)
    if not email:
        return None
    return db.get_by_email(db.connect(), email)


def _plan_for(sub, week: int) -> dict:
    return engine.generate_plan(week, sub["days_per_week"], sub["experience"],
                                bool(sub["include_run"]), db.sub_equipment(sub))


def _last_label(log: dict) -> str:
    """'3 × 8 @ 60kg' — reading as sets × reps at load, dropping what's missing.

    Rows logged before the sets column existed have sets NULL and still read
    correctly as '8 @ 60kg'.
    """
    sets, reps, weight = log.get("sets"), log.get("reps"), log.get("weight_kg")
    volume = f"{sets} × {reps}" if sets and reps else (
        f"{sets} sets" if sets else (f"{reps} reps" if reps else ""))
    if weight is None:
        return volume
    kg = f"{weight:g}kg"
    return f"{volume} @ {kg}" if volume else kg


def _this_week_plan(sub) -> tuple[int, str, dict]:
    """(ISO week, storage key, plan) for the week the subscriber is in now."""
    year, week = datetime.date.today().isocalendar()[:2]
    return week, db.week_key(year, week), _plan_for(sub, week)


@app.get("/exercises", response_class=HTMLResponse)
def exercise_library(request: Request):
    """Members-only exercise library."""
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    week, _key, plan = _this_week_plan(sub)
    return templates.TemplateResponse(request, "exercises.html", {
        "exercises": engine.flat_library(), "parts": engine.PART_NAMES,
        "part_order": engine.PART_ORDER, "levels": engine.LEVELS,
        "member": True, "sub": sub, "default_level": sub["experience"],
        "week": week, "active": "exercises",
        "equipment_options": engine.EQUIPMENT,
        "equipment_names": engine.EQUIPMENT_NAMES,
        "default_equipment": db.sub_equipment(sub),
        "this_week": {ex["slug"] for day in plan["days"]
                      for ex in day["exercises"]},
    })


@app.get("/account/exercises")
def my_exercises():
    return RedirectResponse("/exercises", status_code=303)


def _opt_number(raw: str, cast, label: str):
    """Form number fields arrive as strings, and empty means 'not recorded'."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return cast(raw)
    except ValueError:
        raise HTTPException(400, f"{label} must be a number.")


@app.post("/account/plan/log")
def log_exercise(request: Request, week: str = Form(...), day: int = Form(...),
                 slug: str = Form(...), done: bool = Form(False),
                 weight_kg: str = Form(""), reps: str = Form(""),
                 sets: str = Form("")):
    """No-JavaScript fallback for the plan page's tick boxes.

    Each exercise is a real form posting here; the page's JS intercepts the
    submit and calls the JSON API instead. Same validation either way — this
    goes through _apply_completion too.
    """
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    _apply_completion(db.connect(), sub, week, day, slug, done,
                      _opt_number(weight_kg, float, "Weight"),
                      _opt_number(reps, int, "Reps"),
                      _opt_number(sets, int, "Sets"))
    return RedirectResponse(f"/account/plan?saved={urllib.parse.quote(slug)}"
                            f"#day{day}", status_code=303)


@app.get("/account/plan", response_class=HTMLResponse)
def my_plan(request: Request, saved: str = ""):
    """This week's plan, in the browser — and where exercises get ticked off."""
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    week, key, plan = _this_week_plan(sub)
    # The sets box starts on what the plan asked for ('3 x 10-12' -> 3), so it
    # only needs touching on the days you deviate.
    for day in plan["days"]:
        for ex in day["exercises"]:
            ex["sets_n"] = engine.prescribed_sets(ex["sets"])
    conn = db.connect()
    last = {slug: _last_label(log)
            for slug, log in db.last_logged(conn, sub["id"],
                                            before_week=key).items()}
    return templates.TemplateResponse(request, "plan.html", {
        "sub": sub, "plan": plan, "week": week, "week_key": key,
        "active": "plan", "saved": saved,
        "logged": db.completions_for_week(conn, sub["id"], key),
        "last": {k: v for k, v in last.items() if v},
    })


@app.get("/exercise/{slug}", response_class=HTMLResponse)
def exercise_page(request: Request, slug: str):
    if slug not in engine.all_slugs():
        raise HTTPException(404, "Unknown exercise.")
    meta = EXDB.get(slug, {})
    name = meta.get("name") or engine.SLUG_NAMES.get(slug) or slug.replace("-", " ").capitalize()
    yt = ("https://www.youtube.com/results?search_query="
          + urllib.parse.quote_plus(f"{name} form how to"))
    # Swaps are filtered to the signed-in member's kit; visitors see them all.
    sub = _current_sub(request)
    equipment = db.sub_equipment(sub) if sub else "full"
    return templates.TemplateResponse(request, "exercise.html", {
        "name": name,
        "instructions": meta.get("instructions", []),
        "images": meta.get("images", []),
        "youtube_url": yt,
        "alternatives": engine.alternatives_for(slug, equipment, limit=4),
        "equipment": engine.SLUG_EQUIPMENT.get(slug, "full"),
        "equipment_names": engine.EQUIPMENT_NAMES,
    })


# --- JSON API ---------------------------------------------------------------
# These endpoints back the tick boxes on the plan page *and* anything else you
# point at them later (a phone app, a script, a Shortcut). Two ways in:
#
#   Authorization: Bearer ss_...   an API key from /account
#   the ss_session cookie          the plan page's own fetch() calls
#
# Keeping the browser on the same endpoints means the API can't quietly rot —
# if ticking a box works, the API works. The session cookie is samesite=lax
# and these take a JSON body, so a cross-site form can't drive them.

class CompletionIn(BaseModel):
    slug: str
    day: int                                # 1-based day within the week
    week: str | None = None                 # '2026-W30'; defaults to now
    sets: int | None = None                 # sets done
    reps: int | None = None                 # per set, not the total
    weight_kg: float | None = None          # per dumbbell, not the pair
    done: bool = True                       # false deletes the entry


def _api_sub(request: Request):
    auth = request.headers.get("authorization", "")
    conn = db.connect()
    if auth.lower().startswith("bearer "):
        return conn, db.get_by_api_key(conn, auth[7:].strip())
    email = _session_email(request)
    return conn, (db.get_by_email(conn, email) if email else None)


def _require_sub(request: Request):
    conn, sub = _api_sub(request)
    if not sub:
        raise HTTPException(401, "Sign in, or send a valid API key.")
    return conn, sub


def _week_from_key(key: str) -> tuple[int, int]:
    try:
        year, week = key.split("-W")
        return int(year), int(week)
    except (ValueError, AttributeError):
        raise HTTPException(400, "week must look like '2026-W30'.")


@app.get("/api/v1/me")
def api_me(request: Request):
    _conn, sub = _require_sub(request)
    return {"email": sub["email"], "status": sub["status"],
            "days_per_week": sub["days_per_week"],
            "experience": sub["experience"],
            "equipment": db.sub_equipment(sub),
            "include_run": bool(sub["include_run"])}


@app.get("/api/v1/plan")
def api_plan(request: Request, week: str | None = None):
    """This week's plan (or ?week=2026-W30) with what's already been done."""
    conn, sub = _require_sub(request)
    if week:
        year, iso_week = _week_from_key(week)
    else:
        year, iso_week = datetime.date.today().isocalendar()[:2]
    key = db.week_key(year, iso_week)
    plan = _plan_for(sub, iso_week)
    logged = db.completions_for_week(conn, sub["id"], key)
    for i, day in enumerate(plan["days"], start=1):
        day["day"] = i
        for ex in day["exercises"]:
            log = logged.get(f"{i}|{ex['slug']}")
            ex["done"] = bool(log)
            # .get: rows written before the sets column existed lack the key.
            ex["sets_done"] = log.get("sets") if log else None
            ex["weight_kg"] = log["weight_kg"] if log else None
            ex["reps"] = log["reps"] if log else None
    plan["week_key"] = key
    return plan


def _apply_completion(conn, sub, week: str | None, day: int, slug: str,
                      done: bool, weight_kg: float | None,
                      reps: int | None, sets: int | None = None) -> str:
    """Validate one tick against that week's plan, then write or delete it.

    Shared by the JSON API and the plain-form fallback so both paths behave
    identically. Returns the week key that was written.
    """
    if week:
        year, iso_week = _week_from_key(week)
    else:
        year, iso_week = datetime.date.today().isocalendar()[:2]
    key = db.week_key(year, iso_week)

    # Only accept slots that exist in that week's plan, so the table can't
    # fill up with exercises the subscriber was never given.
    days = _plan_for(sub, iso_week)["days"]
    if not 1 <= day <= len(days):
        raise HTTPException(400, f"That week has days 1-{len(days)}.")
    if slug not in {ex["slug"] for ex in days[day - 1]["exercises"]}:
        raise HTTPException(400, "That exercise isn't in that day's plan.")

    if done:
        db.set_completion(conn, sub["id"], key, day, slug, weight_kg, reps,
                          sets)
    else:
        db.clear_completion(conn, sub["id"], key, day, slug)
    return key


@app.post("/api/v1/completions")
def api_set_completion(request: Request, body: CompletionIn):
    conn, sub = _require_sub(request)
    key = _apply_completion(conn, sub, body.week, body.day, body.slug,
                            body.done, body.weight_kg, body.reps, body.sets)
    return {"ok": True, "week": key, "day": body.day, "slug": body.slug,
            "done": body.done, "sets": body.sets, "reps": body.reps,
            "weight_kg": body.weight_kg}


@app.get("/api/v1/completions")
def api_completions(request: Request, limit: int = 200):
    """Raw history, newest first — for progress charts and exports."""
    conn, sub = _require_sub(request)
    return {"completions": db.recent_completions(
        conn, sub["id"], max(1, min(limit, 1000)))}


@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})


@app.get("/health")
def health():
    """For uptime monitors: verifies the app AND its database connection."""
    try:
        conn = db.connect()
        conn.execute("SELECT 1").fetchone()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(503, f"database unreachable: {e}")


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
