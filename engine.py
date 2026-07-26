"""Weekly plan generator.

Generalised from the personal gym_plan.py: deterministic per ISO week, but now
parameterised by days-per-week (2-5), experience level, available equipment,
and an optional run day. The plan for (week, days, level, equipment, run) is
always the same, and consecutive weeks rotate through the pools below so the
structure stays constant while the exercises vary.

Every exercise is tagged with the *minimum* equipment it needs, and each pool
carries at least one option per level for each tier, so a bodyweight-only
subscriber gets the same week shape as someone in a full gym. ALTERNATIVES
gives each movement a ranked list of swaps for when the machine is taken.

Exercise `slug`s are our own canonical ids. Emails link to our own
/exercise/<slug> pages (see app.py), which serve public-domain instructions and
images from free-exercise-db once scripts/fetch_exercise_media.py has run.
"""

from __future__ import annotations

LEVELS = ("beginner", "intermediate", "advanced")

# Equipment tiers, least to most equipped. Each tier includes everything below
# it: a full gym can do the dumbbell and bodyweight movements too.
EQUIPMENT = ("bodyweight", "dumbbells", "full")
EQUIPMENT_RANK = {tier: i for i, tier in enumerate(EQUIPMENT)}
EQUIPMENT_NAMES = {
    "bodyweight": "Bodyweight only",
    "dumbbells": "Dumbbells / home weights",
    "full": "Full gym (machines, cables, barbells)",
}

# ---------------------------------------------------------------------------
# Exercise pools, keyed by movement pattern then level.
# Each entry: (display name, slug, sets x reps, minimum equipment). Week N picks
# (N + slot_index) % len(pool) so consecutive weeks differ per slot; the pool is
# filtered to the subscriber's equipment first.
# ---------------------------------------------------------------------------

