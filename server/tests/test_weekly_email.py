"""Which week of training it is, and turning the Sunday email off."""
import unittest
from unittest import mock

from tests.dbhelp import db, fresh_db
from tests.test_day_plans import ApiBase, EMAIL

import emails  # noqa: E402
import send_weekly  # noqa: E402


class WeekNumber(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db()
        self.sid = db.upsert_subscriber(self.conn, EMAIL, 3, "intermediate",
                                        False, "monthly", "full")

    def log(self, week, sid=None):
        db.set_completion(self.conn, sid or self.sid, week, 1, "bench-press")

    def test_the_first_week_is_week_1(self):
        self.assertEqual(db.week_number(self.conn, self.sid, "2026-W41"), 1)

    def test_counts_earlier_weeks_with_anything_logged(self):
        self.log("2026-W30")
        self.log("2026-W30")        # the same week twice counts once
        self.log("2026-W35")
        self.assertEqual(db.week_number(self.conn, self.sid, "2026-W41"), 3)

    def test_neither_this_week_nor_later_ones_count(self):
        self.log("2026-W41")
        self.log("2026-W45")
        self.assertEqual(db.week_number(self.conn, self.sid, "2026-W41"), 1)

    def test_runs_on_into_the_next_year(self):
        self.log("2026-W52")
        self.assertEqual(db.week_number(self.conn, self.sid, "2027-W01"), 2)

    def test_someone_elses_log_does_not_count(self):
        other = db.upsert_subscriber(self.conn, "x@example.com", 3,
                                     "intermediate", False, "monthly", "full")
        self.log("2026-W30", sid=other)
        self.assertEqual(db.week_number(self.conn, self.sid, "2026-W41"), 1)


class WeekNumberShown(ApiBase):
    def test_the_api_serves_it_beside_the_iso_week(self):
        db.set_completion(self.conn, self.sid, "2000-W01", 1, "bench-press")
        plan = self.plan()
        self.assertEqual(plan["training_week"], 2)
        self.assertEqual(plan["week_key"], self.week)

    def test_the_plan_page_heads_with_it(self):
        self.sign_in_browser()
        page = self.client.get("/account/plan").text
        self.assertIn("Your week — week 1<", page)
        self.assertIn("Then 5-minute abs:", page)

    def test_the_email_heads_with_it_and_lists_each_days_circuit(self):
        sub = db.get_by_email(self.conn, EMAIL)
        subject, html, text = emails.render_plan_email(sub, 2026, 42, 7)
        self.assertEqual(subject, "Your gym week — week 7")
        self.assertIn("week 7</h1>", html)
        self.assertTrue(text.startswith("Your plan - week 7 ("))
        self.assertEqual(html.count("Then 5-minute abs:"), 4)
        self.assertEqual(text.count("Then 5-minute abs:"), 4)
        self.assertIn("/email/off?token=", html)
        self.assertIn("/email/off?token=", text)


class OptOut(ApiBase):
    def me(self):
        return self.client.get("/api/v1/me", headers=self.auth).json()

    def send(self):
        with mock.patch("mailer.send", return_value=True) as sent:
            stats = send_weekly.run()
        return stats, [c.args[0] for c in sent.call_args_list]

    def setUp(self):
        super().setUp()
        db.set_status(self.conn, EMAIL, "active")

    def test_on_unless_turned_off(self):
        self.assertTrue(self.me()["weekly_email"])
        self.assertEqual(self.send()[1], [EMAIL])

    def test_turned_off_from_the_app_it_is_not_sent(self):
        r = self.client.patch("/api/v1/me", headers=self.auth,
                              json={"weekly_email": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["weekly_email"])
        stats, sent = self.send()
        self.assertEqual(sent, [])
        self.assertEqual((stats["active"], stats["opted_out"]), (1, 1))

    def test_other_settings_leave_it_alone(self):
        db.set_weekly_email(self.conn, self.sid, False)
        self.client.patch("/api/v1/me", headers=self.auth,
                          json={"days_per_week": 3})
        self.assertFalse(self.me()["weekly_email"])

    def test_the_email_link_asks_first_and_turns_it_off_on_post(self):
        token = db.sign_email(EMAIL)
        page = self.client.get(f"/email/off?token={token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Stop the Sunday email?", page.text)
        self.assertTrue(self.me()["weekly_email"])     # a GET changes nothing
        done = self.client.post("/email/off", data={"token": token})
        self.assertIn("No more Sunday emails", done.text)
        self.assertFalse(self.me()["weekly_email"])
        self.assertEqual(db.get_by_email(self.conn, EMAIL)["status"], "active")

    def test_a_forged_link_is_refused(self):
        r = self.client.post("/email/off", data={"token": "nope"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self.me()["weekly_email"])

    def test_the_account_page_turns_it_off_and_on(self):
        self.sign_in_browser()
        self.assertIn("Stop the Sunday email", self.client.get("/account").text)
        self.client.post("/account/weekly-email", data={"on": "false"})
        self.assertFalse(self.me()["weekly_email"])
        self.assertIn("Send me the Sunday email",
                      self.client.get("/account").text)
        self.client.post("/account/weekly-email", data={"on": "true"})
        self.assertTrue(self.me()["weekly_email"])

    def test_the_prefs_form_does_not_touch_it(self):
        db.set_weekly_email(self.conn, self.sid, False)
        self.sign_in_browser()
        self.client.post("/account", data={"days": 3,
                                           "experience": "beginner",
                                           "equipment": "full"})
        self.assertFalse(self.me()["weekly_email"])


if __name__ == "__main__":
    unittest.main()
