"""Weekly plan generator.

Generalised from the personal gym_plan.py: deterministic per ISO week, but now
parameterised by days-per-week (2-5), experience level, and an optional run day.
The plan for (week, days, level, run) is always the same, and consecutive weeks
rotate through the pools below so the structure stays constant while the
exercises vary.

Exercise `slug`s are our own canonical ids. Emails link to our own
/exercise/<slug> pages (see app.py), which serve public-domain instructions and
images from free-exercise-db once scripts/fetch_exercise_media.py has run.
"""

from __future__ import annotations

LEVELS = ("beginner", "intermediate", "advanced")

# ---------------------------------------------------------------------------
# Exercise pools, keyed by movement pattern then level.
# Each entry: (display name, slug, sets x reps). Week N picks
# (N + slot_index) % len(pool) so consecutive weeks differ per slot.
# ---------------------------------------------------------------------------

POOLS: dict[str, dict[str, list[tuple[str, str, str]]]] = {
    "squat": {
        "beginner": [
            ("Goblet squat", "goblet-squat", "2 x 10-12"),
            ("Leg press", "leg-press", "2 x 10-12"),
            ("Bodyweight box squat", "box-squat", "2 x 12"),
        ],
        "intermediate": [
            ("Goblet squat", "goblet-squat", "3 x 10-12"),
            ("Barbell back squat", "back-squat", "3 x 8-10"),
            ("Leg press", "leg-press", "3 x 10-12"),
        ],
        "advanced": [
            ("Barbell back squat", "back-squat", "4 x 6-8"),
            ("Front squat", "front-squat", "4 x 6-8"),
            ("Leg press", "leg-press", "3 x 8-10"),
        ],
    },
    "hinge": {
        "beginner": [
            ("Kettlebell swing", "kettlebell-swing", "2 x 15"),
            ("Hip thrust", "hip-thrust", "2 x 10-12"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "2 x 10"),
        ],
        "intermediate": [
            ("Romanian deadlift", "romanian-deadlift", "3 x 8-10"),
            ("Hip thrust", "hip-thrust", "3 x 10-12"),
            ("Kettlebell swing", "kettlebell-swing", "3 x 15"),
        ],
        "advanced": [
            ("Deadlift", "deadlift", "3 x 5"),
            ("Romanian deadlift", "romanian-deadlift", "4 x 6-8"),
            ("Barbell hip thrust", "hip-thrust", "4 x 8-10"),
        ],
    },
    "single_leg": {
        "beginner": [
            ("Dumbbell lunge", "dumbbell-lunge", "2 x 8 each leg"),
            ("Step-up", "step-up", "2 x 10 each leg"),
            ("Leg extension", "leg-extension", "2 x 12"),
        ],
        "intermediate": [
            ("Dumbbell lunge", "dumbbell-lunge", "2 x 10 each leg"),
            ("Bulgarian split squat", "bulgarian-split-squat", "2 x 8-10 each leg"),
            ("Leg extension", "leg-extension", "3 x 12"),
        ],
        "advanced": [
            ("Bulgarian split squat", "bulgarian-split-squat", "3 x 8-10 each leg"),
            ("Walking lunge", "walking-lunge", "3 x 10 each leg"),
            ("Step-up", "step-up", "3 x 8 each leg"),
        ],
    },
    "ham_curl": {
        "beginner": [
            ("Lying leg curl", "lying-leg-curl", "2 x 10-12"),
            ("Seated leg curl", "seated-leg-curl", "2 x 10-12"),
        ],
        "intermediate": [
            ("Lying leg curl", "lying-leg-curl", "3 x 10-12"),
            ("Seated leg curl", "seated-leg-curl", "3 x 10-12"),
            ("Standing calf raise", "standing-calf-raise", "3 x 12-15"),
        ],
        "advanced": [
            ("Lying leg curl", "lying-leg-curl", "3 x 10-12"),
            ("Nordic ham curl", "nordic-ham-curl", "3 x 5-8"),
            ("Seated leg curl", "seated-leg-curl", "3 x 10-12"),
        ],
    },
    "calf": {
        "beginner": [
            ("Standing calf raise", "standing-calf-raise", "2 x 12-15"),
            ("Seated calf raise", "seated-calf-raise", "2 x 15"),
        ],
        "intermediate": [
            ("Standing calf raise", "standing-calf-raise", "3 x 12-15"),
            ("Seated calf raise", "seated-calf-raise", "3 x 15"),
        ],
        "advanced": [
            ("Standing calf raise", "standing-calf-raise", "4 x 10-12"),
            ("Seated calf raise", "seated-calf-raise", "4 x 15"),
        ],
    },
    "core": {
        "beginner": [
            ("Plank", "plank", "3 x 20-30 sec"),
            ("Dead bug", "dead-bug", "3 x 6 each side"),
            ("Crunch", "crunch", "3 x 12-15"),
            ("Side plank", "side-plank", "2 x 15-20 sec each side"),
        ],
        "intermediate": [
            ("Plank", "plank", "3 x 30-45 sec"),
            ("Dead bug", "dead-bug", "3 x 8 each side"),
            ("Hanging knee raise", "hanging-knee-raise", "3 x 8-12"),
            ("Pallof press", "pallof-press", "3 x 10 each side"),
            ("Side plank", "side-plank", "3 x 20-30 sec each side"),
            ("Russian twist", "russian-twist", "3 x 10 each side"),
        ],
        "advanced": [
            ("Hanging leg raise", "hanging-leg-raise", "3 x 10-12"),
            ("Ab wheel rollout", "ab-wheel-rollout", "3 x 8-10"),
            ("Cable crunch", "cable-crunch", "3 x 12-15"),
            ("Pallof press", "pallof-press", "3 x 10 each side"),
            ("Weighted plank", "plank", "3 x 30-45 sec, plate on back"),
            ("Russian twist", "russian-twist", "3 x 12 each side, hold a plate"),
        ],
    },
    "h_push": {
        "beginner": [
            ("Machine chest press", "machine-chest-press", "2 x 10-12"),
            ("Dumbbell chest press", "dumbbell-chest-press", "2 x 10-12"),
            ("Push-up (knees are fine)", "push-up", "3 x max, leave 2 in the tank"),
        ],
        "intermediate": [
            ("Barbell bench press", "bench-press", "3 x 8-10"),
            ("Dumbbell chest press", "dumbbell-chest-press", "3 x 10-12"),
            ("Incline bench press", "incline-bench-press", "3 x 8-10"),
        ],
        "advanced": [
            ("Barbell bench press", "bench-press", "4 x 6-8"),
            ("Incline bench press", "incline-bench-press", "4 x 6-8"),
            ("Weighted dip", "bar-dip", "3 x 6-10"),
        ],
    },
    "v_push": {
        "beginner": [
            ("Seated dumbbell shoulder press", "seated-dumbbell-shoulder-press", "2 x 10-12"),
            ("Machine shoulder press", "machine-shoulder-press", "2 x 10-12"),
        ],
        "intermediate": [
            ("Overhead press", "overhead-press", "3 x 8-10"),
            ("Seated dumbbell shoulder press", "seated-dumbbell-shoulder-press", "3 x 10-12"),
        ],
        "advanced": [
            ("Overhead press", "overhead-press", "4 x 6-8"),
            ("Seated dumbbell shoulder press", "seated-dumbbell-shoulder-press", "3 x 8-10"),
            ("Push press", "push-press", "4 x 5"),
        ],
    },
    "chest_acc": {
        "beginner": [
            ("Cable chest press", "cable-chest-press", "2 x 10-12"),
            ("Push-up (knees are fine)", "push-up", "2 x max, leave 2 in the tank"),
        ],
        "intermediate": [
            ("Cable chest press", "cable-chest-press", "3 x 10-12"),
            ("Push-up", "push-up", "3 x max, leave 2 in the tank"),
            ("Bar dip", "bar-dip", "3 x 6-10"),
        ],
        "advanced": [
            ("Cable fly", "cable-fly", "3 x 12-15"),
            ("Bar dip", "bar-dip", "3 x 8-12"),
            ("Dumbbell fly", "dumbbell-fly", "3 x 10-12"),
        ],
    },
    "side_delt": {
        "beginner": [
            ("Dumbbell lateral raise", "dumbbell-lateral-raise", "2 x 12-15"),
            ("Cable lateral raise", "cable-lateral-raise", "2 x 12-15"),
        ],
        "intermediate": [
            ("Dumbbell lateral raise", "dumbbell-lateral-raise", "3 x 12-15"),
            ("Cable lateral raise", "cable-lateral-raise", "3 x 12-15"),
        ],
        "advanced": [
            ("Dumbbell lateral raise", "dumbbell-lateral-raise", "4 x 12-15"),
            ("Cable lateral raise", "cable-lateral-raise", "4 x 12-15"),
        ],
    },
    "triceps": {
        "beginner": [
            ("Tricep pushdown", "tricep-pushdown", "2 x 12"),
            ("Overhead cable tricep extension", "overhead-tricep-extension", "2 x 12"),
        ],
        "intermediate": [
            ("Tricep pushdown", "tricep-pushdown", "3 x 12"),
            ("Overhead cable tricep extension", "overhead-tricep-extension", "3 x 12"),
            ("Lying tricep extension", "lying-tricep-extension", "3 x 10-12"),
        ],
        "advanced": [
            ("Close-grip bench press", "close-grip-bench-press", "3 x 8-10"),
            ("Lying tricep extension", "lying-tricep-extension", "3 x 10-12"),
            ("Tricep pushdown", "tricep-pushdown", "3 x 12-15"),
        ],
    },
    "row": {
        "beginner": [
            ("Seated machine row", "seated-machine-row", "2 x 10-12"),
            ("Seated cable row", "seated-cable-row", "2 x 10-12"),
            ("One-arm dumbbell row", "dumbbell-row", "2 x 10 each arm"),
        ],
        "intermediate": [
            ("Seated machine row", "seated-machine-row", "3 x 10-12"),
            ("Barbell row", "barbell-row", "3 x 8-10"),
            ("One-arm dumbbell row", "dumbbell-row", "3 x 10 each arm"),
        ],
        "advanced": [
            ("Barbell row", "barbell-row", "4 x 6-8"),
            ("Chest-supported row", "chest-supported-row", "3 x 8-10"),
            ("One-arm dumbbell row", "dumbbell-row", "3 x 8-10 each arm"),
        ],
    },
    "v_pull": {
        "beginner": [
            ("Lat pulldown", "lat-pulldown", "2 x 10-12"),
            ("Assisted pull-up machine", "assisted-pull-up", "2 x 8-10"),
        ],
        "intermediate": [
            ("Lat pulldown", "lat-pulldown", "3 x 10-12"),
            ("Pull-up (band-assisted is fine)", "pull-up", "3 x max"),
        ],
        "advanced": [
            ("Weighted pull-up", "pull-up", "4 x 5-8"),
            ("Lat pulldown", "lat-pulldown", "3 x 8-10"),
            ("Chin-up", "chin-up", "3 x max"),
        ],
    },
    "rear_delt": {
        "beginner": [
            ("Face pull", "face-pull", "2 x 12-15"),
            ("Reverse machine fly", "reverse-machine-fly", "2 x 12-15"),
        ],
        "intermediate": [
            ("Face pull", "face-pull", "3 x 12-15"),
            ("Reverse dumbbell fly", "reverse-dumbbell-fly", "3 x 12-15"),
        ],
        "advanced": [
            ("Face pull", "face-pull", "3 x 12-15"),
            ("Reverse dumbbell fly", "reverse-dumbbell-fly", "4 x 12-15"),
        ],
    },
    "biceps": {
        "beginner": [
            ("Dumbbell curl", "dumbbell-curl", "2 x 10-12"),
            ("Hammer curl", "hammer-curl", "2 x 10-12"),
        ],
        "intermediate": [
            ("Dumbbell curl", "dumbbell-curl", "3 x 10-12"),
            ("Barbell curl", "barbell-curl", "3 x 10"),
            ("Hammer curl", "hammer-curl", "3 x 10-12"),
        ],
        "advanced": [
            ("Barbell curl", "barbell-curl", "3 x 8-10"),
            ("Incline dumbbell curl", "incline-dumbbell-curl", "3 x 10-12"),
            ("Hammer curl", "hammer-curl", "3 x 10-12"),
        ],
    },
}

