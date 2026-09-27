"""Progress metrics computed from logged completions.

Pure data and functions, no I/O — the same contract engine.py holds. Nothing
here reads the database or asks what today is; callers pass the current week
in. That is what makes the arithmetic testable, and the arithmetic is the part
that fails silently.
"""

import datetime
import engine

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
