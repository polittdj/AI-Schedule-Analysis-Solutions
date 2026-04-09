"""Critical Path Method (CPM) engine.

Computes early/late start & finish and total/free float for every detail
task in a `ScheduleData`, then identifies the critical path.

All time is expressed in **working days** (the same unit the parser
normalizes durations to). The CPM does not care about calendar dates or
holidays — it runs purely on topology, durations, and lags.

Key design choices
------------------
* Summary tasks are excluded from the CPM; in MS Project they "roll up"
  from their children and are never on the critical path themselves.
* Milestones are treated as zero-duration activities.
* If `schedule.relationships` is empty, we synthesize FS/0-lag relations
  from `TaskData.predecessors` as a fallback — some MPP files populate
  only one of those two collections.
* Cycles are detected and reported; we still return a best-effort result
  for the non-cyclic subgraph rather than crashing.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.parser.schema import Relationship, ScheduleData, TaskData

# How close to zero total-float must a task be to count as "critical".
# MPP stores floats in units of working days; anything within 1/100th of
# a day is indistinguishable from zero for forensic purposes.
CRITICAL_EPSILON = 0.01


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class TaskFloat(BaseModel):
    """CPM numbers for a single task."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    early_start: float
    early_finish: float
    late_start: float
    late_finish: float
    total_float: float
    free_float: float
    critical: bool = False