# Day templates: ordered movement patterns. Every day ends with a core slot;
# beginners get 3 main slots + core (see generate_plan).
LEGS = ["squat", "hinge", "single_leg", "ham_curl", "core"]
PUSH = ["h_push", "v_push", "chest_acc", "side_delt", "triceps", "core"]
PULL = ["v_pull", "row", "rear_delt", "biceps", "core"]
UPPER_A = ["h_push", "row", "v_push", "v_pull", "biceps", "core"]
UPPER_B = ["v_push", "v_pull", "h_push", "row", "triceps", "core"]
LOWER = ["squat", "hinge", "single_leg", "calf", "core"]
FULL_A = ["squat", "h_push", "row", "core"]
FULL_B = ["hinge", "v_push", "v_pull", "single_leg", "core"]

SPLITS: dict[int, list[tuple[str, list[str]]]] = {
    2: [("Full body A", FULL_A), ("Full body B", FULL_B)],
    3: [("Legs & core", LEGS), ("Push (chest, shoulders, triceps) & core", PUSH),
        ("Pull (back, biceps) & core", PULL)],
    4: [("Upper body 1", UPPER_A), ("Lower body 1", LOWER),
        ("Upper body 2", UPPER_B), ("Lower body 2", LOWER)],
    5: [("Legs & core", LEGS), ("Push (chest, shoulders, triceps) & core", PUSH),
        ("Pull (back, biceps) & core", PULL), ("Upper body", UPPER_A),
        ("Lower body", LOWER)],
}

