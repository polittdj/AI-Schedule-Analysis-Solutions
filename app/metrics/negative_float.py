"""DCMA Metric 7 — Negative Float.

**Formula** (``dcma-14-point-assessment §4.7``):

    numerator   = count of eligible tasks whose ``total_slack`` is
                  strictly negative.
    denominator = count of eligible tasks (excluding summary, LOE,
                  100%-complete, and CPM-cycle-skipped tasks per §3
                  + engine contract).
    percentage  = numerator / denominator * 100
    threshold   = 0% (absolute — any negative-float task flags;
                  configurable via
                  MetricOptions.negative_float_threshold_pct).

**DECM cross-reference.** ``acumen-reference §4.4`` maps Metric 7 to
the DECM ``Negative Float`` row under Guideline 6 of
``DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*).

**Absolute threshold.** Per BUILD-PLAN §5 M6 AC 3, the 0% threshold
is absolute — any negative float is a forensic signal. A downstream
operator may relax it via :class:`MetricOptions`, but the default
must reproduce the protocol bar.

**CPM-cycle skip.** Tasks flagged ``skipped_due_to_cycle`` by the CPM
engine have no defensible slack value; they are dropped from both
the numerator and the denominator, same as Metric 6.

**Forensic read.** Negative float is the canonical "schedule cannot
meet its promised date" signal (``driving-slack-and-paths §1``). Any
flag here indicates either: (a) the contract finish is infeasible as
planned, (b) a hard constraint is pulling a task earlier than its
logic permits, or (c) a lag/lead was entered with insufficient
working-time room. Every offender is surfaced so the narrative layer
and the M11 manipulation engine can triage each case independently
(``forensic-manipulation-patterns §4.3``).
"""

from __future__ import annotations

from app.engine.duration import minutes_to_working_days
from app.engine.result import CPMResult
from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.exceptions import MissingCPMResultError
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-7"
_METRIC_NAME = "Negative Float"
_SOURCE_SKILL = "dcma-14-point-assessment §4.7"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Negative Float "
    "(total_slack < 0); threshold 0% (absolute)"
)


def _is_loe(task: Task, options: MetricOptions) -> bool:
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _is_excluded(task: Task, options: MetricOptions) -> bool:
    """§3 exclusions — summary / LOE / 100% complete."""
    if options.exclude_summary and task.is_summary:
        return True
    if options.exclude_loe and _is_loe(task, options):
        return True
    if options.exclude_completed and task.percent_complete >= 100.0:
        return True
    return False


def _calendar_hours_per_day(schedule: Schedule) -> float:
    for cal in schedule.calendars:
        if cal.name == schedule.default_calendar_name:
            return cal.hours_per_day
    if schedule.calendars:
        return schedule.calendars[0].hours_per_day
    return 8.0


def run_negative_float(
    schedule: Schedule,
    cpm_result: CPMResult | None = None,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 7 (Negative Float).

    See module docstring for formula and absolute-threshold rationale.
    """
    if cpm_result is None:
        raise MissingCPMResultError(_METRIC_ID)

    opts = options if options is not None else MetricOptions()
    # Threshold citation: dcma-14-point-assessment §4.7; DECM sheet
    # Metrics, Guideline 6 (Negative Float). Default 0% is absolute.
    threshold = ThresholdConfig(
        value=opts.negative_float_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.negative_float_threshold_pct != 0.0,
    )

    hours_per_day = _calendar_hours_per_day(schedule)

    eligible: list[Task] = []
    for t in schedule.tasks:
        if _is_excluded(t, opts):
            continue
        tc = cpm_result.tasks.get(t.unique_id)
        if tc is None or tc.skipped_due_to_cycle:
            continue
        eligible.append(t)

    if not eligible:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes="no eligible tasks (empty schedule or all excluded)",
        )

    offenders: list[Offender] = []
    for t in eligible:
        tc = cpm_result.tasks[t.unique_id]
        # AC 3: any negative total_slack flags (absolute threshold).
        if tc.total_slack_minutes < 0:
            tf_days = minutes_to_working_days(
                tc.total_slack_minutes, hours_per_day=hours_per_day
            )
            offenders.append(
                Offender(
                    unique_id=t.unique_id,
                    name=t.name,
                    value=f"{tf_days:.2f} WD",
                )
            )

    denominator = len(eligible)
    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = (
        Severity.PASS
        if pct <= opts.negative_float_threshold_pct
        else Severity.FAIL
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
    )


class NegativeFloatMetric(BaseMetric):
    """Class wrapper around :func:`run_negative_float`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
        cpm_result: CPMResult | None = None,
    ) -> MetricResult:
        return run_negative_float(schedule, cpm_result, options)
