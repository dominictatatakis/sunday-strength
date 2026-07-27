# Progress tracking — design

_27 July 2026. Status: approved, not yet planned._

A `/account/progress` page for every Sunday Strength subscriber, showing whether
they are getting stronger. Five metrics computed from the existing `completions`
table, plus an optional bodyweight log.

## Why this is not trivial

Plans rotate exercises deliberately: `generate_plan` picks
`(week + slot + day * 2) % len(pool)` (`engine.py:557`), so any one exercise
surfaces every third to fifth week. A naive "squat strength" line therefore
mixes mechanically incomparable lifts:

| Week | Exercise | Logged | Est. 1RM |
|---|---|---|---|
| 30 | Leg press | 80 × 3 | 88 kg |
| 31 | Goblet squat | 32 × 12 | 45 kg |
| 32 | Back squat | 70 × 8 | 89 kg |

Plotted raw, that sawtooth reads as a 50% strength loss in a week. It is nothing
of the kind — it is leg press being an easier movement than a goblet squat.

**The fix is structural: index every exercise against its own history before
combining anything.** Percentages relative to a per-exercise baseline are
unitless and therefore safe to average. Rotation stops being damage and becomes
extra sampling.

A second problem shapes the choice of headline. The primary user is in a
~600 kcal deficit, 100 kg heading to 88 kg. Absolute strength gains during a cut
are slow and lumpy, so a page headlined "is your bench going up" will look flat
for months and read as failure, when holding strength through a 12 kg loss is
the actual win. Relative strength — load per kg of bodyweight — improves from
both directions and tells the truth about a cut.

## Schema

Two additions. Both go into `SCHEMA` *and* `SCHEMA_PG`, with idempotent
statements in `MIGRATIONS_SQLITE` *and* `MIGRATIONS_PG`, per `CLAUDE.md:92`.

```sql
CREATE TABLE IF NOT EXISTS bodyweights (
    id INTEGER PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    logged_on TEXT NOT NULL,          -- 'YYYY-MM-DD', one per day
    weight_kg REAL NOT NULL,
    UNIQUE (subscriber_id, logged_on)
);

ALTER TABLE subscribers ADD COLUMN pinned_metric TEXT DEFAULT 'strength_index';
```

`completions` is unchanged; it already carries `sets`, `weight_kg` and `reps`
(`db.py:113-115`).

The Postgres path has never run locally (`CLAUDE.md:98`). Treat both additions as
unverified until they have booted on Render, and check the deploy log for
`migration skipped:`.

## Metrics

Shared primitive, estimated one-rep max by the Epley formula:

```
e1RM = weight_kg × (1 + reps / 30)
```

Computed only when `weight_kg` and `reps` are both present, and only for
**reps ≤ 12**. Epley diverges badly above that; a 20-rep bodyweight squat would
otherwise report an absurd 1RM.

Logs where e1RM computes to ≤ 0 are discarded rather than stored as a baseline,
which is also what prevents a divide-by-zero downstream.

### 1. Strength Index (default headline)

Per slug, the **first** logged e1RM is that slug's baseline = 100. Every later
log of the same slug becomes `100 × e1RM / baseline`. The Index is plotted as one
point per week; each point is the unweighted mean of those percentages across
every slug logged in that week and the three weeks before it. Weeks with no
qualifying slug produce no point, leaving a gap rather than a zero.

Two rules carry more weight than their size suggests:

- **Only slugs with ≥ 2 logs are included.** A slug logged once is 100 by
  definition; including them pulls the mean toward 100 and silently flattens
  genuine progress.
- **Baseline is the first log, not a best-of or median.** A cautious opening set
  inflates every later reading. This is accepted rather than corrected — the
  chart is labelled "vs. your first logged session" so the number is honest
  about what it means.

Because indexing is per-slug, the `weight is per dumbbell` convention
(`db.py:116`) cancels out. Dumbbell and barbell lifts become comparable with no
unit conversion.

### 2. Relative strength

Best e1RM in the trailing eight weeks across the four main patterns (`squat`,
`hinge`, `h_push`, `v_pull`), divided by the most recent bodyweight. Shown as a
total and per lift ("squat 1.1× bodyweight"). Patterns with no qualifying log in
that window are omitted from the total and named as missing, so the figure is
never quietly computed from two lifts while appearing to cover four.

**This metric does need the dumbbell correction.** It divides an absolute load by
an absolute bodyweight, so a per-dumbbell entry must be doubled first or the
result is understated by half.

The equipment tier on each pool entry cannot answer this — `dumbbells` is a
*minimum kit* marker, and single-implement lifts like the kettlebell swing carry
it too. So `progress.py` holds an explicit hand-maintained set of per-dumbbell
slugs. Adding a two-dumbbell exercise to `POOLS` means adding it there as well;
omitting it understates that lift by half in this one metric only.

