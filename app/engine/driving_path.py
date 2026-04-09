"""Task-specific driving-path analysis (SSI-style).

Given a target task, traces the chain of predecessors that actually
*drive* its start/finish date and groups every predecessor into one
of three categories based on relative float:

* **Driving path**      — relative float == 0 (controls the target)
* **Near-driving path** — relative float 1..5 working days
* **Non-driving path**  — relative float > 5 working days

Also walks forward from the target to identify successors the target
*drives* — i.e., the downstream tasks whose dates this task controls.

How "driving" is determined
---------------------------
For each relationship ``pred → succ (type, lag)`` we compute the
date the predecessor *would* need to finish at in order to keep the
successor exactly on its current schedule. If the predecessor's
actual finish (or start, for SS/SF) is already at that date, it is
the driver; any other predecessor that finishes earlier is a
non-driver with relative float equal to the difference.

All math is done in **working days** via the existing CPM helpers,
so results are consistent with the rest of the forensic engine.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.engine.cpm import CPMResults, TaskFloat, compute_cpm
from app.parser.schema import Relationship, ScheduleData, TaskData

DRIVING_EPSILON = 0.01  # working days
NEAR_DRIVING_MAX_DAYS = 5.0  # classification ceiling for "near driving"
MAX_CHAIN_DEPTH = 500  # safety net for pathological schedules


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class DrivingPathNode(BaseModel):
    """A single predecessor in a driving-path chain."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    id: Optional[int] = None
    name: Optional[str] = None
    wbs: Optional[str] = None
    start: Optional[datetime] = None
    finish: Optional[datetime] = None
    duration: Optional[float] = None
    percent_complete: Optional[float] = None
    total_slack: Optional[float] = None
    driving: bool = False
    relative_float_days: float = 0.0
    relationship_type: Optional[str] = None  # FS / SS / FF / SF
    lag_days: Optional[float] = None
    successor_uid: Optional[int] = None  # which task in the chain this node feeds
    depth: int = 0  # 1 = direct predecessor, 2 = predecessor's predecessor, ...


class DrivingPathChain(BaseModel):
    """An ordered list of nodes for one category."""

    model_config = ConfigDict(extra="forbid")

    category: str  # "driving" | "near_driving" | "non_driving"
    nodes: List[DrivingPathNode] = Field(default_factory=list)


