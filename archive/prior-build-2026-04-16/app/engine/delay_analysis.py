"""Delay root-cause tracing.

Given a `ComparisonResults` (prior vs. later) and the later
`ScheduleData`, this module identifies:

* the **first mover** — the earliest critical-path task whose finish
  slipped between the two updates,
* **cascade chains** — downstream tasks impacted by each slipped
  critical task, walked through the later schedule's successor graph,
* **categorization** — owner / contractor / third-party / weather /
  unknown, inferred from keywords in the task name and notes,
* **concurrent windows** — overlapping slip windows where two or more
  independent critical tasks slipped at the same calendar time, which
  matters for concurrent-delay apportionment.

None of this is authoritative forensic opinion — it's deterministic
pre-processing so the AI narrative layer can write the human-readable
report with accurate anchor metrics.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from app.engine.comparator import ComparisonResults, TaskDelta
from app.parser.schema import ScheduleData, TaskData


# --------------------------------------------------------------------------- #
# Categorization keywords
# --------------------------------------------------------------------------- #

DELAY_CATEGORIES: Dict[str, List[str]] = {
    "owner": ["owner", "client", "government", "agency", "rfi", "change order", "co "],
    "contractor": [
        "contractor",
        "subcontractor",
        "sub ",
        "crew",
        "workforce",
        "labor",
        "mobilization",
    ],
    "third_party": [
        "inspection",
        "inspector",
        "permit",
        "approval",
        "utility",
        "utilities",
        "fdot",
        "doh",
        "usace",
    ],
    "weather": [
        "weather",
        "rain",
        "snow",
        "storm",
        "hurricane",
        "wind",
        "freeze",
        "flood",
    ],
}

# Classify anything with a finish slip greater than this (in calendar days)
# as a meaningful delay. Sub-day jitter is ignored.
DELAY_THRESHOLD_DAYS = 0.5


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class DelayRootCause(BaseModel):
    """A single slipped task identified as a delay driver."""

    model_config = ConfigDict(extra="forbid")

    task_uid: int
    task_name: Optional[str] = None
    slip_days: float
    category: str
    reason: Optional[str] = None
    on_critical_path: bool = False
    prior_start: Optional[datetime] = None
    later_start: Optional[datetime] = None
    later_finish: Optional[datetime] = None


class CascadeChain(BaseModel):
    """Downstream tasks affected by a root-cause delay."""

    model_config = ConfigDict(extra="forbid")

    root_uid: int
    affected_uids: List[int] = Field(default_factory=list)
    total_slip_days: float = 0.0


class ConcurrentWindow(BaseModel):
    """Overlapping period during which multiple critical tasks slipped."""

    model_config = ConfigDict(extra="forbid")

    start_date: datetime
    end_date: datetime
    task_uids: List[int] = Field(default_factory=list)


class DelayAnalysisResults(BaseModel):
    """Output of `analyze_delays`."""

    model_config = ConfigDict(extra="forbid")

    first_mover_uid: Optional[int] = None
    first_mover_name: Optional[str] = None
    first_mover_slip_days: Optional[float] = None
    root_causes: List[DelayRootCause] = Field(default_factory=list)
    cascade_chains: List[CascadeChain] = Field(default_factory=list)
    concurrent_windows: List[ConcurrentWindow] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _categorize(task: TaskData) -> str:
    """Best-effort keyword categorization."""
    haystacks = []
    if task.name:
        haystacks.append(task.name.lower())
    if task.notes:
        haystacks.append(task.notes.lower())
    blob = " | ".join(haystacks)
    if not blob:
        return "unknown"
    for category, keywords in DELAY_CATEGORIES.items():
        for kw in keywords:
            if kw in blob:
                return category
    return "unknown"


def _reason_text(task: TaskData) -> Optional[str]:
    """Pull a short reason blurb from the task notes, if any."""
    if not task.notes:
        return None
    # First non-empty line, trimmed.
    for line in task.notes.splitlines():
        line = line.strip()
        if line:
            return line[:240]
    return None


def _successor_graph(schedule: ScheduleData) -> Dict[int, List[int]]:
    """uid → list of successor uids (from relationships, with predecessor list fallback)."""
    graph: Dict[int, List[int]] = defaultdict(list)
    if schedule.relationships:
        for rel in schedule.relationships:
            graph[rel.predecessor_uid].append(rel.successor_uid)
    else:
        for task in schedule.tasks:
            for pred_uid in task.predecessors:
                graph[pred_uid].append(task.uid)
    return graph


def _walk_cascade(
    root_uid: int,
    graph: Dict[int, List[int]],
    slipped_uids: Set[int],
) -> List[int]:
    """BFS through successors, collecting every slipped task downstream."""
    affected: List[int] = []
    visited: Set[int] = {root_uid}
    queue: deque[int] = deque(graph.get(root_uid, []))
    while queue:
        uid = queue.popleft()
        if uid in visited:
            continue
        visited.add(uid)
        if uid in slipped_uids:
            affected.append(uid)
        for succ in graph.get(uid, []):
            if succ not in visited:
                queue.append(succ)
    return affected


def _detect_concurrent_windows(
    root_causes: List[DelayRootCause],
    task_index: Dict[int, TaskData],
) -> List[ConcurrentWindow]:
    """Find overlapping slip windows on the critical path."""
    critical_with_dates = [
        rc
        for rc in root_causes
        if rc.on_critical_path
        and rc.later_start is not None
        and rc.later_finish is not None
    ]
    if len(critical_with_dates) < 2:
        return []

    # Sort by start; sweep for overlaps.
    sorted_rcs = sorted(critical_with_dates, key=lambda rc: rc.later_start)  # type: ignore[return-value,arg-type]
    windows: List[ConcurrentWindow] = []
    current_group: List[DelayRootCause] = [sorted_rcs[0]]
    current_end: datetime = sorted_rcs[0].later_finish  # type: ignore[assignment]

    for rc in sorted_rcs[1:]:
        assert rc.later_start is not None and rc.later_finish is not None
        if rc.later_start <= current_end:
            current_group.append(rc)
            if rc.later_finish > current_end:
                current_end = rc.later_finish
        else:
            if len(current_group) >= 2:
                windows.append(
                    ConcurrentWindow(
                        start_date=min(g.later_start for g in current_group),  # type: ignore[type-var]
                        end_date=max(g.later_finish for g in current_group),  # type: ignore[type-var]
                        task_uids=[g.task_uid for g in current_group],
                    )
                )
            current_group = [rc]
            current_end = rc.later_finish

    if len(current_group) >= 2:
        windows.append(
            ConcurrentWindow(
                start_date=min(g.later_start for g in current_group),  # type: ignore[type-var]
                end_date=max(g.later_finish for g in current_group),  # type: ignore[type-var]
                task_uids=[g.task_uid for g in current_group],
            )
        )
    return windows


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def analyze_delays(
    comparison: ComparisonResults,
    later_schedule: ScheduleData,
) -> DelayAnalysisResults:
    """Trace delay root causes from a comparison result."""
    task_index: Dict[int, TaskData] = {t.uid: t for t in later_schedule.tasks}

    # Map uid → TaskDelta for the slipped tasks (finish moved later by more
    # than the jitter threshold).
    deltas_by_uid: Dict[int, TaskDelta] = {d.uid: d for d in comparison.task_deltas}
    slipped_deltas: List[TaskDelta] = [
        d
        for d in comparison.task_deltas
        if d.finish_slip_days is not None
        and d.finish_slip_days > DELAY_THRESHOLD_DAYS
    ]
    slipped_uids: Set[int] = {d.uid for d in slipped_deltas}

    # Build root causes for slipped tasks that still exist in the later schedule.
    root_causes: List[DelayRootCause] = []
    for delta in slipped_deltas:
        task = task_index.get(delta.uid)
        if task is None:
            continue
        root_causes.append(
            DelayRootCause(
                task_uid=delta.uid,
                task_name=task.name,
                slip_days=float(delta.finish_slip_days or 0.0),
                category=_categorize(task),
                reason=_reason_text(task),
                on_critical_path=bool(task.critical),
                prior_start=None,  # filled in below if we can reconstruct it
                later_start=task.start,
                later_finish=task.finish,
            )
        )

    # Find the first mover: earliest-starting critical-path slipped task.
    critical_slipped = [rc for rc in root_causes if rc.on_critical_path]
    first_mover_uid: Optional[int] = None
    first_mover_name: Optional[str] = None
    first_mover_slip: Optional[float] = None
    if critical_slipped:
        # Prefer earliest later_start; fall back to earliest task.id for stability.
        critical_slipped.sort(
            key=lambda rc: (
                rc.later_start or datetime.max,
                task_index[rc.task_uid].id or 0,
            )
        )
        fm = critical_slipped[0]
        first_mover_uid = fm.task_uid
        first_mover_name = fm.task_name
        first_mover_slip = fm.slip_days

    # Cascade chains: walk successors from every critical slipped task and
    # collect downstream tasks that also slipped.
    graph = _successor_graph(later_schedule)
    cascade_chains: List[CascadeChain] = []
    for rc in critical_slipped:
        affected = _walk_cascade(rc.task_uid, graph, slipped_uids)
        total_slip = sum(
            (deltas_by_uid[u].finish_slip_days or 0.0) for u in affected
        )
        cascade_chains.append(
            CascadeChain(
                root_uid=rc.task_uid,
                affected_uids=affected,
                total_slip_days=total_slip,
            )
        )

    concurrent_windows = _detect_concurrent_windows(root_causes, task_index)

    return DelayAnalysisResults(
        first_mover_uid=first_mover_uid,
        first_mover_name=first_mover_name,
        first_mover_slip_days=first_mover_slip,
        root_causes=root_causes,
        cascade_chains=cascade_chains,
        concurrent_windows=concurrent_windows,
    )
