"""Float consumption analysis.

Walks a `ComparisonResults` to understand how total float evolved
between two schedule updates. Answers the questions:

* Which tasks became critical (had slack, now don't)?
* Which tasks dropped off the critical path (had zero slack, now have some)?
* Is the project as a whole consuming float, recovering it, or flat?
* Which WBS areas are losing the most float?

The analysis relies on the `total_slack_delta` values the comparator
already computed plus the parser-provided `critical` flag for the
threshold-crossing detection. Both signals are used; if either
indicates a transition the task is flagged.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.engine.comparator import ComparisonResults, TaskDelta
from app.parser.schema import ScheduleData, TaskData


# Threshold to decide whether a float value is "zero" for criticality
CRITICAL_EPSILON = 0.01
# Net delta above/below which the trend flips from "stable"
TREND_THRESHOLD_DAYS = 1.0


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class TaskFloatChange(BaseModel):
    """Per-task float-consumption snapshot."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    name: Optional[str] = None
    wbs: Optional[str] = None
    prior_total_float: Optional[float] = None
    later_total_float: Optional[float] = None
    float_delta: Optional[float] = None
    became_critical: bool = False
    dropped_off_critical: bool = False


class WBSFloatSummary(BaseModel):
    """Roll-up of float movement by WBS prefix."""

    model_config = ConfigDict(extra="forbid")

    wbs_prefix: str
    task_count: int
    avg_float_delta: float
    total_float_consumed: float  # sum of negative deltas (absolute value)


class FloatAnalysisResults(BaseModel):
    """Output of `analyze_float`."""

    model_config = ConfigDict(extra="forbid")

    task_changes: List[TaskFloatChange] = Field(default_factory=list)
    became_critical_uids: List[int] = Field(default_factory=list)
    dropped_off_critical_uids: List[int] = Field(default_factory=list)
    net_float_delta: float = 0.0
    avg_float_delta: float = 0.0
    wbs_summaries: List[WBSFloatSummary] = Field(default_factory=list)
    trend: str = "stable"  # "consuming" | "recovering" | "stable"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _wbs_prefix(wbs: Optional[str], depth: int = 2) -> str:
    """Return the first `depth` dot-separated segments of a WBS code."""
    if not wbs:
        return "(unassigned)"
    parts = wbs.split(".")
    return ".".join(parts[:depth]) if parts else wbs


def _crossed_zero_down(prior: Optional[float], later: Optional[float]) -> bool:
    """Prior > epsilon and later <= epsilon → task became critical."""
    if prior is None or later is None:
        return False
    return prior > CRITICAL_EPSILON and later <= CRITICAL_EPSILON


def _crossed_zero_up(prior: Optional[float], later: Optional[float]) -> bool:
    if prior is None or later is None:
        return False
    return prior <= CRITICAL_EPSILON and later > CRITICAL_EPSILON


def _task_lookup(schedule: ScheduleData) -> Dict[int, TaskData]:
    return {t.uid: t for t in schedule.tasks}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def analyze_float(
    comparison: ComparisonResults,
    prior_schedule: ScheduleData,
    later_schedule: ScheduleData,
) -> FloatAnalysisResults:
    """Produce a `FloatAnalysisResults` from a comparison + both schedules."""
    prior_tasks = _task_lookup(prior_schedule)
    later_tasks = _task_lookup(later_schedule)

    task_changes: List[TaskFloatChange] = []
    became_critical: List[int] = []
    dropped_off_critical: List[int] = []

    for delta in comparison.task_deltas:
        prior_task = prior_tasks.get(delta.uid)
        later_task = later_tasks.get(delta.uid)
        if later_task is None:
            continue

        prior_float = prior_task.total_slack if prior_task is not None else None
        later_float = later_task.total_slack

        delta_value: Optional[float] = delta.total_slack_delta
        if delta_value is None and prior_float is not None and later_float is not None:
            delta_value = later_float - prior_float

        transitioned_down = _crossed_zero_down(prior_float, later_float) or (
            prior_task is not None
            and (not prior_task.critical)
            and later_task.critical
        )
        transitioned_up = _crossed_zero_up(prior_float, later_float) or (
            prior_task is not None
            and prior_task.critical
            and (not later_task.critical)
        )

        if transitioned_down:
            became_critical.append(delta.uid)
        if transitioned_up:
            dropped_off_critical.append(delta.uid)

        task_changes.append(
            TaskFloatChange(
                uid=delta.uid,
                name=later_task.name or delta.name,
                wbs=later_task.wbs,
                prior_total_float=prior_float,
                later_total_float=later_float,
                float_delta=delta_value,
                became_critical=transitioned_down,
                dropped_off_critical=transitioned_up,
            )
        )

    # Project-level rollups
    real_deltas = [tc.float_delta for tc in task_changes if tc.float_delta is not None]
    net = sum(real_deltas) if real_deltas else 0.0
    avg = (net / len(real_deltas)) if real_deltas else 0.0

    # WBS groupings
    wbs_buckets: Dict[str, List[TaskFloatChange]] = {}
    for tc in task_changes:
        if tc.float_delta is None:
            continue
        key = _wbs_prefix(tc.wbs)
        wbs_buckets.setdefault(key, []).append(tc)

    wbs_summaries: List[WBSFloatSummary] = []
    for prefix, bucket in sorted(wbs_buckets.items()):
        deltas = [tc.float_delta for tc in bucket if tc.float_delta is not None]
        if not deltas:
            continue
        consumed = sum(-d for d in deltas if d is not None and d < 0)
        wbs_summaries.append(
            WBSFloatSummary(
                wbs_prefix=prefix,
                task_count=len(bucket),
                avg_float_delta=round(sum(deltas) / len(deltas), 4),
                total_float_consumed=round(consumed, 4),
            )
        )

    if net < -TREND_THRESHOLD_DAYS:
        trend = "consuming"
    elif net > TREND_THRESHOLD_DAYS:
        trend = "recovering"
    else:
        trend = "stable"

    return FloatAnalysisResults(
        task_changes=task_changes,
        became_critical_uids=became_critical,
        dropped_off_critical_uids=dropped_off_critical,
        net_float_delta=round(net, 4),
        avg_float_delta=round(avg, 4),
        wbs_summaries=wbs_summaries,
        trend=trend,
    )
