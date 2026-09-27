"""Fetch public-domain exercise instructions + images from free-exercise-db.

free-exercise-db (github.com/yuhonas/free-exercise-db) is released under the
Unlicense (public domain): 800+ exercises with step-by-step instructions and
demonstration photos, free for commercial use, no attribution required.

This script matches our exercise slugs (engine.all_slugs()) against that
dataset, downloads the images into static/exercises/, and writes
static/exdb.json which app.py serves on the /exercise/<slug> pages.

Usage:  python3 scripts/fetch_exercise_media.py
Re-run any time exercises are added to engine.py. Unmatched slugs are listed
at the end — add an alias below and re-run.
"""

from __future__ import annotations

import difflib
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine  # noqa: E402

RAW = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE, "static", "exercises")
OUT = os.path.join(BASE, "static", "exdb.json")

# Our slug -> free-exercise-db exercise name, where names differ too much for
# fuzzy matching. Extend as needed.
ALIASES = {
    "back-squat": "Barbell Squat",
    "front-squat": "Front Barbell Squat",
    "goblet-squat": "Dumbbell Goblet Squat",
    "box-squat": "Bodyweight Squat",
    "leg-press": "Leg Press",
    "deadlift": "Barbell Deadlift",
    "romanian-deadlift": "Romanian Deadlift",
    "dumbbell-romanian-deadlift": "Stiff-Legged Dumbbell Deadlift",
    "hip-thrust": "Barbell Hip Thrust",
    "kettlebell-swing": "One-Arm Kettlebell Swings",  # no two-arm swing in the db
    "dumbbell-lunge": "Dumbbell Lunges",
    "walking-lunge": "Dumbbell Walking Lunge",
    "bulgarian-split-squat": "Split Squat with Dumbbells",
    "step-up": "Dumbbell Step Ups",
    "leg-extension": "Leg Extensions",
    "lying-leg-curl": "Lying Leg Curls",
    "seated-leg-curl": "Seated Leg Curl",
    "nordic-ham-curl": "Natural Glute Ham Raise",
    "standing-calf-raise": "Standing Calf Raises",
    "seated-calf-raise": "Seated Calf Raise",
    "plank": "Plank",
    "dead-bug": "Dead Bug",
    "crunch": "Crunches",
    "side-plank": "Side Bridge",
    "russian-twist": "Russian Twist",
    "hanging-knee-raise": "Hanging Leg Raise",
    "hanging-leg-raise": "Hanging Leg Raise",
    "ab-wheel-rollout": "Ab Roller",
    "cable-crunch": "Cable Crunch",
    "pallof-press": "Pallof Press",
    "bench-press": "Barbell Bench Press - Medium Grip",
    "incline-bench-press": "Barbell Incline Bench Press - Medium Grip",
    "close-grip-bench-press": "Close-Grip Barbell Bench Press",
    "dumbbell-chest-press": "Dumbbell Bench Press",
    "machine-chest-press": "Machine Bench Press",
    "cable-chest-press": "Cable Chest Press",
    "cable-fly": "Cable Crossover",
    "dumbbell-fly": "Dumbbell Flyes",
    "push-up": "Pushups",
    "bar-dip": "Dips - Chest Version",
    "overhead-press": "Standing Military Press",
    "push-press": "Push Press",
    "seated-dumbbell-shoulder-press": "Seated Dumbbell Press",
    "machine-shoulder-press": "Machine Shoulder (Military) Press",
    "dumbbell-lateral-raise": "Side Lateral Raise",
    "cable-lateral-raise": "Cable Lateral Raise",
    "tricep-pushdown": "Triceps Pushdown",
    "overhead-tricep-extension": "Cable Rope Overhead Triceps Extension",
    "lying-tricep-extension": "Lying Triceps Press",
    "seated-machine-row": "Leverage Iso Row",
    "seated-cable-row": "Seated Cable Rows",
    "barbell-row": "Bent Over Barbell Row",
    "dumbbell-row": "One-Arm Dumbbell Row",
    "chest-supported-row": "Lying T-Bar Row",
    "lat-pulldown": "Wide-Grip Lat Pulldown",
    "pull-up": "Pullups",
    "chin-up": "Chin-Up",
    "assisted-pull-up": "Machine-Assisted Pull-Up",
    "face-pull": "Face Pull",
    "reverse-machine-fly": "Reverse Machine Flyes",
    "reverse-dumbbell-fly": "Seated Bent-Over Rear Delt Raise",
    "dumbbell-curl": "Dumbbell Bicep Curl",
    "barbell-curl": "Barbell Curl",
    "hammer-curl": "Hammer Curls",
    "incline-dumbbell-curl": "Incline Dumbbell Curl",
    # bodyweight / home-kit options
    "inverted-row": "Inverted Row",
    "superman": "Superman",
    "pike-push-up": None,        # not in free-exercise-db; see EXTRA below
    "bench-dip": "Bench Dips",
    "diamond-push-up": "Push-Ups - Close Triceps Position",
    "decline-push-up": "Decline Push-Up",
    "dumbbell-pullover": "Straight-Arm Dumbbell Pullover",
}

