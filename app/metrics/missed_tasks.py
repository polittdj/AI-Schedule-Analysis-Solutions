"""DCMA Metric 11 — Missed Tasks.

**Formula** (``dcma-14-point-assessment §4.11``):

    numerator   = count of eligible tasks with ``baseline_finish <=
                  status_date`` AND ``actual_finish is None``.
    denominator = count of eligible tasks with ``baseline_finish <=
                  status_date``.
    percentage  = numerator / denominator * 100
    threshold   = ≤ 5% (configurable via
                  MetricOptions.missed_tasks_threshold_pct).

**Eligibility and exclusions.** Per ``dcma-14-point-assessment §3``
and BUILD-PLAN §§3.11, 3.12:

* Summary tasks and milestones are excluded from both numerator and
  denominator (§3).
* Rolling-wave tasks (``is_rolling_wave=True``) are exempt from the
  numerator but remain in the denominator (§3.11; mirrors Metric 8
  precedent).
* LOE tasks (``is_loe=True``) are exempt from the numerator but
  remain in the denominator (§3.12; LOE tasks don't "complete" in
  the traditional sense).

The denominator is the count of "should have finished by now" tasks;
the numerator is the count of those that in fact did not. Rolling-
wave and LOE exemptions reduce the numerator without inflating the
denominator because the skill's forensic intent is "miss rate of
genuine deliverables", not "miss rate inclusive of placeholder
work".

**Baseline required.** On a schedule with no baseline coverage
(:func:`~app.metrics.baseline.has_baseline_coverage` returns
``False`` across the non-milestone / non-summary task population),
the metric returns an indicator-only :class:`MetricResult` with
``severity=Severity.WARN`` and an explanatory note. It does **not**
raise — per BUILD-PLAN §§2.15, 3.7 the raise is reserved for CPM
prerequisites (Missing CPMResult on CPM-consuming metrics); a
missing baseline is an inspection gap, not a structural error.

**Status date required.** When ``schedule.status_date is None`` the
"baseline ≤ status" predicate is undefined. Same convention as the
baseline-missing case: indicator-only WARN with a note.

**Forensic read.** Per ``§4.11``: "Missed-task share trending upward
across versions is the clearest leading indicator of schedule
failure and is the ground-truth input to §4.14 BEI." Metric 11 is
the inventory lens; Metric 14 is the velocity lens; they almost
always move together.
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

_METRIC_ID = "DCMA-11"
_METRIC_NAME = "Missed Tasks"
_SOURCE_SKILL = "dcma-14-point-assessment §4.11"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Missed Tasks "
    "(incomplete tasks with baseline_finish ≤ status_date); threshold ≤ 5%"
)


def _is_loe(task: Task, options: MetricOptions) -> bool:
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _denominator_eligible(task: Task) -> bool:
    """Denominator eligibility — excludes summary and milestone."""
    return not task.is_summary and not task.is_milestone


def _exempt_from_numerator(task: Task, options: MetricOptions) -> bool:
    """Rolling-wave and LOE exemptions (§§3.11, 3.12)."""
    if task.is_rolling_wave:
        return True
    if options.exclude_loe and _is_loe(task, options):
        return True
    return False


def _indicator_threshold(opts: MetricOptions) -> ThresholdConfig:
    """Threshold carrier with the configured percent kept populated
    even in the indicator-only branches so downstream consumers can
    still read a consistent schema."""
    return ThresholdConfig(
        value=opts.missed_tasks_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.missed_tasks_threshold_pct != 5.0,
    )


def run_missed_tasks(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 11 (Missed Tasks).

    Baseline-required per ``dcma-14-point-assessment §4.11``. See
    module docstring for exemption policy and no-baseline /
    no-status-date graceful behaviour.
    """
    opts = options if options is not None else MetricOptions()
    threshold = _indicator_threshold(opts)

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
                "(dcma-14-point-assessment §4.11)"
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
                "(dcma-14-point-assessment §4.11)"
            ),
        )

    # Denominator: baseline-due tasks (excluding summary + milestone).
    denominator_tasks: list[Task] = [
        t
        for t in tasks_with_baseline_finish_by(schedule, schedule.status_date)
        if _denominator_eligible(t)
    ]

    if not denominator_tasks:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes=(
                "no baseline-due tasks at or before status_date "
                "(vacuous PASS)"
            ),
        )

    offenders: list[Offender] = []
    for t in denominator_tasks:
        if t.actual_finish is not None:
            # Task finished — not missed.
            continue
        if _exempt_from_numerator(t, opts):
            continue
        # An offender: baseline-due, not actually finished, not
        # rolling-wave, not LOE.
        offenders.append(
            Offender(
                unique_id=t.unique_id,
                name=t.name,
                value=(
                    f"baseline_finish={t.baseline_finish.isoformat()}; "
                    f"status_date={schedule.status_date.isoformat()}"
                ),
            )
        )

    denominator = len(denominator_tasks)
    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = (
        Severity.PASS if pct <= opts.missed_tasks_threshold_pct else Severity.FAIL
    )

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=severity,
        threshold=threshold,
        numerator=numerator,
        denominator=denominator,
        offenders=tuple(offenders),
        computed_value=pct,
        notes=(
            "denominator = tasks with baseline_finish ≤ status_date "
            "(excl. summary, milestone); numerator = those without "
            "actual_finish (excl. rolling-wave, LOE)"
        ),
    )


class MissedTasksMetric(BaseMetric):
    """Class wrapper around :func:`run_missed_tasks`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_missed_tasks(schedule, options)