class ForwardDrivenTask(BaseModel):
    """A successor that is driven by the target task."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    id: Optional[int] = None
    name: Optional[str] = None
    start: Optional[datetime] = None
    finish: Optional[datetime] = None
    relationship_type: Optional[str] = None
    lag_days: Optional[float] = None
    is_driven: bool = True  # whether the target is this task's driving pred


class DrivingPathResults(BaseModel):
    """Output of `analyze_driving_path`."""

    model_config = ConfigDict(extra="forbid")

    target_uid: int
    target_name: Optional[str] = None
    target_start: Optional[datetime] = None
    target_finish: Optional[datetime] = None
    target_duration: Optional[float] = None
    target_total_float: Optional[float] = None
    target_free_float: Optional[float] = None
    target_percent_complete: Optional[float] = None

    driving_chain: List[DrivingPathNode] = Field(default_factory=list)
    near_driving_paths: List[DrivingPathNode] = Field(default_factory=list)
    non_driving_paths: List[DrivingPathNode] = Field(default_factory=list)
    forward_driven_tasks: List[ForwardDrivenTask] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _build_relationship_map(
    schedule: ScheduleData, tasks: Dict[int, TaskData]
) -> Tuple[Dict[int, List[Relationship]], Dict[int, List[Relationship]]]:
    """Return (preds_by_succ, succs_by_pred).

    Falls back to synthesizing FS/0-lag relationships from
    ``TaskData.predecessors`` when ``schedule.relationships`` is empty.
    """
    preds_by_succ: Dict[int, List[Relationship]] = defaultdict(list)
    succs_by_pred: Dict[int, List[Relationship]] = defaultdict(list)

    rels: List[Relationship] = [
        r
        for r in schedule.relationships
        if r.predecessor_uid in tasks and r.successor_uid in tasks
    ]
    if not rels:
        for uid, t in tasks.items():
            for pred_uid in t.predecessors:
                if pred_uid in tasks:
                    rels.append(
                        Relationship(
                            predecessor_uid=pred_uid,
                            successor_uid=uid,
                            type="FS",
                            lag_days=0.0,
                        )
                    )

    for r in rels:
        preds_by_succ[r.successor_uid].append(r)
        succs_by_pred[r.predecessor_uid].append(r)
    return preds_by_succ, succs_by_pred


def _driving_slack_for_relation(
    rel: Relationship,
    task_floats: Dict[int, TaskFloat],
) -> Optional[float]:
    """Working-day slack between predecessor and successor through `rel`.

    A slack of zero means this predecessor is the driver of the
    successor. Positive slack means the predecessor could finish
    later (or start later, for SS/SF) by that many working days
    without pushing the successor's ES or EF.
    """
    pred = task_floats.get(rel.predecessor_uid)
    succ = task_floats.get(rel.successor_uid)
    if pred is None or succ is None:
        return None
    lag = rel.lag_days or 0.0

    if rel.type == "FS":
        # Successor starts after predecessor finishes + lag
        return succ.early_start - (pred.early_finish + lag)
    if rel.type == "SS":
        return succ.early_start - (pred.early_start + lag)
    if rel.type == "FF":
        return succ.early_finish - (pred.early_finish + lag)
    if rel.type == "SF":
        return succ.early_finish - (pred.early_start + lag)
    # Unknown type: treat as FS
    return succ.early_start - (pred.early_finish + lag)


def _node_for_predecessor(
    rel: Relationship,
    pred_task: TaskData,
    successor_uid: int,
    task_floats: Dict[int, TaskFloat],
    depth: int,
) -> DrivingPathNode:
    slack = _driving_slack_for_relation(rel, task_floats)
    driving = slack is not None and abs(slack) < DRIVING_EPSILON
    tf = task_floats.get(pred_task.uid)
    return DrivingPathNode(
        uid=pred_task.uid,
        id=pred_task.id,
        name=pred_task.name,
        wbs=pred_task.wbs,
        start=pred_task.start,
        finish=pred_task.finish,
        duration=pred_task.duration,
        percent_complete=pred_task.percent_complete,
        total_slack=(
            round(tf.total_float, 2)
            if tf is not None
            else pred_task.total_slack
        ),
        driving=bool(driving),
        relative_float_days=round(max(0.0, slack or 0.0), 2),
        relationship_type=rel.type,
        lag_days=rel.lag_days,
        successor_uid=successor_uid,
        depth=depth,
    )


def _classify(node: DrivingPathNode) -> str:
    if node.driving or node.relative_float_days < DRIVING_EPSILON:
        return "driving"
    if node.relative_float_days <= NEAR_DRIVING_MAX_DAYS:
        return "near_driving"
    return "non_driving"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def analyze_driving_path(
    schedule: ScheduleData,
    target_uid: int,
    cpm_results: Optional[CPMResults] = None,
) -> DrivingPathResults:
    """Trace the driving chain that controls `target_uid`.

    Walks backward from the target task through every predecessor,
    stopping at tasks with no predecessors or tasks that are already
    100% complete (they cannot drive anything anymore). Also walks
    forward one level to find successors the target drives.
    """
    tasks: Dict[int, TaskData] = {t.uid: t for t in schedule.tasks}
    if target_uid not in tasks:
        raise ValueError(f"Target task {target_uid} not found in schedule")

    target = tasks[target_uid]
    cpm = cpm_results or compute_cpm(schedule)
    task_floats = cpm.task_floats or {}

    preds_by_succ, succs_by_pred = _build_relationship_map(schedule, tasks)

    driving_chain: List[DrivingPathNode] = []
    near_driving: List[DrivingPathNode] = []
    non_driving: List[DrivingPathNode] = []

    # BFS backward, marking driving predecessors and enqueueing them for
    # further backward traversal. Non-driving predecessors are recorded
    # once and not traversed (the user is interested in *what controls
    # the target*, not everything upstream of it).
    visited: set[int] = set()
    queue: deque[Tuple[int, int]] = deque([(target_uid, 0)])
    depth_limit = 0
    while queue:
        current_uid, depth = queue.popleft()
        if current_uid in visited:
            continue
        visited.add(current_uid)
        depth_limit += 1
        if depth_limit > MAX_CHAIN_DEPTH:
            break
        if depth >= MAX_CHAIN_DEPTH:
            continue

        rels = preds_by_succ.get(current_uid, [])
        for rel in rels:
            pred_task = tasks.get(rel.predecessor_uid)
            if pred_task is None:
                continue
            # Skip predecessors that are already finished — they cannot
            # drive anything going forward.
            if (pred_task.percent_complete or 0.0) >= 100.0:
                continue

            node = _node_for_predecessor(
                rel, pred_task, current_uid, task_floats, depth + 1
            )
            category = _classify(node)
            if category == "driving":
                driving_chain.append(node)
                # Recurse further back through drivers only.
                queue.append((pred_task.uid, depth + 1))
            elif category == "near_driving":
                near_driving.append(node)
            else:
                non_driving.append(node)

    # Order driving chain from project-start → target (by depth desc,
    # then by early start ascending for stability).
    driving_chain.sort(
        key=lambda n: (
            -n.depth,
            (
                task_floats[n.uid].early_start
                if n.uid in task_floats
                else 0.0
            ),
        )
    )
    near_driving.sort(key=lambda n: n.relative_float_days)
    non_driving.sort(key=lambda n: n.relative_float_days)

    # Forward trace: find successors the target actually drives.
    forward: List[ForwardDrivenTask] = []
    for rel in succs_by_pred.get(target_uid, []):
        succ_task = tasks.get(rel.successor_uid)
        if succ_task is None:
            continue
        slack = _driving_slack_for_relation(rel, task_floats)
        is_driven = slack is not None and abs(slack) < DRIVING_EPSILON
        forward.append(
            ForwardDrivenTask(
                uid=succ_task.uid,
                id=succ_task.id,
                name=succ_task.name,
                start=succ_task.start,
                finish=succ_task.finish,
                relationship_type=rel.type,
                lag_days=rel.lag_days,
                is_driven=is_driven,
            )
        )
    forward.sort(key=lambda f: (not f.is_driven, f.uid))

    target_tf = task_floats.get(target_uid)
    return DrivingPathResults(
        target_uid=target_uid,
        target_name=target.name,
        target_start=target.start,
        target_finish=target.finish,
        target_duration=target.duration,
        target_total_float=(
            round(target_tf.total_float, 2)
            if target_tf is not None
            else target.total_slack
        ),
        target_free_float=(
            round(target_tf.free_float, 2)
            if target_tf is not None
            else target.free_slack
        ),
        target_percent_complete=target.percent_complete,
        driving_chain=driving_chain,
        near_driving_paths=near_driving,
        non_driving_paths=non_driving,
        forward_driven_tasks=forward,
    )
