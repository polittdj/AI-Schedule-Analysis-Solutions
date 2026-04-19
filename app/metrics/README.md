# `app.metrics` — DCMA 14-Point Metric Engine (Phase 1, Milestones 5 + 6 + 7)

Pure-computation metric layer for the Schedule Forensics tool.
Milestone 5 shipped the first four DCMA 14-Point checks (Logic,
Leads, Lags, Relationship Types). Milestone 6 added metrics 5, 6,
7, 8, and 10 (Hard Constraints, High Float, Negative Float, High
Duration, Resources). Milestone 7 ships the remaining five —
Metric 9 (Invalid Dates), Metric 11 (Missed Tasks), Metric 12
(Critical Path Test), Metric 13 (CPLI), Metric 14 (BEI) — plus the
:mod:`app.metrics.baseline` plumbing module the baseline-dependent
metrics (11, 13, 14) share.

Every metric is a pure function of `Schedule` (and, for the CPM-
consuming metrics, `CPMResult`); none mutate their inputs and none
touch I/O, COM, or the network.

## Public API

```python
from app.metrics import (
    # primitives
    Severity, MetricResult, Offender, ThresholdConfig, BaseMetric,
    # configuration
    MetricOptions,
    # exceptions
    MetricError, InvalidThresholdError, MissingCPMResultError,
    # M5 metrics (functional + class form)
    run_logic, LogicMetric,
    run_leads, LeadsMetric,
    run_lags, LagsMetric,
    run_relationship_types, RelationshipTypesMetric,
    # M6 metrics (functional + class form)
    run_hard_constraints, HardConstraintsMetric,
    run_high_float, HighFloatMetric,
    run_negative_float, NegativeFloatMetric,
    run_high_duration, HighDurationMetric,
    run_resources, ResourcesMetric,
    # M7 metrics (functional + class form)
    run_invalid_dates, InvalidDatesMetric, InvalidDateKind,
    run_missed_tasks, MissedTasksMetric,
    run_critical_path_test, CriticalPathTestMetric,
    run_cpli, CPLIMetric,
    run_bei, BEIMetric,
    # M7 baseline plumbing
    has_baseline, has_baseline_coverage,
    baseline_slip_minutes, tasks_with_baseline_finish_by,
    baseline_critical_path_length_minutes, BaselineComparison,
)
```

Calling pattern for schedule-only metrics (1, 2, 3, 4, 5, 8, 10):

```python
result = run_logic(schedule)                              # default thresholds
result = run_hard_constraints(schedule, MetricOptions(    # client overrides
    hard_constraints_threshold_pct=7.0,
))
```

Calling pattern for CPM-consuming metrics (6, 7):

```python
from app.engine import compute_cpm
cpm = compute_cpm(schedule)
result = run_high_float(schedule, cpm)
result = run_negative_float(schedule, cpm, MetricOptions(
    negative_float_threshold_pct=5.0,    # client tolerance for tiny slip
))
```

Missing CPM input raises `MissingCPMResultError` — the metric never
fabricates a silent PASS when given insufficient information.

## Forensic-defensibility contract

Every metric satisfies BUILD-PLAN §6 AC bar #3:

1. **Specific** — the metric is named (`DCMA-1` … `DCMA-10`), the
   denominator population is documented, and the source rows in
   `dcma-14-point-assessment/SKILL.md` and
   `docs/sources/DeltekDECMMetricsJan2022.xlsx` travel on the
   result via `ThresholdConfig`.
2. **Testable** — every metric ships a hand-calculable golden test
   plus the gotcha-band tests (44.0-WD boundary, rolling-wave
   exemption, cycle-skipped denominator exclusion, 09NOV09 four-
   constraint list).
3. **Forensically defensible** — every offender is enumerated with
   its UniqueID, task name, and a per-metric evidence value
   (constraint kind, total-float in working days, duration in
   working days, or literal `resource_count=0`). No black-box
   percentage; no aggregate score without the contributing-task
   drill-down.

The metric output is an *indicator*, not a verdict
(`dcma-14-point-assessment §6 Rule 1`). Downstream narrative copy
must phrase findings as items for further forensic investigation,
never as standalone findings of fault. Metric 10 is the most
literal expression of this rule — it carries no pass/fail threshold
and its `severity` is always `Severity.WARN`.

