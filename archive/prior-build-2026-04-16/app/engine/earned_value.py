"""Earned Value Management (EVM) metrics.

Computes the core EVM numbers for a schedule. The tool supports two
units of measure:

* **working_days** — duration-based EVM. Each task contributes its
  `baseline_duration` to BAC; Planned Value and Earned Value are
  expressed in working-day equivalents. This mode is always available
  because the parser normalizes durations to working days.
* **currency** — cost-based EVM. Used automatically when the schedule
  has non-zero assignment costs (`cost` / `actual_cost`). BAC is the
  sum of task costs, EV is cost-weighted by `percent_complete`, AC
  is summed from actual costs.

The engine returns both raw numbers and the derived indices
(SPI, CPI, SV, CV, TCPI, EAC).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict

from app.parser.schema import ScheduleData, TaskData


UNITS_WORKING_DAYS = "working_days"
UNITS_CURRENCY = "currency"


# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #


class EarnedValueResults(BaseModel):
    """Output of `compute_earned_value`."""

    model_config = ConfigDict(extra="forbid")

    units: str  # "working_days" or "currency"
    status_date: Optional[datetime] = None

    planned_value: float
    earned_value: float
    actual_cost: Optional[float] = None
    budget_at_completion: float

    schedule_variance: float
    cost_variance: Optional[float] = None

    schedule_performance_index: float
    cost_performance_index: Optional[float] = None
    to_complete_performance_index: Optional[float] = None
    estimate_at_completion: Optional[float] = None

    notes: Optional[str] = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _detail_tasks(schedule: ScheduleData):
    return [t for t in schedule.tasks if not t.summary]


def _task_total_cost(uid: int, schedule: ScheduleData) -> float:
    """Sum of cost fields across all assignments for a task."""
    total = 0.0
    for a in schedule.assignments:
        if a.task_uid == uid and a.cost is not None:
            total += a.cost
    return total


def _task_actual_cost(uid: int, schedule: ScheduleData) -> float:
    total = 0.0
    for a in schedule.assignments:
        if a.task_uid == uid and a.actual_cost is not None:
            total += a.actual_cost
    return total


def _has_cost_data(schedule: ScheduleData) -> bool:
    for a in schedule.assignments:
        if (a.cost or 0.0) > 0 or (a.actual_cost or 0.0) > 0:
            return True
    return False


def _planned_baseline_days(task: TaskData) -> float:
    """Per-task baseline duration (working days)."""
    if task.baseline_duration is not None:
        return float(task.baseline_duration)
    # Fall back to current duration if no baseline was saved
    if task.duration is not None:
        return float(task.duration)
    return 0.0


def _portion_planned_complete(task: TaskData, status_date: Optional[datetime]) -> float:
    """What fraction of this task *should* be done by the status date.

    Uses the baseline start/finish (or current start/finish as fallback).
    Returns 0..1.
    """
    if status_date is None:
        return 0.0
    start = task.baseline_start or task.start
    finish = task.baseline_finish or task.finish
    if start is None or finish is None or finish <= start:
        return 0.0
    if status_date <= start:
        return 0.0
    if status_date >= finish:
        return 1.0
    total = (finish - start).total_seconds()
    elapsed = (status_date - start).total_seconds()
    return max(0.0, min(1.0, elapsed / total))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compute_earned_value(schedule: ScheduleData) -> EarnedValueResults:
    """Compute EVM metrics from a single `ScheduleData` snapshot."""
    detail = _detail_tasks(schedule)
    status_date = schedule.project_info.status_date

    cost_mode = _has_cost_data(schedule)
    units = UNITS_CURRENCY if cost_mode else UNITS_WORKING_DAYS

    bac = 0.0
    pv = 0.0
    ev = 0.0
    ac: Optional[float] = 0.0 if cost_mode else None

    for task in detail:
        if cost_mode:
            task_bac = _task_total_cost(task.uid, schedule)
            task_ac = _task_actual_cost(task.uid, schedule)
        else:
            task_bac = _planned_baseline_days(task)
            task_ac = None

        bac += task_bac
        portion_planned = _portion_planned_complete(task, status_date)
        pv += task_bac * portion_planned

        pct = (task.percent_complete or 0.0) / 100.0
        ev += task_bac * pct

        if ac is not None and task_ac is not None:
            ac += task_ac

    sv = ev - pv
    cv = (ev - ac) if ac is not None else None
    spi = (ev / pv) if pv > 0 else 1.0
    cpi = (ev / ac) if (ac is not None and ac > 0) else None

    if ac is not None and (bac - ac) != 0 and (bac - ev) != 0:
        tcpi = (bac - ev) / (bac - ac)
    else:
        tcpi = None

    eac: Optional[float] = None
    if cpi is not None and cpi > 0:
        eac = bac / cpi

    notes: Optional[str] = None
    if not cost_mode:
        notes = (
            "Cost data not present in schedule — EVM computed in working-day "
            "equivalents (duration-based)."
        )

    return EarnedValueResults(
        units=units,
        status_date=status_date,
        planned_value=round(pv, 4),
        earned_value=round(ev, 4),
        actual_cost=round(ac, 4) if ac is not None else None,
        budget_at_completion=round(bac, 4),
        schedule_variance=round(sv, 4),
        cost_variance=round(cv, 4) if cv is not None else None,
        schedule_performance_index=round(spi, 4),
        cost_performance_index=round(cpi, 4) if cpi is not None else None,
        to_complete_performance_index=round(tcpi, 4) if tcpi is not None else None,
        estimate_at_completion=round(eac, 4) if eac is not None else None,
        notes=notes,
    )