class CPMResults(BaseModel):
    """Output of `compute_cpm`."""

    model_config = ConfigDict(extra="forbid")

    project_duration_days: float
    critical_path_uids: List[int] = Field(default_factory=list)
    task_floats: Dict[int, TaskFloat] = Field(default_factory=dict)
    cycles_detected: List[List[int]] = Field(default_factory=list)
    excluded_summary_uids: List[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _detail_tasks(schedule: ScheduleData) -> Dict[int, TaskData]:
    """Return a dict of detail (non-summary) tasks keyed by uid."""
    return {t.uid: t for t in schedule.tasks if not t.summary}


def _effective_duration(task: TaskData) -> float:
    """Zero for milestones; task.duration otherwise."""
    if task.milestone:
        return 0.0
    return float(task.duration) if task.duration is not None else 0.0


def _gather_relationships(
    schedule: ScheduleData, tasks: Dict[int, TaskData]
) -> List[Relationship]:
    """Return relationships whose both endpoints are detail tasks.

    Falls back to synthesizing FS/0-lag relations from `TaskData.predecessors`
    if `schedule.relationships` is empty or does not cover the known preds.
    """
    rels: List[Relationship] = [
        r
        for r in schedule.relationships
        if r.predecessor_uid in tasks and r.successor_uid in tasks
    ]
    if rels:
        return rels

    # Fallback: build from the tasks' predecessor lists.
    synthetic: List[Relationship] = []
    for succ_uid, task in tasks.items():
        for pred_uid in task.predecessors:
            if pred_uid in tasks:
                synthetic.append(
                    Relationship(
                        predecessor_uid=pred_uid,
                        successor_uid=succ_uid,
                        type="FS",
                        lag_days=0.0,
                    )
                )
    return synthetic


def _topological_order(
    tasks: Dict[int, TaskData], relationships: List[Relationship]
) -> Tuple[List[int], List[List[int]]]:
    """Kahn's algorithm. Returns (order, cycles).

    `order` contains the uids in a valid topological order for whatever
    portion of the graph is acyclic. `cycles` contains any uids that
    were stuck in a cycle (reported but still included at the end of
    the order in arbitrary insertion sequence so the CPM can still
    produce numbers for them).
    """
    indegree: Dict[int, int] = {uid: 0 for uid in tasks}
    adjacency: Dict[int, List[int]] = defaultdict(list)
    for rel in relationships:
        adjacency[rel.predecessor_uid].append(rel.successor_uid)
        indegree[rel.successor_uid] = indegree.get(rel.successor_uid, 0) + 1

    queue: deque[int] = deque([uid for uid, d in indegree.items() if d == 0])
    order: List[int] = []
    while queue:
        uid = queue.popleft()
        order.append(uid)
        for succ in adjacency[uid]:
            indegree[succ] -= 1
            if indegree[succ] == 0:
                queue.append(succ)

    cycles: List[List[int]] = []
    stuck = [uid for uid, d in indegree.items() if d > 0]
    if stuck:
        # Don't try to enumerate all simple cycles — just report the stuck set.
        cycles.append(stuck)
        order.extend(stuck)
    return order, cycles


# --------------------------------------------------------------------------- #
# Forward / backward pass
# --------------------------------------------------------------------------- #


def _forward_pass(
    order: List[int],
    tasks: Dict[int, TaskData],
    preds_by_succ: Dict[int, List[Relationship]],
) -> Tuple[Dict[int, float], Dict[int, float]]:
    es: Dict[int, float] = {}
    ef: Dict[int, float] = {}
    for uid in order:
        dur = _effective_duration(tasks[uid])
        rels = preds_by_succ.get(uid, [])
        if not rels:
            es[uid] = 0.0
        else:
            candidates: List[float] = []
            for rel in rels:
                p = rel.predecessor_uid
                if p not in ef:  # stuck in an unresolvable cycle
                    continue
                lag = rel.lag_days
                if rel.type == "FS":
                    candidates.append(ef[p] + lag)
                elif rel.type == "SS":
                    candidates.append(es[p] + lag)
                elif rel.type == "FF":
                    candidates.append(ef[p] + lag - dur)
                elif rel.type == "SF":
                    candidates.append(es[p] + lag - dur)
                else:  # unknown type — treat as FS
                    candidates.append(ef[p] + lag)
            es[uid] = max(candidates) if candidates else 0.0
        # ES can't go negative (a constraint might push it there otherwise).
        if es[uid] < 0:
            es[uid] = 0.0
        ef[uid] = es[uid] + dur
    return es, ef


def _backward_pass(
    order: List[int],
    tasks: Dict[int, TaskData],
    succs_by_pred: Dict[int, List[Relationship]],
    project_finish: float,
    es: Dict[int, float],
    ef: Dict[int, float],
) -> Tuple[Dict[int, float], Dict[int, float]]:
    ls: Dict[int, float] = {}
    lf: Dict[int, float] = {}
    for uid in reversed(order):
        dur = _effective_duration(tasks[uid])
        rels = succs_by_pred.get(uid, [])
        if not rels:
            lf[uid] = project_finish
        else:
            candidates: List[float] = []
            for rel in rels:
                s = rel.successor_uid
                if s not in ls:  # successor not yet resolved (cycle)
                    continue
                lag = rel.lag_days
                if rel.type == "FS":
                    candidates.append(ls[s] - lag)
                elif rel.type == "SS":
                    candidates.append(ls[s] - lag + dur)
                elif rel.type == "FF":
                    candidates.append(lf[s] - lag)
                elif rel.type == "SF":
                    candidates.append(lf[s] - lag + dur)
                else:
                    candidates.append(ls[s] - lag)
            lf[uid] = min(candidates) if candidates else project_finish
        ls[uid] = lf[uid] - dur
    return ls, lf


def _compute_free_float(
    uid: int,
    dur: float,
    es: Dict[int, float],
    ef: Dict[int, float],
    succ_rels: List[Relationship],
    total_float: float,
) -> float:
    """Free float: delay absorbed without impacting any immediate successor."""
    if not succ_rels:
        return total_float
    candidates: List[float] = []
    for rel in succ_rels:
        s = rel.successor_uid
        if s not in es:
            continue
        lag = rel.lag_days
        if rel.type == "FS":
            candidates.append(es[s] - lag - ef[uid])
        elif rel.type == "SS":
            candidates.append(es[s] - lag - es[uid])
        elif rel.type == "FF":
            candidates.append(ef[s] - lag - ef[uid])
        elif rel.type == "SF":
            candidates.append(ef[s] - lag - es[uid])
        else:
            candidates.append(es[s] - lag - ef[uid])
    if not candidates:
        return total_float
    ff = min(candidates)
    return max(0.0, ff)  # free float can't be negative


def _ordered_critical_path(
    task_floats: Dict[int, TaskFloat],
    succs_by_pred: Dict[int, List[Relationship]],
) -> List[int]:
    """Walk critical tasks from earliest ES to latest, following successors."""
    critical_uids = {uid for uid, tf in task_floats.items() if tf.critical}
    if not critical_uids:
        return []

    # Start from the critical task with the smallest ES (and no critical pred).
    crit_preds: Dict[int, int] = {uid: 0 for uid in critical_uids}
    for pred_uid, rels in succs_by_pred.items():
        if pred_uid not in critical_uids:
            continue
        for rel in rels:
            if rel.successor_uid in critical_uids:
                crit_preds[rel.successor_uid] += 1

    roots = [uid for uid, n in crit_preds.items() if n == 0]
    if not roots:
        # Degenerate — just return all critical tasks sorted by ES
        return sorted(critical_uids, key=lambda u: task_floats[u].early_start)

    roots.sort(key=lambda u: task_floats[u].early_start)
    start = roots[0]

    path: List[int] = [start]
    visited = {start}
    cur = start
    while True:
        next_uid: Optional[int] = None
        best_es = float("inf")
        for rel in succs_by_pred.get(cur, []):
            s = rel.successor_uid
            if s in critical_uids and s not in visited:
                if task_floats[s].early_start < best_es:
                    best_es = task_floats[s].early_start
                    next_uid = s
        if next_uid is None:
            break
        path.append(next_uid)
        visited.add(next_uid)
        cur = next_uid

    # Include any critical tasks we couldn't walk to (parallel critical paths).
    for uid in sorted(
        critical_uids - visited, key=lambda u: task_floats[u].early_start
    ):
        path.append(uid)
    return path


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compute_cpm(schedule: ScheduleData) -> CPMResults:
    """Run the CPM forward/backward pass and identify the critical path."""
    tasks = _detail_tasks(schedule)
    excluded = [t.uid for t in schedule.tasks if t.summary]

    if not tasks:
        return CPMResults(
            project_duration_days=0.0,
            critical_path_uids=[],
            task_floats={},
            cycles_detected=[],
            excluded_summary_uids=excluded,
        )

    relationships = _gather_relationships(schedule, tasks)
    preds_by_succ: Dict[int, List[Relationship]] = defaultdict(list)
    succs_by_pred: Dict[int, List[Relationship]] = defaultdict(list)
    for rel in relationships:
        preds_by_succ[rel.successor_uid].append(rel)
        succs_by_pred[rel.predecessor_uid].append(rel)

    order, cycles = _topological_order(tasks, relationships)

    es, ef = _forward_pass(order, tasks, preds_by_succ)
    project_finish = max(ef.values()) if ef else 0.0

    ls, lf = _backward_pass(order, tasks, succs_by_pred, project_finish, es, ef)

    task_floats: Dict[int, TaskFloat] = {}
    for uid, task in tasks.items():
        dur = _effective_duration(task)
        total_float = ls[uid] - es[uid]
        free_float = _compute_free_float(
            uid, dur, es, ef, succs_by_pred.get(uid, []), total_float
        )
        task_floats[uid] = TaskFloat(
            uid=uid,
            early_start=es[uid],
            early_finish=ef[uid],
            late_start=ls[uid],
            late_finish=lf[uid],
            total_float=total_float,
            free_float=free_float,
            critical=abs(total_float) < CRITICAL_EPSILON,
        )

    critical_path = _ordered_critical_path(task_floats, succs_by_pred)

    return CPMResults(
        project_duration_days=project_finish,
        critical_path_uids=critical_path,
        task_floats=task_floats,
        cycles_detected=cycles,
        excluded_summary_uids=excluded,
    )