# Movements free-exercise-db doesn't carry. Our own words, so no licence
# question; alias them to None above so fuzzy matching can't grab something
# unrelated (it offered "Pin Presses" for the pike push-up).
EXTRA: dict[str, dict] = {
    "pike-push-up": {
        "name": "Pike push-up",
        "instructions": [
            "Start in a push-up position, then walk your feet in and lift your "
            "hips so your body makes an upside-down V.",
            "Your hands should be a little wider than your shoulders, head "
            "between your arms, looking back towards your feet.",
            "Bend your elbows and lower the crown of your head towards the "
            "floor between your hands. Keep your hips high.",
            "Stop just before your head touches, then press back up until your "
            "arms are straight.",
            "To make it harder, put your feet on a step, chair or sofa "
            "(elevated pike push-up) - the higher the feet, the more weight "
            "goes through your shoulders.",
        ],
    },
}


def main() -> None:
    os.makedirs(IMG_DIR, exist_ok=True)
    print("Downloading exercise index...")
    data = httpx.get(f"{RAW}/dist/exercises.json", timeout=60,
                     follow_redirects=True).json()
    by_name = {ex["name"].lower(): ex for ex in data}
    names = list(by_name)

    out: dict[str, dict] = {}
    misses: list[str] = []
    for slug in sorted(engine.all_slugs()):
        if slug in EXTRA:
            out[slug] = {"images": [], **EXTRA[slug]}
            print(f"  ok: {slug} -> {EXTRA[slug]['name']} (our own copy)")
            continue
        target = (ALIASES.get(slug) or slug.replace("-", " ")).lower()
        ex = by_name.get(target)
        if ex is None:
            close = difflib.get_close_matches(target, names, n=1, cutoff=0.75)
            if close:
                ex = by_name[close[0]]
                print(f"  fuzzy: {slug} -> {ex['name']}")
        if ex is None:
            misses.append(slug)
            continue
        images = []
        for i, path in enumerate(ex.get("images", [])[:2]):
            fname = f"{slug}-{i}.jpg"
            dest = os.path.join(IMG_DIR, fname)
            if not os.path.exists(dest):
                r = httpx.get(f"{RAW}/exercises/{path}", timeout=60,
                              follow_redirects=True)
                if r.status_code == 200:
                    with open(dest, "wb") as f:
                        f.write(r.content)
                else:
                    continue
            images.append(fname)
        out[slug] = {"name": ex["name"], "instructions": ex.get("instructions", []),
                     "images": images}
        print(f"  ok: {slug} -> {ex['name']} ({len(images)} images)")

    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nWrote {OUT} with {len(out)} exercises.")
    if misses:
        print(f"UNMATCHED ({len(misses)}) - add aliases and re-run: {misses}")


if __name__ == "__main__":
    main()
