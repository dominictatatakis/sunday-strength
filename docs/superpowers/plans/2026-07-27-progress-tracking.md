# Progress Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/account/progress`, a page showing every Sunday Strength subscriber whether they are getting stronger, computed from the `completions` they already log.

**Architecture:** All metric maths lives in a new pure `progress.py` — no I/O, no database, no reading the clock — mirroring the contract `engine.py` holds. `db.py` gains a `bodyweights` table and five queries; `app.py` gains four routes that pass rows into `progress.py` and hand the result to a template. Charts are server-rendered inline SVG with geometry computed in Python, so the page needs no JavaScript.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, SQLite locally / Postgres on Render, stdlib `unittest`. No new dependencies.

## Global Constraints

- **No new dependencies.** `requirements.txt` must not change. Stdlib over libraries, per house style (passwords are stdlib `scrypt`, there is no ORM).
- **`progress.py` is pure.** No database, no network, no `datetime.date.today()`. Parsing a week key into a date is fine; asking what today is, is not. Callers pass the current week in.
- **Schema changes go in four places.** `SCHEMA` *and* `SCHEMA_PG`, plus an idempotent statement in `MIGRATIONS_SQLITE` *and* `MIGRATIONS_PG`. Missing one breaks a live back-end.
- **The Postgres path cannot be verified locally** (no Postgres on this machine). Any schema work is unverified until it boots on Render; check the deploy log for `migration skipped:`.
- **Never run anything against `gymdigest.db`.** Pass `DB_PATH=/tmp/<name>.db`.
- **Clear provider vars before running the app**, or you will email real subscribers: `BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER=`.
- **Week bucketing uses the `week` column, never `done_at`.** `done_at` is UTC; bucketing on it misfiles late-evening BST sessions.
- **British English in user-facing copy.** Plain hand-written CSS using existing custom properties.
- **The page must work with JavaScript disabled**, like the plan page.

## File Structure

| File | Responsibility |
|---|---|
| `progress.py` (new) | Every metric calculation. Pure functions. ~300 lines. |
| `test_progress.py` (new) | stdlib `unittest` for the maths. |
| `db.py` (modify) | `bodyweights` table, `pinned_metric` column, four queries. |
| `app.py` (modify) | `GET /account/progress`, `POST /account/progress/pin`, `POST /account/bodyweight`, `GET /api/v1/progress`. |
| `templates/progress.html` (new) | Page markup, metric cards, SVG charts. |
| `templates/_nav.html` (modify) | "Progress" link. |
| `static/style.css` (modify) | Card and chart styles. |
| `scripts/seed_progress.py` (new) | Six months of plausible history into a throwaway DB. |

Test command throughout: `.venv/bin/python -m unittest test_progress -v`

---

### Task 1: Core primitives — e1RM, week arithmetic, per-slug series

**Files:**
- Create: `progress.py`
- Test: `test_progress.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `e1rm(weight_kg, reps) -> float | None`, `week_to_date(key) -> datetime.date`, `week_range(first, last) -> list[str]`, `slug_series(completions) -> dict[str, list[tuple[str, float]]]`, and the module constants.

- [ ] **Step 1: Write the failing test**

Create `test_progress.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'progress'`

- [ ] **Step 3: Write the implementation**

Create `progress.py`:

```python
"""Progress metrics computed from logged completions.

Pure data and functions, no I/O — the same contract engine.py holds. Nothing
here reads the database or asks what today is; callers pass the current week
in. That is what makes the arithmetic testable, and the arithmetic is the part
that fails silently.
"""

import datetime

# Epley diverges badly on high-rep sets: a 20-rep bodyweight squat would report
# an absurd 1RM. Above this we decline to estimate rather than guess.
MAX_EPLEY_REPS = 12

MIN_BODYWEIGHT_KG = 30.0
MAX_BODYWEIGHT_KG = 300.0

INDEX_WINDOW_WEEKS = 4          # trailing window for the Strength Index
RELATIVE_WINDOW_WEEKS = 8       # trailing window for relative strength
SESSION_THRESHOLD = 0.5         # share of a day's exercises that counts as done

MAIN_PATTERNS = ("squat", "hinge", "h_push", "v_pull")

METRICS = ("strength_index", "relative_strength", "consistency", "tonnage")

# Slugs held one dumbbell per hand. weight_kg is logged per dumbbell, so total
# load is double — which matters only where an absolute load is compared to
# bodyweight. The equipment tier cannot answer this: 'dumbbells' is a
# minimum-kit marker that single-implement lifts (goblet squat, kettlebell
# swing, one-arm row) carry too. Adding a two-dumbbell exercise to POOLS means
# adding it here.
PER_DUMBBELL = frozenset({
    "dumbbell-chest-press",
    "dumbbell-curl",
    "dumbbell-fly",
    "dumbbell-lateral-raise",
    "dumbbell-lunge",
    "dumbbell-romanian-deadlift",
    "hammer-curl",
    "incline-dumbbell-curl",
    "reverse-dumbbell-fly",
    "seated-dumbbell-shoulder-press",
})

# Lifts where the load is your own body and any logged weight is *added*. A
# 20 kg weighted pull-up is not a 20 kg lift, so these are excluded from
# relative strength rather than reported as a fraction of bodyweight we would
# have to invent. They still count in the Strength Index, where every reading
# is relative to the same lift's own history and the leverage cancels.
BODYWEIGHT_LOADED = frozenset({
    "assisted-pull-up", "bar-dip", "bench-dip", "bulgarian-split-squat",
    "box-squat", "chin-up", "crunch", "dead-bug", "decline-push-up",
    "diamond-push-up", "hanging-knee-raise", "hanging-leg-raise",
    "hip-thrust", "inverted-row", "nordic-ham-curl", "pike-push-up",
    "plank", "pull-up", "push-up", "russian-twist", "side-plank",
    "standing-calf-raise", "step-up", "superman", "walking-lunge",
})


def e1rm(weight_kg, reps):
    """Estimated one-rep max, Epley. None when it cannot be estimated."""
    if weight_kg is None or reps is None:
        return None
    if reps <= 0 or reps > MAX_EPLEY_REPS or weight_kg <= 0:
        return None
    return weight_kg * (1 + reps / 30)


