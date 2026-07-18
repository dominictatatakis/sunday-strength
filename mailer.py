"""Email sending. Three modes, checked in order:

1. Gmail SMTP  — set GMAIL_USER + GMAIL_APP_PASSWORD. Sends from your own
   Gmail to ANYONE (~500/day cap). Good for the beta before a domain exists.
   App password: Google Account -> Security -> 2-Step Verification ->
   App passwords.
2. Resend      — set RESEND_API_KEY (+ EMAIL_FROM). Free 3,000/month, but
   until a domain is verified it only delivers to the account owner.
3. Dry run     — nothing set: prints the email to stdout.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Sunday Strength <plan@example.com>")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


def _send_gmail(to: str, subject: str, html: str, text: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Sunday Strength <{GMAIL_USER}>"
    msg["To"] = to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"Gmail SMTP error for {to}: {e}")
        return False


def send(to: str, subject: str, html: str, text: str) -> bool:
    if GMAIL_USER and GMAIL_APP_PASSWORD:
        return _send_gmail(to, subject, html, text)
    if not RESEND_API_KEY:
        print(f"--- DRY RUN (no email configured): would send to {to} ---")
        print(f"Subject: {subject}")
        print(text)
        print("--- end dry run ---")
        return True
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": EMAIL_FROM, "to": [to], "subject": subject,
              "html": html, "text": text},
        timeout=30,
    )
    if resp.status_code >= 400:
        print(f"Resend error for {to}: {resp.status_code} {resp.text}")
        return False
    return True
