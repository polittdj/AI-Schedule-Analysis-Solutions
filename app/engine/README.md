# `app/engine/` — CPM Engine (Milestone 4)

Pure-computation CPM layer. Forward pass, backward pass, total / free
/ driving slack, near-critical banding, and per-relation-type link
arithmetic over an `app.models.Schedule`. Consumed by the DCMA
metric modules (M5–M7), the NASA SMH overlay (M8), the driving-path
tracer (M10), and the manipulation engine (M11).

## Scope

Inputs: `Schedule` (`app.models.schedule.Schedule`), optional
`CPMOptions`.

Outputs: `CPMResult` wrapping per-task `TaskCPMResult` records plus
project-level dates, cycles, critical / near-critical UID sets, and
soft-constraint violations.

Non-goals — not in this module:

* DCMA metric computation (owned by `app/engine/dcma/` starting at
  M5).
* Cross-version comparison (M9 comparator).
* AI narrative / export (M12 / M13).
* COM or any I/O (BUILD-PLAN §2 guardrail).

## Mutation-vs-wrap decision

**Decision:** the engine returns a `CPMResult` dataclass wrapper and
**never mutates** the input `Schedule`.

Rationale:

1. **M7 AC1 non-mutation invariant.** DCMA CPT (M7) runs a
   `+600-day probe` via `Schedule.model_copy(update=...)` and then
   re-runs CPM on the copy. Mutating the input would double-book
   either schedule on re-invocation.
2. **M9 comparator symmetry.** The comparator runs CPM on two
   schedule versions. Mutation would corrupt the Period A / Period B
   references held by the comparator during cross-version delta
   analysis (`driving-slack-and-paths §§7, 9`).
3. **Forensic defensibility (BUILD-PLAN §6 AC bar).** An immutable
   input + immutable result pair is the simplest shape that satisfies
   "show your work" — every CPM rerun, whether on an original or
   an M7 copy, produces a fresh `CPMResult` that can be serialized
   and cited.
4. **No Pydantic round-trip cost.** `CPMResult` is a plain
   `@dataclass(frozen=True, slots=True)` because every value is
   already validated upstream (dates are tz-aware from the parser per
   `mpp-parsing-com-automation §3.10`; integers come from working-
   minute arithmetic here).

The engine does consume `Schedule` fields read-only. It does not
produce a new `Schedule`; downstream consumers that need a synthesized
schedule view (rare) build it from `CPMResult` + the original
`Schedule`.

## Algorithm notes

Topological sort (`topology.py`): Kahn's algorithm on the acyclic
subgraph. Cycles are isolated via Tarjan's SCC (iterative, to avoid
recursion depth on large schedules). Tie-break by ascending
`unique_id` for deterministic forensic output.

Forward pass (`cpm.py::CPMEngine._forward_pass`): for each task in
topological order, gather predecessor-link bounds from
`relations.forward_link_bound`, pick `max` across all incoming links
per the E15 invariant, derive the missing ES/EF boundary from the
task's duration (working-minute arithmetic), and apply the task's
constraint via `constraints.apply_forward_constraint`. Soft
constraint breaches (SNLT / FNLT) surface as `ConstraintViolation`
records; hard MSO / MFO dates lock the corresponding boundary and
re-derive the other.

Backward pass: symmetric — reverse topological order, `min` across
outgoing links, anchor tasks with no successors on the project
finish (or `CPMOptions.project_finish_override` per E18).

Total slack: `TS = working_minutes_between(ES, LS, calendar)`. Free
slack: `FS = min(link_driving_slack)` across successor links (E16).

Driving slack (`paths.driving_slack_to_focus`): SSI §2 definition
implemented as a DAG shortest-path from every predecessor back to the
Focus Point. Reverse topological relaxation yields an O(V+E)
computation.

## Big-O

Let `n = |tasks|` and `m = |relations|`.

* Topological sort: **O(n + m)**.
* Forward pass: **O(n + m)** (one scan of relations per task is
  amortized via the indexed predecessor map).
* Backward pass: **O(n + m)**.
* Free slack per task: **O(m)** total (each relation looked at once).
* Driving slack to a focus: **O(n + m)**.
* Calendar arithmetic: each `add_working_minutes` /
  `subtract_working_minutes` call is **O(days spanned)**. Bounded by a
  20-year horizon; typical IMS ranges fit in weeks.

Memory: **O(n + m)** for the result and intermediate maps.

## Forensic defensibility

