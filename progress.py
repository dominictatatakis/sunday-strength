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