def week_to_date(key):
    """'2026-W30' -> the Monday of that ISO week."""
    return datetime.date.fromisocalendar(int(key[:4]), int(key[6:]), 1)


def date_to_week(day):
    year, week = day.isocalendar()[:2]
    return f"{year}-W{week:02d}"


def week_range(first, last):
    """Every week key from first to last inclusive, in order."""
    out, day, end = [], week_to_date(first), week_to_date(last)
    while day <= end:
        out.append(date_to_week(day))
        day += datetime.timedelta(weeks=1)
    return out


def slug_series(completions):
    """{slug: [(week, value)]} sorted by week, one entry per logged session.

    Value is estimated 1RM where the slug has ever been loaded, and raw reps
    where it has not — progress on a bodyweight movement genuinely is more
    reps. A slug never mixes the two, so a line is always in one unit.
    """
    loaded, bare = {}, {}
    for row in completions:
        est = e1rm(row.get("weight_kg"), row.get("reps"))
        if est is not None:
            loaded.setdefault(row["slug"], []).append((row["week"], est))
        elif row.get("reps"):
            bare.setdefault(row["slug"], []).append(
                (row["week"], float(row["reps"])))

    series = {slug: pts for slug, pts in bare.items() if slug not in loaded}
    series.update(loaded)
    for pts in series.values():
        pts.sort(key=lambda p: p[0])
    return series
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add progress.py test_progress.py
git commit -m "Add progress primitives: e1RM, week arithmetic, per-slug series"
```

---

### Task 2: Strength Index

**Files:**
- Modify: `progress.py`
- Test: `test_progress.py`

**Interfaces:**
- Consumes: `slug_series`, `week_range`, `INDEX_WINDOW_WEEKS` from Task 1.
- Produces: `strength_index(completions, latest_week) -> list[tuple[str, float | None]]` — one point per week from first log to `latest_week`, value `None` where no qualifying data. Also `indexed_series(completions) -> dict[str, list[tuple[str, float]]]`.

- [ ] **Step 1: Write the failing test**

Append to `test_progress.py`, before the `if __name__` block:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: FAIL with `AttributeError: module 'progress' has no attribute 'strength_index'`

- [ ] **Step 3: Write the implementation**

Append to `progress.py`:

```python
def indexed_series(completions):
    """{slug: [(week, percent-of-baseline)]} for slugs logged more than once.

    Indexing against each lift's own first log is what makes the weekly
    exercise rotation harmless: percentages are unitless, so a goblet squat and
    a leg press can be averaged without pretending they are the same movement.
    It also cancels the per-dumbbell logging convention for free.
    """
    out = {}
    for slug, points in slug_series(completions).items():
        if len(points) < 2:
            continue
        baseline = points[0][1]
        if baseline <= 0:
            continue
        out[slug] = [(week, 100.0 * value / baseline) for week, value in points]
    return out


def strength_index(completions, latest_week):
    """[(week, index | None)] from the first log to latest_week.

    Each point averages the most recent reading of every qualifying lift seen
    in that week or the three before it. Weeks with nothing qualifying get
    None, which the chart draws as a gap rather than a fall to zero.
    """
    series = indexed_series(completions)
    if not series:
        return []

    first = min(points[0][0] for points in series.values())
    if first > latest_week:
        return []

    out = []
    for week in week_range(first, latest_week):
        cutoff = week_to_date(week) - datetime.timedelta(
            weeks=INDEX_WINDOW_WEEKS - 1)
        latest = {}
        for slug, points in series.items():
            inside = [(w, v) for w, v in points
                      if cutoff <= week_to_date(w) <= week_to_date(week)]
            if inside:
                latest[slug] = inside[-1][1]
        out.append((week, sum(latest.values()) / len(latest) if latest else None))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: PASS, 18 tests.

- [ ] **Step 5: Commit**

```bash
git add progress.py test_progress.py
git commit -m "Index each lift against its own baseline so rotation cancels"
```

---

### Task 3: Relative strength

**Files:**
- Modify: `progress.py`
- Test: `test_progress.py`

**Interfaces:**
- Consumes: `e1rm`, `week_to_date`, `PER_DUMBBELL`, `BODYWEIGHT_LOADED`, `MAIN_PATTERNS`, `RELATIVE_WINDOW_WEEKS` from Task 1.
- Produces: `slug_patterns() -> dict[str, str]`, `relative_strength(completions, bodyweight_kg, latest_week) -> dict` with keys `total`, `lifts` (list of `{"pattern", "slug", "load", "ratio"}`), `missing` (list of pattern names).

- [ ] **Step 1: Write the failing test**

Append to `test_progress.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: FAIL with `AttributeError: module 'progress' has no attribute 'relative_strength'`

- [ ] **Step 3: Write the implementation**

Add `import engine` at the top of `progress.py` (below `import datetime`), then append:

```python
def slug_patterns():
    """{slug: movement pattern}. Derived from engine.POOLS, never hardcoded."""
    out = {}
    for pattern, levels in engine.POOLS.items():
        for pool in levels.values():
            for _name, slug, _sets, _tier in pool:
                out.setdefault(slug, pattern)
    return out


def relative_strength(completions, bodyweight_kg, latest_week):
    """Load per kg of bodyweight across the four main patterns.

    None when no bodyweight is known. Patterns with nothing logged in the
    window are named in 'missing' rather than dropped, so a two-lift total
    never poses as a four-lift one.
    """
    if not bodyweight_kg:
        return None

    patterns = slug_patterns()
    cutoff = week_to_date(latest_week) - datetime.timedelta(
        weeks=RELATIVE_WINDOW_WEEKS - 1)

    best = {}
    for row in completions:
        slug = row["slug"]
        pattern = patterns.get(slug)
        if pattern not in MAIN_PATTERNS or slug in BODYWEIGHT_LOADED:
            continue
        if not (cutoff <= week_to_date(row["week"]) <= week_to_date(latest_week)):
            continue
        load = e1rm(row.get("weight_kg"), row.get("reps"))
        if load is None:
            continue
        if slug in PER_DUMBBELL:
            load *= 2
        if load > best.get(pattern, (0.0, None))[0]:
            best[pattern] = (load, slug)

    lifts = [{"pattern": p, "slug": best[p][1], "load": best[p][0],
              "ratio": best[p][0] / bodyweight_kg}
             for p in MAIN_PATTERNS if p in best]
    missing = [p for p in MAIN_PATTERNS if p not in best]
    total = (sum(l["load"] for l in lifts) / bodyweight_kg) if lifts else None
    return {"total": total, "lifts": lifts, "missing": missing}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: PASS, 25 tests.

