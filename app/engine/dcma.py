"""DCMA 14-Point Schedule Assessment.

The Defense Contract Management Agency (DCMA) 14-point schedule health
check is the industry-standard go/no-go for contractor schedules. Each
point is a deterministic metric with a threshold; failing a metric
earns a specific finding in the forensic report.

Numbers use **working days** (consistent with the parser) for all
duration-based thresholds. The 44-day threshold in DCMA corresponds
roughly to a two-month activity.

References
----------
* DCMA 14-Point Assessment (v3, 2012)
* GAO Schedule Assessment Guide (GAO-16-89G)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.engine.cpm import CPMResults, compute_cpm
from app.parser.schema import ScheduleData, TaskData


# --------------------------------------------------------------------------- #
# Thresholds (DCMA 14-point, standard industry values)
# --------------------------------------------------------------------------- #

THRESHOLD_LOGIC_PCT = 5.0
THRESHOLD_LEADS_PCT = 0.0
THRESHOLD_LAGS_PCT = 5.0
THRESHOLD_RELATION_TYPES_PCT = 5.0
THRESHOLD_HARD_CONSTRAINTS_PCT = 5.0
THRESHOLD_HIGH_FLOAT_PCT = 5.0
THRESHOLD_NEGATIVE_FLOAT_PCT = 0.0
THRESHOLD_HIGH_DURATION_PCT = 5.0
THRESHOLD_INVALID_DATES_PCT = 0.0
THRESHOLD_RESOURCES_PCT = 5.0
THRESHOLD_MISSED_TASKS_PCT = 5.0
THRESHOLD_CPLI = 1.0  # ≥1.0 passes
THRESHOLD_BEI = 1.0  # ≥1.0 passes
HIGH_FLOAT_DAYS = 44.0
HIGH_DURATION_DAYS = 44.0
HARD_CONSTRAINT_TYPES = {"MUST_START_ON", "MUST_FINISH_ON"}


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class DCMAMetric(BaseModel):
    """A single DCMA point's evaluation result."""

    model_config = ConfigDict(extra="forbid")

    number: int  # 1–14
    name: str
    value: float
    threshold: float
    unit: str  # "%", "count", "index", "bool"
    comparison: str  # "<", "<=", ">", ">=", "=="
    passed: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class DCMAResults(BaseModel):
    """Output of `compute_dcma`."""

    model_config = ConfigDict(extra="forbid")

    metrics: List[DCMAMetric] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    overall_score_pct: float = 0.0  # % of metrics passed
    status_date: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Metric helpers
# --------------------------------------------------------------------------- #


def _detail_tasks(schedule: ScheduleData) -> List[TaskData]:
    return [t for t in schedule.tasks if not t.summary]


def _incomplete(tasks: List[TaskData]) -> List[TaskData]:
    return [t for t in tasks if (t.percent_complete or 0.0) < 100.0]


def _pct(num: int, denom: int) -> float:
    return (num / denom * 100.0) if denom > 0 else 0.0


def _evaluate(value: float, threshold: float, comparison: str) -> bool:
    if comparison == "<":
        return value < threshold
    if comparison == "<=":
        return value <= threshold
    if comparison == ">":
        return value > threshold
    if comparison == ">=":
        return value >= threshold
    if comparison == "==":
        return abs(value - threshold) < 1e-9
    return False


# --------------------------------------------------------------------------- #
# Individual metric calculators
# --------------------------------------------------------------------------- #


def _metric_logic(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    incomplete = _incomplete(detail)
    missing = [
        t for t in incomplete if (not t.predecessors) or (not t.successors)
    ]
    value = _pct(len(missing), len(incomplete))
    return DCMAMetric(
        number=1,
        name="Logic",
        value=round(value, 2),
        threshold=THRESHOLD_LOGIC_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_LOGIC_PCT, "<"),
        details={
            "missing_count": len(missing),
            "incomplete_count": len(incomplete),
            "missing_uids": [t.uid for t in missing],
        },
    )