Every public class and function in `app/engine/` cites the skill
section that governs its semantics (BUILD-PLAN §5 M4 AC5). The
citation pattern makes a reviewer's audit trivial: read the
docstring, jump to the skill, confirm the computed number.

Specifics:

* Calendar arithmetic cites
  `mpp-parsing-com-automation §3.5` (Gotcha 5, minutes vs. days).
* Cycle handling cites `driving-slack-and-paths §4` (critical-path
  discipline) and BUILD-PLAN §5 M4 AC5 (lenient-mode justification).
* Per-relation driving slack cites `driving-slack-and-paths §3`
  (four relation types, formulas verbatim).
* Constraint-type semantics cite `driving-slack-and-paths §4` (six
  date-bearing types) plus MSP default-scheduling behavior for
  ASAP / ALAP (E9).
* Driving-slack-to-focus cites SSI slides 5–22 via the skill.

MSP-validation test (BUILD-PLAN §5 M4 AC1): the engine's
`is_critical_from_msp` field is read but not overwritten. A
Milestone 4 integration test on a real schedule compares MSP's flag
task-for-task against `CPMResult.critical_path_uids` — this test
requires MS Project on the host and is deferred to on-workstation
verification, tracked in `docs/BUILD-PLAN.md §7`.

## Calendar-synthesis gating (Option B)

When a `Schedule` arrives with an empty `calendars` list — a shape
permitted by the Pydantic model and used by several minimal fixtures
— the engine needs *some* calendar to drive
`add_working_minutes` / `subtract_working_minutes`. There are two
defensible behaviors:

* **Option A (strict, forensic default).** Raise
  `MissingCalendarError`. A schedule without a calendar cannot yield
  MSP-match dates, which is the `driving-slack-and-paths §8` CPM
  discipline requirement. Under Option A, every fixture and every
  parsed `.mpp` must carry an explicit calendar.
* **Option B (gated synthesis).** Synthesize a default `Standard`
  calendar when absent, but expose the switch on `CPMOptions` so
  forensic callers can force Option A locally. Minimal fixtures and
  unit tests that do not care about calendar semantics still
  compute.

M4 adopts **Option B**. Rationale:

1. The M4 cleanup pass is not a fixture rewrite. Flipping to strict
   would require updating every unit fixture in the repo to add an
   explicit `Calendar`, expanding the blast radius of this PR
   beyond the audit's minors list.
2. The knob
   (`CPMOptions.auto_synthesize_calendar: bool = True`) makes the
   behavior explicit rather than silent. A forensic caller that
   must reproduce MSP output (M7, M9, M10 downstream consumers)
   can opt into the strict mode by passing
   `CPMOptions(auto_synthesize_calendar=False)`, which the engine
   surfaces as `MissingCalendarError`.
3. The default flip to `False` is slated for **Milestone 5**, once
   every fixture carries an explicit `Standard` calendar and the
   M5 parser path emits calendars deterministically per
   `mpp-parsing-com-automation §3.5`. The flip is therefore a
   one-line change guarded by a single option default.

Tests:

* `test_calendar_synthesis_default_allows_empty_calendars` —
  empty-calendar schedule under default options still computes.
* `test_calendar_synthesis_off_raises_on_empty_calendars` —
  empty-calendar schedule under `auto_synthesize_calendar=False`
  raises `MissingCalendarError`.

## Guardrails enforced

* No `win32com`, `ollama`, `anthropic`, or cloud SDK imports
  (`cui-compliance-constraints §2a`; BUILD-PLAN §5 M4 guardrails).
* No mutation of `Schedule` (see above).
* No disk / network I/O — pure-function arithmetic.
* Cycle handling is lenient by default; strict mode available via
  `CPMOptions(strict_cycles=True)`.
* All dates stay tz-aware per model validator G1
  (`mpp-parsing-com-automation §3.10`).

## Files

