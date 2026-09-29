"""The abs circuit through the API: served with each day, ticked like a set."""
import unittest

from tests.test_day_plans import ApiBase

import engine  # noqa: E402


class CircuitApi(ApiBase):
    def test_each_day_has_a_circuit_not_repeating_its_exercises(self):
        for day in self.plan()["days"]:
            c = day["circuit"]
            self.assertEqual((c["work"], c["rest"], c["done"]), (40, 20, False))
            self.assertEqual(len(c["moves"]), 5)
            self.assertFalse({m["slug"] for m in c["moves"]}
                             & set(day["original"]))

    def test_ticking_it_marks_it_done(self):
        self.assertEqual(self.tick(engine.CIRCUIT_SLUG, day=2).status_code, 200)
        days = self.plan()["days"]
        self.assertTrue(days[1]["circuit"]["done"])
        self.assertFalse(days[0]["circuit"]["done"])
        self.client.post("/api/v1/completions", headers=self.auth,
                         json={"slug": engine.CIRCUIT_SLUG, "day": 2,
                               "done": False})
        self.assertFalse(self.plan()["days"][1]["circuit"]["done"])

    def test_a_day_outside_the_week_is_refused(self):
        self.assertEqual(self.tick(engine.CIRCUIT_SLUG, day=9).status_code, 400)

    def test_it_is_not_an_exercise_for_a_day(self):
        r = self.client.put("/api/v1/plan/days/1", headers=self.auth,
                            json={"slugs": [engine.CIRCUIT_SLUG]})
        self.assertEqual(r.status_code, 400)

    def test_editing_the_day_keeps_the_circuit(self):
        before = self.plan()["days"][0]["circuit"]["moves"]
        self.client.put("/api/v1/plan/days/1", headers=self.auth,
                        json={"slugs": []})
        self.assertEqual(self.plan()["days"][0]["circuit"]["moves"], before)

    def test_new_moves_can_be_added_to_a_day(self):
        r = self.client.put("/api/v1/plan/days/1", headers=self.auth,
                            json={"slugs": ["mountain-climber"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["days"][0]["exercises"][0]["sets"],
                         "3 x 30 sec")

    def test_new_moves_have_exercise_pages(self):
        self.assertEqual(self.client.get("/exercise/flutter-kick").status_code,
                         200)


if __name__ == "__main__":
    unittest.main()
