import unittest

import progress


def c(week, slug, weight=None, reps=None, sets=None, day=1):
    """One completion row, shaped like db.py returns."""
    return {"week": week, "day": day, "slug": slug,
            "weight_kg": weight, "reps": reps, "sets": sets}


class TestE1RM(unittest.TestCase):
    def test_epley(self):
        self.assertAlmostEqual(progress.e1rm(80, 3), 88.0)
        self.assertAlmostEqual(progress.e1rm(60, 10), 80.0)

    def test_missing_data_is_none(self):
        self.assertIsNone(progress.e1rm(None, 5))
        self.assertIsNone(progress.e1rm(60, None))

    def test_rejects_high_reps(self):
        # Epley diverges past ~12; a 20-rep bodyweight set is not a 1RM.
        self.assertIsNone(progress.e1rm(40, 20))

    def test_rejects_zero_and_negative(self):
        self.assertIsNone(progress.e1rm(0, 5))
        self.assertIsNone(progress.e1rm(-10, 5))
        self.assertIsNone(progress.e1rm(60, 0))


class TestWeekArithmetic(unittest.TestCase):
    def test_week_to_date_is_the_monday(self):
        import datetime
        self.assertEqual(progress.week_to_date("2026-W30"),
                         datetime.date.fromisocalendar(2026, 30, 1))

    def test_week_range_is_inclusive(self):
        self.assertEqual(progress.week_range("2026-W30", "2026-W33"),
                         ["2026-W30", "2026-W31", "2026-W32", "2026-W33"])

    def test_week_range_crosses_the_year_boundary(self):
        got = progress.week_range("2025-W52", "2026-W02")
        self.assertEqual(got[0], "2025-W52")
        self.assertEqual(got[-1], "2026-W02")
        self.assertIn("2026-W01", got)


class TestSlugSeries(unittest.TestCase):
    def test_uses_e1rm_when_weight_is_logged(self):
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W32", "leg-press", 90, 3)]
        series = progress.slug_series(rows)
        self.assertEqual([w for w, _ in series["leg-press"]],
                         ["2026-W30", "2026-W32"])
        self.assertAlmostEqual(series["leg-press"][0][1], 88.0)

    def test_falls_back_to_reps_for_bodyweight_only(self):
        rows = [c("2026-W30", "push-up", None, 10),
                c("2026-W31", "push-up", None, 14)]
        series = progress.slug_series(rows)
        self.assertEqual([v for _, v in series["push-up"]], [10.0, 14.0])

    def test_mixed_slug_prefers_weighted_logs_only(self):
        # A slug with any real load ignores its bare-rep entries, so the
        # series never mixes kilos and reps in one line.
        rows = [c("2026-W30", "bench-press", None, 10),
                c("2026-W31", "bench-press", 60, 10)]
        series = progress.slug_series(rows)
        self.assertEqual(len(series["bench-press"]), 1)
        self.assertAlmostEqual(series["bench-press"][0][1], 80.0)

    def test_ignores_bare_ticks(self):
        self.assertEqual(progress.slug_series([c("2026-W30", "plank")]), {})