| File               | Role |
| ------------------ | ---- |
| `exceptions.py`    | `EngineError` hierarchy + `ConstraintViolation`. |
| `options.py`       | `CPMOptions` dataclass. |
| `calendar_math.py` | Working-time arithmetic (windows, snap, add/subtract). |
| `topology.py`      | Kahn sort + Tarjan SCC cycle detection. |
| `relations.py`     | FS/SS/FF/SF forward/backward bounds + link DS. |
| `constraints.py`   | 8 constraint-type handlers (forward + backward). |
| `cpm.py`           | `CPMEngine` forward + backward passes. |
| `paths.py`         | Critical-path chains, driving slack, near-critical. |
| `result.py`        | `CPMResult` / `TaskCPMResult` wrapper dataclasses. |
| `duration.py`      | Minutes ↔ working-days helpers (`§3.5`). |
| `delta.py`         | M9 comparator contract — `FieldDelta`, `TaskDelta`, `RelationshipDelta`, `ComparatorResult` + `DeltaType` / `TaskPresence` / `RelationshipPresence` enums. |
| `windowing.py`     | M9 status-date windowing predicate `is_legitimate_actual`. |
| `comparator.py`    | M9 cross-version `compare_schedules` — UniqueID-only matching, per-field and per-relationship deltas. |
| `driving_path_types.py` | M10 frozen contract — `DrivingPathNode`, `DrivingPathEdge`, `NonDrivingPredecessor`, `ConstraintDrivenPredecessor`, `DrivingPathResult`, `DrivingPathCrossVersionResult`, `FocusPointAnchor`. (Block 7 reshape: chain + parallel-links pair replaced with an adjacency-map. M10.1 addition: `ConstraintDrivenPredecessor` plus `skipped_cycle_participants` on `DrivingPathResult` per BUILD-PLAN §2.20.) |
| `focus_point.py`   | M10 Focus Point resolver — maps an int UID or `FocusPointAnchor` to a concrete `Task.unique_id`. |
| `driving_path.py`  | M10 backward-walk tracer — `trace_driving_path` + `trace_driving_path_cross_version`. |
| `driving_path_render_acumen.py` | Block 7 default Acumen-style table renderer — `render_acumen_table`. |
| `units.py`         | Block 7 minute→day conversion helper for public contract — `minutes_to_days`. M10.1 addition: `format_days` user-visible duration formatter per BUILD-PLAN §2.19. |

## Cross-version comparator (Milestone 9)

`compare_schedules(period_a: Schedule, period_b: Schedule, options:
ComparatorOptions | None = None) -> ComparatorResult` is the M9
diff. Mission:

1. **UniqueID-only matching.** Non-negotiable per BUILD-PLAN §2.7
   and `mpp-parsing-com-automation §5`. A regression test
   (`test_ac4_rename_all_tasks_in_b_preserves_match`) renames every
   task in Period B and verifies the matched-delta count is
   unchanged. `Task.task_id` and `Task.name` are never consulted
   for matching.
2. **Non-mutation contract.** The comparator never writes to
   `period_a` or `period_b`. Both inputs round-trip
   `Schedule.model_dump()` byte-identical across a call (verified by
   `test_mutation_invariance_both_sides` and the relationship
   equivalent).
3. **Legitimate-actual windowing predicate.** A matched task whose
   Period A `finish` is less than or equal to Period B `status_date`
   is tagged `is_legitimate_actual = True` per
   `forensic-manipulation-patterns §3.2` and
   `driving-slack-and-paths §10`. Either status date `None`, either
   task missing, or Period A `finish` `None` ⇒ `False`. The
   predicate lives in `app/engine/windowing.py` as a standalone
   function for audit-ability.
4. **Delta shape.** `ComparatorResult` carries tuples of
   `TaskDelta` and `RelationshipDelta`, plus `frozenset`s of added
   / deleted UIDs and `matched_task_count`. Every model is Pydantic
   v2 `ConfigDict(frozen=True)`. `FieldDelta` records raw values on
   both sides; presentation-layer unit conversion (calendar-day
   slip, working-day duration delta) happens at render time per
   BUILD-PLAN §2.16.
5. **Downstream consumers.** M10 (task-specific driving path) will
   consume `RelationshipDelta` to detect added / removed driving
   predecessors across versions. M11 (manipulation scoring) will
   consume the full `ComparatorResult`, filtering matched deltas
   by `is_legitimate_actual` before scoring per
   `forensic-manipulation-patterns §3.2`. Both consumers read the
   result tree read-only; the frozen contract makes "show your
   work" forensically reproducible across pipeline stages.

Forensic-integrity raises:

* `ComparatorError` — duplicate `Task.unique_id` within a schedule
  (bypassed G10 validator) or duplicate relationship pair
  `(pred_uid, succ_uid)` within a schedule (the pair-key matching
  is ambiguous on concurrent FS + SS links; a future extension
  could switch to the `(pred, succ, type)` triple).

## Driving path analysis (Milestone 10)