## Threshold citation table

| Metric    | Module                       | Default threshold                      | Direction        | Skill section                         | DeltekDECM row                                                                          |
|-----------|------------------------------|----------------------------------------|------------------|---------------------------------------|-----------------------------------------------------------------------------------------|
| DCMA-1    | `logic.py`                   | ≤ 5.0%                                 | `<=`             | `dcma-14-point-assessment §4.1`       | `06A204b` — dangling logic / missing predecessors-successors                            |
| DCMA-2    | `leads.py`                   | ≤ 0.0%                                 | `<=`             | `dcma-14-point-assessment §4.2`       | `06A205` — lag usage; leads scored at `X/Y = 0%`                                        |
| DCMA-3    | `lags.py`                    | ≤ 5.0%                                 | `<=`             | `dcma-14-point-assessment §4.3`       | `06A205a` — lag usage; DECM `≤ 10%` vs DCMA `≤ 5%` delta                                |
| DCMA-4    | `relationship_types.py`      | ≥ 90.0% FS                             | `>=`             | `dcma-14-point-assessment §4.4`       | DECM sheet *Metrics*, Guideline 6 — FS Relationship %                                   |
| DCMA-5    | `hard_constraints.py`        | ≤ 5.0%                                 | `<=`             | `dcma-14-point-assessment §4.5`       | DECM sheet *Metrics*, Guideline 6 — Hard Constraints (MSO/MFO/SNLT/FNLT)                |
| DCMA-6    | `high_float.py`              | ≤ 5.0% (tasks > 44 WD)                 | `<=`             | `dcma-14-point-assessment §4.6`       | DECM sheet *Metrics*, Guideline 6 — High Float (`total_slack > 44 WD`)                  |
| DCMA-7    | `negative_float.py`          | ≤ 0.0% (absolute)                      | `<=`             | `dcma-14-point-assessment §4.7`       | DECM sheet *Metrics*, Guideline 6 — Negative Float (`total_slack < 0`)                  |
| DCMA-8    | `high_duration.py`           | ≤ 5.0% (tasks > 44 WD remaining)       | `<=`             | `dcma-14-point-assessment §4.8`       | DECM sheet *Metrics*, Guideline 6 — High Duration (`remaining_duration > 44 WD`)        |
| DCMA-10   | `resources.py`               | none (indicator-only)                  | `indicator-only` | `dcma-14-point-assessment §4.10`      | DECM sheet *Metrics*, Guideline 6 — Resources (`resource_count == 0`, no threshold)     |
| DCMA-9    | `invalid_dates.py`           | ≤ 0.0% (any offender flags)            | `<=`             | `dcma-14-point-assessment §4.9`       | DECM sheet *Metrics*, Guideline 6 — Invalid Dates (9a forecast + 9b actual)             |
| DCMA-11   | `missed_tasks.py`            | ≤ 5.0%                                 | `<=`             | `dcma-14-point-assessment §4.11`      | DECM sheet *Metrics*, Guideline 6 — Missed Tasks (incomplete baseline-due)              |
| DCMA-12   | `critical_path_test.py`      | binary (pass/fail, no %)               | `structural-pass-fail` | `dcma-14-point-assessment §4.12` | not published by DECM — DCMA protocol only (structural variant, not +600-WD probe)      |
| DCMA-13   | `critical_path_length_index.py` | ≥ 0.95 (CPLI)                      | `>=`             | `dcma-14-point-assessment §4.13`      | DECM sheet *Metrics*, Guideline 6 — CPLI                                                |
| DCMA-14   | `baseline_execution_index.py`| ≥ 0.95 (BEI)                           | `>=`             | `dcma-14-point-assessment §4.14`      | DECM sheet *Metrics*, Guideline 6 — BEI (cumulative-hit numerator per §5.1)             |

All pct thresholds are configurable via `MetricOptions`. When an
operator supplies a non-default value, `MetricResult.threshold.is_overridden`
is `True` and the override appears in the narrative export. The
working-day ceilings for Metrics 6 and 8 (44.0 WD) are likewise
configurable (`high_float_threshold_working_days`,
`high_duration_threshold_working_days`).