RUNS = [
    "Easy run - 30 min at a pace where you could hold a conversation.",
    "Intervals - 10 min easy, then 6 x (2 min brisk / 2 min easy), 5 min easy to finish.",
    "Long easy run - 40-45 min, slow and comfortable. Walking breaks are allowed.",
    "Hills or treadmill incline - 10 min easy, then 8 x (1 min uphill hard / 2 min easy).",
]

NOTES = {
    "beginner": [
        "Spread the days out - never two hard days back to back if you can help it.",
        "Warm up: 5 min brisk walk or row, then 1 light set of the first exercise.",
        "Pick a weight where the last 2 reps feel hard but doable. Rest 60-90 sec between sets.",
        "Form beats load. If you're unsure about a movement, tap it in the email for a demo.",
        "Every session finishes with core - it's five minutes, don't skip it.",
        "Short on time? Do the first three exercises and leave - that still counts.",
    ],
    "intermediate": [
        "Spread the days out (e.g. Mon / Wed / Fri, run at the weekend).",
        "Warm up: 5 min brisk walk/row + 1 light set of the first exercise.",
        "Pick a load where the last 2 reps feel hard but doable. Rest 60-90 sec.",
        "Short on time? Do the first three exercises and leave - that's still a session.",
    ],
    "advanced": [
        "Add a little weight or a rep versus last time on the first two lifts - that's the whole game.",
        "Warm up properly on the main lift: 2-3 ramping sets before your work sets.",
        "Rest 2-3 min on the big compounds, 60-90 sec on accessories.",
        "Short on time? Keep the first two lifts heavy and cut the accessories.",
    ],
}


