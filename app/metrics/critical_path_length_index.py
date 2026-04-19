"""DCMA Metric 13 — Critical Path Length Index (CPLI).

**Formula** (``dcma-14-point-assessment §4.13``):

    CPLI = (baseline_cp_length + total_float_to_contract_finish)
           / baseline_cp_length

    threshold = ≥ 0.95 (configurable via
                MetricOptions.cpli_threshold_value).

Where:

* ``baseline_cp_length`` is the critical-path length from baseline
  fields — Phase 1 approximation per
  :func:`app.metrics.baseline.baseline_critical_path_length_minutes`.
* ``total_float_to_contract_finish`` is the signed calendar-minute
  delta between the baseline project finish and the current project
  finish. Positive means the project is forecast to finish before
  baseline (ahead of schedule); negative means late. Convention
  matches the DCMA worked example — see ``§5.2``: CP=250 WD, TF =
  -10 WD → CPLI = 0.96 (pass); TF = -20 WD → CPLI = 0.92 (fail).

**Unit convention.** Both the CP length and the total float are in
**calendar minutes** for Phase 1 (per §9.1 ledger — working-minute
refinement at weekend / holiday boundaries is a Phase 2 item). The
ratio cancels units, so calendar vs working minutes yields the
same CPLI provided both sides use the same unit. The narrative
layer renders the CP length in working days via
:func:`app.engine.duration.minutes_to_working_days` for analyst
readability; the metric itself operates on minutes.

**Baseline project finish.** Derived as the latest ``baseline_finish``
across tasks on the current critical path
(``cpm_result.critical_path_uids``). This matches the Phase 1
convention in
:func:`app.metrics.baseline.baseline_critical_path_length_minutes`:
baseline relations are assumed identical to current relations, so
the critical-path UID set is a defensible stand-in.

**Baseline required.** When the schedule has no baseline coverage
(``has_baseline_coverage(schedule) is False``) or when
:func:`baseline_critical_path_length_minutes` returns ``None``, the
metric returns an indicator-only
:class:`~app.metrics.base.MetricResult` with
``severity=Severity.WARN`` and an explanatory ``notes`` string.
It does **not** raise per BUILD-PLAN §§2.15, 3.7.

**CPMResult required.** ``cpm_result is None`` raises
:class:`~app.metrics.exceptions.MissingCPMResultError`.

**Forensic read.** Per ``§4.13``: "CPLI is the single most sensitive
lagging indicator of programmatic compression. A drop from 1.02 to
0.94 across two periods is a more serious finding than a drop from
1.50 to 1.40, even though the delta is smaller." Metric 13 is read
in trend; the offender list is by design a single row (the critical
path itself) carrying evidence fields rather than a drill-down of
individual tasks.
"""

from __future__ import annotations

from datetime import datetime

from app.engine.duration import minutes_to_working_days
from app.engine.result import CPMResult
from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.baseline import (
    baseline_critical_path_length_minutes,
    has_baseline_coverage,
)
from app.metrics.exceptions import MissingCPMResultError
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule

_METRIC_ID = "DCMA-13"
_METRIC_NAME = "Critical Path Length Index"
_SOURCE_SKILL = "dcma-14-point-assessment §4.13"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Critical Path Length Index "
    "(CPLI); threshold ≥ 0.95"
)


def _calendar_hours_per_day(schedule: Schedule) -> float:
    for cal in schedule.calendars:
        if cal.name == schedule.default_calendar_name:
            return cal.hours_per_day
    if schedule.calendars:
        return schedule.calendars[0].hours_per_day
    return 8.0


def _baseline_project_finish(
    schedule: Schedule, cpm_result: CPMResult
) -> datetime | None:
    """Return the latest ``baseline_finish`` across tasks on the
    current critical path. ``None`` when the set is empty or any
    critical task lacks a baseline finish."""
    if not cpm_result.critical_path_uids:
        return None
    by_uid = {t.unique_id: t for t in schedule.tasks}
    finishes: list[datetime] = []
    for uid in cpm_result.critical_path_uids:
        t = by_uid.get(uid)
        if t is None or t.baseline_finish is None:
            return None
        finishes.append(t.baseline_finish)
    if not finishes:
        return None
    return max(finishes)


def _threshold_config(opts: MetricOptions) -> ThresholdConfig:
    return ThresholdConfig(
        value=opts.cpli_threshold_value,
        direction=">=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.cpli_threshold_value != 0.95,
    )


def run_cpli(
    schedule: Schedule,
    cpm_result: CPMResult | None = None,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 13 (CPLI).

    See module docstring for formula and no-baseline / missing-CPM
    behaviour.
    """
    if cpm_result is None:
        raise MissingCPMResultError(_METRIC_ID)

    opts = options if options is not None else MetricOptions()
    threshold = _threshold_config(opts)

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
                "(dcma-14-point-assessment §4.13)"
            ),
        )

    cp_length = baseline_critical_path_length_minutes(schedule, cpm_result)
    if cp_length is None:
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
                "baseline critical-path length could not be derived "
                "(missing baseline dates on critical-path tasks)"
            ),
        )

    baseline_finish = _baseline_project_finish(schedule, cpm_result)
    current_finish = schedule.project_finish
    if baseline_finish is None or current_finish is None:
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
                "baseline or current project_finish unavailable "
                "(required for CPLI)"
            ),
        )

    total_float_minutes = int(
        (baseline_finish - current_finish).total_seconds() // 60
    )
    numerator = cp_length + total_float_minutes
    denominator = cp_length

    cpli = numerator / denominator if denominator else 0.0
    severity = (
        Severity.PASS if cpli >= opts.cpli_threshold_value else Severity.FAIL
    )

    hpd = _calendar_hours_per_day(schedule)
    cp_wd = minutes_to_working_days(cp_length, hours_per_day=hpd)
    tf_wd = minutes_to_working_days(total_float_minutes, hours_per_day=hpd)

    # Single-row offender carrying the evidence fields. On PASS the
    # offender list is still populated — the single row acts as the
    # transparency record per BUILD-PLAN §6 AC bar #3. The narrative
    # layer renders it as the critical-path summary.
    offenders = (
        Offender(
            unique_id=0,
            name="critical path",
            value=(
                f"CPLI={cpli:.4f}; "
                f"baseline_cp_length={cp_wd:.2f} WD; "
                f"total_float_to_baseline_finish={tf_wd:.2f} WD"
            ),
        ),
    )

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=severity,
        threshold=threshold,
        numerator=numerator,
        denominator=denominator,
        offenders=offenders,
        computed_value=cpli,
        notes=(
            f"CPLI = (baseline_cp_length + total_float) / "
            f"baseline_cp_length = {cpli:.4f}; "
            f"baseline_cp_length={cp_wd:.2f} WD, "
            f"total_float={tf_wd:.2f} WD"
        ),
    )


class CPLIMetric(BaseMetric):
    """Class wrapper around :func:`run_cpli`."""

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
        return run_cpli(schedule, cpm_result, options)