Boundary semantics are strict ``>`` for Metrics 6 and 8: a task at
exactly 44.0 WD does **not** flag, 44.01 WD does
(BUILD-PLAN §5 M6 AC 2).

## Denominator and exclusion policies

| Metric    | Denominator                                         | Exclusions / notes                                                                                                                              |
|-----------|-----------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| DCMA-1    | Eligible incomplete tasks                           | Excludes summary, LOE, and 100%-complete per `§3`. Project start / finish milestones detected structurally per `§4.1` (gotcha L1).              |
| DCMA-2    | All relations                                       | Zero-relation schedule → PASS with `no relations` note. A lead between two 100%-complete tasks is still flagged (gotcha LD4).                   |
| DCMA-3    | Non-lead relations (`lag_minutes >= 0`)             | Leads excluded so M2 and M3 do not double-count the same offender (gotcha LG5). Zero non-lead relations → PASS.                                 |
| DCMA-4    | All relations                                       | Zero-relation schedule → WARN (FS share undefined). All four type counts are reported in `notes` for the narrative layer.                       |
| DCMA-5    | Eligible tasks (§3)                                 | 09NOV09 four-constraint list — MSO, MFO, SNLT, FNLT. ALAP / SNET / FNET do NOT count here; ALAP's detection path is M11.                        |
| DCMA-6    | Eligible incomplete tasks, CPM-reported, non-cycle  | Cycle-skipped tasks (`skipped_due_to_cycle=True`) are dropped from the eligible pool; they have no defensible slack.                            |
| DCMA-7    | Eligible incomplete tasks, CPM-reported, non-cycle  | Same denominator scope as DCMA-6. Threshold 0% is absolute — any negative-float task flags.                                                     |
| DCMA-8    | Eligible incomplete tasks                           | Scores on `remaining_duration_minutes` (falls back to `duration_minutes` when zero). `is_rolling_wave=True` tasks are exempt from the numerator. |
| DCMA-10   | Eligible incomplete tasks                           | Indicator-only — no pass/fail threshold (AC 5). `severity` is always `Severity.WARN`; downstream narrative renders the ratio without verdict.   |
| DCMA-9    | Eligible tasks (excl. summary + milestone)          | LOE DOES apply — date validity is universal (§3.12). Missing `status_date` → reduced-mode (inversion-only). Three invalidity kinds per §4.9.    |
| DCMA-11   | Tasks with baseline_finish ≤ status_date            | Excludes summary + milestone; rolling-wave and LOE exempt from numerator only (§§3.11, 3.12). No-baseline → indicator-only WARN.                |
| DCMA-12   | 1 (structural)                                      | Pass/fail is binary. Endpoint milestones detected structurally (no incoming / no outgoing relation). Missing endpoints → indicator-only WARN.    |
| DCMA-13   | Baseline critical-path length (min.)                | Baseline + CP-length derived from critical-path UIDs against baseline dates. No-baseline → indicator-only WARN.                                 |
| DCMA-14   | Tasks with baseline_finish ≤ status_date            | Cumulative-hit numerator — `actual_finish ≤ status_date`. Rolling-wave + LOE exempt from numerator only. Zero-denominator → indicator-only.     |

## CPM-consumer table

| Metric    | Needs CPMResult? | Reason                                                                                          |
|-----------|------------------|-------------------------------------------------------------------------------------------------|
| DCMA-1…5  | No               | Pure structural / task-attribute checks.                                                        |
| DCMA-6    | Yes              | Consumes `TaskCPMResult.total_slack_minutes` — converted to working days via the engine helper. |
| DCMA-7    | Yes              | Consumes `TaskCPMResult.total_slack_minutes` — flags any strictly-negative value.               |
| DCMA-8    | No               | Scores on task attributes (`remaining_duration_minutes`); no slack comparison needed.           |
| DCMA-9    | No               | Date-validity checks run against `status_date` / actual / forecast / early / late task dates.   |
| DCMA-10   | No               | Scores on `Task.resource_count`.                                                                |
| DCMA-11   | No               | Baseline-dependent only; no CPM traversal required.                                             |
| DCMA-12   | Yes              | Traverses zero-slack predecessors — consumes `critical_path_uids` + `total_slack_minutes`.      |
| DCMA-13   | Yes              | Baseline CP length derived from `critical_path_uids` + baseline dates.                          |
| DCMA-14   | No               | Baseline- + status-date-dependent; no CPM traversal required.                                   |

