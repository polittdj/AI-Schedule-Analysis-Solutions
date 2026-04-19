"""DCMA Metric 9 — Invalid Dates.

**Formula** (``dcma-14-point-assessment §4.9``):

    numerator   = count of eligible tasks with at least one invalid
                  date (see kinds below).
    denominator = count of eligible tasks (excluding summary tasks
                  and milestones per the §3 + §4.9 convention;
                  LOE tasks are INCLUDED because date validity is
                  universal per BUILD-PLAN §3.12).
    percentage  = numerator / denominator * 100
    threshold   = 0% — any offender flags FAIL
                  (configurable via
                  MetricOptions.invalid_dates_threshold_pct).

**Invalid-date kinds detected.**

Per ``dcma-14-point-assessment §4.9`` (check 9a + 9b) and the BUILD-
PLAN §5 M7 §3.8 temporal-validity rule:

* ``ACTUAL_AFTER_STATUS`` — ``actual_start`` or ``actual_finish``
  dated **after** ``status_date``. Actuals after the status date are
  temporally impossible (``§4.9`` Rationale: "actuals after the
  status date are temporally impossible and usually indicate a
  data-entry error or a status-date misalignment").
* ``FORECAST_BEFORE_STATUS`` — forecast ``start`` / ``finish``
  (and CPM ``early_start`` / ``early_finish`` / ``late_start`` /
  ``late_finish``) dated **before** ``status_date`` on a task that
  is incomplete and has not started (``actual_start is None``).
  Forecasts before the status date on not-yet-started incomplete
  work mean the update cycle did not refresh the forecast.
* ``ACTUAL_FINISH_BEFORE_ACTUAL_START`` — temporal inversion.
  ``actual_finish`` predates ``actual_start`` for the same task.
  The inversion is a data-entry error independent of the status
  date and flags even when ``status_date`` is set.

**Denominator.** Tasks are eligible when they are neither summary
nor milestone. Milestones carry only a single date (start == finish)
and the forecast-before and actual-after checks do not map cleanly
to that shape; summary tasks are a roll-up and their date fields
inherit from their children. LOE tasks are eligible — per
BUILD-PLAN §3.12, "Metric 9 (invalid dates) DOES apply to LOE —
date validity is universal."

**No status_date.** When ``schedule.status_date is None`` the
status-date-relative checks (A/B) cannot run. The inversion check
(C) is still well-defined, so the metric runs in a reduced mode:
only inversions are reported, and the result carries a
``notes`` string explaining the partial evaluation. This matches
the BUILD-PLAN §2.15 indicator-style reduction pattern — the
metric does not raise.

**Evidence.** Each offender's :attr:`Offender.value` is a
semicolon-separated list of the invalid-date kinds flagged for the
task (e.g., ``"ACTUAL_AFTER_STATUS;ACTUAL_FINISH_BEFORE_ACTUAL_START"``).
A single task with multiple invalidities produces one offender
whose value string enumerates them — the numerator counts tasks,
not kinds, so the denominator math stays honest.

**Forensic read.** §4.9 hits "almost always signal a broken update
cycle — correlate with the dangling-logic count before blaming the
scheduler" (skill §4.9 Forensic read). The M11 manipulation engine
consumes offenders without re-deriving them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

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

_METRIC_ID = "DCMA-9"
_METRIC_NAME = "Invalid Dates"
_SOURCE_SKILL = "dcma-14-point-assessment §4.9"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Invalid Dates "
    "(9a forecast-before-status + 9b actual-after-status); threshold 0%"
)


class InvalidDateKind(StrEnum):
    """Kinds of date invalidity detected by Metric 9.

    Stringly-typed for stable JSON export (same pattern as
    :class:`~app.metrics.base.Severity`).
    """

    ACTUAL_AFTER_STATUS = "ACTUAL_AFTER_STATUS"
    FORECAST_BEFORE_STATUS = "FORECAST_BEFORE_STATUS"
    ACTUAL_FINISH_BEFORE_ACTUAL_START = "ACTUAL_FINISH_BEFORE_ACTUAL_START"


def _is_excluded(task: Task) -> bool:
    """Metric 9 eligibility — excludes summary and milestone only.

    LOE and 100%-complete tasks remain in scope: a completed task
    can still carry a temporal-inversion bug, and an LOE task with
    actuals past the status date is still a data-entry error.
    """
    return task.is_summary or task.is_milestone


def _flag_actual_after(
    task: Task, status_date: datetime | None
) -> list[InvalidDateKind]:
    """Check rule A — actual dates after status date."""
    if status_date is None:
        return []
    kinds: list[InvalidDateKind] = []
    if task.actual_start is not None and task.actual_start > status_date:
        kinds.append(InvalidDateKind.ACTUAL_AFTER_STATUS)
        return kinds  # one flag per task is enough — avoid duplicate
    if task.actual_finish is not None and task.actual_finish > status_date:
        kinds.append(InvalidDateKind.ACTUAL_AFTER_STATUS)
    return kinds


def _flag_forecast_before(
    task: Task, status_date: datetime | None
) -> list[InvalidDateKind]:
    """Check rule B — forecast dates before status on incomplete /
    not-yet-started tasks."""
    if status_date is None:
        return []
    if task.percent_complete >= 100.0:
        return []
    if task.actual_start is not None:
        # Task is in progress; its ``start`` field holds the actual,
        # which is tested by rule A. Rule B is specifically for
        # not-yet-started incomplete work.
        return []
    candidates = (
        task.start,
        task.finish,
        task.early_start,
        task.early_finish,
        task.late_start,
        task.late_finish,
    )
    for d in candidates:
        if d is not None and d < status_date:
            return [InvalidDateKind.FORECAST_BEFORE_STATUS]
    return []


def _flag_inversion(task: Task) -> list[InvalidDateKind]:
    """Check rule C — actual_finish < actual_start."""
    if task.actual_start is None or task.actual_finish is None:
        return []
    if task.actual_finish < task.actual_start:
        return [InvalidDateKind.ACTUAL_FINISH_BEFORE_ACTUAL_START]
    return []


def _task_kinds(task: Task, status_date: datetime | None) -> list[InvalidDateKind]:
    """Return the list of invalidity kinds flagged for a single task."""
    kinds: list[InvalidDateKind] = []
    kinds.extend(_flag_actual_after(task, status_date))
    kinds.extend(_flag_forecast_before(task, status_date))
    kinds.extend(_flag_inversion(task))
    return kinds


def run_invalid_dates(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 9 (Invalid Dates).

    See module docstring for the invalid-date kinds and the
    no-status-date reduced-mode behaviour.
    """
    opts = options if options is not None else MetricOptions()
    # Threshold citation: dcma-14-point-assessment §4.9; DECM sheet
    # Metrics, Guideline 6 (Invalid Dates). Default 0% is absolute.
    threshold = ThresholdConfig(
        value=opts.invalid_dates_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.invalid_dates_threshold_pct != 0.0,
    )

    status_date = schedule.status_date

    eligible = [t for t in schedule.tasks if not _is_excluded(t)]

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
        kinds = _task_kinds(t, status_date)
        if kinds:
            offenders.append(
                Offender(
                    unique_id=t.unique_id,
                    name=t.name,
                    value=";".join(k.value for k in kinds),
                )
            )

    denominator = len(eligible)
    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = (
        Severity.PASS if pct <= opts.invalid_dates_threshold_pct else Severity.FAIL
    )

    if status_date is None:
        notes = (
            "no status_date — only temporal-inversion checks ran "
            "(rules A / B deferred; see dcma-14-point-assessment §4.9)"
        )
    else:
        notes = (
            "invalid-date kinds: ACTUAL_AFTER_STATUS, "
            "FORECAST_BEFORE_STATUS (not-yet-started incomplete), "
            "ACTUAL_FINISH_BEFORE_ACTUAL_START"
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
        notes=notes,
    )


class InvalidDatesMetric(BaseMetric):
    """Class wrapper around :func:`run_invalid_dates`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_invalid_dates(schedule, options)
