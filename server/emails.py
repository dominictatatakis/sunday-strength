"""Shared email rendering + the transactional emails (welcome, magic login)."""

from __future__ import annotations

import datetime
import os

from jinja2 import Environment, FileSystemLoader

import db
import engine
import mailer

APP_BASE_URL = (os.environ.get("APP_BASE_URL")
                or os.environ.get("RENDER_EXTERNAL_URL")  # set by Render
                or "http://localhost:8000")

_env = Environment(loader=FileSystemLoader(
    os.path.join(os.path.dirname(__file__), "templates")), autoescape=True)


def render_plan_email(sub, year: int, week: int, number: int,
                      intro: str | None = None,
                      subject: str | None = None) -> tuple[str, str, str]:
    """Returns (subject, html, text) for one subscriber's plan for ISO `week`
    of `year`, headed as their `number`th week of training."""
    equipment = db.sub_equipment(sub)
    plan = engine.generate_plan(week, sub["days_per_week"], sub["experience"],
                                bool(sub["include_run"]), equipment, year=year)
    plan["number"] = number
    # The abs circuit each day ends on, chosen as the app chooses it, so
    # someone who only reads the email still does it.
    for i, day in enumerate(plan["days"], start=1):
        day["circuit"] = engine.abs_circuit(
            week, i, sub["experience"], equipment,
            {ex["slug"] for ex in day["exercises"]})
    token = db.sign_email(sub["email"])
    manage_url = f"{APP_BASE_URL}/manage?token={token}"
    stop_url = f"{APP_BASE_URL}/email/off?token={token}"
    html = _env.get_template("email.html").render(
        plan=plan, base_url=APP_BASE_URL, manage_url=manage_url,
        stop_url=stop_url, intro=intro)
    text = engine.plan_text(
        plan, exercise_url=lambda s: f"{APP_BASE_URL}/exercise/{s}")
    if intro:
        text = f"{intro}\n\n{text}"
    text += (f"\n\nStop the Sunday email: {stop_url}"
             f"\nManage or cancel: {manage_url}")
    return subject or f"Your gym week — week {number}", html, text


def send_welcome(sub) -> bool:
    """Thank-you email with a sample plan, sent the moment someone joins.

    Uses the *current* week so they can start today; the Sunday job then takes
    over with next week's plan.
    """
    year, week = datetime.date.today().isocalendar()[:2]
    number = db.week_number(db.connect(), sub["id"], db.week_key(year, week))
    intro = ("Thanks for joining — great to have you. Here's a sample week so "
             "you can get started today. Your first full plan lands this "
             "Sunday evening, and every Sunday after that. You can change "
             f"your days or level any time at {APP_BASE_URL}/login.")
    subject, html, text = render_plan_email(
        sub, year, week, number, intro=intro,
        subject="Welcome to Sunday Strength — your first week is inside")
    return mailer.send(sub["email"], subject, html, text)
