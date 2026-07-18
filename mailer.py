"""Email sending via Resend (free tier: 3,000 emails/month, 100/day).

Set RESEND_API_KEY and EMAIL_FROM in the environment. Without a key, send()
prints the email to stdout instead (dry-run), so the whole pipeline is
testable before signing up for anything.
"""

from __future__ import annotations

import os

import httpx

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Sunday Strength <plan@example.com>")


def send(to: str, subject: str, html: str, text: str) -> bool:
    if not RESEND_API_KEY:
        print(f"--- DRY RUN (no RESEND_API_KEY): would send to {to} ---")
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