A CPM-consuming metric invoked with `cpm_result=None` raises
`MissingCPMResultError` rather than reporting a silent PASS.

## Grouping rationale — why Metric 10 clusters with M6

Milestone 6's scope is the five *simple-ratio* DCMA metrics — those
that compute a single population, apply one per-task predicate, and
report a ratio. Hard Constraints (M5), High Float (M6), High
Duration (M8), and Resources (M10) all fit this shape. High Float
and Negative Float (M7) are *nearly* simple-ratio — they add a
single working-day threshold conversion via the engine helper, but
they do not consume a cross-version comparator or a status-date
window.

Metric 9 (Invalid Dates) and Metrics 11–14 (Missed Tasks, Critical
Path Test, CPLI, BEI) are the *date-sensitive* cluster — every one
of them compares a task attribute against `status_date`, computes
cross-version arithmetic, or rebuilds the schedule via
`model_copy(update=...)`. They group together in M7 because the
plumbing they need (status-date windowing, `model_copy` CPM probe,
cumulative-hit counting) is shared infrastructure that would be
wasted on a simple-ratio metric.

Placing Metric 10 in M6 rather than M7 keeps the simple-ratio
cluster coherent — every metric in M6 can be reasoned about in
terms of "count tasks satisfying predicate P / eligible tasks" —
and defers date-arithmetic plumbing to a milestone that needs it
five times. The groupings are recorded in BUILD-PLAN §5 M6 / M7
preamble.

## Mixed-shape metrics (M7)

The five M7 metrics are deliberately heterogeneous — Metric 9 is a
validator (no ratio denominator in the usual sense; its denominator
is "eligible tasks" and its numerator "tasks with any invalidity"),
Metric 12 is a structural binary, and Metrics 13 / 14 are signed
ratio indices rather than percent-of-total. All five fit the
:class:`MetricResult` contract without new dataclasses:

* **Metric 9** — reuses the percent-of-total shape. Offender `value`
  is a semicolon-separated list of invalidity kinds.
* **Metric 11** — reuses the percent-of-total shape, with
  baseline-due tasks as the denominator and baseline-due-not-actually-
  finished tasks (minus rolling-wave / LOE) as the numerator.
* **Metric 12** — encodes binary pass/fail via
  `threshold.direction = "structural-pass-fail"` and
  `numerator=1/denominator=1` on PASS / `numerator=0/denominator=1`
  on FAIL. The `computed_value` is `100.0` / `0.0` respectively.
* **Metric 13 (CPLI)** and **Metric 14 (BEI)** — ratio indices
  (not percent). `computed_value` is the raw ratio (e.g., `0.96`).
  `numerator` is the cumulative count or minute-signed length, and
  `denominator` is the baseline cumulative count or baseline-CP
  length — in the same units — so consumers can divide them to
  recover the ratio or use `computed_value` directly.
* Both index metrics use `direction=">="`; Metric 11 uses
  `direction="<="`; Metric 9 uses `direction="<="` (≤ 0%).

No extension of :class:`~app.metrics.base.MetricResult`,
:class:`~app.metrics.base.Offender`,
:class:`~app.metrics.base.ThresholdConfig`, or
:class:`~app.metrics.base.MetricOptions` was necessary — BUILD-PLAN
§2.14's frozen-contract invariant holds across M5 + M6 + M7. The
`"structural-pass-fail"` direction string is a new literal value
documented here; downstream consumers should treat it as an
opaque sentinel when they care about numeric direction, and render
the binary result from `severity` when they care about the verdict.

## Baseline plumbing (`baseline.py`)

M7 introduces :mod:`app.metrics.baseline` — the single consumption
surface for baseline fields on :class:`Task`. Consumers:

* **Metric 11** uses `has_baseline_coverage` + `tasks_with_
  baseline_finish_by` to build its denominator.
