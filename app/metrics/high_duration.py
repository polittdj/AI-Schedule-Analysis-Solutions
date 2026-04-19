"""DCMA Metric 8 — High Duration.

**Formula** (``dcma-14-point-assessment §4.8``):

    numerator   = count of eligible incomplete tasks whose
                  remaining duration (converted to working days)
                  strictly exceeds
                  ``high_duration_threshold_working_days`` (default
                  44.0). ``is_rolling_wave=True`` tasks are excluded
                  from the numerator per BUILD-PLAN §5 M6 AC 4.
    denominator = count of eligible incomplete tasks (excluding
                  summary, LOE, and 100%-complete tasks per §3).
    percentage  = numerator / denominator * 100
    threshold   = ≤ 5% (configurable via
                  MetricOptions.high_duration_threshold_pct).

**DECM cross-reference.** ``acumen-reference §4.4`` maps Metric 8 to
the DECM ``High Duration`` row under Guideline 6 of
``DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*).

**Remaining duration semantics.** Per ``dcma-14-point-assessment
§4.8``, the comparison is on **remaining** duration, not total
duration. A task whose total duration is 60 WD but has already been
50% consumed (remaining = 30 WD) does not flag. When
``Task.remaining_duration_minutes`` is zero (typical for tasks the
parser didn't populate it), the metric falls back to
``Task.duration_minutes`` so the DECM default behaviour is
preserved.

**Strict comparison.** A task at 44.0 WD does NOT flag; 44.01 WD
does (same strict-``>`` semantics as Metric 6).

**Rolling-wave exemption.** Per BUILD-PLAN §5 M6 AC 4, a task with
``is_rolling_wave=True`` is excluded from the numerator (and stays
in the denominator — the exemption is a rolling-wave detour, not a
population scope). The same task with the flag absent is counted.

**Working-days conversion.** Routes through
:func:`app.engine.duration.minutes_to_working_days`, honoring the
project-default calendar's ``hours_per_day``.

**Forensic read.** A schedule with many long-duration tasks is a
rolling-wave-deferral signal (``nasa-schedule-management §4`` / M8
NASA overlay). The present metric flags the quantitative violation;
the M8 NASA overlay layers the 6–12 month rolling-wave window rule
on top without modifying this module.
"""

from __future__ import annotations

from app.engine.duration import minutes_to_working_days
from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-8"
_METRIC_NAME = "High Duration"
_SOURCE_SKILL = "dcma-14-point-assessment §4.8"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — High Duration "
    "(remaining_duration > 44 WD); threshold ≤ 5%"
)


def _is_loe(task: Task, options: MetricOptions) -> bool:
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _is_excluded(task: Task, options: MetricOptions) -> bool:
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


def _remaining_minutes(task: Task) -> int:
    """Return the task's remaining duration in minutes.

    DECM scores Metric 8 on remaining duration per §4.8. Parsers that
    don't populate ``remaining_duration_minutes`` (it defaults to 0)
    fall through to total duration so the default DCMA behaviour is
    preserved. An explicitly zero remaining value on a not-100%-
    complete task would be unusual, but mapping it to total duration
    matches the DECM-interpretable worst case.
    """
    if task.remaining_duration_minutes > 0:
        return task.remaining_duration_minutes
    return task.duration_minutes


def run_high_duration(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 8 (High Duration)."""
    opts = options if options is not None else MetricOptions()
    # Threshold citation: dcma-14-point-assessment §4.8; DECM sheet
    # Metrics, Guideline 6 (High Duration).
    threshold = ThresholdConfig(
        value=opts.high_duration_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=(
            opts.high_duration_threshold_pct != 5.0
            or opts.high_duration_threshold_working_days != 44.0
        ),
    )

    hours_per_day = _calendar_hours_per_day(schedule)
    wd_ceiling = opts.high_duration_threshold_working_days

    eligible: list[Task] = [
        t for t in schedule.tasks if not _is_excluded(t, opts)
    ]

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
        rem_minutes = _remaining_minutes(t)
        rem_days = minutes_to_working_days(
            rem_minutes, hours_per_day=hours_per_day
        )
        # AC 4: rolling-wave tasks are exempt from the numerator but
        # remain in the denominator — the flag is a forensic detour,
        # not a population-scope change. Test pair: fixture pins a
        # 60 WD task with is_rolling_wave=True and another without.
        if rem_days > wd_ceiling and not t.is_rolling_wave:
            offenders.append(
                Offender(
                    unique_id=t.unique_id,
                    name=t.name,
                    value=f"{rem_days:.2f} WD",
                )
            )

    denominator = len(eligible)
    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = (
        Severity.PASS
        if pct <= opts.high_duration_threshold_pct
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
        notes=(
            f"working-day ceiling: {wd_ceiling} WD "
            f"(hours_per_day={hours_per_day})"
        ),
    )


class HighDurationMetric(BaseMetric):
    """Class wrapper around :func:`run_high_duration`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_high_duration(schedule, options)