`trace_driving_path(schedule, focus_spec, cpm_result) ->
DrivingPathResult` and
`trace_driving_path_cross_version(period_a, period_b, focus_spec,
period_a_cpm_result, period_b_cpm_result) ->
DrivingPathCrossVersionResult` are the M10 task-specific driving
path tracers.

Mission:

1. **Operator-nominated Focus Point.** The analyst picks a Focus
   Point — either a specific `Task.unique_id` or a predefined
   `FocusPointAnchor` (`PROJECT_FINISH` / `PROJECT_START`). The
   project critical path is a special case of the driving path
   with `focus_spec = FocusPointAnchor.PROJECT_FINISH` per
   `driving-slack-and-paths §1`. The resolver lives in
   `app/engine/focus_point.py` and is read-only.
2. **Backward walk on zero-relationship-slack edges.** Per
   `driving-slack-and-paths §5`, the trace starts at the Focus
   Point and walks incoming relations. An edge with relationship
   slack = 0 is a driving edge (followed); an edge with
   relationship slack > 0 is non-driving (recorded and terminates
   that branch). Per-link slack is computed via
   `app.engine.relations.link_driving_slack_minutes` (the M4
   per-relation-type formulas from
   `driving-slack-and-paths §3`), not recomputed locally.
3. **Non-mutation contract.** Neither `Schedule` nor `CPMResult`
   is written to. `cpm_result_snapshot(...)` + `model_dump()`
   byte-equality is asserted around every trace call in the unit
   tests. `cpm_result=None` raises `DrivingPathError` rather than
   running CPM internally — the engine is the sole producer of
   CPM data per BUILD-PLAN §2.17.
4. **Period A slack rule.** Per `driving-slack-and-paths §9`,
   cross-version but-for analysis uses Period A slack
   exclusively. The cross-version result stores both periods'
   traces (`period_a_result` and `period_b_result`) for UI
   display, but the `added_predecessor_uids` /
   `removed_predecessor_uids` / `retained_predecessor_uids` sets
   are framed from Period A's perspective. Period B slack is
   descriptive, never prescriptive — using it would be circular
   (a task that became a driver *because* of the Period B change
   will read zero slack in Period B).
5. **Forensic drill-down.** Every `DrivingPathNode` carries
   `unique_id` + `name` + CPM dates + `total_float_days` +
   `calendar_hours_per_day`; every `DrivingPathEdge` carries
   predecessor / successor UIDs + names + `relation_type` +
   `lag_days` + `relationship_slack_days` + `calendar_hours_per_day`;
   every `NonDrivingPredecessor` carries both endpoints' UIDs +
   names + `slack_days` + `calendar_hours_per_day`. No black-box
   output per BUILD-PLAN §6 AC bar #3.