def _metric_leads(schedule: ScheduleData) -> DCMAMetric:
    rels = schedule.relationships
    leads = [r for r in rels if r.lag_days < 0]
    value = _pct(len(leads), len(rels))
    return DCMAMetric(
        number=2,
        name="Leads",
        value=round(value, 2),
        threshold=THRESHOLD_LEADS_PCT,
        unit="%",
        comparison="<=",
        passed=_evaluate(value, THRESHOLD_LEADS_PCT, "<="),
        details={
            "lead_count": len(leads),
            "total_relationships": len(rels),
        },
    )


def _metric_lags(schedule: ScheduleData) -> DCMAMetric:
    rels = schedule.relationships
    lags = [r for r in rels if r.lag_days > 0]
    value = _pct(len(lags), len(rels))
    return DCMAMetric(
        number=3,
        name="Lags",
        value=round(value, 2),
        threshold=THRESHOLD_LAGS_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_LAGS_PCT, "<"),
        details={
            "lag_count": len(lags),
            "total_relationships": len(rels),
        },
    )


def _metric_relationship_types(schedule: ScheduleData) -> DCMAMetric:
    rels = schedule.relationships
    non_fs = [r for r in rels if r.type != "FS"]
    value = _pct(len(non_fs), len(rels))
    return DCMAMetric(
        number=4,
        name="Relationship Types",
        value=round(value, 2),
        threshold=THRESHOLD_RELATION_TYPES_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_RELATION_TYPES_PCT, "<"),
        details={
            "non_fs_count": len(non_fs),
            "total_relationships": len(rels),
            "type_breakdown": {
                t: sum(1 for r in rels if r.type == t)
                for t in {r.type for r in rels}
            },
        },
    )


def _metric_hard_constraints(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    hard = [
        t
        for t in detail
        if t.constraint_type and t.constraint_type.upper() in HARD_CONSTRAINT_TYPES
    ]
    value = _pct(len(hard), len(detail))
    return DCMAMetric(
        number=5,
        name="Hard Constraints",
        value=round(value, 2),
        threshold=THRESHOLD_HARD_CONSTRAINTS_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_HARD_CONSTRAINTS_PCT, "<"),
        details={
            "hard_count": len(hard),
            "total_detail": len(detail),
            "hard_uids": [t.uid for t in hard],
        },
    )


def _metric_high_float(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    incomplete = _incomplete(detail)
    high = [
        t
        for t in incomplete
        if t.total_slack is not None and t.total_slack > HIGH_FLOAT_DAYS
    ]
    value = _pct(len(high), len(incomplete))
    return DCMAMetric(
        number=6,
        name="High Float",
        value=round(value, 2),
        threshold=THRESHOLD_HIGH_FLOAT_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_HIGH_FLOAT_PCT, "<"),
        details={
            "high_float_count": len(high),
            "incomplete_count": len(incomplete),
            "threshold_days": HIGH_FLOAT_DAYS,
            "high_float_uids": [t.uid for t in high],
        },
    )


