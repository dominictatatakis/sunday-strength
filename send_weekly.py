"""Weekly send job — run every Sunday evening (cron/launchd/GitHub Action).

  python3 send_weekly.py                # send to all active subscribers
  python3 send_weekly.py --dry-run      # print instead of sending
  python3 send_weekly.py --to a@b.com   # send only to one subscriber (testing)
  python3 send_weekly.py --week 30      # override the ISO week

The plan sent is for the week *starting the next day* (Sunday email covers the
Monday-onwards week), matching the original personal setup. Sends are recorded
per (subscriber, week) so a re-run after a crash never double-sends.
"""

from __future__ import annotations

import envfile  # noqa: F401  (must load .env before the imports below)

import argparse
import datetime

import db
import emails
import mailer


def run(week: int | None = None, to: str | None = None,
        dry_run: bool = False) -> dict:
    """Send this week's plan to every active subscriber. Idempotent per
    (subscriber, week). Returns stats — used by the CLI below and by the
    /admin/send-weekly endpoint that the Sunday GitHub Action hits."""
    if week is None:
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        week = tomorrow.isocalendar()[1]

    conn = db.connect()
    subs = db.active_subscribers(conn)
    if to:
        subs = [s for s in subs if s["email"] == to.lower().strip()]

    sent = skipped = failed = 0
    for sub in subs:
        subject, html, text = emails.render_plan_email(sub, week)
        if dry_run:
            print(f"--- {sub['email']} ({sub['days_per_week']}d, "
                  f"{sub['experience']}, run={bool(sub['include_run'])}) ---")
            print(text)
            print()
            continue
        if not db.record_send(conn, sub["id"], week):
            skipped += 1
            continue
        if mailer.send(sub["email"], subject, html, text):
            sent += 1
        else:
            failed += 1

    return {"week": week, "active": len(subs), "sent": sent,
            "skipped": skipped, "failed": failed}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--to", help="send only to this subscriber email")
    p.add_argument("--week", type=int, default=None)
    args = p.parse_args()
    stats = run(week=args.week, to=args.to, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Week {stats['week']}: sent={stats['sent']} "
              f"skipped(already sent)={stats['skipped']} "
              f"failed={stats['failed']} of {stats['active']} active subscribers")


if __name__ == "__main__":
    main()