Hidden entirely when no bodyweight exists.

### 3. Per-pattern trends

Small multiples, one panel per movement pattern, each exercise its own series
with visible gaps where rotation skipped it. The honest detail view: no
smoothing and no interpolation across missing weeks.

### 4. Consistency

Sessions done against sessions planned, per week, plus current streak. A day
counts as trained when **≥ 50%** of its prescribed exercises are logged. Planned
volume comes free from `generate_plan`, which is deterministic and needs no
stored history. Streak counts consecutive weeks meeting the target day count.

### 5. Weekly tonnage

`sets × reps × weight_kg` summed per week. For a subscriber logging no weight
this would be a flat zero, so it falls back to total reps and relabels itself
accordingly.

### Bodyweight-only subscribers

The strength story degrades rather than vanishing. With no load logged, the
Index uses reps as its basis: `100 × reps / baseline_reps`. Progress in
bodyweight training genuinely is more reps, so this is the correct measure for
that population, not a downgrade.

## Module boundaries

`progress.py` is new and **pure — no I/O, no clock, no database**, the same
contract `engine.py` holds. It receives completion rows and bodyweight rows and
returns metric structures.

| File | Owns |
|---|---|
| `progress.py` (new) | e1RM, per-slug indexing, the five metric builders |
| `db.py` | `completions_all()`, `bodyweights()`, `log_bodyweight()`, `set_pinned_metric()` |
| `app.py` | `GET /account/progress`, `POST /account/bodyweight`, `GET /api/v1/progress` |
| `templates/progress.html` (new) | Page and SVG sparkline macro |

The API endpoint exists so page and API compute through one function — the
mechanism described at `CLAUDE.md:76` that keeps the JSON API from rotting
unnoticed.

## Page

The pinned metric leads: large number, change over the last month, sparkline. A
tab row switches the pin and persists it to `subscribers.pinned_metric`. The
remaining four metrics follow as cards in fixed order, then the per-pattern
small multiples.

Charts are **server-rendered inline SVG** — no JavaScript, no charting library,
consistent with the no-bundler rule and with the plan page working scripting-off
(`CLAUDE.md:80`). Every chart carries a `<title>` and a visually hidden data
table so it is legible to screen readers rather than decorative.

## Cold start

The page is judged by a subscriber three weeks in, so scarcity is the design
case, not an afterthought.

| State | Behaviour |
|---|---|
| No logs at all | No charts and no zeroes. One line of copy and a link to this week's plan. |
| Logging, no slug logged twice | Strength Index card states what it needs ("2 more sessions"). Hero falls back automatically to consistency, which works from week one. |
| No bodyweight recorded | Relative strength hidden, replaced by an inline single-field form. |

The governing rule: **a metric renders only when it has the data to be true.**
Otherwise it names what is missing. No zero-filling, no interpolation across
gaps.

## Failure modes

- **Bodyweight typos.** Entry validated to 30–300 kg, rejected outside. A stray
  `1000` would otherwise flatten every relative-strength reading at once.
- **Zero or missing baselines.** Any log with e1RM ≤ 0 is skipped before it can
  become a baseline or a divisor.
- **Week bucketing reads the `week` column, never `done_at`.** `done_at` is a UTC
  `CURRENT_TIMESTAMP`; bucketing on it would misfile a late-evening BST session
  into the wrong week. `week` is the authoritative zero-padded key that
  `last_logged` already depends on.

## Verification

`CLAUDE.md:19` records that there is no test suite and that verification means
driving the real flow. That stands for the page.

**One deliberate exception: `progress.py` gets a stdlib `unittest` file.**
Indexing, baselines and the ≥2-logs rule are arithmetic that fails silently — a
wrong number renders exactly as confidently as a right one, and no amount of
clicking reveals it. Stdlib only, so no new dependency and no departure from the
scrypt/no-ORM house style.

A seeding script writes roughly six months of plausible history into a throwaway
`DB_PATH`, because the real table holds one row and an empty chart cannot be
eyeballed. Never run either against `gymdigest.db`.

## Out of scope

- Progress content in the weekly email. Worth doing once the page exists and has
  proven itself; it should link to the page rather than duplicate it.
- A stored `metrics` table with precomputed aggregates. Correct at ~10,000
  subscribers; at current scale it buys nothing and costs a migration on two
  back-ends, one of which cannot be verified locally. Metrics are computed on
  read.
- Reading bodyweight from the personal weight-loss Google Sheet. Rejected: it
  would couple a paid product to one user's spreadsheet and could not ship to
  subscribers.
