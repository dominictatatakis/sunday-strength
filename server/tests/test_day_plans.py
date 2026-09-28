"""Days a subscriber rearranges: storage, the plan they change, the API."""
import unittest

from tests.dbhelp import db, fresh_db

EMAIL = "dom@example.com"


class Store(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db()
        self.sid = db.upsert_subscriber(self.conn, EMAIL, 4, "intermediate",
                                        False, "monthly", "full")

    def days(self, week):
        return db.day_plans_for_week(self.conn, self.sid, week)

    def test_saving_a_day_twice_keeps_the_latest(self):
        db.set_day_plan(self.conn, self.sid, "2026-W40", 1, ["plank", "push-up"])
        db.set_day_plan(self.conn, self.sid, "2026-W40", 1, ["push-up"])
        self.assertEqual(self.days("2026-W40"), {1: ["push-up"]})

    def test_weeks_days_and_subscribers_are_kept_apart(self):
        other = db.upsert_subscriber(self.conn, "x@example.com", 4,
                                     "intermediate", False, "monthly", "full")
        db.set_day_plan(self.conn, self.sid, "2026-W40", 1, ["plank"])
        db.set_day_plan(self.conn, self.sid, "2026-W40", 2, [])
        db.set_day_plan(self.conn, self.sid, "2026-W41", 1, ["push-up"])
        db.set_day_plan(self.conn, other, "2026-W40", 1, ["crunch"])
        self.assertEqual(self.days("2026-W40"), {1: ["plank"], 2: []})

    def test_clearing_a_day(self):
        db.set_day_plan(self.conn, self.sid, "2026-W40", 1, ["plank"])
        db.clear_day_plan(self.conn, self.sid, "2026-W40", 1)
        db.clear_day_plan(self.conn, self.sid, "2026-W40", 3)   # never saved
        self.assertEqual(self.days("2026-W40"), {})

    def test_a_new_split_clears_this_week_and_later_only(self):
        now = db.current_week_key()
        for week in ("2020-W01", now, "2099-W01"):
            db.set_day_plan(self.conn, self.sid, week, 1, ["plank"])
        db.update_prefs(self.conn, EMAIL, 3, "intermediate", False, "full")
        self.assertEqual(self.days(now), {})
        self.assertEqual(self.days("2099-W01"), {})
        self.assertEqual(self.days("2020-W01"), {1: ["plank"]})

    def test_a_new_kit_clears_them_too(self):
        now = db.current_week_key()
        db.set_day_plan(self.conn, self.sid, now, 1, ["plank"])
        db.update_prefs(self.conn, EMAIL, 4, "intermediate", False, "bodyweight")
        self.assertEqual(self.days(now), {})

    def test_a_level_or_run_change_keeps_them(self):
        now = db.current_week_key()
        db.set_day_plan(self.conn, self.sid, now, 1, ["plank"])
        db.update_prefs(self.conn, EMAIL, 4, "advanced", True, "full")
        self.assertEqual(self.days(now), {1: ["plank"]})
