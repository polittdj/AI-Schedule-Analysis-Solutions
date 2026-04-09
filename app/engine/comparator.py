"""Two-schedule comparison engine.

Takes a prior and a later `ScheduleData` and produces a structured
diff — task-level deltas, logic changes, added/deleted/completed task
lists, and project-level rollups. The forensic engine and the AI
narrative layer both consume the resulting `ComparisonResults`.

All date slips are reported in **calendar days** (signed: positive =
moved later, negative = pulled in). All duration changes and float
deltas are in **working days** because that's what the parser stores.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.parser.schema import Relationship, ScheduleData, TaskData


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class LogicChange(BaseModel):
    """A relationship that was changed between the two schedules."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # "added" | "removed" | "type_change" | "lag_change"
    predecessor_uid: int
    successor_uid: int
    prior_type: Optional[str] = None
    later_type: Optional[str] = None
    prior_lag_days: Optional[float] = None
    later_lag_days: Optional[float] = None


class TaskDelta(BaseModel):
    """Per-task change summary."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    name: Optional[str] = None

    # Date slips — calendar days, signed (positive = later)
    start_slip_days: Optional[float] = None
    finish_slip_days: Optional[float] = None

    # Duration / completion deltas — working days / percentage points
    duration_change_days: Optional[float] = None
    percent_complete_delta: Optional[float] = None
    remaining_duration_delta: Optional[float] = None

    # Float deltas — working days
    total_slack_delta: Optional[float] = None
    free_slack_delta: Optional[float] = None

    # Baseline movement — calendar days (baselines should never move)
    baseline_start_delta_days: Optional[float] = None
    baseline_finish_delta_days: Optional[float] = None

    # Logic changes touching this task as the successor
    predecessors_added: List[int] = Field(default_factory=list)
    predecessors_removed: List[int] = Field(default_factory=list)
    relationship_type_changes: List[LogicChange] = Field(default_factory=list)
    lag_changes: List[LogicChange] = Field(default_factory=list)

    became_critical: bool = False
    dropped_off_critical: bool = False


class ComparisonResults(BaseModel):
    """Output of `compare_schedules`."""

    model_config = ConfigDict(extra="forbid")

    prior_project_name: Optional[str] = None
    later_project_name: Optional[str] = None
    prior_status_date: Optional[datetime] = None
    later_status_date: Optional[datetime] = None

    added_task_uids: List[int] = Field(default_factory=list)
    deleted_task_uids: List[int] = Field(default_factory=list)
    completed_task_uids: List[int] = Field(default_factory=list)

    task_deltas: List[TaskDelta] = Field(default_factory=list)
    logic_changes: List[LogicChange] = Field(default_factory=list)

    # Project-level rollups
    completion_date_slip_days: Optional[float] = None
    net_float_change_days: Optional[float] = None
    tasks_slipped_count: int = 0
    tasks_pulled_in_count: int = 0
    tasks_completed_count: int = 0
    tasks_added_count: int = 0
    tasks_deleted_count: int = 0
    baseline_movement_count: int = 0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _days_between(prior: Optional[datetime], later: Optional[datetime]) -> Optional[float]:
    """(later − prior) in calendar days. None if either is missing."""
    if prior is None or later is None:
        return None
    return (later - prior).total_seconds() / 86400.0


def _float_delta(prior: Optional[float], later: Optional[float]) -> Optional[float]:
    if prior is None or later is None:
        return None
    return later - prior


def _predecessor_map(
    schedule: ScheduleData,
) -> Dict[int, Dict[int, Relationship]]:
    """succ_uid → {pred_uid → Relationship}.

    Uses `schedule.relationships` as the canonical source; falls back to
    `TaskData.predecessors` when relationships is empty.
    """
    result: Dict[int, Dict[int, Relationship]] = {}
    if schedule.relationships:
        for rel in schedule.relationships:
            result.setdefault(rel.successor_uid, {})[rel.predecessor_uid] = rel
        return result
    # Fallback
    for task in schedule.tasks:
        for pred_uid in task.predecessors:
            result.setdefault(task.uid, {})[pred_uid] = Relationship(
                predecessor_uid=pred_uid,
                successor_uid=task.uid,
                type="FS",
                lag_days=0.0,
            )
    return result


def _is_completed(task: TaskData) -> bool:
    pc = task.percent_complete
    return pc is not None and pc >= 100.0


def _diff_task_logic(
    succ_uid: int,
    prior_preds: Dict[int, Relationship],
    later_preds: Dict[int, Relationship],
) -> Tuple[List[int], List[int], List[LogicChange], List[LogicChange]]:
    added = sorted(set(later_preds.keys()) - set(prior_preds.keys()))
    removed = sorted(set(prior_preds.keys()) - set(later_preds.keys()))
    type_changes: List[LogicChange] = []
    lag_changes: List[LogicChange] = []
    common = set(prior_preds.keys()) & set(later_preds.keys())
    for pred_uid in sorted(common):
        p = prior_preds[pred_uid]
        l = later_preds[pred_uid]
        if p.type != l.type:
            type_changes.append(
                LogicChange(
                    kind="type_change",
                    predecessor_uid=pred_uid,
                    successor_uid=succ_uid,
                    prior_type=p.type,
                    later_type=l.type,
                    prior_lag_days=p.lag_days,
                    later_lag_days=l.lag_days,
                )
            )
        if abs(p.lag_days - l.lag_days) > 1e-6:
            lag_changes.append(
                LogicChange(
                    kind="lag_change",
                    predecessor_uid=pred_uid,
                    successor_uid=succ_uid,
                    prior_type=p.type,
                    later_type=l.type,
                    prior_lag_days=p.lag_days,
                    later_lag_days=l.lag_days,
                )
            )
    return added, removed, type_changes, lag_changes


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compare_schedules(prior: ScheduleData, later: ScheduleData) -> ComparisonResults:
    """Produce a structured diff between two schedule updates."""
    prior_tasks: Dict[int, TaskData] = {t.uid: t for t in prior.tasks}
    later_tasks: Dict[int, TaskData] = {t.uid: t for t in later.tasks}

    added_uids = sorted(set(later_tasks) - set(prior_tasks))
    deleted_uids = sorted(set(prior_tasks) - set(later_tasks))
    common = sorted(set(prior_tasks) & set(later_tasks))

    prior_preds_map = _predecessor_map(prior)
    later_preds_map = _predecessor_map(later)

    task_deltas: List[TaskDelta] = []
    completed_uids: List[int] = []
    logic_changes_all: List[LogicChange] = []

    slipped = 0
    pulled_in = 0
    baseline_moved = 0

    for uid in common:
        p = prior_tasks[uid]
        l = later_tasks[uid]

        # Completed detection: was <100% in prior, now ≥100% in later.
        if not _is_completed(p) and _is_completed(l):
            completed_uids.append(uid)

        start_slip = _days_between(p.start, l.start)
        finish_slip = _days_between(p.finish, l.finish)
        duration_delta = _float_delta(p.duration, l.duration)
        pct_delta = _float_delta(p.percent_complete, l.percent_complete)
        rem_delta = _float_delta(p.remaining_duration, l.remaining_duration)
        ts_delta = _float_delta(p.total_slack, l.total_slack)
        fs_delta = _float_delta(p.free_slack, l.free_slack)
        bs_delta = _days_between(p.baseline_start, l.baseline_start)
        bf_delta = _days_between(p.baseline_finish, l.baseline_finish)

        if (bs_delta and abs(bs_delta) > 0) or (bf_delta and abs(bf_delta) > 0):
            baseline_moved += 1

        if finish_slip is not None:
            if finish_slip > 0:
                slipped += 1
            elif finish_slip < 0:
                pulled_in += 1

        prior_preds = prior_preds_map.get(uid, {})
        later_preds = later_preds_map.get(uid, {})
        added_preds, removed_preds, type_changes, lag_changes = _diff_task_logic(
            uid, prior_preds, later_preds
        )

        # Convert added/removed predecessor uid lists to LogicChange entries too,
        # so the project-level logic_changes roll-up is complete.
        for pred_uid in added_preds:
            rel = later_preds[pred_uid]
            logic_changes_all.append(
                LogicChange(
                    kind="added",
                    predecessor_uid=pred_uid,
                    successor_uid=uid,
                    later_type=rel.type,
                    later_lag_days=rel.lag_days,
                )
            )
        for pred_uid in removed_preds:
            rel = prior_preds[pred_uid]
            logic_changes_all.append(
                LogicChange(
                    kind="removed",
                    predecessor_uid=pred_uid,
                    successor_uid=uid,
                    prior_type=rel.type,
                    prior_lag_days=rel.lag_days,
                )
            )
        logic_changes_all.extend(type_changes)
        logic_changes_all.extend(lag_changes)

        became_critical = (not p.critical) and l.critical
        dropped_off_critical = p.critical and (not l.critical)

        task_deltas.append(
            TaskDelta(
                uid=uid,
                name=l.name or p.name,
                start_slip_days=start_slip,
                finish_slip_days=finish_slip,
                duration_change_days=duration_delta,
                percent_complete_delta=pct_delta,
                remaining_duration_delta=rem_delta,
                total_slack_delta=ts_delta,
                free_slack_delta=fs_delta,
                baseline_start_delta_days=bs_delta,
                baseline_finish_delta_days=bf_delta,
                predecessors_added=added_preds,
                predecessors_removed=removed_preds,
                relationship_type_changes=type_changes,
                lag_changes=lag_changes,
                became_critical=became_critical,
                dropped_off_critical=dropped_off_critical,
            )
        )

    # Project-level slip: compare project finish dates.
    completion_slip = _days_between(
        prior.project_info.finish_date, later.project_info.finish_date
    )

    # Net float change: average total-slack delta across common tasks that have
    # values on both sides. "Net" here means "on average, did float get eaten?"
    float_deltas = [
        td.total_slack_delta
        for td in task_deltas
        if td.total_slack_delta is not None
    ]
    net_float_change = (
        sum(float_deltas) / len(float_deltas) if float_deltas else None
    )

    return ComparisonResults(
        prior_project_name=prior.project_info.name,
        later_project_name=later.project_info.name,
        prior_status_date=prior.project_info.status_date,
        later_status_date=later.project_info.status_date,
        added_task_uids=added_uids,
        deleted_task_uids=deleted_uids,
        completed_task_uids=completed_uids,
        task_deltas=task_deltas,
        logic_changes=logic_changes_all,
        completion_date_slip_days=completion_slip,
        net_float_change_days=net_float_change,
        tasks_slipped_count=slipped,
        tasks_pulled_in_count=pulled_in,
        tasks_completed_count=len(completed_uids),
        tasks_added_count=len(added_uids),
        tasks_deleted_count=len(deleted_uids),
        baseline_movement_count=baseline_moved,
    )
