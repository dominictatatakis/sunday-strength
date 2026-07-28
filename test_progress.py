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


if __name__ == "__main__":
    unittest.main()