def _metric_negative_float(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    neg = [
        t
        for t in detail
        if t.total_slack is not None and t.total_slack < 0
    ]
    value = _pct(len(neg), len(detail))
    return DCMAMetric(
        number=7,
        name="Negative Float",
        value=round(value, 2),
        threshold=THRESHOLD_NEGATIVE_FLOAT_PCT,
        unit="%",
        comparison="<=",
        passed=_evaluate(value, THRESHOLD_NEGATIVE_FLOAT_PCT, "<="),
        details={
            "negative_count": len(neg),
            "total_detail": len(detail),
            "negative_uids": [t.uid for t in neg],
        },
    )


def _metric_high_duration(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    incomplete = _incomplete(detail)
    high = [
        t
        for t in incomplete
        if t.duration is not None and t.duration > HIGH_DURATION_DAYS
    ]
    value = _pct(len(high), len(incomplete))
    return DCMAMetric(
        number=8,
        name="High Duration",
        value=round(value, 2),
        threshold=THRESHOLD_HIGH_DURATION_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_HIGH_DURATION_PCT, "<"),
        details={
            "high_duration_count": len(high),
            "incomplete_count": len(incomplete),
            "threshold_days": HIGH_DURATION_DAYS,
            "high_duration_uids": [t.uid for t in high],
        },
    )


def _metric_invalid_dates(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    status_date = schedule.project_info.status_date
    if status_date is None:
        return DCMAMetric(
            number=9,
            name="Invalid Dates",
            value=0.0,
            threshold=THRESHOLD_INVALID_DATES_PCT,
            unit="%",
            comparison="<=",
            passed=True,  # cannot evaluate without a status date
            details={"reason": "no_status_date"},
        )
    invalid: List[int] = []
    for t in detail:
        if t.actual_start is not None and t.actual_start > status_date:
            invalid.append(t.uid)
            continue
        if t.actual_finish is not None and t.actual_finish > status_date:
            invalid.append(t.uid)
    value = _pct(len(invalid), len(detail))
    return DCMAMetric(
        number=9,
        name="Invalid Dates",
        value=round(value, 2),
        threshold=THRESHOLD_INVALID_DATES_PCT,
        unit="%",
        comparison="<=",
        passed=_evaluate(value, THRESHOLD_INVALID_DATES_PCT, "<="),
        details={
            "invalid_count": len(invalid),
            "total_detail": len(detail),
            "invalid_uids": invalid,
        },
    )


def _metric_resources(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    incomplete = _incomplete(detail)
    assigned_uids = {a.task_uid for a in schedule.assignments}
    missing = [
        t
        for t in incomplete
        if not (t.resource_names or "").strip() and t.uid not in assigned_uids
    ]
    value = _pct(len(missing), len(incomplete))
    return DCMAMetric(
        number=10,
        name="Resources",
        value=round(value, 2),
        threshold=THRESHOLD_RESOURCES_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_RESOURCES_PCT, "<"),
        details={
            "missing_resource_count": len(missing),
            "incomplete_count": len(incomplete),
            "missing_uids": [t.uid for t in missing],
        },
    )


def _metric_missed_tasks(schedule: ScheduleData) -> DCMAMetric:
    detail = _detail_tasks(schedule)
    status_date = schedule.project_info.status_date
    if status_date is None:
        return DCMAMetric(
            number=11,
            name="Missed Tasks",
            value=0.0,
            threshold=THRESHOLD_MISSED_TASKS_PCT,
            unit="%",
            comparison="<",
            passed=True,
            details={"reason": "no_status_date"},
        )
    missed = [
        t
        for t in detail
        if t.baseline_finish is not None
        and t.baseline_finish < status_date
        and (t.percent_complete or 0.0) < 100.0
    ]
    value = _pct(len(missed), len(detail))
    return DCMAMetric(
        number=11,
        name="Missed Tasks",
        value=round(value, 2),
        threshold=THRESHOLD_MISSED_TASKS_PCT,
        unit="%",
        comparison="<",
        passed=_evaluate(value, THRESHOLD_MISSED_TASKS_PCT, "<"),
        details={
            "missed_count": len(missed),
            "total_detail": len(detail),
            "missed_uids": [t.uid for t in missed],
        },
    )


def _metric_critical_path_test(
    schedule: ScheduleData, cpm_results: Optional[CPMResults]
) -> DCMAMetric:
    """Verify that adding 1 day to a critical task delays the project by 1 day."""
    if cpm_results is None:
        cpm_results = compute_cpm(schedule)

    if not cpm_results.critical_path_uids:
        return DCMAMetric(
            number=12,
            name="Critical Path Test",
            value=0.0,
            threshold=1.0,
            unit="bool",
            comparison="==",
            passed=False,
            details={"reason": "no_critical_path"},
        )

    original_duration = cpm_results.project_duration_days
    target_uid = cpm_results.critical_path_uids[0]

    # Shallow-rebuild the schedule with 1 extra day on the target task.
    modified_tasks = []
    for t in schedule.tasks:
        if t.uid == target_uid:
            modified_tasks.append(
                t.model_copy(update={"duration": (t.duration or 0.0) + 1.0})
            )
        else:
            modified_tasks.append(t)
    modified_schedule = schedule.model_copy(update={"tasks": modified_tasks})
    modified_cpm = compute_cpm(modified_schedule)
    delay = modified_cpm.project_duration_days - original_duration
    passed = abs(delay - 1.0) < 0.01

    return DCMAMetric(
        number=12,
        name="Critical Path Test",
        value=1.0 if passed else 0.0,
        threshold=1.0,
        unit="bool",
        comparison="==",
        passed=passed,
        details={
            "original_duration": original_duration,
            "modified_duration": modified_cpm.project_duration_days,
            "delay_days": round(delay, 4),
            "modified_task_uid": target_uid,
        },
    )


def _metric_cpli(
    schedule: ScheduleData, cpm_results: Optional[CPMResults]
) -> DCMAMetric:
    """Critical Path Length Index = (CPL + Total Float) / CPL."""
    status_date = schedule.project_info.status_date
    current_finish = schedule.project_info.finish_date
    baseline_finishes = [
        t.baseline_finish for t in schedule.tasks if t.baseline_finish is not None
    ]
    baseline_finish = max(baseline_finishes) if baseline_finishes else None

    if status_date is None or current_finish is None or baseline_finish is None:
        return DCMAMetric(
            number=13,
            name="CPLI",
            value=1.0,
            threshold=THRESHOLD_CPLI,
            unit="index",
            comparison=">=",
            passed=True,
            details={"reason": "insufficient_date_data"},
        )

    cpl = max(1.0, (baseline_finish - status_date).total_seconds() / 86400.0)
    slip = (current_finish - baseline_finish).total_seconds() / 86400.0
    cpli = (cpl - slip) / cpl

    return DCMAMetric(
        number=13,
        name="CPLI",
        value=round(cpli, 4),
        threshold=THRESHOLD_CPLI,
        unit="index",
        comparison=">=",
        passed=_evaluate(cpli, THRESHOLD_CPLI, ">="),
        details={
            "critical_path_length_days": round(cpl, 2),
            "slip_days": round(slip, 2),
            "baseline_finish": baseline_finish.isoformat(),
            "current_finish": current_finish.isoformat(),
        },
    )


def _metric_bei(schedule: ScheduleData) -> DCMAMetric:
    """Baseline Execution Index = completed / tasks planned complete."""
    detail = _detail_tasks(schedule)
    status_date = schedule.project_info.status_date
    if status_date is None:
        return DCMAMetric(
            number=14,
            name="BEI",
            value=1.0,
            threshold=THRESHOLD_BEI,
            unit="index",
            comparison=">=",
            passed=True,
            details={"reason": "no_status_date"},
        )
    planned = [
        t for t in detail if t.baseline_finish is not None and t.baseline_finish <= status_date
    ]
    completed = [t for t in planned if (t.percent_complete or 0.0) >= 100.0]
    if not planned:
        return DCMAMetric(
            number=14,
            name="BEI",
            value=1.0,
            threshold=THRESHOLD_BEI,
            unit="index",
            comparison=">=",
            passed=True,
            details={"reason": "no_tasks_planned_complete"},
        )
    bei = len(completed) / len(planned)
    return DCMAMetric(
        number=14,
        name="BEI",
        value=round(bei, 4),
        threshold=THRESHOLD_BEI,
        unit="index",
        comparison=">=",
        passed=_evaluate(bei, THRESHOLD_BEI, ">="),
        details={
            "completed_count": len(completed),
            "planned_count": len(planned),
        },
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compute_dcma(
    schedule: ScheduleData, cpm_results: Optional[CPMResults] = None
) -> DCMAResults:
    """Run all 14 DCMA checks against a schedule."""
    metrics: List[DCMAMetric] = [
        _metric_logic(schedule),
        _metric_leads(schedule),
        _metric_lags(schedule),
        _metric_relationship_types(schedule),
        _metric_hard_constraints(schedule),
        _metric_high_float(schedule),
        _metric_negative_float(schedule),
        _metric_high_duration(schedule),
        _metric_invalid_dates(schedule),
        _metric_resources(schedule),
        _metric_missed_tasks(schedule),
        _metric_critical_path_test(schedule, cpm_results),
        _metric_cpli(schedule, cpm_results),
        _metric_bei(schedule),
    ]
    passed = sum(1 for m in metrics if m.passed)
    failed = len(metrics) - passed
    return DCMAResults(
        metrics=metrics,
        passed_count=passed,
        failed_count=failed,
        overall_score_pct=round(passed / len(metrics) * 100.0, 2),
        status_date=schedule.project_info.status_date,
    )
