# `app.metrics` — DCMA 14-Point Metric Engine (Phase 1, Milestone 5)

Pure-computation metric layer for the Schedule Forensics tool.
Milestone 5 ships the first four DCMA 14-Point checks (Logic, Leads,
Lags, Relationship Types). Subsequent milestones (M6 / M7) add the
remaining ten. Every metric is a pure function of
`Schedule` (and, later, `CPMResult`); none mutate their inputs and
none touch I/O, COM, or the network.

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
)
```

The functional form (`run_*`) is the recommended caller surface; the
class form is available for callers that want to hold a homogeneous
list of metric instances (the orchestration layer in M13).

Calling pattern:

```python
result = run_logic(schedule)                           # default thresholds
result = run_logic(schedule, MetricOptions(           # client overrides
    logic_threshold_pct=7.0,
    loe_name_patterns=("loe", "level of effort"),
))
assert result.metric_id == "DCMA-1"
assert result.severity in (Severity.PASS, Severity.WARN, Severity.FAIL)
for offender in result.offenders:
    print(offender.unique_id, offender.name, offender.value)
```

## Forensic-defensibility contract

Every metric satisfies BUILD-PLAN §6 AC bar #3:

1. **Specific** — the metric is named (`DCMA-1` … `DCMA-4`), the
   denominator population is documented, and the source rows in
   `dcma-14-point-assessment/SKILL.md` and
   `docs/sources/DeltekDECMMetricsJan2022.xlsx` travel on the
   result.
2. **Testable** — every metric ships a hand-calculable golden test
   plus the gotcha-band tests required by the M5 prompt §5.
3. **Forensically defensible** — every offender is enumerated with
   its UniqueID, task name, and the per-metric value that drove
   inclusion. No black-box percentage; no aggregate score without
   the contributing-task drill-down.

The metric output is an *indicator*, not a verdict
(`dcma-14-point-assessment §6 Rule 1`). Downstream narrative copy
must phrase findings as items for further forensic investigation,
never as standalone findings of fault.

## Threshold citation table

| Metric    | Module                       | Default threshold | Direction | Skill section                       | DeltekDECM row                                                                  |
|-----------|------------------------------|-------------------|-----------|-------------------------------------|---------------------------------------------------------------------------------|
| DCMA-1    | `logic.py`                   | ≤ 5.0%            | `<=`      | `dcma-14-point-assessment §4.1`     | `06A204b` (Guideline 6, row 32) — dangling logic / missing predecessors-successors |
| DCMA-2    | `leads.py`                   | ≤ 0.0%            | `<=`      | `dcma-14-point-assessment §4.2`     | `06A205` (Guideline 6, row 33) — lag usage; leads scored at `X/Y = 0%`          |
| DCMA-3    | `lags.py`                    | ≤ 5.0%            | `<=`      | `dcma-14-point-assessment §4.3`     | `06A205a` (Guideline 6, row 33) — lag usage; DECM `≤ 10%` vs DCMA `≤ 5%` delta  |
| DCMA-4    | `relationship_types.py`      | ≥ 90.0%           | `>=`      | `dcma-14-point-assessment §4.4`     | DECM sheet *Metrics*, Guideline 6 — FS Relationship %; threshold ≥ 90%          |

All four thresholds are configurable via `MetricOptions`. When an
operator supplies a non-default value, `MetricResult.threshold.is_overridden`
is `True` and the override appears in the narrative export.

## Denominator and exclusion policies

| Metric    | Denominator                                         | Exclusions / notes                                                                                                                              |
|-----------|-----------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| DCMA-1    | Eligible incomplete tasks                           | Excludes summary, LOE, and 100%-complete tasks per `§3`. Project start / finish milestones detected structurally and excluded per `§4.1` (gotcha L1). |
| DCMA-2    | All relations                                       | Zero-relation schedule → PASS with `no relations` note. A lead between two 100%-complete tasks is still flagged (gotcha LD4).                  |
| DCMA-3    | Non-lead relations (`lag_minutes >= 0`)             | Leads excluded so M2 and M3 do not double-count the same offender (gotcha LG5). Zero non-lead relations → PASS.                                 |
| DCMA-4    | All relations                                       | Zero-relation schedule → WARN (FS share undefined). All four type counts are reported in `notes` for the narrative layer.                       |

## LOE detection

Default policy: a task is treated as Level-of-Effort iff
`Task.is_loe == True`. The flag is set by the parser when MS Project
exposes the LOE custom field.

Optional fallback: `MetricOptions.loe_name_patterns` accepts a tuple
of case-insensitive substrings. When a substring appears in
`Task.name`, the task is treated as LOE for Metric 1's denominator.
This fallback is **opt-in** — empty tuple by default — because
name-based detection is brittle.

## Forensic-pattern fields emitted for M11

The Milestone 11 manipulation engine consumes M5 outputs without
re-deriving them. M5 emits, on every `MetricResult`:

* `metric_id`, `severity`, `computed_value`, `threshold` (with
  `is_overridden`, `source_skill_section`, `source_decm_row`).
* `numerator`, `denominator`.
* `offenders: tuple[Offender, ...]` — drill-down keyed by
  `unique_id`, with relation-side fields populated for relation-
  valued metrics (Leads, Lags, Relationship Types).
* `notes` — free-form context and per-type breakdown for M4.

M5 does **not** compute manipulation scores or NASA severity
mapping; those live in M11 and M8 respectively per the BUILD-PLAN
milestone graph.

## Scope deferrals (M5)

| Item                                                          | Defer reason                                                                                                                       |
|---------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| 09NOV09 5-day MSP/OpenPlan lag carve-out (DCMA-3)             | Requires per-file tool-provenance detection (MSP / OpenPlan / P6) that is not yet plumbed through the parser. Queued as an opt-in `MetricOptions` extension. |
| Metric 1b "Dangling Logic" (SS-only / FF-only successors)     | M5 prompt scope is Logic 1 only. M6 or a follow-up M5b can ship the dangling subcheck once the engine emits per-relation drivership. |
| NASA severity overlay                                          | Owned by M8 per BUILD-PLAN milestone graph.                                                                                       |
| Manipulation scoring                                           | Owned by M11 per BUILD-PLAN milestone graph.                                                                                       |
