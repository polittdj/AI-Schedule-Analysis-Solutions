"""DCMA Metric 14 — Baseline Execution Index (BEI).

**Formula** (``dcma-14-point-assessment §4.14`` / §5.1):

    numerator   = count of eligible tasks with baseline_finish ≤
                  status_date AND actual_finish ≤ status_date.
    denominator = count of eligible tasks with baseline_finish ≤
                  status_date.
    BEI         = numerator / denominator
    threshold   = ≥ 0.95 (configurable via
                  MetricOptions.bei_threshold_value).

**Cumulative-hit definition.** Per ``§4.14``: "The 09NOV09 protocol
uses cumulative counts — tasks completed at any time up to the
status date divided by tasks whose baseline finish was on or before
the status date. Edwards 2016 emphasises that the numerator counts
tasks that 'hit' the status-date target even if they hit late." A
task that finished after its baseline but still before the status
date counts in the numerator. A task that finished after the status
date does not.

**Worked example** (``§5.1``): 200-task schedule, 80 baseline-due,
68 completed-by-status → BEI = 68 / 80 = 0.85 → FAIL.
Early-finishing tasks with later baselines are excluded — their
denominator row is outside the BEI window — and therefore excluded
from the numerator as well.

**Eligibility and exclusions.** Per ``dcma-14-point-assessment §3``
and BUILD-PLAN §§3.11, 3.12:

* Summary tasks and milestones are excluded from both numerator
  and denominator (§3).
* Rolling-wave tasks (``is_rolling_wave=True``) are exempt from the
  numerator but remain in the denominator (§3.11; mirrors Metric 11
  precedent — they would otherwise drag BEI down for a planning
  reason the schedule already accounts for).
* LOE tasks (``is_loe=True``) are exempt from the numerator but
  remain in the denominator (§3.12; LOE tasks don't "complete" in
  the traditional sense).

**Zero-denominator.** A schedule with no baseline-due tasks in the
window returns an indicator-only :class:`MetricResult` with
``severity=Severity.WARN`` and ``notes`` explaining the vacuous
case. BEI is mathematically undefined when the denominator is zero;
returning 1.0 would be misleading.

**Baseline / status required.** No-baseline-coverage and
no-``status_date`` cases return indicator-only WARN per BUILD-PLAN
§2.15. The metric never raises — raise is reserved for CPM
prerequisites.

**Forensic read.** Per ``§4.14`` Forensic read: "BEI pairs with
Missed Tasks (§4.11): BEI is the velocity lens, Missed Tasks is the
inventory lens, and they almost always move together." A
consistently low BEI across versions is a classic schedule-failure
leading indicator; a BEI-down + Missed-Tasks-up divergence within
a period suggests the scheduler is absorbing hits against later-
baseline tasks.
"""

from __future__ import annotations

from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.baseline import (
    has_baseline_coverage,
    tasks_with_baseline_finish_by,
)
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-14"
_METRIC_NAME = "Baseline Execution Index"
_SOURCE_SKILL = "dcma-14-point-assessment §4.14"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Baseline Execution Index "
    "(BEI); threshold ≥ 0.95 (cumulative-hit definition per §4.14)"
)


def _is_loe(task: Task, options: MetricOptions) -> bool:
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _denominator_eligible(task: Task) -> bool:
    return not task.is_summary and not task.is_milestone


def _exempt_from_numerator(task: Task, options: MetricOptions) -> bool:
    if task.is_rolling_wave:
        return True
    if options.exclude_loe and _is_loe(task, options):
        return True
    return False


def _threshold_config(opts: MetricOptions) -> ThresholdConfig:
    return ThresholdConfig(
        value=opts.bei_threshold_value,
        direction=">=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.bei_threshold_value != 0.95,
    )


def run_bei(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 14 (BEI).

    See module docstring for formula, cumulative-hit definition, and
    indicator-only behaviour in the baseline-missing / status-missing
    / zero-denominator cases.
    """
    opts = options if options is not None else MetricOptions()
    threshold = _threshold_config(opts)

    if schedule.status_date is None:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.WARN,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=None,
            notes=(
                "no status_date — metric not computable "
                "(dcma-14-point-assessment §4.14)"
            ),
        )

    if not has_baseline_coverage(schedule):
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.WARN,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=None,
            notes=(
                "no baseline available — metric not computable "
                "(dcma-14-point-assessment §4.14)"
            ),
        )

    baseline_due = [
        t
        for t in tasks_with_baseline_finish_by(schedule, schedule.status_date)
        if _denominator_eligible(t)
    ]

    if not baseline_due:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.WARN,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=None,
            notes=(
                "no baseline-due tasks in window — BEI undefined "
                "(zero denominator)"
            ),
        )

    status_date = schedule.status_date
    numerator_tasks: list[Task] = []
    missed_tasks: list[Task] = []
    for t in baseline_due:
        if _exempt_from_numerator(t, opts):
            # Rolling-wave or LOE — denominator only.
            continue
        if t.actual_finish is not None and t.actual_finish <= status_date:
            numerator_tasks.append(t)
        else:
            missed_tasks.append(t)

    denominator = len(baseline_due)
    numerator = len(numerator_tasks)
    bei = numerator / denominator
    severity = (
        Severity.PASS if bei >= opts.bei_threshold_value else Severity.FAIL
    )

    offenders = tuple(
        Offender(
            unique_id=t.unique_id,
            name=t.name,
            value=(
                f"baseline_finish={t.baseline_finish.isoformat()}; "
                f"not completed by status_date"
            ),
        )
        for t in missed_tasks
    )

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=severity,
        threshold=threshold,
        numerator=numerator,
        denominator=denominator,
        offenders=offenders,
        computed_value=bei,
        notes=(
            f"BEI = completed-by-status ({numerator}) / "
            f"baseline-due ({denominator}) = {bei:.4f}; "
            f"rolling-wave and LOE tasks exempt from numerator"
        ),
    )


class BEIMetric(BaseMetric):
    """Class wrapper around :func:`run_bei`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_bei(schedule, options)
