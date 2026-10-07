"""The shape of a gym day: the muscles each one reaches, and no core slot
from 2026-W42, when the abs circuit took over."""
import unittest

import engine

# What each pattern mainly trains. Secondary movers don't count: a bench
# press works the triceps, but a push day still gets its own triceps move.
MUSCLES = {
    "squat": {"quads", "glutes"}, "hinge": {"hamstrings", "glutes"},
    "single_leg": {"quads", "glutes"}, "ham_curl": {"hamstrings"},
    "calf": {"calves"}, "h_push": {"chest"}, "chest_acc": {"chest"},
    "v_push": {"shoulders"}, "side_delt": {"shoulders"},
    "triceps": {"triceps"}, "v_pull": {"back"}, "row": {"back"},
    "rear_delt": {"shoulders"}, "biceps": {"biceps"},
}
NEEDS = {
    "Legs": {"quads", "hamstrings", "glutes", "calves"},
    "Push": {"chest", "shoulders", "triceps"},
    "Pull": {"back", "biceps"},
}
CORE = {slug for pool in engine.POOLS["core"].values() for _, slug, _, _ in pool}
# ISO weeks on the new layout, into the next year.
NEW_WEEKS = [(2026, w) for w in range(42, 54)] + [(2027, w) for w in range(1, 53)]


def patterns_for(patterns, level):
    return patterns[:engine.BEGINNER_SLOTS] if level == "beginner" else patterns


class MajorMuscles(unittest.TestCase):
    def test_push_pull_and_legs_reach_every_one_they_are_named_for(self):
        for days, split in engine.SPLITS.items():
            for title, patterns in split:
                kind = title.split()[0]
                if kind not in NEEDS:
                    continue
                for level in engine.LEVELS:
                    reached = set().union(*(MUSCLES[p] for p in
                                            patterns_for(patterns, level)))
                    self.assertLessEqual(NEEDS[kind], reached,
                                         (days, title, level))

    def test_every_kit_still_reaches_them(self):
        """With no kit, two slots can share their only exercise and merge:
        the inverted row is the back and the biceps move. What a day ends up
        with must still cover it."""
        for year, week in NEW_WEEKS:
            for days, split in engine.SPLITS.items():
                for level in engine.LEVELS:
                    for kit in engine.EQUIPMENT:
                        plan = engine.generate_plan(week, days, level, False,
                                                    kit, year=year)
                        for (title, _), day in zip(split, plan["days"]):
                            kind = title.split()[0]
                            if kind not in NEEDS:
                                continue
                            slugs = {e["slug"] for e in day["exercises"]}
                            reached = set().union(*(
                                muscles for pattern, muscles in MUSCLES.items()
                                if slugs & {e[1] for e in
                                            engine.POOLS[pattern][level]}))
                            self.assertLessEqual(
                                NEEDS[kind], reached,
                                (year, week, days, level, kit, title))


class CoreSlot(unittest.TestCase):
    def test_gone_from_2026_w42_as_the_circuit_covers_it(self):
        for year, week in NEW_WEEKS:
            for days in engine.SPLITS:
                for level in engine.LEVELS:
                    plan = engine.generate_plan(week, days, level, False,
                                                "full", year=year)
                    for day in plan["days"]:
                        self.assertFalse({e["slug"] for e in day["exercises"]}
                                         & CORE, (year, week, days, level))
                        self.assertNotIn("core", day["title"])

    def test_earlier_weeks_keep_it_as_they_were_logged_against(self):
        for year, week in [(2025, 50), (2026, 1), (2026, 41)]:
            for level in engine.LEVELS:
                plan = engine.generate_plan(week, 3, level, False, "full",
                                            year=year)
                for day in plan["days"]:
                    self.assertIn(day["exercises"][-1]["slug"], CORE)
                    self.assertTrue(day["title"].endswith("& core"))

    def test_beginners_still_get_four_exercises(self):
        for year, week in [(2026, 41), (2026, 42)]:
            plan = engine.generate_plan(week, 3, "beginner", False, "full",
                                        year=year)
            self.assertEqual([len(d["exercises"]) for d in plan["days"]],
                             [4, 4, 4])


if __name__ == "__main__":
    unittest.main()
