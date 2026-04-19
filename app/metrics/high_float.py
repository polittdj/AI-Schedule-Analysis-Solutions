"""DCMA Metric 6 — High Float.

**Formula** (``dcma-14-point-assessment §4.6``):

    numerator   = count of eligible incomplete tasks whose
                  ``total_slack`` (converted to working days)
                  strictly exceeds
                  ``high_float_threshold_working_days`` (default 44.0).
    denominator = count of eligible incomplete tasks (excluding
                  summary, LOE, 100%-complete, and CPM-cycle-skipped
                  tasks per §3 + engine contract).
    percentage  = numerator / denominator * 100
    threshold   = ≤ 5% (configurable via
                  MetricOptions.high_float_threshold_pct).

**DECM cross-reference.** ``acumen-reference §4.4`` maps Metric 6 to
the DECM ``High Float`` row under Guideline 6 of
``DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*).

**Working-days conversion.** :func:`app.engine.duration.minutes_to_
working_days` is the single source of truth for the minutes → WD
conversion (``mpp-parsing-com-automation §3.5`` Gotcha 5). The
conversion factor is the project default calendar's
:attr:`~app.models.calendar.Calendar.hours_per_day` so non-8h/day
calendars scale correctly. There is no duplicate arithmetic in this
module.

**Strict comparison.** Per BUILD-PLAN §5 M6 AC 2, a task with
``total_slack = 44.0 WD`` does **not** flag; ``44.01 WD`` does.
``>`` (strict) is used rather than ``>=``.

**CPM-cycle skip.** Tasks flagged ``skipped_due_to_cycle`` by the CPM
engine have no defensible slack value. They are excluded from both
the numerator and the denominator rather than counted as zero-float
— the mutation-vs-wrap invariant (BUILD-PLAN M4 AC10) prevents the
metric from fabricating CPM output for those tasks.

**Forensic read.** Sustained high float across versions indicates
unconsumed programmatic margin (``forensic-manipulation-patterns
§10``) — slack that never erodes is a likely candidate for network-
of-convenience links (dummy relations inserted to dampen slip
propagation).
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

_METRIC_ID = "DCMA-6"
_METRIC_NAME = "High Float"
_SOURCE_SKILL = "dcma-14-point-assessment §4.6"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — High Float "
    "(total_slack > 44 WD); threshold ≤ 5%"
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
    """Return the default calendar's ``hours_per_day``.

    Looks up :attr:`Schedule.default_calendar_name`; falls back to
    the first calendar if none matches (permissive because the
    metric must still run when the default-calendar pointer is
    stale — the narrative can annotate). Final fallback: 8.0.
    """
    for cal in schedule.calendars:
        if cal.name == schedule.default_calendar_name:
            return cal.hours_per_day
    if schedule.calendars:
        return schedule.calendars[0].hours_per_day
    return 8.0


def run_high_float(
    schedule: Schedule,
    cpm_result: CPMResult | None = None,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 6 (High Float).

    See module docstring for formula, threshold, and forensic read.
    """
    if cpm_result is None:
        raise MissingCPMResultError(_METRIC_ID)

    opts = options if options is not None else MetricOptions()
    # Threshold citation: dcma-14-point-assessment §4.6; DECM sheet
    # Metrics, Guideline 6 (High Float).
    threshold = ThresholdConfig(
        value=opts.high_float_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=(
            opts.high_float_threshold_pct != 5.0
            or opts.high_float_threshold_working_days != 44.0
        ),
    )

    hours_per_day = _calendar_hours_per_day(schedule)
    # Threshold citation for the WD ceiling: §4.6; DECM default 44 WD.
    wd_ceiling = opts.high_float_threshold_working_days

    eligible: list[Task] = []
    for t in schedule.tasks:
        if _is_excluded(t, opts):
            continue
        tc = cpm_result.tasks.get(t.unique_id)
        # CPM contract (M4 mutation-vs-wrap invariant): a task the
        # engine skipped due to cycle has no defensible slack; drop
        # from the eligible population entirely.
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
        tf_days = minutes_to_working_days(
            tc.total_slack_minutes, hours_per_day=hours_per_day
        )
        # Strict ``>`` per AC 2: a task with TF == 44.0 does NOT flag.
        if tf_days > wd_ceiling:
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
        Severity.PASS if pct <= opts.high_float_threshold_pct else Severity.FAIL
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


class HighFloatMetric(BaseMetric):
    """Class wrapper around :func:`run_high_float`.

    Diverges from the M5 ``BaseMetric.run`` signature: this metric
    consumes a :class:`CPMResult`, so the wrapper accepts it as a
    second positional. The abstract contract in
    :class:`~app.metrics.base.BaseMetric` is deliberately satisfied
    by the two-argument form; M6-and-later metric wrappers expose a
    richer invocation surface but remain compatible with homogeneous
    registries by virtue of the shared ``metric_id`` / ``metric_name``
    attributes.
    """

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
        return run_high_float(schedule, cpm_result, options)