class TestStrengthIndex(unittest.TestCase):
    def test_baseline_is_the_first_log_at_100(self):
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W31", "leg-press", 88, 3)]
        idx = dict(progress.strength_index(rows, "2026-W31"))
        self.assertAlmostEqual(idx["2026-W30"], 100.0)
        self.assertAlmostEqual(idx["2026-W31"], 110.0)

    def test_single_log_slugs_are_excluded(self):
        # A slug logged once is 100 by definition. Including it would drag the
        # mean toward 100 and flatten real progress on everything else.
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W31", "leg-press", 88, 3),
                c("2026-W31", "bench-press", 60, 5)]
        idx = dict(progress.strength_index(rows, "2026-W31"))
        self.assertAlmostEqual(idx["2026-W31"], 110.0)

    def test_rotation_does_not_move_the_index(self):
        # Two mechanically different squats, each improved 10% against its own
        # baseline. The Index must read 110, not sawtooth between them.
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W31", "goblet-squat", 30, 10),
                c("2026-W32", "leg-press", 88, 3),
                c("2026-W33", "goblet-squat", 33, 10)]
        idx = dict(progress.strength_index(rows, "2026-W33"))
        self.assertAlmostEqual(idx["2026-W33"], 110.0)

    def test_window_holds_a_slug_for_four_weeks_then_drops_it(self):
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W31", "leg-press", 88, 3),
                c("2026-W40", "bench-press", 60, 5),
                c("2026-W41", "bench-press", 66, 5)]
        idx = dict(progress.strength_index(rows, "2026-W41"))
        self.assertAlmostEqual(idx["2026-W34"], 110.0)   # still in window
        self.assertIsNone(idx["2026-W35"])               # aged out, a gap
        self.assertAlmostEqual(idx["2026-W41"], 110.0)   # bench now carries it

    def test_latest_log_per_slug_wins_inside_the_window(self):
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W31", "leg-press", 88, 3),
                c("2026-W32", "leg-press", 96, 3)]
        idx = dict(progress.strength_index(rows, "2026-W32"))
        self.assertAlmostEqual(idx["2026-W32"], 120.0)

    def test_bodyweight_only_indexes_on_reps(self):
        rows = [c("2026-W30", "push-up", None, 10),
                c("2026-W31", "push-up", None, 13)]
        idx = dict(progress.strength_index(rows, "2026-W31"))
        self.assertAlmostEqual(idx["2026-W31"], 130.0)

    def test_no_qualifying_data_is_an_empty_series(self):
        self.assertEqual(progress.strength_index([], "2026-W31"), [])


class TestRelativeStrength(unittest.TestCase):
    def test_ratio_against_bodyweight(self):
        rows = [c("2026-W30", "back-squat", 100, 5)]
        out = progress.relative_strength(rows, 100.0, "2026-W30")
        squat = [l for l in out["lifts"] if l["pattern"] == "squat"][0]
        self.assertAlmostEqual(squat["load"], 116.67, places=1)
        self.assertAlmostEqual(squat["ratio"], 1.167, places=2)

    def test_per_dumbbell_load_is_doubled(self):
        # 30 kg in each hand is a 60 kg lift when compared to bodyweight.
        rows = [c("2026-W30", "dumbbell-chest-press", 30, 10)]
        out = progress.relative_strength(rows, 100.0, "2026-W30")
        press = [l for l in out["lifts"] if l["pattern"] == "h_push"][0]
        self.assertAlmostEqual(press["load"], 80.0)

    def test_bodyweight_loaded_lifts_are_excluded(self):
        # A 20 kg weighted pull-up is not a 20 kg lift; reporting it as one
        # would understate v_pull badly.
        rows = [c("2026-W30", "pull-up", 20, 5)]
        out = progress.relative_strength(rows, 100.0, "2026-W30")
        self.assertEqual(out["lifts"], [])
        self.assertIn("v_pull", out["missing"])

    def test_missing_patterns_are_named_not_hidden(self):
        rows = [c("2026-W30", "back-squat", 100, 5)]
        out = progress.relative_strength(rows, 100.0, "2026-W30")
        self.assertEqual(sorted(out["missing"]), ["h_push", "hinge", "v_pull"])

    def test_only_the_trailing_eight_weeks_count(self):
        rows = [c("2026-W10", "back-squat", 100, 5)]
        out = progress.relative_strength(rows, 100.0, "2026-W30")
        self.assertEqual(out["lifts"], [])
        self.assertIsNone(out["total"])

    def test_best_lift_in_the_window_wins(self):
        rows = [c("2026-W29", "back-squat", 100, 5),
                c("2026-W30", "back-squat", 90, 5)]
        out = progress.relative_strength(rows, 100.0, "2026-W30")
        self.assertAlmostEqual(out["lifts"][0]["load"], 116.67, places=1)

    def test_no_bodyweight_means_no_metric(self):
        rows = [c("2026-W30", "back-squat", 100, 5)]
        self.assertIsNone(progress.relative_strength(rows, None, "2026-W30"))


if __name__ == "__main__":
    unittest.main()
