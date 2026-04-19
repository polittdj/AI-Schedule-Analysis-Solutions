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