- [ ] **Step 5: Commit**

```bash
git add progress.py test_progress.py
git commit -m "Add relative strength, excluding lifts loaded by your own body"
```

---

### Task 4: Consistency and tonnage

**Files:**
- Modify: `progress.py`
- Test: `test_progress.py`

**Interfaces:**
- Consumes: `week_range`, `week_to_date`, `SESSION_THRESHOLD` from Task 1.
- Produces: `consistency(completions, prefs, latest_week) -> dict` with keys `weeks` (list of `{"week", "done", "planned"}`), `streak`; and `tonnage(completions, latest_week) -> dict` with keys `weeks` (list of `{"week", "value"}`), `unit` (`"kg"` or `"reps"`).
  `prefs` is a dict with `days`, `experience`, `include_run`, `equipment`.

- [ ] **Step 1: Write the failing test**

Append to `test_progress.py`:

```python
PREFS = {"days": 3, "experience": "beginner", "include_run": False,
         "equipment": "full"}


class TestConsistency(unittest.TestCase):
    def _full_day(self, week, day):
        """Every exercise the engine prescribes for that day, logged."""
        iso = int(week[6:])
        plan = progress.planned_week(PREFS, iso)
        return [c(week, ex["slug"], 60, 10, day=day)
                for ex in plan["days"][day - 1]["exercises"]]

    def test_counts_completed_sessions(self):
        rows = self._full_day("2026-W30", 1) + self._full_day("2026-W30", 2)
        out = progress.consistency(rows, PREFS, "2026-W30")
        self.assertEqual(out["weeks"][-1], {"week": "2026-W30", "done": 2,
                                            "planned": 3})

    def test_half_a_session_counts(self):
        rows = self._full_day("2026-W30", 1)
        half = rows[:max(1, len(rows) // 2)]
        out = progress.consistency(half, PREFS, "2026-W30")
        self.assertEqual(out["weeks"][-1]["done"], 1)

    def test_one_exercise_of_four_does_not_count(self):
        rows = self._full_day("2026-W30", 1)[:1]
        out = progress.consistency(rows, PREFS, "2026-W30")
        self.assertEqual(out["weeks"][-1]["done"], 0)

    def test_streak_counts_back_from_the_latest_week(self):
        rows = []
        for week in ("2026-W29", "2026-W30"):
            for day in (1, 2, 3):
                rows += self._full_day(week, day)
        out = progress.consistency(rows, PREFS, "2026-W30")
        self.assertEqual(out["streak"], 2)

    def test_a_missed_week_breaks_the_streak(self):
        rows = []
        for day in (1, 2, 3):
            rows += self._full_day("2026-W28", day)
            rows += self._full_day("2026-W30", day)
        out = progress.consistency(rows, PREFS, "2026-W30")
        self.assertEqual(out["streak"], 1)


class TestTonnage(unittest.TestCase):
    def test_sets_times_reps_times_weight(self):
        rows = [c("2026-W30", "leg-press", 80, 10, sets=3)]
        out = progress.tonnage(rows, "2026-W30")
        self.assertEqual(out["unit"], "kg")
        self.assertAlmostEqual(out["weeks"][-1]["value"], 2400.0)

    def test_missing_sets_counts_as_one(self):
        rows = [c("2026-W30", "leg-press", 80, 10)]
        out = progress.tonnage(rows, "2026-W30")
        self.assertAlmostEqual(out["weeks"][-1]["value"], 800.0)

    def test_falls_back_to_reps_when_nothing_is_loaded(self):
        rows = [c("2026-W30", "push-up", None, 20, sets=3)]
        out = progress.tonnage(rows, "2026-W30")
        self.assertEqual(out["unit"], "reps")
        self.assertAlmostEqual(out["weeks"][-1]["value"], 60.0)

    def test_empty_history_is_empty(self):
        self.assertEqual(progress.tonnage([], "2026-W30")["weeks"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: FAIL with `AttributeError: module 'progress' has no attribute 'planned_week'`

- [ ] **Step 3: Write the implementation**

Append to `progress.py`:

```python
def planned_week(prefs, iso_week):
    """The plan the subscriber was given that week.

    Plans are deterministic, so what was prescribed is always recoverable from
    (week, prefs) — nothing needs storing to know what they were meant to do.
    """
    return engine.generate_plan(iso_week, prefs["days"], prefs["experience"],
                                prefs["include_run"], prefs["equipment"])


def consistency(completions, prefs, latest_week):
    """Sessions done against sessions planned, plus the current streak.

    A day counts as trained once half its prescribed exercises are logged —
    forgiving on purpose, since a session cut short is still a session.
    """
    if not completions:
        return {"weeks": [], "streak": 0}

    logged = {}
    for row in completions:
        logged.setdefault((row["week"], row["day"]), set()).add(row["slug"])

    first = min(row["week"] for row in completions)
    weeks = []
    for week in week_range(first, latest_week):
        plan = planned_week(prefs, int(week[6:]))
        done = 0
        for index, day in enumerate(plan["days"], start=1):
            prescribed = {ex["slug"] for ex in day["exercises"]}
            if not prescribed:
                continue
            hit = len(prescribed & logged.get((week, index), set()))
            if hit / len(prescribed) >= SESSION_THRESHOLD:
                done += 1
        weeks.append({"week": week, "done": done, "planned": prefs["days"]})

    streak = 0
    for entry in reversed(weeks):
        if entry["done"] < entry["planned"]:
            break
        streak += 1
    return {"weeks": weeks, "streak": streak}


