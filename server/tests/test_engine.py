"""Exercises the subscriber picks, and the days they rearrange."""
import copy
import unittest

import engine

PLAN = {"week": 40, "equipment": "full", "run": None, "notes": [], "days": [
    {"title": "Day 1 - Legs", "exercises": [
        {"name": "Single-leg glute bridge", "slug": "hip-thrust",
         "sets": "3 x 12 each side", "equipment": "bodyweight", "alts": []},
        {"name": "Leg press", "slug": "leg-press", "sets": "3 x 10-12",
         "equipment": "full", "alts": []}]},
    {"title": "Day 2 - Push", "exercises": [
        {"name": "Bench press", "slug": "bench-press", "sets": "3 x 8-10",
         "equipment": "full", "alts": []}]}]}


class ExerciseEntry(unittest.TestCase):
    def test_takes_the_name_and_sets_at_the_subscribers_level(self):
        ex = engine.exercise_entry("goblet-squat", "intermediate", "full")
        self.assertEqual((ex["name"], ex["sets"], ex["equipment"]),
                         ("Goblet squat", "3 x 10-12", "dumbbells"))
        self.assertEqual(ex["alts"],
                         engine.alternatives_for("goblet-squat", "full"))

    def test_a_level_it_lacks_borrows_the_nearest(self):
        # Front squats are only written for advanced lifters.
        ex = engine.exercise_entry("front-squat", "beginner", "full")
        self.assertEqual(ex["sets"], "4 x 6-8")

    def test_a_tie_between_levels_goes_to_the_easier(self):
        # Step-ups exist for beginners and advanced lifters, not in between.
        ex = engine.exercise_entry("step-up", "intermediate", "bodyweight")
        self.assertEqual(ex["sets"], "2 x 10 each leg")

    def test_the_variant_follows_the_kit(self):
        home = engine.exercise_entry("hip-thrust", "intermediate", "bodyweight")
        gym = engine.exercise_entry("hip-thrust", "intermediate", "full")
        self.assertEqual((home["name"], home["equipment"]),
                         ("Single-leg glute bridge", "bodyweight"))
        self.assertEqual((gym["name"], gym["equipment"]), ("Hip thrust", "full"))

    def test_refuses_what_the_kit_cannot_do(self):
        with self.assertRaises(ValueError):
            engine.exercise_entry("front-squat", "advanced", "bodyweight")

    def test_refuses_an_unknown_slug(self):
        with self.assertRaises(ValueError):
            engine.exercise_entry("moon-squat", "advanced", "full")


class ApplyDayEdits(unittest.TestCase):
    def edit(self, edited):
        return engine.apply_day_edits(PLAN, edited, "intermediate", "full")

    def test_nothing_edited_changes_nothing_but_the_flags(self):
        plan = self.edit({})
        self.assertEqual([d["exercises"] for d in plan["days"]],
                         [d["exercises"] for d in PLAN["days"]])
        self.assertEqual([d["edited"] for d in plan["days"]], [False, False])
        self.assertEqual(plan["days"][0]["original"], ["hip-thrust", "leg-press"])

    def test_an_edited_day_follows_the_list_in_order(self):
        day = self.edit({1: ["leg-press", "goblet-squat"]})["days"][0]
        self.assertEqual([e["slug"] for e in day["exercises"]],
                         ["leg-press", "goblet-squat"])
        self.assertTrue(day["edited"])
        self.assertEqual(day["title"], "Day 1 - Legs")
        self.assertEqual(day["original"], ["hip-thrust", "leg-press"])

    def test_a_row_already_there_keeps_its_generated_entry(self):
        """Adding a squat must not rename the glute bridge to a hip thrust."""
        day = self.edit({1: ["hip-thrust", "goblet-squat"]})["days"][0]
        self.assertEqual(day["exercises"][0], PLAN["days"][0]["exercises"][0])

    def test_other_days_are_untouched(self):
        plan = self.edit({1: []})
        self.assertEqual(plan["days"][0]["exercises"], [])
        self.assertEqual(plan["days"][1]["exercises"],
                         PLAN["days"][1]["exercises"])

    def test_a_retired_or_out_of_kit_slug_is_dropped(self):
        plan = engine.apply_day_edits(
            PLAN, {2: ["moon-squat", "front-squat", "push-up"]},
            "advanced", "bodyweight")
        self.assertEqual([e["slug"] for e in plan["days"][1]["exercises"]],
                         ["push-up"])

    def test_the_generated_plan_is_not_modified(self):
        before = copy.deepcopy(PLAN)
        self.edit({1: ["goblet-squat"]})
        self.assertEqual(PLAN, before)


class Library(unittest.TestCase):
    def test_only_what_the_kit_allows_once_each(self):
        slugs = [e["slug"] for e in engine.library_for("intermediate", "bodyweight")]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(engine.SLUG_EQUIPMENT[s] == "bodyweight" for s in slugs))
        self.assertIn("push-up", slugs)
        self.assertNotIn("bench-press", slugs)

    def test_names_and_sets_match_what_adding_it_would_give(self):
        for e in engine.library_for("beginner", "dumbbells"):
            added = engine.exercise_entry(e["slug"], "beginner", "dumbbells")
            self.assertEqual((e["name"], e["sets"]),
                             (added["name"], added["sets"]))

    def test_each_has_one_body_part_and_its_patterns(self):
        lib = {e["slug"]: e for e in engine.library_for("advanced", "full")}
        self.assertEqual(lib["inverted-row"]["part"], "pull")
        self.assertEqual(set(lib["inverted-row"]["patterns"]),
                         {"row", "v_pull", "biceps"})
        self.assertEqual(lib["goblet-squat"]["patterns"], ["squat"])
        self.assertTrue(all(e["part"] in engine.PART_ORDER for e in lib.values()))

    def test_ordered_by_body_part(self):
        parts = [e["part"] for e in engine.library_for("advanced", "full")]
        self.assertEqual(parts, sorted(parts, key=engine.PART_ORDER.index))

    def test_alternatives_are_the_exercise_pages_four(self):
        lib = {e["slug"]: e for e in engine.library_for("advanced", "full")}
        self.assertEqual(lib["goblet-squat"]["alternatives"],
                         engine.alternatives_for("goblet-squat", "full", limit=4))