POOLS: dict[str, dict[str, list[tuple[str, str, str, str]]]] = {
    "squat": {
        "beginner": [
            ("Goblet squat", "goblet-squat", "2 x 10-12", "dumbbells"),
            ("Leg press", "leg-press", "2 x 10-12", "full"),
            ("Bodyweight box squat", "box-squat", "2 x 12", "bodyweight"),
        ],
        "intermediate": [
            ("Goblet squat", "goblet-squat", "3 x 10-12", "dumbbells"),
            ("Barbell back squat", "back-squat", "3 x 8-10", "full"),
            ("Leg press", "leg-press", "3 x 10-12", "full"),
            ("Bodyweight squat, 3 sec down", "box-squat", "3 x 15-20", "bodyweight"),
        ],
        "advanced": [
            ("Barbell back squat", "back-squat", "4 x 6-8", "full"),
            ("Front squat", "front-squat", "4 x 6-8", "full"),
            ("Leg press", "leg-press", "3 x 8-10", "full"),
            ("Goblet squat", "goblet-squat", "4 x 10-12", "dumbbells"),
            ("Bodyweight squat, 3 sec down", "box-squat", "4 x 20-25", "bodyweight"),
        ],
    },
    "hinge": {
        "beginner": [
            ("Kettlebell swing", "kettlebell-swing", "2 x 15", "dumbbells"),
            ("Glute bridge", "hip-thrust", "2 x 12-15", "bodyweight"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "2 x 10", "dumbbells"),
        ],
        "intermediate": [
            ("Romanian deadlift", "romanian-deadlift", "3 x 8-10", "full"),
            ("Hip thrust", "hip-thrust", "3 x 10-12", "full"),
            ("Kettlebell swing", "kettlebell-swing", "3 x 15", "dumbbells"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "3 x 10-12", "dumbbells"),
            ("Single-leg glute bridge", "hip-thrust", "3 x 12 each side", "bodyweight"),
        ],
        "advanced": [
            ("Deadlift", "deadlift", "3 x 5", "full"),
            ("Romanian deadlift", "romanian-deadlift", "4 x 6-8", "full"),
            ("Barbell hip thrust", "hip-thrust", "4 x 8-10", "full"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "4 x 8-10", "dumbbells"),
            ("Single-leg glute bridge", "hip-thrust", "4 x 15 each side", "bodyweight"),
        ],
    },
    "single_leg": {
        "beginner": [
            ("Dumbbell lunge", "dumbbell-lunge", "2 x 8 each leg", "dumbbells"),
            ("Step-up", "step-up", "2 x 10 each leg", "bodyweight"),
            ("Leg extension", "leg-extension", "2 x 12", "full"),
        ],
        "intermediate": [
            ("Dumbbell lunge", "dumbbell-lunge", "2 x 10 each leg", "dumbbells"),
            ("Bulgarian split squat", "bulgarian-split-squat", "2 x 8-10 each leg", "bodyweight"),
            ("Leg extension", "leg-extension", "3 x 12", "full"),
            ("Walking lunge", "walking-lunge", "3 x 12 each leg", "bodyweight"),
        ],
        "advanced": [
            ("Bulgarian split squat", "bulgarian-split-squat", "3 x 8-10 each leg", "bodyweight"),
            ("Walking lunge", "walking-lunge", "3 x 10 each leg", "bodyweight"),
            ("Step-up", "step-up", "3 x 8 each leg", "bodyweight"),
            ("Dumbbell lunge", "dumbbell-lunge", "3 x 10 each leg", "dumbbells"),
        ],
    },
    "ham_curl": {
        "beginner": [
            ("Lying leg curl", "lying-leg-curl", "2 x 10-12", "full"),
            ("Seated leg curl", "seated-leg-curl", "2 x 10-12", "full"),
            ("Glute bridge", "hip-thrust", "2 x 15", "bodyweight"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "2 x 10-12", "dumbbells"),
        ],
        "intermediate": [
            ("Lying leg curl", "lying-leg-curl", "3 x 10-12", "full"),
            ("Seated leg curl", "seated-leg-curl", "3 x 10-12", "full"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "3 x 10-12", "dumbbells"),
            ("Single-leg glute bridge", "hip-thrust", "3 x 12 each side", "bodyweight"),
        ],
        "advanced": [
            ("Lying leg curl", "lying-leg-curl", "3 x 10-12", "full"),
            ("Nordic ham curl", "nordic-ham-curl", "3 x 5-8", "bodyweight"),
            ("Seated leg curl", "seated-leg-curl", "3 x 10-12", "full"),
            ("Dumbbell Romanian deadlift", "dumbbell-romanian-deadlift", "4 x 8-10", "dumbbells"),
        ],
    },
    "calf": {
        "beginner": [
            ("Standing calf raise", "standing-calf-raise", "2 x 12-15", "bodyweight"),
            ("Seated calf raise", "seated-calf-raise", "2 x 15", "full"),
        ],
        "intermediate": [
            ("Standing calf raise", "standing-calf-raise", "3 x 12-15", "bodyweight"),
            ("Seated calf raise", "seated-calf-raise", "3 x 15", "full"),
            ("Dumbbell calf raise", "standing-calf-raise", "3 x 15", "dumbbells"),
        ],
        "advanced": [
            ("Standing calf raise", "standing-calf-raise", "4 x 10-12", "bodyweight"),
            ("Seated calf raise", "seated-calf-raise", "4 x 15", "full"),
            ("Single-leg calf raise", "standing-calf-raise", "4 x 12-15 each leg", "bodyweight"),
        ],
    },
    "core": {
        "beginner": [
            ("Plank", "plank", "3 x 20-30 sec", "bodyweight"),
            ("Dead bug", "dead-bug", "3 x 6 each side", "bodyweight"),
            ("Crunch", "crunch", "3 x 12-15", "bodyweight"),
            ("Side plank", "side-plank", "2 x 15-20 sec each side", "bodyweight"),
        ],
        "intermediate": [
            ("Plank", "plank", "3 x 30-45 sec", "bodyweight"),
            ("Dead bug", "dead-bug", "3 x 8 each side", "bodyweight"),
            ("Hanging knee raise", "hanging-knee-raise", "3 x 8-12", "full"),
            ("Pallof press", "pallof-press", "3 x 10 each side", "full"),
            ("Side plank", "side-plank", "3 x 20-30 sec each side", "bodyweight"),
            ("Russian twist", "russian-twist", "3 x 10 each side", "bodyweight"),
        ],
        "advanced": [
            ("Hanging leg raise", "hanging-leg-raise", "3 x 10-12", "full"),
            ("Ab wheel rollout", "ab-wheel-rollout", "3 x 8-10", "dumbbells"),
            ("Cable crunch", "cable-crunch", "3 x 12-15", "full"),
            ("Pallof press", "pallof-press", "3 x 10 each side", "full"),
            ("Weighted plank", "plank", "3 x 30-45 sec, plate on back", "dumbbells"),
            ("Russian twist", "russian-twist", "3 x 12 each side, hold a plate", "dumbbells"),
            ("Plank", "plank", "3 x 45-60 sec", "bodyweight"),
            ("Side plank", "side-plank", "3 x 30-45 sec each side", "bodyweight"),
        ],
    },
    "h_push": {
        "beginner": [
            ("Machine chest press", "machine-chest-press", "2 x 10-12", "full"),
            ("Dumbbell chest press", "dumbbell-chest-press", "2 x 10-12", "dumbbells"),
            ("Push-up (knees are fine)", "push-up", "3 x max, leave 2 in the tank", "bodyweight"),
        ],
        "intermediate": [
            ("Barbell bench press", "bench-press", "3 x 8-10", "full"),
            ("Dumbbell chest press", "dumbbell-chest-press", "3 x 10-12", "dumbbells"),
            ("Incline bench press", "incline-bench-press", "3 x 8-10", "full"),
            ("Push-up", "push-up", "3 x max, leave 2 in the tank", "bodyweight"),
        ],
        "advanced": [
            ("Barbell bench press", "bench-press", "4 x 6-8", "full"),
            ("Incline bench press", "incline-bench-press", "4 x 6-8", "full"),
            ("Weighted dip", "bar-dip", "3 x 6-10", "full"),
            ("Dumbbell chest press", "dumbbell-chest-press", "4 x 8-10", "dumbbells"),
            ("Decline push-up, feet raised", "push-up", "4 x max, leave 1 in the tank", "bodyweight"),
        ],
    },
    "v_push": {
        "beginner": [
            ("Seated dumbbell shoulder press", "seated-dumbbell-shoulder-press", "2 x 10-12", "dumbbells"),
            ("Machine shoulder press", "machine-shoulder-press", "2 x 10-12", "full"),
            ("Pike push-up", "pike-push-up", "2 x 8-10", "bodyweight"),
        ],
        "intermediate": [
            ("Overhead press", "overhead-press", "3 x 8-10", "full"),
            ("Seated dumbbell shoulder press", "seated-dumbbell-shoulder-press", "3 x 10-12", "dumbbells"),
            ("Pike push-up", "pike-push-up", "3 x 8-12", "bodyweight"),
        ],
        "advanced": [
            ("Overhead press", "overhead-press", "4 x 6-8", "full"),
            ("Seated dumbbell shoulder press", "seated-dumbbell-shoulder-press", "3 x 8-10", "dumbbells"),
            ("Push press", "push-press", "4 x 5", "full"),
            ("Elevated pike push-up", "pike-push-up", "4 x 8-12", "bodyweight"),
        ],
    },
    "chest_acc": {
        "beginner": [
            ("Cable chest press", "cable-chest-press", "2 x 10-12", "full"),
            ("Decline push-up, feet on a chair", "decline-push-up", "2 x max, leave 2 in the tank", "bodyweight"),
            ("Dumbbell fly", "dumbbell-fly", "2 x 12", "dumbbells"),
        ],
        "intermediate": [
            ("Cable chest press", "cable-chest-press", "3 x 10-12", "full"),
            ("Decline push-up, feet on a chair", "decline-push-up", "3 x max, leave 2 in the tank", "bodyweight"),
            ("Bar dip", "bar-dip", "3 x 6-10", "full"),
            ("Dumbbell fly", "dumbbell-fly", "3 x 12", "dumbbells"),
        ],
        "advanced": [
            ("Cable fly", "cable-fly", "3 x 12-15", "full"),
            ("Bar dip", "bar-dip", "3 x 8-12", "full"),
            ("Dumbbell fly", "dumbbell-fly", "3 x 10-12", "dumbbells"),
            ("Decline push-up, feet on a chair", "decline-push-up", "3 x max, leave 1 in the tank", "bodyweight"),
        ],
    },
    "side_delt": {
        "beginner": [
            ("Dumbbell lateral raise", "dumbbell-lateral-raise", "2 x 12-15", "dumbbells"),
            ("Cable lateral raise", "cable-lateral-raise", "2 x 12-15", "full"),
            ("Pike push-up", "pike-push-up", "2 x 8-10", "bodyweight"),
        ],
        "intermediate": [
            ("Dumbbell lateral raise", "dumbbell-lateral-raise", "3 x 12-15", "dumbbells"),
            ("Cable lateral raise", "cable-lateral-raise", "3 x 12-15", "full"),
            ("Pike push-up", "pike-push-up", "3 x 8-12", "bodyweight"),
        ],
        "advanced": [
            ("Dumbbell lateral raise", "dumbbell-lateral-raise", "4 x 12-15", "dumbbells"),
            ("Cable lateral raise", "cable-lateral-raise", "4 x 12-15", "full"),
            ("Elevated pike push-up", "pike-push-up", "3 x 8-12", "bodyweight"),
        ],
    },
    "triceps": {
        "beginner": [
            ("Tricep pushdown", "tricep-pushdown", "2 x 12", "full"),
            ("Overhead cable tricep extension", "overhead-tricep-extension", "2 x 12", "full"),
            ("Bench dip", "bench-dip", "2 x 10-12", "bodyweight"),
            ("Dumbbell overhead extension", "overhead-tricep-extension", "2 x 12", "dumbbells"),
        ],
        "intermediate": [
            ("Tricep pushdown", "tricep-pushdown", "3 x 12", "full"),
            ("Overhead cable tricep extension", "overhead-tricep-extension", "3 x 12", "full"),
            ("Lying tricep extension", "lying-tricep-extension", "3 x 10-12", "dumbbells"),
            ("Diamond push-up", "diamond-push-up", "3 x max, leave 2 in the tank", "bodyweight"),
        ],
        "advanced": [
            ("Close-grip bench press", "close-grip-bench-press", "3 x 8-10", "full"),
            ("Lying tricep extension", "lying-tricep-extension", "3 x 10-12", "dumbbells"),
            ("Tricep pushdown", "tricep-pushdown", "3 x 12-15", "full"),
            ("Diamond push-up", "diamond-push-up", "3 x max, leave 1 in the tank", "bodyweight"),
        ],
    },
    "row": {
        "beginner": [
            ("Seated machine row", "seated-machine-row", "2 x 10-12", "full"),
            ("Seated cable row", "seated-cable-row", "2 x 10-12", "full"),
            ("One-arm dumbbell row", "dumbbell-row", "2 x 10 each arm", "dumbbells"),
            ("Inverted row (under a table)", "inverted-row", "2 x 8-10", "bodyweight"),
        ],
        "intermediate": [
            ("Seated machine row", "seated-machine-row", "3 x 10-12", "full"),
            ("Barbell row", "barbell-row", "3 x 8-10", "full"),
            ("One-arm dumbbell row", "dumbbell-row", "3 x 10 each arm", "dumbbells"),
            ("Inverted row", "inverted-row", "3 x 10-12", "bodyweight"),
        ],
        "advanced": [
            ("Barbell row", "barbell-row", "4 x 6-8", "full"),
            ("Chest-supported row", "chest-supported-row", "3 x 8-10", "full"),
            ("One-arm dumbbell row", "dumbbell-row", "3 x 8-10 each arm", "dumbbells"),
            ("Inverted row, feet raised", "inverted-row", "4 x 10-12", "bodyweight"),
        ],
    },
    "v_pull": {
        "beginner": [
            ("Lat pulldown", "lat-pulldown", "2 x 10-12", "full"),
            ("Assisted pull-up machine", "assisted-pull-up", "2 x 8-10", "full"),
            ("Inverted row (under a table)", "inverted-row", "2 x 8-10", "bodyweight"),
            ("Dumbbell pullover", "dumbbell-pullover", "2 x 12", "dumbbells"),
            ("Superman", "superman", "2 x 12-15", "bodyweight"),
        ],
        "intermediate": [
            ("Lat pulldown", "lat-pulldown", "3 x 10-12", "full"),
            ("Pull-up (band-assisted is fine)", "pull-up", "3 x max", "full"),
            ("Inverted row", "inverted-row", "3 x 10-12", "bodyweight"),
            ("Dumbbell pullover", "dumbbell-pullover", "3 x 12", "dumbbells"),
            ("Superman", "superman", "3 x 12-15", "bodyweight"),
        ],
        "advanced": [
            ("Weighted pull-up", "pull-up", "4 x 5-8", "full"),
            ("Lat pulldown", "lat-pulldown", "3 x 8-10", "full"),
            ("Chin-up", "chin-up", "3 x max", "full"),
            ("Dumbbell pullover", "dumbbell-pullover", "3 x 10-12", "dumbbells"),
            ("Inverted row, feet raised", "inverted-row", "4 x 10-12", "bodyweight"),
            ("Superman hold", "superman", "3 x 20-30 sec", "bodyweight"),
        ],
    },
    "rear_delt": {
        "beginner": [
            ("Face pull", "face-pull", "2 x 12-15", "full"),
            ("Reverse machine fly", "reverse-machine-fly", "2 x 12-15", "full"),
            ("Reverse dumbbell fly", "reverse-dumbbell-fly", "2 x 12-15", "dumbbells"),
            ("Superman", "superman", "2 x 12-15", "bodyweight"),
        ],
        "intermediate": [
            ("Face pull", "face-pull", "3 x 12-15", "full"),
            ("Reverse dumbbell fly", "reverse-dumbbell-fly", "3 x 12-15", "dumbbells"),
            ("Superman", "superman", "3 x 12-15", "bodyweight"),
        ],
        "advanced": [
            ("Face pull", "face-pull", "3 x 12-15", "full"),
            ("Reverse dumbbell fly", "reverse-dumbbell-fly", "4 x 12-15", "dumbbells"),
            ("Superman hold", "superman", "3 x 20-30 sec", "bodyweight"),
        ],
    },
    "biceps": {
        "beginner": [
            ("Dumbbell curl", "dumbbell-curl", "2 x 10-12", "dumbbells"),
            ("Hammer curl", "hammer-curl", "2 x 10-12", "dumbbells"),
            ("Inverted row, underhand grip", "inverted-row", "2 x 8-10", "bodyweight"),
        ],
        "intermediate": [
            ("Dumbbell curl", "dumbbell-curl", "3 x 10-12", "dumbbells"),
            ("Barbell curl", "barbell-curl", "3 x 10", "full"),
            ("Hammer curl", "hammer-curl", "3 x 10-12", "dumbbells"),
            ("Inverted row, underhand grip", "inverted-row", "3 x 10-12", "bodyweight"),
        ],
        "advanced": [
            ("Barbell curl", "barbell-curl", "3 x 8-10", "full"),
            ("Incline dumbbell curl", "incline-dumbbell-curl", "3 x 10-12", "dumbbells"),
            ("Hammer curl", "hammer-curl", "3 x 10-12", "dumbbells"),
            ("Inverted row, underhand grip", "inverted-row", "4 x 10-12", "bodyweight"),
        ],
    },
}