def generate_plan(week: int, days_per_week: int, experience: str,
                  include_run: bool) -> dict:
    """Return a structured plan dict for one week."""
    if days_per_week not in SPLITS:
        raise ValueError(f"days_per_week must be one of {sorted(SPLITS)}")
    if experience not in LEVELS:
        raise ValueError(f"experience must be one of {LEVELS}")

    days = []
    for d, (title, patterns) in enumerate(SPLITS[days_per_week]):
        if experience == "beginner":
            # 3 main movements + always finish with core
            patterns = [p for p in patterns if p != "core"][:3] + ["core"]
        exercises = []
        for i, pattern in enumerate(patterns):
            pool = POOLS[pattern][experience]
            # d * 2 offsets repeated templates (e.g. Upper 1 vs Upper 2)
            name, slug, sets = pool[(week + i + d * 2) % len(pool)]
            exercises.append({"name": name, "slug": slug, "sets": sets})
        days.append({"title": f"Day {d + 1} - {title}", "exercises": exercises})

    return {
        "week": week,
        "days": days,
        "run": RUNS[week % len(RUNS)] if include_run else None,
        "notes": NOTES[experience],
    }


def plan_text(plan: dict, exercise_url=lambda slug: "") -> str:
    """Plain-text rendering (email text part, CLI preview)."""
    gym_days = len(plan["days"])
    header = f"{gym_days} gym days" + (" + 1 run" if plan["run"] else "")
    lines = [f"Your plan - week {plan['week']} ({header})", ""]
    for day in plan["days"]:
        lines.append(day["title"])
        for ex in day["exercises"]:
            url = exercise_url(ex["slug"])
            suffix = f"  {url}" if url else ""
            lines.append(f"  - {ex['name']} - {ex['sets']}{suffix}")
        lines.append("")
    if plan["run"]:
        lines.append(f"Day {gym_days + 1} - Run")
        lines.append(f"  - {plan['run']}")
        lines.append("")
    lines.append("How to run the week:")
    lines.extend(f"- {n}" for n in plan["notes"])
    return "\n".join(lines)


