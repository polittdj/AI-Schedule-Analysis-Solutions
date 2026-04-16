"""Task-specific driving-path analysis with tiered critical paths.

Given a target task, walks the predecessor graph backward through
every driver and classifies every predecessor into one of four tiers
based on its *relative float* to the target — the working-day slack
between that predecessor's controlling date and the successor's date
through the relationship that connects them:

* **Primary critical path**   — relative float == 0 (the actual driver chain)
* **Secondary critical path** — 0 < relative float ≤ 15 working days
* **Tertiary critical path**  — 15 < relative float ≤ 30 working days
* **Non-critical**            — relative float > 30 working days

Also walks forward one level from the target to identify successors
the target *drives* — i.e., the downstream tasks whose dates this
task currently controls.

All math is done in working days via the existing CPM helpers, so
results are consistent with the rest of the forensic engine.

Filtering
---------
``DrivingPathResults.all_chain_uids`` is the union of every task UID
touched by the analysis (primary + secondary + tertiary + non-critical
predecessors, plus the target, plus forward-driven successors). The
web layer uses it to filter DCMA, slippage, manipulation, and float
results down to *just the tasks relevant to the chosen UID*, so the
user gets a task-centric view of every downstream metric.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.engine.cpm import CPMResults, TaskFloat, compute_cpm
from app.parser.schema import Relationship, ScheduleData, TaskData

# ---- Tier thresholds (working days) --------------------------------------
PRIMARY_TIER_EPSILON = 0.01    # anything below this is effectively zero
SECONDARY_TIER_MAX_DAYS = 15.0
TERTIARY_TIER_MAX_DAYS = 30.0

MAX_CHAIN_DEPTH = 500  # safety net for pathological schedules

# Public tier identifiers
TIER_PRIMARY = "primary"
TIER_SECONDARY = "secondary"
TIER_TERTIARY = "tertiary"
TIER_NON_CRITICAL = "non_critical"


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class DrivingPathNode(BaseModel):
    """A single predecessor in the driving-path hierarchy."""

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

    # Tier classification
    tier: str = TIER_NON_CRITICAL  # "primary" | "secondary" | "tertiary" | "non_critical"
    driving: bool = False  # shortcut for tier == "primary"
    relative_float_days: float = 0.0

    # How this node feeds the next task in the chain
    relationship_type: Optional[str] = None  # FS / SS / FF / SF
    lag_days: Optional[float] = None
    successor_uid: Optional[int] = None  # which task in the chain this node feeds
    depth: int = 0  # 1 = direct predecessor, 2 = predecessor's predecessor, ...


class ForwardDrivenTask(BaseModel):
    """A successor that is (or is not) driven by the target task."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    id: Optional[int] = None
    name: Optional[str] = None
    start: Optional[datetime] = None
    finish: Optional[datetime] = None
    relationship_type: Optional[str] = None
    lag_days: Optional[float] = None
    is_driven: bool = True  # whether the target is this successor's driving pred


