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


def render_plan_email(sub, week: int, intro: str | None = None,
                      subject: str | None = None) -> tuple[str, str, str]:
    """Returns (subject, html, text) for one subscriber's weekly plan."""
    plan = engine.generate_plan(week, sub["days_per_week"], sub["experience"],
                                bool(sub["include_run"]))
    manage_url = f"{APP_BASE_URL}/manage?token={db.sign_email(sub['email'])}"
    html = _env.get_template("email.html").render(
        plan=plan, base_url=APP_BASE_URL, manage_url=manage_url, intro=intro)
    text = engine.plan_text(
        plan, exercise_url=lambda s: f"{APP_BASE_URL}/exercise/{s}")
    if intro:
        text = f"{intro}\n\n{text}"
    text += f"\n\nManage or cancel: {manage_url}"
    return subject or f"Your gym week — week {week}", html, text


def send_welcome(sub) -> bool:
    """Thank-you email with a sample plan, sent the moment someone joins.

    Uses the *current* week so they can start today; the Sunday job then takes
    over with next week's plan.
    """
    week = datetime.date.today().isocalendar()[1]
    intro = ("Thanks for joining — great to have you. Here's a sample week so "
             "you can get started today. Your first full plan lands this "
             "Sunday evening, and every Sunday after that. You can change "
             f"your days or level any time at {APP_BASE_URL}/login.")
    subject, html, text = render_plan_email(
        sub, week, intro=intro,
        subject="Welcome to Sunday Strength — your first week is inside")
    return mailer.send(sub["email"], subject, html, text)