* **Metric 13** uses `has_baseline_coverage` +
  `baseline_critical_path_length_minutes` for the denominator and
  derives the baseline project finish from the critical-path UID
  set.
* **Metric 14** uses the same helpers as Metric 11 plus the
  cumulative-hit numerator test `actual_finish ≤ status_date`.

All helpers return `None` / `False` rather than raising when the
baseline is missing. Metrics translate that into an indicator-only
`MetricResult` with `Severity.WARN` and explanatory notes — the
raise is reserved for CPM prerequisites (per
:class:`~app.metrics.exceptions.MissingCPMResultError`).

`BaselineComparison.from_schedule(schedule)` produces an immutable
snapshot keyed by UniqueID that later milestones (M9 comparator,
M11 manipulation engine) can pass around without re-reading
`schedule.tasks`.

## LOE detection

Default policy: a task is treated as Level-of-Effort iff
`Task.is_loe == True`. The flag is set by the parser when MS Project
exposes the LOE custom field.

Optional fallback: `MetricOptions.loe_name_patterns` accepts a tuple
of case-insensitive substrings. When a substring appears in
`Task.name`, the task is treated as LOE for every metric's
denominator. This fallback is **opt-in** — empty tuple by default —
because name-based detection is brittle.

## Forensic-pattern fields emitted for M11

The Milestone 11 manipulation engine consumes M5 + M6 outputs
without re-deriving them. Every `MetricResult` emits:

* `metric_id`, `severity`, `computed_value`, `threshold` (with
  `is_overridden`, `source_skill_section`, `source_decm_row`).
* `numerator`, `denominator`.
* `offenders: tuple[Offender, ...]` — drill-down keyed by
  `unique_id`, with per-metric evidence in the `value` field
  (constraint kind, TF in WD, remaining duration in WD, literal
  `resource_count=0`).
* `notes` — free-form context (per-type breakdown for M4,
  WD-ceiling + calendar for M6 / M8, indicator-only disclaimer for
  M10).

The metric layer does **not** compute manipulation scores or NASA
severity mapping; those live in M11 and M8 respectively per the
BUILD-PLAN milestone graph.

## Scope deferrals

| Item                                                          | Deferred to | Reason                                                                                                                             |
|---------------------------------------------------------------|-------------|------------------------------------------------------------------------------------------------------------------------------------|
| 09NOV09 5-day MSP/OpenPlan lag carve-out (DCMA-3)             | Post-M5     | Requires per-file tool-provenance detection (MSP / OpenPlan / P6) that is not yet plumbed through the parser. Queued as opt-in.   |
| Metric 1b "Dangling Logic" (SS-only / FF-only successors)     | Post-M5     | M5 prompt scope was Logic 1 only. A follow-up can ship the dangling subcheck once the engine emits per-relation drivership.       |
| Metric 9 (Invalid Dates)                                      | Shipped M7  | Date-validity validator — three invalidity kinds detected (§4.9).                                                                 |
| Metrics 11–14 (Missed Tasks, CPT, CPLI, BEI)                  | Shipped M7  | Baseline-dependent + structural cluster — see grouping rationale above.                                                            |
| Metric 12 +600-WD `model_copy` probe (DCMA canonical variant) | Phase 2     | Phase 1 ships the structural zero-slack-traversal variant; the +600-WD probe is available as a future check (BUILD-PLAN §9.1).     |
| Working-time precision on calendar-minute slips               | Phase 2     | Metrics 13 / 14 use calendar minutes for Phase 1 (§9.1 ledger); working-minute precision at weekend / holiday boundaries defers.   |
| NASA severity overlay                                          | M8          | Owned per BUILD-PLAN milestone graph. Consumes M5 + M6 results as inputs.                                                          |
| Status-date windowing / cross-version comparator              | M9          | Infrastructure for M7's metrics and the comparator layer.                                                                          |
| Manipulation scoring                                           | M11         | Consumes all M5 + M6 + M7 outputs.                                                                                                |
| Earned Value Analysis (Phase 3)                                | Phase 3     | Consumes `Task.resource_count` and Metric-10 offenders but is out of Phase 1 scope.                                               |