# Site-facing grouping: everything rolls up to Legs / Push / Pull / Core.
BODY_PARTS = {
    "squat": "legs", "hinge": "legs", "single_leg": "legs",
    "ham_curl": "legs", "calf": "legs",
    "h_push": "push", "v_push": "push", "chest_acc": "push",
    "side_delt": "push", "triceps": "push",
    "row": "pull", "v_pull": "pull", "rear_delt": "pull", "biceps": "pull",
    "core": "core",
}
PART_ORDER = ["legs", "push", "pull", "core"]
PART_NAMES = {"legs": "Legs", "push": "Push", "pull": "Pull", "core": "Core"}


def flat_library() -> list[dict]:
    """Every exercise as a flat row: name, slug, sets, level, body part.

    Ordered legs -> push -> pull -> core, for the filterable /exercises pages.
    """
    rows = []
    for part in PART_ORDER:
        for pattern, groups in POOLS.items():
            if BODY_PARTS[pattern] != part:
                continue
            for level in LEVELS:
                for name, slug, sets in groups[level]:
                    rows.append({"name": name, "slug": slug, "sets": sets,
                                 "level": level, "part": part})
    return rows


PATTERN_NAMES = {
    "squat": "Squat pattern",
    "hinge": "Hip hinge (deadlifts & thrusts)",
    "single_leg": "Single-leg work",
    "ham_curl": "Hamstring curls",
    "calf": "Calves",
    "core": "Core",
    "h_push": "Horizontal push (chest)",
    "v_push": "Vertical push (shoulders)",
    "chest_acc": "Chest accessories",
    "side_delt": "Side delts",
    "triceps": "Triceps",
    "row": "Rows (mid-back)",
    "v_pull": "Vertical pull (lats)",
    "rear_delt": "Rear delts & face pulls",
    "biceps": "Biceps",
}


def library() -> list[dict]:
    """Full exercise library grouped by movement pattern, for /exercises."""
    return [{"pattern": PATTERN_NAMES[p],
             "levels": [{"level": lvl, "exercises": [
                 {"name": n, "slug": s, "sets": sets}
                 for n, s, sets in POOLS[p][lvl]]} for lvl in LEVELS]}
            for p in PATTERN_NAMES]


def all_slugs() -> set[str]:
    """Every exercise slug used anywhere (for media fetching and page checks)."""
    return {slug
            for pattern in POOLS.values()
            for pool in pattern.values()
            for _, slug, _ in pool}


if __name__ == "__main__":
    import argparse
    import datetime

    p = argparse.ArgumentParser()
    p.add_argument("--week", type=int,
                   default=datetime.date.today().isocalendar()[1])
    p.add_argument("--days", type=int, default=3, choices=sorted(SPLITS))
    p.add_argument("--level", default="intermediate", choices=LEVELS)
    p.add_argument("--no-run", action="store_true")
    args = p.parse_args()
    print(plan_text(generate_plan(args.week, args.days, args.level,
                                  not args.no_run)))