# ---------------------------------------------------------------------------
# Swaps: "the machine is taken / I don't have that" -> try these instead.
# Ordered most-similar first; filtered to the subscriber's equipment at
# render time by alternatives_for().
# ---------------------------------------------------------------------------

ALTERNATIVES: dict[str, list[str]] = {
    # legs
    "leg-press": ["goblet-squat", "back-squat", "box-squat"],
    "back-squat": ["goblet-squat", "leg-press", "front-squat", "box-squat"],
    "front-squat": ["back-squat", "goblet-squat", "leg-press"],
    "goblet-squat": ["box-squat", "leg-press", "back-squat"],
    "box-squat": ["goblet-squat", "leg-press", "walking-lunge"],
    "deadlift": ["romanian-deadlift", "dumbbell-romanian-deadlift", "kettlebell-swing"],
    "romanian-deadlift": ["dumbbell-romanian-deadlift", "kettlebell-swing", "hip-thrust"],
    "dumbbell-romanian-deadlift": ["kettlebell-swing", "romanian-deadlift", "hip-thrust"],
    "kettlebell-swing": ["dumbbell-romanian-deadlift", "hip-thrust", "romanian-deadlift"],
    "hip-thrust": ["kettlebell-swing", "dumbbell-romanian-deadlift", "romanian-deadlift",
                   "nordic-ham-curl"],
    "leg-extension": ["bulgarian-split-squat", "step-up", "dumbbell-lunge"],
    "dumbbell-lunge": ["walking-lunge", "step-up", "bulgarian-split-squat"],
    "walking-lunge": ["dumbbell-lunge", "step-up", "bulgarian-split-squat"],
    "step-up": ["bulgarian-split-squat", "walking-lunge", "dumbbell-lunge"],
    "bulgarian-split-squat": ["walking-lunge", "step-up", "dumbbell-lunge"],
    "lying-leg-curl": ["seated-leg-curl", "nordic-ham-curl", "dumbbell-romanian-deadlift", "hip-thrust"],
    "seated-leg-curl": ["lying-leg-curl", "nordic-ham-curl", "dumbbell-romanian-deadlift", "hip-thrust"],
    "nordic-ham-curl": ["lying-leg-curl", "dumbbell-romanian-deadlift", "hip-thrust"],
    "standing-calf-raise": ["seated-calf-raise"],
    "seated-calf-raise": ["standing-calf-raise"],
    # push
    "machine-chest-press": ["dumbbell-chest-press", "bench-press", "push-up"],
    "bench-press": ["dumbbell-chest-press", "machine-chest-press", "push-up"],
    "incline-bench-press": ["dumbbell-chest-press", "bench-press", "push-up"],
    "dumbbell-chest-press": ["push-up", "machine-chest-press", "bench-press"],
    "push-up": ["dumbbell-chest-press", "machine-chest-press", "cable-chest-press",
                "decline-push-up", "diamond-push-up", "bench-dip"],
    "cable-chest-press": ["dumbbell-chest-press", "push-up", "machine-chest-press"],
    "cable-fly": ["dumbbell-fly", "cable-chest-press", "push-up"],
    "dumbbell-fly": ["cable-fly", "push-up", "cable-chest-press", "decline-push-up"],
    "decline-push-up": ["push-up", "dumbbell-fly", "cable-chest-press", "bench-dip"],
    "bar-dip": ["bench-dip", "push-up", "close-grip-bench-press"],
    "bench-dip": ["diamond-push-up", "bar-dip", "tricep-pushdown"],
    "machine-shoulder-press": ["seated-dumbbell-shoulder-press", "overhead-press", "pike-push-up"],
    "overhead-press": ["seated-dumbbell-shoulder-press", "machine-shoulder-press", "pike-push-up"],
    "seated-dumbbell-shoulder-press": ["overhead-press", "machine-shoulder-press", "pike-push-up"],
    "push-press": ["overhead-press", "seated-dumbbell-shoulder-press", "pike-push-up"],
    "pike-push-up": ["seated-dumbbell-shoulder-press", "overhead-press",
                     "machine-shoulder-press", "push-up"],
    "dumbbell-lateral-raise": ["cable-lateral-raise", "pike-push-up"],
    "cable-lateral-raise": ["dumbbell-lateral-raise", "pike-push-up"],
    "tricep-pushdown": ["overhead-tricep-extension", "lying-tricep-extension", "diamond-push-up", "bench-dip"],
    "overhead-tricep-extension": ["tricep-pushdown", "lying-tricep-extension", "bench-dip"],
    "lying-tricep-extension": ["overhead-tricep-extension", "tricep-pushdown", "diamond-push-up"],
    "close-grip-bench-press": ["diamond-push-up", "bar-dip", "tricep-pushdown"],
    "diamond-push-up": ["bench-dip", "tricep-pushdown", "close-grip-bench-press"],
    # pull
    "lat-pulldown": ["assisted-pull-up", "pull-up", "inverted-row", "dumbbell-pullover"],
    "pull-up": ["assisted-pull-up", "lat-pulldown", "inverted-row"],
    "chin-up": ["pull-up", "lat-pulldown", "inverted-row"],
    "assisted-pull-up": ["lat-pulldown", "pull-up", "inverted-row"],
    "dumbbell-pullover": ["lat-pulldown", "inverted-row", "dumbbell-row"],
    "seated-machine-row": ["seated-cable-row", "dumbbell-row", "inverted-row"],
    "seated-cable-row": ["seated-machine-row", "dumbbell-row", "inverted-row"],
    "barbell-row": ["dumbbell-row", "chest-supported-row", "seated-cable-row", "inverted-row"],
    "chest-supported-row": ["dumbbell-row", "seated-machine-row", "inverted-row"],
    "dumbbell-row": ["inverted-row", "seated-cable-row", "seated-machine-row"],
    "inverted-row": ["dumbbell-row", "seated-cable-row", "lat-pulldown", "superman"],
    "face-pull": ["reverse-dumbbell-fly", "reverse-machine-fly", "superman"],
    "reverse-machine-fly": ["reverse-dumbbell-fly", "face-pull", "superman"],
    "reverse-dumbbell-fly": ["face-pull", "reverse-machine-fly", "superman"],
    "superman": ["reverse-dumbbell-fly", "face-pull", "reverse-machine-fly", "inverted-row"],
    "dumbbell-curl": ["hammer-curl", "barbell-curl", "inverted-row"],
    "hammer-curl": ["dumbbell-curl", "barbell-curl", "inverted-row"],
    "barbell-curl": ["dumbbell-curl", "hammer-curl", "chin-up"],
    "incline-dumbbell-curl": ["dumbbell-curl", "hammer-curl", "barbell-curl"],
    # core
    "hanging-knee-raise": ["dead-bug", "crunch", "cable-crunch"],
    "hanging-leg-raise": ["hanging-knee-raise", "ab-wheel-rollout", "dead-bug"],
    "cable-crunch": ["crunch", "ab-wheel-rollout", "dead-bug"],
    "pallof-press": ["side-plank", "plank", "dead-bug"],
    "ab-wheel-rollout": ["plank", "dead-bug", "cable-crunch"],
    "plank": ["side-plank", "dead-bug", "ab-wheel-rollout"],
    "side-plank": ["plank", "pallof-press", "dead-bug"],
    "dead-bug": ["plank", "crunch", "side-plank"],
    "crunch": ["dead-bug", "cable-crunch", "plank"],
    "russian-twist": ["side-plank", "pallof-press", "dead-bug"],
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

EQUIPMENT_NOTES = {
    "full": "Machine taken? Every exercise lists a swap - use it and carry on.",
    "dumbbells": "Dumbbells only: control the lowering (3 seconds) so a lighter weight still counts.",
    "bodyweight": "No kit needed. Slow the lowering to 3 seconds and stop 1-2 reps short of failure.",
}


def _derive_slug_maps() -> tuple[dict[str, str], dict[str, str]]:
    """slug -> cleanest display name, and slug -> least equipment it needs."""
    names: dict[str, str] = {}
    equip: dict[str, str] = {}
    for pattern in POOLS.values():
        for pool in pattern.values():
            for name, slug, _sets, tier in pool:
                if slug not in names or len(name) < len(names[slug]):
                    names[slug] = name
                if (slug not in equip
                        or EQUIPMENT_RANK[tier] < EQUIPMENT_RANK[equip[slug]]):
                    equip[slug] = tier
    return names, equip


SLUG_NAMES, SLUG_EQUIPMENT = _derive_slug_maps()


def available(pool: list[tuple[str, str, str, str]],
              equipment: str) -> list[tuple[str, str, str, str]]:
    """The entries in `pool` doable with `equipment` (which includes lower tiers)."""
    rank = EQUIPMENT_RANK[equipment]
    return [e for e in pool if EQUIPMENT_RANK[e[3]] <= rank]


def alternatives_for(slug: str, equipment: str = "full",
                     limit: int = 2) -> list[dict]:
    """Swaps for one exercise, filtered to what the subscriber can actually do."""
    rank = EQUIPMENT_RANK[equipment]
    out = []
    for alt in ALTERNATIVES.get(slug, []):
        if alt == slug or EQUIPMENT_RANK[SLUG_EQUIPMENT.get(alt, "full")] > rank:
            continue
        out.append({"name": SLUG_NAMES.get(alt, alt.replace("-", " ").capitalize()),
                    "slug": alt})
        if len(out) >= limit:
            break
    return out


def generate_plan(week: int, days_per_week: int, experience: str,
                  include_run: bool, equipment: str = "full") -> dict:
    """Return a structured plan dict for one week."""
    if days_per_week not in SPLITS:
        raise ValueError(f"days_per_week must be one of {sorted(SPLITS)}")
    if experience not in LEVELS:
        raise ValueError(f"experience must be one of {LEVELS}")
    if equipment not in EQUIPMENT_RANK:
        raise ValueError(f"equipment must be one of {EQUIPMENT}")

    days = []
    for d, (title, patterns) in enumerate(SPLITS[days_per_week]):
        if experience == "beginner":
            # 3 main movements + always finish with core
            patterns = [p for p in patterns if p != "core"][:3] + ["core"]
        exercises = []
        used: set[str] = set()
        for i, pattern in enumerate(patterns):
            pool = available(POOLS[pattern][experience], equipment)
            # d * 2 offsets repeated templates (e.g. Upper 1 vs Upper 2)
            start = (week + i + d * 2) % len(pool)
            # Walk the pool from there for the first movement not already in
            # today's session: narrow pools (bodyweight especially) overlap
            # between adjacent slots. If everything is taken, drop the slot
            # rather than prescribe the same exercise twice.
            entry = next((pool[(start + k) % len(pool)] for k in range(len(pool))
                          if pool[(start + k) % len(pool)][1] not in used), None)
            if entry is None:
                continue
            name, slug, sets, tier = entry
            used.add(slug)
            exercises.append({"name": name, "slug": slug, "sets": sets,
                              "equipment": tier,
                              "alts": alternatives_for(slug, equipment)})
        days.append({"title": f"Day {d + 1} - {title}", "exercises": exercises})

    return {
        "week": week,
        "days": days,
        "equipment": equipment,
        "run": RUNS[week % len(RUNS)] if include_run else None,
        "notes": NOTES[experience] + [EQUIPMENT_NOTES[equipment]],
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
            if ex["alts"]:
                swaps = " or ".join(a["name"] for a in ex["alts"])
                lines.append(f"      no kit / taken? {swaps}")
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
    """Every exercise as a flat row: name, slug, sets, level, body part, kit.

    Ordered legs -> push -> pull -> core, for the filterable /exercises pages.
    """
    rows = []
    for part in PART_ORDER:
        for pattern, groups in POOLS.items():
            if BODY_PARTS[pattern] != part:
                continue
            for level in LEVELS:
                for name, slug, sets, tier in groups[level]:
                    rows.append({"name": name, "slug": slug, "sets": sets,
                                 "level": level, "part": part,
                                 "equipment": tier})
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
                 {"name": n, "slug": s, "sets": sets, "equipment": tier}
                 for n, s, sets, tier in POOLS[p][lvl]]} for lvl in LEVELS]}
            for p in PATTERN_NAMES]


def all_slugs() -> set[str]:
    """Every exercise slug used anywhere (for media fetching and page checks)."""
    return {slug
            for pattern in POOLS.values()
            for pool in pattern.values()
            for _, slug, _, _ in pool}


if __name__ == "__main__":
    import argparse
    import datetime

    p = argparse.ArgumentParser()
    p.add_argument("--week", type=int,
                   default=datetime.date.today().isocalendar()[1])
    p.add_argument("--days", type=int, default=3, choices=sorted(SPLITS))
    p.add_argument("--level", default="intermediate", choices=LEVELS)
    p.add_argument("--equipment", default="full", choices=EQUIPMENT)
    p.add_argument("--no-run", action="store_true")
    args = p.parse_args()
    print(plan_text(generate_plan(args.week, args.days, args.level,
                                  not args.no_run, args.equipment)))
