"""The 5-minute abs circuit at the end of each gym day."""
import unittest

import engine

NEW = {"mountain-climber", "reverse-crunch", "bicycle-crunch", "flutter-kick"}


class Circuit(unittest.TestCase):
    def test_five_different_moves_whatever_the_day(self):
        for level in engine.LEVELS:
            for kit in engine.EQUIPMENT:
                for days in engine.SPLITS:
                    for week in range(1, 54):
                        plan = engine.generate_plan(week, days, level, False, kit)
                        for d, day in enumerate(plan["days"], start=1):
                            taken = {e["slug"] for e in day["exercises"]}
                            slugs = [m["slug"] for m in engine.abs_circuit(
                                week, d, level, kit, taken)["moves"]]
                            where = (level, kit, days, week, d)
                            self.assertEqual(len(slugs), 5, where)
                            self.assertEqual(len(set(slugs)), 5, where)
                            self.assertFalse(taken & set(slugs), where)

    def test_respects_level_and_kit(self):
        for week in range(1, 20):
            home = engine.abs_circuit(week, 1, "beginner", "bodyweight")["moves"]
            self.assertTrue(all(engine.SLUG_EQUIPMENT[m["slug"]] == "bodyweight"
                                for m in home))
            self.assertFalse({"pallof-press", "hanging-leg-raise"}
                             & {m["slug"] for m in home})

    def test_times_follow_the_level(self):
        times = [(engine.abs_circuit(1, 1, lvl, "full")["work"],
                  engine.abs_circuit(1, 1, lvl, "full")["rest"])
                 for lvl in engine.LEVELS]
        self.assertEqual(times, [(30, 30), (40, 20), (45, 15)])

    def test_the_same_day_gets_the_same_circuit(self):
        self.assertEqual(engine.abs_circuit(40, 2, "intermediate", "full"),
                         engine.abs_circuit(40, 2, "intermediate", "full"))

    def test_it_changes_from_week_to_week(self):
        seen = {tuple(m["slug"] for m in
                      engine.abs_circuit(w, 1, "intermediate", "full")["moves"])
                for w in range(1, 11)}
        self.assertGreater(len(seen), 1)

    def test_front_first_and_a_fast_finish_last(self):
        moves = [m["slug"] for m in
                 engine.abs_circuit(40, 1, "intermediate", "full")["moves"]]
        self.assertIn(moves[0], {s for s, _ in engine.CIRCUIT_GROUPS[0]})
        self.assertIn(moves[-1], {s for s, _ in engine.CIRCUIT_GROUPS[-1]})

    def test_a_used_up_group_gives_its_place_away(self):
        moves = engine.abs_circuit(1, 1, "beginner", "bodyweight",
                                   {"side-plank"})["moves"]
        self.assertEqual(len(moves), 5)
        self.assertNotIn("side-plank", [m["slug"] for m in moves])


class NewMoves(unittest.TestCase):
    def test_they_are_in_the_library_as_core(self):
        lib = {e["slug"]: e for e in engine.library_for("beginner", "bodyweight")}
        for slug in NEW:
            self.assertEqual(lib[slug]["part"], "core")
            self.assertTrue(lib[slug]["sets"])

    def test_they_can_be_added_to_a_day(self):
        ex = engine.exercise_entry("mountain-climber", "advanced", "full")
        self.assertEqual((ex["name"], ex["equipment"]),
                         ("Mountain climbers", "bodyweight"))

    def test_they_never_enter_the_rotation(self):
        rotation = {s for pattern in engine.POOLS.values()
                    for pool in pattern.values() for _, s, _, _ in pool}
        self.assertFalse(NEW & rotation)
        self.assertTrue(NEW <= engine.all_slugs())