6. **No path is dropped on multi-branch backward walk (Block 7,
   AM8).** When a task has two or more zero-slack incoming edges,
   **every** edge is retained on `DrivingPathResult.edges` per
   `driving-slack-and-paths §4` ("No path is dropped.") and §5
   ("Walking every relationship-slack-zero link backward … walks
   recursively until every driving predecessor is exhausted.").
   The AM7 "lowest-UID tie-break" rule is withdrawn — tie-break is
   no longer a concept in this module. Shared ancestors are
   deduplicated via the adjacency-map `nodes: dict[int, …]` shape.
7. **Cross-version anchor disambiguation.** When a
   `FocusPointAnchor` resolves to different UIDs in Period A and
   Period B, `trace_driving_path_cross_version` raises
   `DrivingPathError` rather than silently comparing different
   chains. The operator must pass an explicit integer UID to
   compare two different focus milestones.

### Contract shape (Block 7 adjacency-map)

`DrivingPathResult`:

```
DrivingPathResult(
    focus_point_uid: int,
    focus_point_name: str,
    nodes: dict[int, DrivingPathNode],          # keyed by UID
    edges: list[DrivingPathEdge],               # every zero-slack driving edge
    non_driving_predecessors: list[NonDrivingPredecessor],
    constraint_driven_predecessors: list[ConstraintDrivenPredecessor],
    skipped_cycle_participants: list[int],
)
```

`DrivingPathCrossVersionResult`:

```
DrivingPathCrossVersionResult(
    period_a_result: DrivingPathResult,
    period_b_result: DrivingPathResult,
    added_predecessor_uids: set[int],
    removed_predecessor_uids: set[int],
    retained_predecessor_uids: set[int],
    added_edges: list[DrivingPathEdge],
    removed_edges: list[DrivingPathEdge],
    retained_edges: list[DrivingPathEdge],
)
```

Edge identity for the cross-version diffs is the tuple
`(predecessor_uid, successor_uid, relation_type)`.

### Units convention

Public contract fields are in **days** (float). The CPM engine
internals stay in **minutes** (`TaskCPMResult.total_slack_minutes`,
`Relation.lag_minutes`, `link_driving_slack_minutes`) so multi-
calendar schedules don't lose precision to premature rounding.
Conversion happens at the contract boundary via
`app.engine.units.minutes_to_days(minutes, hours_per_day)` —
the single helper; inline `minutes / 480` arithmetic is forbidden.

Every public model that carries a days-denominated field also
carries `calendar_hours_per_day: float`. This is the forensic
audit trail per BUILD-PLAN §2.18: an attorney or senior reviewer
can reconstruct minutes via `days * hours_per_day * 60`.
`calendar_hours_per_day` is populated at parse time by the COM
parser (M1.1 patch session) from `Task.calendar_hours_per_day`
when non-None or `Schedule.project_calendar_hours_per_day`
otherwise. The driving-path tracer does not walk calendars; it
reads the denormalised fields directly.

### Three-bucket partition (BUILD-PLAN §2.20)

Every incoming relationship on a node in the driving sub-graph
lands in exactly one of three mutually-exclusive, exhaustive
buckets keyed on per-relationship driving slack
(`driving-slack-and-paths §3`). The partition is enforced by
Pydantic `model_validator`s on the three models below — there is
no escape hatch and no tie-break.

| Bucket | Model | Slack regime (days) |
| ------ | ----- | ------------------- |
| Driving | `DrivingPathEdge` | within `±(1/86,400)` of zero |
| Also-ran | `NonDrivingPredecessor` | strictly `> +(1/86,400)` |
| Constraint-driven | `ConstraintDrivenPredecessor` | strictly `< -(1/86,400)` |

`ConstraintDrivenPredecessor` captures edges whose predecessor is
held by a hard constraint (MSO / MFO / SNLT / FNLT per
`dcma-14-point-assessment §4.5`) or by negative-float propagation
from a missed deadline. DCMA-EA Metric #7 (Edwards 2016, pp. 9-10)
verbatim: "Negative float occurs when the project schedule is
forecasting a missed deadline, or when a hard constraint is holding
a task further to the left than it would otherwise be." NASA
Schedule Management Handbook on hard constraints, verbatim:
"Improper use can cause negative float to be calculated throughout
the schedule." See BUILD-PLAN §2.20 for the full statement.

Each `ConstraintDrivenPredecessor` carries the predecessor's
`predecessor_constraint_type` (a `ConstraintType` enum),
`predecessor_constraint_date` (`datetime | None` — `None` on
ASAP / ALAP), and a `rationale` string for deposition-grade reports.

The renderer surfaces the third bucket on every row via
`constraint_driven_predecessor_count: int` and
`constraint_driven_predecessors: list[dict]` (the enum is
serialized as its `.name` string — e.g., `"MUST_START_ON"`).

### User-visible durations (`format_days`)

`app.engine.format_days(days: float) -> str` is the **sole**
formatting point for user-visible durations — Pydantic contract
string fields, renderer output, README examples, Word / Excel /
HTML report bodies, and CLI output all route through it per
BUILD-PLAN §2.19 (AM9, 4/23/2026). Authority: NASA Schedule
Management Handbook §5.5.9.1 ("task durations should generally be
assigned in workdays"); Papicito's forensic-tool standard dated
4/23/2026.

Format rules:

* 2-decimal precision maximum.
* Positive values round by ceiling to the next `0.01`; negative
  values round by floor to the next `-0.01`; exactly `0.0` is
  preserved without rounding.
* Trailing zeros and any orphan decimal point are stripped.
* Leading zero omitted on fractional absolute values (`0.5`
  renders as `".5"`, `-0.5` renders as `"-.5"`).
* Singular suffix `" day"` only when the rounded value equals
  `+1.0` or `-1.0` exactly; `" days"` everywhere else, including
  `".5 days"` and `"0 days"`.

Example inputs and outputs:

| Input     | Output         |
| --------- | -------------- |
| `0.0`     | `"0 days"`     |
| `1.0`     | `"1 day"`      |
| `-1.0`    | `"-1 day"`     |
| `0.5`     | `".5 days"`    |
| `-2.0`    | `"-2 days"`    |
| `0.003`   | `".01 days"`   |
| `2.25`    | `"2.25 days"`  |
| `100.0`   | `"100 days"`   |

A schema invariant test
(`tests/test_engine_no_minute_hour_fields_on_public_models.py`)
scans every public Pydantic model in `app.engine.__all__` and
asserts no `model_fields` key matches `/_(minutes|hours|seconds)$/` —
new public models that carry a duration MUST use the `*_days`
convention per §2.19.

### Forensic-visibility field: `skipped_cycle_participants`

`DrivingPathResult.skipped_cycle_participants: list[int]` captures
**non-focus** task UniqueIDs that the backward walk encountered but
could not materialise as `DrivingPathNode` records — cycle
participants flagged by `TaskCPMResult.skipped_due_to_cycle` or
tasks with `None`-valued early / late dates from an incomplete CPM
pass. Listing these UIDs on the result (rather than silently
dropping them) preserves forensic visibility: a reviewer can see
which predecessors were encountered but not walked, and chase the
underlying CPM-engine issue. Ordering is UniqueID ascending.

When the FOCUS task itself is skipped / missing dates,
`trace_driving_path` raises `DrivingPathError` instead — an empty-
nodes result is refused (Codex P2, see `driving_path.py` contract).

### Migration note (Block 7)

The pre-Block-7 contract exposed `result.chain: tuple[DrivingPathNode, …]`
and `result.links: tuple[DrivingPathLink, …]`. Both are gone.
Callers that need the chain-like linear view of a sub-graph should
use `render_acumen_table(result)` — it returns a
`list[dict]` sorted by `early_start` ascending, with nested
`driving_predecessors` per row. That list is the Block 7 default
view; an SSI gantt-style renderer and multi-view toggle arrive in
Block 8.

### Worked example

```python
from app.engine import (
    compute_cpm,
    format_days,
    render_acumen_table,
    trace_driving_path,
)

# schedule: A → B → C, all FS zero-lag
cpm = compute_cpm(schedule)
result = trace_driving_path(schedule, focus_spec=3, cpm_result=cpm)

result.nodes.keys()          # {1, 2, 3}
result.nodes[1].name         # "A"
result.nodes[1].total_float_days  # 2.0 (internal float value)
format_days(result.nodes[1].total_float_days)  # "2 days" (user-visible)
result.nodes[1].calendar_hours_per_day  # 8.0 (project default)

len(result.edges)            # 2: (1→2) and (2→3)
result.edges[0].relationship_slack_days  # ~0.0

# Acumen-style rendering for a table view
rows = render_acumen_table(result)
# rows[0]["unique_id"] == 1, rows[0]["driving_predecessor_count"] == 0
# rows[2]["unique_id"] == 3, rows[2]["driving_predecessors"][0]["predecessor_uid"] == 2
# rows[N]["constraint_driven_predecessor_count"] > 0 when the node has a
# hard-constraint-pinned predecessor (BUILD-PLAN §2.20 third bucket).
```

Downstream consumption convention:

* **M11 (manipulation scoring)** will consume
  `DrivingPathCrossVersionResult.added_predecessor_uids` /
  `removed_predecessor_uids` / `retained_predecessor_uids` plus
  the edge-level diffs for its driving-predecessor churn detector
  per `forensic-manipulation-patterns §7` and §9. The frozen-
  contract posture of the result tree means the manipulation
  engine reads predecessor churn without widening the M10 API.
* **M12 / M13 (AI narrative and UI)** will render the adjacency
  map via `render_acumen_table` (default) plus the Block 8 SSI
  gantt-style variant, with UniqueID + name citations throughout
  and the `calendar_hours_per_day` audit trail on every row.

Forensic-integrity raises:

* `DrivingPathError` — `cpm_result=None` or cross-version anchor
  divergence.
* `FocusPointError` — unresolvable `focus_spec` (integer UID not
  in schedule, `PROJECT_FINISH` / `PROJECT_START` on empty or
  cyclic-only schedules).
* `ValidationError` on `DrivingPathEdge` when
  `relationship_slack_days > 1/86_400` (one-second tolerance).
* `ValidationError` on `NonDrivingPredecessor` when
  `slack_days <= 1/86_400`.
* `ValidationError` on `ConstraintDrivenPredecessor` when
  `slack_days >= -1/86_400`. The three slack regimes are mutually
  exclusive and exhaustive per BUILD-PLAN §2.20.
