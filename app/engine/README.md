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
| `driving_path_types.py` | M10 frozen contract — `DrivingPathNode`, `DrivingPathLink`, `NonDrivingPredecessor`, `DrivingPathResult`, `DrivingPathCrossVersionResult`, `FocusPointAnchor`. |
| `focus_point.py`   | M10 Focus Point resolver — maps an int UID or `FocusPointAnchor` to a concrete `Task.unique_id`. |
| `driving_path.py`  | M10 backward-walk tracer — `trace_driving_path` + `trace_driving_path_cross_version`. |

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
   `unique_id` + `name`; every `DrivingPathLink` carries
   predecessor / successor UIDs + `relation_type` + `lag_minutes`
   + `relationship_slack_minutes`; every
   `NonDrivingPredecessor` carries both endpoints' UIDs and
   names + the slack value that terminated the branch. No
   black-box output per BUILD-PLAN §6 AC bar #3.
6. **Multi-driver tie-break.** When a chain task has two or more
   zero-slack incoming edges, the walk follows the predecessor
   with the lowest `Task.unique_id`. The non-followed driver(s)
   land on `non_driving_predecessors` with
   `relationship_slack_minutes = 0` so the UI can surface the
   parallel-driver case without widening the contract. This
   tie-break is deterministic and audit-traceable.
7. **Cross-version anchor disambiguation.** When a
   `FocusPointAnchor` resolves to different UIDs in Period A and
   Period B, `trace_driving_path_cross_version` raises
   `DrivingPathError` rather than silently comparing different
   chains. The operator must pass an explicit integer UID to
   compare two different focus milestones.

Downstream consumption convention:

* **M11 (manipulation scoring)** will consume
  `DrivingPathCrossVersionResult.added_predecessor_uids` /
  `removed_predecessor_uids` / `retained_predecessor_uids` for
  its driving-predecessor churn detector per
  `forensic-manipulation-patterns §7` and §9. The frozen-contract
  posture of the result tree means the manipulation engine reads
  predecessor churn without widening the M10 API.
* **M12 / M13 (AI narrative and UI)** will render the chain,
  the per-link slack table, the non-driving-predecessor
  secondary list, and the cross-version delta sets with
  UniqueID + name citations throughout.

Forensic-integrity raises:

* `DrivingPathError` — `cpm_result=None` or cross-version anchor
  divergence.
* `FocusPointError` — unresolvable `focus_spec` (integer UID not
  in schedule, `PROJECT_FINISH` / `PROJECT_START` on empty or
  cyclic-only schedules).