def tonnage(completions, latest_week):
    """Weekly training volume: sets x reps x weight.

    Subscribers who never log a load would see a flat zero, so for them the
    series counts reps instead and says so. The choice is made once across all
    history, not per week, or the label would flicker.
    """
    if not completions:
        return {"weeks": [], "unit": "kg"}

    loaded = any(row.get("weight_kg") for row in completions)
    totals = {}
    for row in completions:
        reps, sets = row.get("reps"), row.get("sets") or 1
        if not reps:
            continue
        if loaded:
            weight = row.get("weight_kg")
            if not weight:
                continue
            totals[row["week"]] = totals.get(row["week"], 0.0) + sets * reps * weight
        else:
            totals[row["week"]] = totals.get(row["week"], 0.0) + sets * reps

    first = min(row["week"] for row in completions)
    weeks = [{"week": week, "value": totals.get(week, 0.0)}
             for week in week_range(first, latest_week)]
    return {"weeks": weeks, "unit": "kg" if loaded else "reps"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: PASS, 34 tests.

- [ ] **Step 5: Commit**

```bash
git add progress.py test_progress.py
git commit -m "Add consistency and tonnage from the deterministic plan"
```

---

### Task 5: Per-pattern trends and chart geometry

**Files:**
- Modify: `progress.py`
- Test: `test_progress.py`

**Interfaces:**
- Consumes: `slug_series`, `slug_patterns` from Tasks 1 and 3.
- Produces: `pattern_trends(completions) -> list[dict]` (each `{"pattern", "name", "lifts": [{"slug", "name", "points"}]}`), `sparkline(values, width, height) -> dict` with keys `segments`, `width`, `height`, `lo`, `hi`.

- [ ] **Step 1: Write the failing test**

Append to `test_progress.py`:

```python
class TestPatternTrends(unittest.TestCase):
    def test_groups_lifts_under_their_pattern(self):
        rows = [c("2026-W30", "leg-press", 80, 3),
                c("2026-W31", "goblet-squat", 30, 10),
                c("2026-W31", "bench-press", 60, 5)]
        trends = {t["pattern"]: t for t in progress.pattern_trends(rows)}
        self.assertEqual({l["slug"] for l in trends["squat"]["lifts"]},
                         {"leg-press", "goblet-squat"})
        self.assertEqual(len(trends["h_push"]["lifts"]), 1)

    def test_names_come_from_the_engine(self):
        rows = [c("2026-W30", "leg-press", 80, 3)]
        trend = progress.pattern_trends(rows)[0]
        self.assertEqual(trend["lifts"][0]["name"], "Leg press")

    def test_unlogged_patterns_are_absent(self):
        rows = [c("2026-W30", "leg-press", 80, 3)]
        self.assertEqual([t["pattern"] for t in progress.pattern_trends(rows)],
                         ["squat"])


class TestSparkline(unittest.TestCase):
    def test_flat_series_sits_mid_height(self):
        chart = progress.sparkline([50.0, 50.0], width=100, height=50)
        ys = {round(y) for x, y in chart["segments"][0]}
        self.assertEqual(ys, {25})

    def test_rising_series_goes_up_the_screen(self):
        chart = progress.sparkline([10.0, 20.0], width=100, height=50)
        (_, y0), (_, y1) = chart["segments"][0]
        self.assertLess(y1, y0)   # SVG y grows downward

    def test_none_breaks_the_line_into_segments(self):
        chart = progress.sparkline([1.0, 2.0, None, 3.0, 4.0])
        self.assertEqual(len(chart["segments"]), 2)

    def test_too_few_points_draws_nothing(self):
        self.assertEqual(progress.sparkline([5.0])["segments"], [])
        self.assertEqual(progress.sparkline([])["segments"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: FAIL with `AttributeError: module 'progress' has no attribute 'pattern_trends'`

- [ ] **Step 3: Write the implementation**

Append to `progress.py`:

```python
def _slug_names():
    out = {}
    for levels in engine.POOLS.values():
        for pool in levels.values():
            for name, slug, _sets, _tier in pool:
                out.setdefault(slug, name)
    return out


def pattern_trends(completions):
    """Per-pattern detail: every lift as its own series, gaps left visible.

    No smoothing and no interpolation. If rotation skipped a lift for a month,
    the line should show a month-long gap, because that is what happened.
    """
    patterns, names = slug_patterns(), _slug_names()
    grouped = {}
    for slug, points in slug_series(completions).items():
        pattern = patterns.get(slug)
        if pattern:
            grouped.setdefault(pattern, []).append(
                {"slug": slug, "name": names.get(slug, slug), "points": points})

    order = [p for p in engine.PATTERN_NAMES if p in grouped]
    return [{"pattern": p, "name": engine.PATTERN_NAMES[p],
             "lifts": sorted(grouped[p], key=lambda l: l["name"])}
            for p in order]


def sparkline(values, width=260, height=48, pad=4):
    """Polyline geometry for an inline SVG chart.

    Geometry belongs here rather than in Jinja so the template stays markup and
    the maths stays testable. None values break the line into segments instead
    of dropping it to the floor.
    """
    numbers = [v for v in values if v is not None]
    if len(numbers) < 2 or len(values) < 2:
        return {"segments": [], "width": width, "height": height,
                "lo": None, "hi": None}

    lo, hi = min(numbers), max(numbers)
    span = (hi - lo) or 1.0
    step = (width - 2 * pad) / (len(values) - 1)
    inner = height - 2 * pad

    segments, current = [], []
    for i, value in enumerate(values):
        if value is None:
            if len(current) > 1:
                segments.append(current)
            current = []
            continue
        x = pad + i * step
        # A flat series would otherwise pin to the bottom; centre it instead.
        y = (height / 2 if hi == lo
             else height - pad - (value - lo) / span * inner)
        current.append((round(x, 1), round(y, 1)))
    if len(current) > 1:
        segments.append(current)

    return {"segments": segments, "width": width, "height": height,
            "lo": lo, "hi": hi}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_progress -v`
Expected: PASS, 41 tests.

- [ ] **Step 5: Commit**

```bash
git add progress.py test_progress.py
git commit -m "Add per-pattern trends and SVG sparkline geometry"
```

---

### Task 6: Schema and queries

**Files:**
- Modify: `db.py` (`SCHEMA`, `SCHEMA_PG`, `MIGRATIONS_SQLITE`, `MIGRATIONS_PG`, plus new query functions)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `db.completions_all(conn, subscriber_id) -> list[dict]`, `db.bodyweights(conn, subscriber_id) -> list[dict]`, `db.latest_bodyweight(conn, subscriber_id) -> float | None`, `db.log_bodyweight(conn, subscriber_id, logged_on, weight_kg) -> None`, `db.set_pinned_metric(conn, subscriber_id, metric) -> None`.

- [ ] **Step 1: Add the table to both schemas**

In `db.py`, append to `SCHEMA` (the SQLite one, after the `completions` table):

```sql
-- Optional bodyweight log. Strength means little without it: load per kg of
-- you is the number that improves when you are cutting.
CREATE TABLE IF NOT EXISTS bodyweights (
    id INTEGER PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    logged_on TEXT NOT NULL,                        -- 'YYYY-MM-DD'
    weight_kg REAL NOT NULL,
    UNIQUE (subscriber_id, logged_on)
);
```

Append the Postgres twin to `SCHEMA_PG`:

```sql
CREATE TABLE IF NOT EXISTS bodyweights (
    id SERIAL PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    logged_on TEXT NOT NULL,
    weight_kg DOUBLE PRECISION NOT NULL,
    UNIQUE (subscriber_id, logged_on)
);
```

- [ ] **Step 2: Add migrations to both lists**

Append to `MIGRATIONS_SQLITE`:

```python
    "ALTER TABLE subscribers ADD COLUMN pinned_metric TEXT DEFAULT 'strength_index'",
```

Append to `MIGRATIONS_PG` (the `IF NOT EXISTS` form, since Postgres supports it):

```python
    "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS pinned_metric TEXT DEFAULT 'strength_index'",
```

Add `pinned_metric TEXT DEFAULT 'strength_index'` to the `subscribers` table in **both** `SCHEMA` and `SCHEMA_PG` as well, so fresh databases get it without relying on the migration.

- [ ] **Step 3: Add the queries**

Append to `db.py`, after the completions section:

```python
def completions_all(conn, subscriber_id: int) -> list:
    """Every completion, oldest first — the whole history the metrics need."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM completions WHERE subscriber_id = ? ORDER BY week, day",
        (subscriber_id,)).fetchall()]


# --- bodyweight -------------------------------------------------------------

def log_bodyweight(conn, subscriber_id: int, logged_on: str,
                   weight_kg: float) -> None:
    """Record a weigh-in. Re-logging the same day overwrites it."""
    conn.execute(
        """INSERT INTO bodyweights (subscriber_id, logged_on, weight_kg)
           VALUES (?, ?, ?)
           ON CONFLICT(subscriber_id, logged_on) DO UPDATE SET
             weight_kg = excluded.weight_kg""",
        (subscriber_id, logged_on, weight_kg))
    conn.commit()


def bodyweights(conn, subscriber_id: int) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM bodyweights WHERE subscriber_id = ? ORDER BY logged_on",
        (subscriber_id,)).fetchall()]


def latest_bodyweight(conn, subscriber_id: int):
    rows = conn.execute(
        "SELECT weight_kg FROM bodyweights WHERE subscriber_id = ? "
        "ORDER BY logged_on DESC LIMIT 1", (subscriber_id,)).fetchall()
    return rows[0]["weight_kg"] if rows else None


def set_pinned_metric(conn, subscriber_id: int, metric: str) -> None:
    conn.execute("UPDATE subscribers SET pinned_metric = ? WHERE id = ?",
                 (metric, subscriber_id))
    conn.commit()
```

- [ ] **Step 4: Verify against a throwaway database**

Run:

```bash
DB_PATH=/tmp/progress-schema.db .venv/bin/python -c "
import db
conn = db.connect()
db.log_bodyweight(conn, 1, '2026-07-27', 99.4)
db.log_bodyweight(conn, 1, '2026-07-27', 99.2)   # same day overwrites
print('bodyweights:', db.bodyweights(conn, 1))
print('latest:', db.latest_bodyweight(conn, 1))
print('completions:', db.completions_all(conn, 1))
"
```

Expected: exactly one row at `99.2`, latest `99.2`, completions `[]`. One row proves the `ON CONFLICT` works; two means the `UNIQUE` constraint is missing.

- [ ] **Step 5: Commit**

```bash
rm -f /tmp/progress-schema.db
git add db.py
git commit -m "Store bodyweight and the subscriber's pinned metric"
```

---

### Task 7: Seed script

**Files:**
- Create: `scripts/seed_progress.py`

**Interfaces:**
- Consumes: `db.set_completion`, `db.log_bodyweight` from Task 6.
- Produces: a runnable script. Nothing imports it.

- [ ] **Step 1: Write the script**

Create `scripts/seed_progress.py`:

```python
"""Fill a throwaway database with plausible history, so the progress page has
something to draw. The real table has a handful of rows and you cannot eyeball
a chart of nothing.

    DB_PATH=/tmp/seed.db .venv/bin/python scripts/seed_progress.py you@example.com

Refuses to touch gymdigest.db.
"""

import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db      # noqa: E402
import engine  # noqa: E402
import progress  # noqa: E402

WEEKS = 26
START_WEIGHT, END_WEIGHT = 100.0, 92.0


def main(email):
    if "gymdigest.db" in os.environ.get("DB_PATH", "gymdigest.db"):
        sys.exit("Refusing to seed the real database. Set DB_PATH.")

    random.seed(7)                      # reproducible history
    conn = db.connect()
    sub = db.get_by_email(conn, email)
    if not sub:
        sys.exit(f"No subscriber {email}. Sign up in the app first.")

    prefs = {"days": sub["days_per_week"], "experience": sub["experience"],
             "include_run": bool(sub["include_run"]),
             "equipment": db.sub_equipment(sub)}

    today = datetime.date.today()
    for offset in range(WEEKS, 0, -1):
        day_one = today - datetime.timedelta(weeks=offset)
        week_key = progress.date_to_week(day_one)
        plan = progress.planned_week(prefs, int(week_key[6:]))

        # Bodyweight drifts down, with noise, roughly weekly.
        share = (WEEKS - offset) / WEEKS
        weight = START_WEIGHT + (END_WEIGHT - START_WEIGHT) * share
        db.log_bodyweight(conn, sub["id"],
                          day_one.isoformat(), round(weight + random.uniform(-0.4, 0.4), 1))

        for index, day in enumerate(plan["days"], start=1):
            if random.random() < 0.15:          # a missed session now and then
                continue
            for exercise in day["exercises"]:
                sets = engine.prescribed_sets(exercise["sets"]) or 3
                # Loads creep up ~15% over the six months, plus session noise.
                base = 20 + (hash(exercise["slug"]) % 60)
                load = base * (1 + 0.15 * share) * random.uniform(0.97, 1.03)
                db.set_completion(conn, sub["id"], week_key, index,
                                  exercise["slug"],
                                  weight_kg=round(load / 2.5) * 2.5,
                                  reps=random.choice([5, 8, 10, 12]),
                                  sets=sets)

    print(f"Seeded {WEEKS} weeks for {email} into {os.environ['DB_PATH']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.exit("Pass an email."))
```

- [ ] **Step 2: Create a subscriber and seed against it**

Run:

```bash
export DB_PATH=/tmp/seed.db
.venv/bin/python -c "
import db
conn = db.connect()
# upsert_subscriber(conn, email, days, experience, include_run, plan, equipment)
db.upsert_subscriber(conn, 'seed@example.com', 4, 'intermediate', False,
                     'monthly', 'full')
db.set_status(conn, 'seed@example.com', 'active')
db.set_password(conn, 'seed@example.com', 'seedpassword')
print(db.get_by_email(conn, 'seed@example.com')['email'])
"
.venv/bin/python scripts/seed_progress.py seed@example.com
```

Expected: `Seeded 26 weeks for seed@example.com into /tmp/seed.db`. The status and password are set so you can actually sign in as this account in Task 8.

- [ ] **Step 3: Check the metrics produce sane numbers**

Run:

```bash
DB_PATH=/tmp/seed.db .venv/bin/python -c "
import datetime, db, progress
conn = db.connect()
sub = db.get_by_email(conn, 'seed@example.com')
rows = db.completions_all(conn, sub['id'])
week = progress.date_to_week(datetime.date.today())
idx = progress.strength_index(rows, week)
print('points:', len(idx), 'latest index:', round(idx[-1][1], 1))
print('relative:', progress.relative_strength(
    rows, db.latest_bodyweight(conn, sub['id']), week)['total'])
"
```

Expected: 20+ points, a latest index somewhere near 105–125 (rising, since seeded loads creep up), and a relative-strength total above zero. An index pinned at exactly 100 means the ≥2-logs rule or the baseline is wrong.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_progress.py
git commit -m "Seed plausible training history for eyeballing the charts"
```

---

### Task 8: The progress page

**Files:**
- Create: `templates/progress.html`
- Modify: `app.py` (new route after `/account/plan`), `templates/_nav.html`, `static/style.css`

**Interfaces:**
- Consumes: everything from `progress.py` (Tasks 1–5) and `db.completions_all`, `db.latest_bodyweight` (Task 6).
- Produces: `app._progress_context(sub) -> dict` — reused by the API in Task 10.

- [ ] **Step 1: Add the context builder and route to `app.py`**

Add `import progress` alongside the existing `import engine`, then add after the `/account/plan` route:

```python
def _progress_context(sub) -> dict:
    """Every metric for one subscriber. Shared by the page and the API."""
    conn = db.connect()
    rows = db.completions_all(conn, sub["id"])
    bodyweight = db.latest_bodyweight(conn, sub["id"])
    week = progress.date_to_week(datetime.date.today())
    prefs = {"days": sub["days_per_week"], "experience": sub["experience"],
             "include_run": bool(sub["include_run"]),
             "equipment": db.sub_equipment(sub)}

    index = progress.strength_index(rows, week)
    # The Index emits None for any week with nothing qualifying in its window.
    # Show the most recent real reading and date it, rather than inventing a
    # number for someone who trained in June and stopped.
    index_latest = next(((w, v) for w, v in reversed(index) if v is not None),
                        None)
    pinned = sub["pinned_metric"] if "pinned_metric" in sub.keys() else None
    return {
        "sub": sub, "active": "progress", "logged": bool(rows),
        "bodyweight": bodyweight, "current_week": week,
        "strength_index": index, "index_latest": index_latest,
        "index_chart": progress.sparkline([v for _w, v in index]),
        "relative": progress.relative_strength(rows, bodyweight, week),
        "consistency": progress.consistency(rows, prefs, week),
        "tonnage": progress.tonnage(rows, week),
        "trends": progress.pattern_trends(rows),
        "pattern_names": engine.PATTERN_NAMES,
        "metrics": progress.METRICS,
        # Strength needs two logs of one lift; consistency works from day one,
        # so it carries the hero until the Index has something true to say.
        "pinned": (pinned or "strength_index") if index_latest else "consistency",
    }


@app.get("/account/progress", response_class=HTMLResponse)
def progress_page(request: Request):
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "progress.html",
                                      _progress_context(sub))
```

- [ ] **Step 2: Create the template**

**There is no base template.** Every template here is a standalone HTML document — `plan.html` starts at `<!doctype html>`. Copy its `<!doctype>`/`<head>`/opening `<body>` scaffold verbatim into `templates/progress.html`, change the `<title>` to "Progress — Sunday Strength", and put the markup below inside the same content wrapper `plan.html` uses. Close the document the same way it does.

```html
{% include "_nav.html" %}

<h1>Progress</h1>

{% if not logged %}
  <p class="empty">Nothing logged yet. Tick off a few exercises on
    <a href="/account/plan">this week's plan</a> and your progress will start
    building here.</p>
{% else %}

  {# A chart nobody can read is decoration. The SVG carries a title, and the
     numbers behind it stay reachable as a real table. #}
  {% macro chart(spark, label, series) %}
    {% if spark.segments %}
    <svg class="spark" viewBox="0 0 {{ spark.width }} {{ spark.height }}"
         width="{{ spark.width }}" height="{{ spark.height }}" role="img">
      <title>{{ label }}</title>
      {% for segment in spark.segments %}
      <polyline fill="none" stroke="currentColor" stroke-width="2"
        points="{% for x, y in segment %}{{ x }},{{ y }} {% endfor %}"/>
      {% endfor %}
    </svg>
    <table class="visually-hidden">
      <caption>{{ label }}</caption>
      <tr><th>Week</th><th>Value</th></tr>
      {% for week, value in series %}{% if value is not none %}
      <tr><td>{{ week }}</td><td>{{ '%.0f'|format(value) }}</td></tr>
      {% endif %}{% endfor %}
    </table>
    {% endif %}
  {% endmacro %}

  <section class="card hero">
    {% if pinned == 'strength_index' and index_latest %}
      <h2>Strength Index</h2>
      <p class="big">{{ '%.0f'|format(index_latest[1]) }}</p>
      <p class="sub">vs. your first logged session (100){%
        if index_latest[0] != current_week %} — as of
        {{ index_latest[0] }}{% endif %}</p>
      {{ chart(index_chart, 'Strength Index over time', strength_index) }}
    {% elif pinned == 'relative_strength' and relative %}
      <h2>Relative strength</h2>
      <p class="big">{{ '%.2f'|format(relative.total) }}&times;</p>
      <p class="sub">total main-lift load per kg of bodyweight</p>
    {% elif pinned == 'consistency' %}
      <h2>Consistency</h2>
      <p class="big">{{ consistency.streak }}</p>
      <p class="sub">week{{ '' if consistency.streak == 1 else 's' }} hitting
        every session</p>
    {% else %}
      <h2>Weekly volume</h2>
      <p class="big">{{ '%.0f'|format(tonnage.weeks[-1].value) }}</p>
      <p class="sub">{{ tonnage.unit }} lifted last week</p>
    {% endif %}

    <form method="post" action="/account/progress/pin" class="pins">
      {% for metric in metrics %}
      <button name="metric" value="{{ metric }}"
        class="pin {% if metric == pinned %}on{% endif %}">
        {{ metric.replace('_', ' ')|capitalize }}</button>
      {% endfor %}
    </form>
  </section>

  {% if not index_latest %}
  <section class="card">
    <h2>Strength Index</h2>
    <p class="empty">Log the same exercise twice and this starts working. It
      measures every lift against your own first attempt, so swapping exercises
      week to week doesn't break it.</p>
  </section>
  {% endif %}

  <section class="card">
    <h2>Relative strength</h2>
    {% if not bodyweight %}
      <p class="empty">Add your bodyweight and this shows what you lift per kg
        of you — the number that keeps improving while you're losing weight.</p>
      <form method="post" action="/account/bodyweight" class="inline">
        <label>Bodyweight (kg)
          <input type="number" name="weight_kg" step="0.1"
                 min="30" max="300" required></label>
        <button type="submit">Save</button>
      </form>
    {% else %}
      <ul class="lifts">
        {% for lift in relative.lifts %}
        <li>{{ pattern_names[lift.pattern] }}
          <strong>{{ '%.2f'|format(lift.ratio) }}&times;</strong>
          bodyweight</li>
        {% endfor %}
      </ul>
      {% if relative.missing %}
      <p class="sub">No recent log for
        {{ relative.missing|map('replace', '_', ' ')|join(', ') }} —
        not counted in the total.</p>
      {% endif %}
      <form method="post" action="/account/bodyweight" class="inline">
        <label>Update bodyweight (kg)
          <input type="number" name="weight_kg" step="0.1" min="30" max="300"
                 value="{{ bodyweight }}" required></label>
        <button type="submit">Save</button>
      </form>
    {% endif %}
  </section>

  <section class="card">
    <h2>Consistency</h2>
    <p>{{ consistency.weeks[-1].done }} of
      {{ consistency.weeks[-1].planned }} sessions this week.
      Streak: {{ consistency.streak }}.</p>
  </section>

  <section class="card">
    <h2>Weekly volume</h2>
    <p>{{ '%.0f'|format(tonnage.weeks[-1].value) }} {{ tonnage.unit }} last
      week.</p>
  </section>

  {% for trend in trends %}
  <section class="card">
    <h2>{{ trend.name }}</h2>
    <table class="trend">
      <tr><th>Lift</th><th>First</th><th>Latest</th></tr>
      {% for lift in trend.lifts %}
      <tr><td>{{ lift.name }}</td>
        <td>{{ '%.0f'|format(lift.points[0][1]) }}</td>
        <td>{{ '%.0f'|format(lift.points[-1][1]) }}</td></tr>
      {% endfor %}
    </table>
  </section>
  {% endfor %}
{% endif %}
```

Do not restructure the other templates to introduce a base — that is out of scope.

- [ ] **Step 3: Add the pin route to `app.py`**

```python
@app.post("/account/progress/pin")
def progress_pin(request: Request, metric: str = Form(...)):
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    if metric not in progress.METRICS:
        raise HTTPException(400, "Unknown metric.")
    db.set_pinned_metric(db.connect(), sub["id"], metric)
    return RedirectResponse("/account/progress", status_code=303)
```

- [ ] **Step 4: Add the bodyweight route to `app.py`**

The template above posts to this, so the page is not testable without it.

```python
@app.post("/account/bodyweight")
def bodyweight_log(request: Request, weight_kg: float = Form(...)):
    sub = _current_sub(request)
    if not sub:
        return RedirectResponse("/login", status_code=303)
    # A stray 1000 would flatten every relative-strength reading at once, and
    # the browser's min/max is only a hint — anything can POST here.
    if not (progress.MIN_BODYWEIGHT_KG <= weight_kg <= progress.MAX_BODYWEIGHT_KG):
        raise HTTPException(400, "Bodyweight must be between 30 and 300 kg.")
    db.log_bodyweight(db.connect(), sub["id"],
                      datetime.date.today().isoformat(), weight_kg)
    return RedirectResponse("/account/progress", status_code=303)
```

- [ ] **Step 5: Add the nav link**

In `templates/_nav.html`, after the "This week" link:

```html
    <a href="/account/progress" {% if active == 'progress' %}class="on"{% endif %}>Progress</a>
```

- [ ] **Step 6: Add styles**

Append to `static/style.css`, using the existing custom properties rather than new colour literals:

The palette is defined in `:root` at the top of `style.css`. The accent is `--acc` (not `--accent`); `--muted`, `--line` and `--ink` are as named.

```css
.hero .big { font-size: 3rem; margin: .2rem 0; line-height: 1; }
.hero .sub, .card .sub { color: var(--muted); font-size: .9rem; }
.spark { display: block; margin-top: .6rem; color: var(--acc); }
.pins { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: 1rem; }
.pin { font-size: .8rem; padding: .3rem .6rem; }
.pin.on { font-weight: 600; }
.card .empty { color: var(--muted); }
.lifts { list-style: none; padding: 0; }
.trend { width: 100%; border-collapse: collapse; }
.trend th, .trend td { text-align: left; padding: .3rem 0;
                       border-bottom: 1px solid var(--line); }

/* Chart data, reachable by screen readers but not shown. */
.visually-hidden {
  position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
}
```

- [ ] **Step 7: Drive the real flow**

Run:

```bash
DB_PATH=/tmp/seed.db BREVO_API_KEY= RESEND_API_KEY= GMAIL_USER= \
  .venv/bin/uvicorn app:app --port 8123
```

Log in as `seed@example.com` and open `/account/progress`. Confirm:
1. The Strength Index number is not exactly 100 and the sparkline rises.
2. Relative strength lists lifts as ratios and names any missing pattern.
3. The pin buttons change the hero and survive a reload.
4. **With JavaScript disabled**, all of the above still works — every control is a real form.
5. A fresh subscriber (sign up a second address, log nothing) sees the empty state, no charts and no zeroes.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/progress.html templates/_nav.html static/style.css
git commit -m "Show progress: strength index, relative strength, consistency"
```

---


### Task 9: JSON API

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `_progress_context` (Task 8).
- Produces: `GET /api/v1/progress`.

- [ ] **Step 1: Add the endpoint**

Auth here is **not** a FastAPI `Depends`. `_require_sub(request)` returns a `(conn, sub)` tuple and raises 401 itself; it accepts either a `Bearer` API key or a session cookie. Match the other `/api/v1/` routes exactly:

```python
@app.get("/api/v1/progress")
def api_progress(request: Request):
    """Same numbers as the page, from the same function.

    Page and API computing through one path is what stops the API rotting
    unnoticed — the same reason _apply_completion is the only place a tick is
    written.
    """
    _conn, sub = _require_sub(request)
    context = _progress_context(sub)
    return {
        "strength_index": [{"week": w, "value": v}
                           for w, v in context["strength_index"]],
        "relative_strength": context["relative"],
        "consistency": context["consistency"],
        "tonnage": context["tonnage"],
        "bodyweight_kg": context["bodyweight"],
    }
```

- [ ] **Step 2: Verify it returns the same numbers as the page**

Create an API key in the account page, then:

```bash
curl -s -H "Authorization: Bearer $KEY" \
  http://127.0.0.1:8123/api/v1/progress | .venv/bin/python -m json.tool | head -30
```

Expected: the final `strength_index` value matches the number rendered in the page hero. If they differ, the page and API are not sharing a path — fix that rather than the numbers.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Expose progress metrics over the JSON API"
```

---

### Task 10: Documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Add the load-bearing rules to `CLAUDE.md`**

Under "Rules that are load-bearing":

```markdown
**Strength metrics index each lift against its own first log.** Plans rotate
exercises weekly, so raw per-exercise lines mix incomparable lifts and read as
sudden strength loss. `progress.indexed_series` converts to percentages before
anything is averaged — which also cancels the per-dumbbell logging convention.
Never average raw loads across slugs.

**`progress.py` is pure, like `engine.py`.** No database, no clock. Callers pass
the current week in. It has the project's only test file for exactly this
reason: wrong arithmetic renders as confidently as right arithmetic.

**`PER_DUMBBELL` and `BODYWEIGHT_LOADED` in `progress.py` are hand-maintained.**
The equipment tier cannot substitute — `dumbbells` is a minimum-kit marker that
single-implement lifts carry too. Adding a two-dumbbell or bodyweight-loaded
exercise to `POOLS` means adding it to the matching set, or relative strength
misreports that lift.
```

Update the "Shape of it" table with `progress.py`, and amend the testing note in "Run it" to record that `progress.py` has stdlib unittest coverage while everything else is verified by driving the flow:

```bash
.venv/bin/python -m unittest test_progress -v    # the only tests here
```

- [ ] **Step 2: Add the page to `README.md`**

Describe `/account/progress` in the product section: the five metrics, that bodyweight is optional, and that the Strength Index is measured against the subscriber's own first logged session rather than any population norm.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Document the progress page and its load-bearing rules"
```

---

## Verification checklist

Before calling this done:

- [ ] `.venv/bin/python -m unittest test_progress -v` passes, 41 tests.
- [ ] The page renders against seeded data with a rising Strength Index.
- [ ] The page renders for a subscriber with **zero** logs — empty state, no charts, no zeroes.
- [ ] The page renders for a subscriber with **one** log — Index card explains what it needs, hero falls back to consistency.
- [ ] Every control works with JavaScript disabled.
- [ ] `/api/v1/progress` returns the same latest index as the page hero.
- [ ] Bodyweight of `1000` is rejected with a 400.
- [ ] `gymdigest.db` is untouched: `git status` shows no change to it.
- [ ] After deploying to Render, the boot log shows no `migration skipped:` line for `bodyweights` or `pinned_metric`.
