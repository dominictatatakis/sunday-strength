"""Days a subscriber rearranges: storage, the plan they change, the API."""
import unittest

from tests.dbhelp import db, fresh_db

import app as app_module  # noqa: E402  (after dbhelp has set the env)
import engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

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


class ApiBase(unittest.TestCase):
    kit = "full"

    def setUp(self):
        self.conn = fresh_db()
        self.sid = db.upsert_subscriber(self.conn, EMAIL, 4, "intermediate",
                                        False, "monthly", self.kit)
        self.client = TestClient(app_module.app)
        self.auth = {"Authorization":
                     f"Bearer {db.issue_api_key(self.conn, EMAIL)}"}
        self.week = db.current_week_key()

    def plan(self):
        r = self.client.get("/api/v1/plan", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    @staticmethod
    def slugs(plan, day=1):
        return [e["slug"] for e in plan["days"][day - 1]["exercises"]]

    def newcomer(self, plan, day=1):
        """An exercise the kit allows that isn't in that day yet."""
        taken = set(self.slugs(plan, day))
        kit = engine.EQUIPMENT_RANK[self.kit]
        return next(s for s in sorted(engine.all_slugs())
                    if s not in taken
                    and engine.EQUIPMENT_RANK[engine.SLUG_EQUIPMENT[s]] <= kit)

    def tick(self, slug, day=1):
        return self.client.post("/api/v1/completions", headers=self.auth,
                                json={"slug": slug, "day": day})

    def sign_in_browser(self):
        self.client.cookies.set(app_module.SESSION_COOKIE, db.sign_email(EMAIL))


class Overlay(ApiBase):
    def test_days_start_as_generated(self):
        plan = self.plan()
        self.assertTrue(all(d["edited"] is False for d in plan["days"]))
        self.assertEqual(plan["days"][0]["original"], self.slugs(plan))

    def test_a_saved_day_is_what_the_api_serves(self):
        plan = self.plan()
        first, new = self.slugs(plan)[0], self.newcomer(plan)
        db.set_day_plan(self.conn, self.sid, self.week, 1, [new, first])
        after = self.plan()
        self.assertEqual(self.slugs(after), [new, first])
        self.assertTrue(after["days"][0]["edited"])
        self.assertEqual(after["days"][0]["original"], self.slugs(plan))
        self.assertEqual(self.slugs(after, 2), self.slugs(plan, 2))

    def test_a_tick_for_an_added_exercise_is_accepted(self):
        new = self.newcomer(self.plan())
        db.set_day_plan(self.conn, self.sid, self.week, 1, [new])
        self.assertEqual(self.tick(new).status_code, 200)
        self.assertTrue(self.plan()["days"][0]["exercises"][0]["done"])

    def test_a_tick_for_a_removed_exercise_is_refused(self):
        plan = self.plan()
        removed = self.slugs(plan)[0]
        db.set_day_plan(self.conn, self.sid, self.week, 1, self.slugs(plan)[1:])
        r = self.tick(removed)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"],
                         "That exercise isn't in that day's plan.")

    def test_the_no_js_form_follows_the_edited_day(self):
        plan = self.plan()
        removed, new = self.slugs(plan)[0], self.newcomer(plan)
        db.set_day_plan(self.conn, self.sid, self.week, 1,
                        self.slugs(plan)[1:] + [new])
        self.sign_in_browser()
        form = {"week": self.week, "day": "1", "done": "true"}
        ok = self.client.post("/account/plan/log", data={**form, "slug": new},
                              follow_redirects=False)
        self.assertEqual(ok.status_code, 303)
        refused = self.client.post("/account/plan/log",
                                   data={**form, "slug": removed},
                                   follow_redirects=False)
        self.assertEqual(refused.status_code, 400)

    def test_the_plan_page_shows_the_edited_day(self):
        plan = self.plan()
        removed, new = self.slugs(plan)[0], self.newcomer(plan)
        self.sign_in_browser()
        before = self.client.get("/account/plan").text
        db.set_day_plan(self.conn, self.sid, self.week, 1,
                        self.slugs(plan)[1:] + [new])
        after = self.client.get("/account/plan").text
        hidden = 'name="slug" value="{}"'
        self.assertIn(hidden.format(new), after)
        self.assertEqual(after.count(hidden.format(removed)),
                         before.count(hidden.format(removed)) - 1)