class DrivingPathResults(BaseModel):
    """Output of `analyze_driving_path`."""

    model_config = ConfigDict(extra="forbid")

    target_uid: int
    target_name: Optional[str] = None
    target_wbs: Optional[str] = None
    target_start: Optional[datetime] = None
    target_finish: Optional[datetime] = None
    target_duration: Optional[float] = None
    target_total_float: Optional[float] = None
    target_free_float: Optional[float] = None
    target_percent_complete: Optional[float] = None

    # Tiered predecessor chains
    primary_critical_path: List[DrivingPathNode] = Field(default_factory=list)
    secondary_critical_path: List[DrivingPathNode] = Field(default_factory=list)
    tertiary_critical_path: List[DrivingPathNode] = Field(default_factory=list)
    non_critical_paths: List[DrivingPathNode] = Field(default_factory=list)

    forward_driven_tasks: List[ForwardDrivenTask] = Field(default_factory=list)

    # Union of every UID touched by the analysis, including the target.
    # The web/report layer uses this to filter every other engine result
    # down to just the tasks relevant to this target.
    all_chain_uids: List[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def classify_tier(relative_float_days: float) -> str:
    """Classify a relative float value into one of the four tiers."""
    if abs(relative_float_days) < PRIMARY_TIER_EPSILON:
        return TIER_PRIMARY
    if relative_float_days <= SECONDARY_TIER_MAX_DAYS:
        return TIER_SECONDARY
    if relative_float_days <= TERTIARY_TIER_MAX_DAYS:
        return TIER_TERTIARY
    return TIER_NON_CRITICAL


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

    A slack of zero means this predecessor is a driver of the
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
        return succ.early_start - (pred.early_finish + lag)
    if rel.type == "SS":
        return succ.early_start - (pred.early_start + lag)
    if rel.type == "FF":
        return succ.early_finish - (pred.early_finish + lag)
    if rel.type == "SF":
        return succ.early_finish - (pred.early_start + lag)
    return succ.early_start - (pred.early_finish + lag)


def _node_for_predecessor(
    rel: Relationship,
    pred_task: TaskData,
    successor_uid: int,
    task_floats: Dict[int, TaskFloat],
    depth: int,
) -> DrivingPathNode:
    slack = _driving_slack_for_relation(rel, task_floats) or 0.0
    rel_float = max(0.0, slack)
    tier = classify_tier(rel_float)
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
        tier=tier,
        driving=(tier == TIER_PRIMARY),
        relative_float_days=round(rel_float, 2),
        relationship_type=rel.type,
        lag_days=rel.lag_days,
        successor_uid=successor_uid,
        depth=depth,
    )


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
    100% complete (they cannot drive anything anymore). Each predecessor
    is classified into a tier based on its relative float. The BFS
    continues backward only through primary drivers — secondary,
    tertiary, and non-critical predecessors are recorded as leaves.
    This matches SSI's behavior and keeps the tree bounded.

    Also walks forward one level to find successors the target drives.
    """
    tasks: Dict[int, TaskData] = {t.uid: t for t in schedule.tasks}
    if target_uid not in tasks:
        raise ValueError(f"Target task {target_uid} not found in schedule")

    target = tasks[target_uid]
    cpm = cpm_results or compute_cpm(schedule)
    task_floats = cpm.task_floats or {}

    preds_by_succ, succs_by_pred = _build_relationship_map(schedule, tasks)

    primary: List[DrivingPathNode] = []
    secondary: List[DrivingPathNode] = []
    tertiary: List[DrivingPathNode] = []
    non_critical: List[DrivingPathNode] = []

    visited: Set[int] = set()
    queue: deque[Tuple[int, int]] = deque([(target_uid, 0)])
    processed = 0
    while queue:
        current_uid, depth = queue.popleft()
        if current_uid in visited:
            continue
        visited.add(current_uid)
        processed += 1
        if processed > MAX_CHAIN_DEPTH or depth >= MAX_CHAIN_DEPTH:
            break

        rels = preds_by_succ.get(current_uid, [])
        for rel in rels:
            pred_task = tasks.get(rel.predecessor_uid)
            if pred_task is None:
                continue
            # Completed predecessors cannot drive anything going forward.
            if (pred_task.percent_complete or 0.0) >= 100.0:
                continue

            node = _node_for_predecessor(
                rel, pred_task, current_uid, task_floats, depth + 1
            )
            if node.tier == TIER_PRIMARY:
                primary.append(node)
                # Only primary drivers feed the backward walk so the
                # tree size stays bounded.
                queue.append((pred_task.uid, depth + 1))
            elif node.tier == TIER_SECONDARY:
                secondary.append(node)
            elif node.tier == TIER_TERTIARY:
                tertiary.append(node)
            else:
                non_critical.append(node)

    # Stable ordering: deepest primary nodes first (i.e., closest to
    # project start → target), then by early start.
    primary.sort(
        key=lambda n: (
            -n.depth,
            (
                task_floats[n.uid].early_start
                if n.uid in task_floats
                else 0.0
            ),
        )
    )
    secondary.sort(key=lambda n: n.relative_float_days)
    tertiary.sort(key=lambda n: n.relative_float_days)
    non_critical.sort(key=lambda n: n.relative_float_days)

    # Forward trace
    forward: List[ForwardDrivenTask] = []
    for rel in succs_by_pred.get(target_uid, []):
        succ_task = tasks.get(rel.successor_uid)
        if succ_task is None:
            continue
        slack = _driving_slack_for_relation(rel, task_floats)
        is_driven = slack is not None and abs(slack) < PRIMARY_TIER_EPSILON
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

    # Union of every UID in any chain plus the target plus forward successors
    chain_set: Set[int] = {target_uid}
    for node in primary + secondary + tertiary + non_critical:
        chain_set.add(node.uid)
    for f in forward:
        chain_set.add(f.uid)
    all_chain_uids = sorted(chain_set)

    target_tf = task_floats.get(target_uid)
    return DrivingPathResults(
        target_uid=target_uid,
        target_name=target.name,
        target_wbs=target.wbs,
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
        primary_critical_path=primary,
        secondary_critical_path=secondary,
        tertiary_critical_path=tertiary,
        non_critical_paths=non_critical,
        forward_driven_tasks=forward,
        all_chain_uids=all_chain_uids,
    )


# --------------------------------------------------------------------------- #
# Engine-result filtering helpers (task-centric views)
# --------------------------------------------------------------------------- #


def filter_engine_results_by_uids(
    results: Dict, chain_uids: Set[int]
) -> Dict:
    """Return a shallow-copied results dict with every task-keyed
    sub-result filtered to only include tasks in ``chain_uids``.

    The helper is intentionally tolerant of missing or None values so
    it can be called on single-file and comparative analysis outputs
    alike.
    """
    if not chain_uids:
        return dict(results)

    out: Dict = {}
    for k, v in results.items():
        out[k] = v

    comparison = results.get("comparison")
    if comparison is not None and hasattr(comparison, "task_deltas"):
        out["filtered_task_deltas"] = [
            d for d in comparison.task_deltas if d.uid in chain_uids
        ]
        out["filtered_completed_task_uids"] = [
            uid for uid in comparison.completed_task_uids if uid in chain_uids
        ]
    else:
        out["filtered_task_deltas"] = []
        out["filtered_completed_task_uids"] = []

    manipulation = results.get("manipulation")
    if manipulation is not None and getattr(manipulation, "findings", None):
        out["filtered_manipulation_findings"] = [
            f
            for f in manipulation.findings
            if (f.task_uid is None) or (f.task_uid in chain_uids)
        ]
    else:
        out["filtered_manipulation_findings"] = []

    float_analysis = results.get("float_analysis")
    if float_analysis is not None and getattr(float_analysis, "task_changes", None):
        out["filtered_float_changes"] = [
            c for c in float_analysis.task_changes if c.uid in chain_uids
        ]
    else:
        out["filtered_float_changes"] = []

    dcma = results.get("dcma")
    if dcma is not None:
        filtered_metrics = []
        for m in dcma.metrics:
            details = dict(m.details or {})
            touched = False
            for key in (
                "missing_uids",
                "hard_uids",
                "high_float_uids",
                "high_duration_uids",
                "negative_uids",
                "missing_resource_uids",
                "invalid_uids",
                "missed_uids",
            ):
                if key in details and isinstance(details[key], list):
                    filtered_list = [
                        u for u in details[key] if u in chain_uids
                    ]
                    details[key] = filtered_list
                    if filtered_list:
                        touched = True
            if touched or not m.passed:
                filtered_metrics.append(
                    {
                        "number": m.number,
                        "name": m.name,
                        "value": m.value,
                        "threshold": m.threshold,
                        "unit": m.unit,
                        "comparison": m.comparison,
                        "passed": m.passed,
                        "details": details,
                        "touched_chain": touched,
                    }
                )
        out["filtered_dcma_metrics"] = filtered_metrics
    else:
        out["filtered_dcma_metrics"] = []

    return out
