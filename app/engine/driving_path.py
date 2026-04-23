"""Task-specific driving-path tracer — Milestone 10.

Block 7 (2026-04-22) replaced the chain-based contract with an
adjacency map (BUILD-PLAN AM8, §2.18). The backward walk visits
**every** zero-relationship-slack incoming edge at every node per
``driving-slack-and-paths §4`` ("No path is dropped.") and §5
("Walking every relationship-slack-zero link backward … walks
recursively until every driving predecessor is exhausted.").

The AM7 "lowest-UID tie-break" is withdrawn — tie-break is no longer
a concept in this module.

Authority:

* SSI driving-slack methodology — ``driving-slack-and-paths §2``.
* Per-link relationship-slack formulas —
  ``driving-slack-and-paths §3`` (reused via
  :func:`app.engine.relations.link_driving_slack_minutes`).
* Full-traversal backward walk —
  ``driving-slack-and-paths §§4, 5`` (verbatim quotes in
  :mod:`app.engine.driving_path_types` error messages).
* Period A slack rule — ``driving-slack-and-paths §9``.
* UniqueID-only matching — BUILD-PLAN §2.7;
  ``mpp-parsing-com-automation §5``.

Non-mutation invariant: neither ``Schedule`` nor ``CPMResult`` is
mutated by any function in this module. Tests snapshot
``Schedule.model_dump()`` and
:func:`tests._utils.cpm_result_snapshot` before / after every trace
call.

Units convention: CPM internals (``TaskCPMResult.total_slack_minutes``
and the :func:`~app.engine.relations.link_driving_slack_minutes`
helper) remain in minutes; the public contract is in days with
``calendar_hours_per_day`` carried on every model as the forensic
audit trail per BUILD-PLAN §2.18. Conversion goes through
:func:`app.engine.units.minutes_to_days` exclusively.
"""

from __future__ import annotations

from collections import defaultdict, deque

from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathCrossVersionResult,
    DrivingPathEdge,
    DrivingPathNode,
    DrivingPathResult,
    FocusPointAnchor,
    NonDrivingPredecessor,
)
from app.engine.exceptions import DrivingPathError
from app.engine.focus_point import resolve_focus_point
from app.engine.relations import link_driving_slack_minutes
from app.engine.result import CPMResult, TaskCPMResult
from app.engine.units import minutes_to_days
from app.models.calendar import Calendar
from app.models.enums import DATE_BEARING_CONSTRAINTS
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

# One-second tolerance in minutes. Integer-minute arithmetic in the
# engine keeps true zero-slack edges at exactly 0; the tolerance
# exists only to match the days-denominated tolerance on
# :class:`DrivingPathEdge` — sub-minute values cannot arise here.
_ZERO_SLACK_TOLERANCE_MIN: float = 1.0 / 60.0


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


def _schedule_calendar(schedule: Schedule) -> Calendar:
    """Return the calendar the CPM engine would have used.

    Matches the private helper in :mod:`app.engine.paths` so the
    driving-path tracer reads relationship slack through the same
    calendar the M4 CPM pass used; otherwise the per-link slack
    and the CPM-computed early dates would diverge.
    """
    for c in schedule.calendars:
        if c.name == schedule.default_calendar_name:
            return c
    if schedule.calendars:
        return schedule.calendars[0]
    return Calendar(name=schedule.default_calendar_name or "Standard")


def _tasks_by_uid(schedule: Schedule) -> dict[int, Task]:
    return {t.unique_id: t for t in schedule.tasks}


def _incoming_relations(relations: list[Relation]) -> dict[int, list[Relation]]:
    out: dict[int, list[Relation]] = defaultdict(list)
    for r in relations:
        out[r.successor_unique_id].append(r)
    return out


def _resolve_hours_per_day(task: Task, schedule: Schedule) -> float:
    """Task-specific calendar factor with project-default fallback.

    Uses the M1.1 denormalised fields: ``Task.calendar_hours_per_day``
    when non-``None``, else ``Schedule.project_calendar_hours_per_day``.
    """
    if task.calendar_hours_per_day is not None:
        return task.calendar_hours_per_day
    return schedule.project_calendar_hours_per_day


def _link_slack_minutes(
    rel: Relation,
    cpm_result: CPMResult,
    cal: Calendar,
) -> int | None:
    """Compute relationship slack for a single relation in minutes.

    Returns ``None`` when slack cannot be computed because either
    end of the link was skipped by the CPM pass due to a cycle
    (``skipped_due_to_cycle=True`` or a ``None`` early date). The
    caller treats ``None`` as a non-traversable edge.
    """
    pred_result = cpm_result.tasks[rel.predecessor_unique_id]
    succ_result = cpm_result.tasks[rel.successor_unique_id]
    if pred_result.skipped_due_to_cycle or succ_result.skipped_due_to_cycle:
        return None
    if (
        pred_result.early_start is None
        or pred_result.early_finish is None
        or succ_result.early_start is None
        or succ_result.early_finish is None
    ):
        return None
    return link_driving_slack_minutes(
        rel.relation_type,
        pred_result.early_start,
        pred_result.early_finish,
        succ_result.early_start,
        succ_result.early_finish,
        rel.lag_minutes,
        cal,
    )


def _build_node(
    task: Task,
    cpm_task: TaskCPMResult,
    hours_per_day: float,
) -> DrivingPathNode:
    """Materialise a :class:`DrivingPathNode` from CPM output.

    Requires non-``None`` early / late dates — callers must filter
    cycle-skipped tasks upstream. The node's ``total_float_days`` is
    converted from minutes through the single minute→day helper.
    """
    assert cpm_task.early_start is not None
    assert cpm_task.early_finish is not None
    assert cpm_task.late_start is not None
    assert cpm_task.late_finish is not None
    return DrivingPathNode(
        unique_id=task.unique_id,
        name=task.name,
        early_start=cpm_task.early_start,
        early_finish=cpm_task.early_finish,
        late_start=cpm_task.late_start,
        late_finish=cpm_task.late_finish,
        total_float_days=minutes_to_days(
            float(cpm_task.total_slack_minutes), hours_per_day
        ),
        calendar_hours_per_day=hours_per_day,
    )


def _build_constraint_driven_predecessor(
    rel: Relation,
    pred_task: Task,
    succ_task: Task,
    lag_days: float,
    slack_days: float,
    hours_per_day: float,
) -> ConstraintDrivenPredecessor:
    """Build a :class:`ConstraintDrivenPredecessor` for a negative-slack edge.

    Per BUILD-PLAN §2.20: the third bucket captures edges whose
    predecessor is held by a hard constraint or by negative-float
    propagation from a missed deadline. The rationale string is written
    here (Block 2) so the M12 narrative layer and the M13 UI can
    surface it verbatim without re-deriving the semantics.

    Manual M/D/YYYY date formatting avoids ``strftime("%-m/%-d/%Y")``,
    which is POSIX-only and breaks on Windows.
    """
    ct = pred_task.constraint_type
    cd = pred_task.constraint_date
    if cd is not None and ct in DATE_BEARING_CONSTRAINTS:
        date_clause = f" of {cd.month}/{cd.day}/{cd.year}"
    else:
        date_clause = ""
    rationale = (
        f"Predecessor has {ct.name} constraint{date_clause}, "
        f"producing negative relationship slack of {slack_days:.2f} days."
    )
    return ConstraintDrivenPredecessor(
        predecessor_uid=rel.predecessor_unique_id,
        predecessor_name=pred_task.name,
        successor_uid=rel.successor_unique_id,
        successor_name=succ_task.name,
        relation_type=rel.relation_type,
        lag_days=lag_days,
        slack_days=slack_days,
        calendar_hours_per_day=hours_per_day,
        predecessor_constraint_type=ct,
        predecessor_constraint_date=cd,
        rationale=rationale,
    )


# ----------------------------------------------------------------------
# Single-schedule trace — adjacency-map backward walk
# ----------------------------------------------------------------------


def trace_driving_path(
    schedule: Schedule,
    focus_spec: int | FocusPointAnchor,
    cpm_result: CPMResult | None = None,
) -> DrivingPathResult:
    """Trace the driving sub-graph from a nominated Focus Point.

    Walks every zero-relationship-slack incoming edge backward from
    the Focus Point recursively per ``driving-slack-and-paths §4``
    ("No path is dropped.") and §5 ("Walking every relationship-
    slack-zero link backward … walks recursively until every driving
    predecessor is exhausted."). Returns an adjacency-map
    :class:`DrivingPathResult` — ``nodes`` keyed by UID (shared
    ancestors deduplicated), ``edges`` enumerating every zero-slack
    driving relationship, and ``non_driving_predecessors`` listing
    the positive-slack relationships that terminated branches.

    Period A slack rule (``driving-slack-and-paths §9``): this
    function treats ``schedule`` as Period A for but-for analysis.
    Cross-version comparisons must use
    :func:`trace_driving_path_cross_version`.

    Non-mutation invariant (BUILD-PLAN §2.13): ``schedule`` and
    ``cpm_result`` are not modified.

    Args:
        schedule: The schedule to trace. Read-only.
        focus_spec: An integer ``Task.unique_id`` or a
            :class:`FocusPointAnchor` — passed to
            :func:`app.engine.focus_point.resolve_focus_point`.
        cpm_result: CPM engine output for ``schedule``. Required:
            the engine is the sole producer of CPM data per
            BUILD-PLAN §2.17, and the tracer refuses to compute
            CPM on its own.

    Returns:
        :class:`DrivingPathResult` — frozen, adjacency-map shape.

    Raises:
        DrivingPathError: ``cpm_result`` is ``None``, or the resolved
            Focus Point UID is missing from ``cpm_result``, was skipped
            by the CPM engine as a cycle participant, or has
            ``None``-valued early/late dates — in any of these cases the
            walk cannot materialise the focus node and refuses to
            return an empty-nodes result (Codex P2). Non-focus tasks
            that hit the same conditions are recorded on
            :attr:`DrivingPathResult.skipped_cycle_participants`
            instead.
        FocusPointError: ``focus_spec`` cannot be resolved.
    """
    if cpm_result is None:
        raise DrivingPathError(
            "trace_driving_path requires a non-None cpm_result; the CPM "
            "engine is the sole producer of CPM data per BUILD-PLAN §2.17"
        )

    focus_uid = resolve_focus_point(schedule, focus_spec)
    tasks = _tasks_by_uid(schedule)
    focus_task = tasks[focus_uid]  # resolve_focus_point validated membership.

    cal = _schedule_calendar(schedule)
    incoming = _incoming_relations(schedule.relations)

    nodes: dict[int, DrivingPathNode] = {}
    edges: list[DrivingPathEdge] = []
    non_driving: list[NonDrivingPredecessor] = []
    constraint_driven: list[ConstraintDrivenPredecessor] = []
    skipped_cycle: list[int] = []
    # O(1) membership dedupe for skipped_cycle. The list is the
    # authoritative container (preserves insertion order before the
    # final sort); the set mirrors it for fast contains-checks across
    # both recording paths (BUILD-PLAN §2.21 / AM11).
    skipped_cycle_set: set[int] = set()

    # BFS queue of UIDs to visit; visited set guards against cyclic
    # input (CPM lenient mode already skips cycles, so this is
    # defensive — cycle participants have skipped_due_to_cycle=True
    # and _link_slack_minutes returns None for their edges — but a
    # schedule author who bypassed CPM could still hand us a loop).
    queue: deque[int] = deque([focus_uid])
    visited: set[int] = set()

    while queue:
        current_uid = queue.popleft()
        if current_uid in visited:
            continue
        visited.add(current_uid)

        current_task = tasks[current_uid]
        current_cpm = cpm_result.tasks.get(current_uid)
        missing_cpm = current_cpm is None or current_cpm.skipped_due_to_cycle
        missing_dates = (not missing_cpm) and (
            current_cpm.early_start is None
            or current_cpm.early_finish is None
            or current_cpm.late_start is None
            or current_cpm.late_finish is None
        )
        if missing_cpm or missing_dates:
            if current_uid == focus_uid:
                reason = (
                    "missing from CPM result / cycle participant"
                    if missing_cpm
                    else "missing early/late dates"
                )
                raise DrivingPathError(
                    f"Focus Point UniqueID {focus_uid} is {reason}; the "
                    "driving-path walk cannot materialise the focus node "
                    "and refuses to return an empty result. Resolve the "
                    "CPM-engine issue (cycle participation or incomplete "
                    "forward/backward pass) or choose a different Focus "
                    "Point."
                )
            # Non-focus UID — record for the forensic audit trail per
            # BUILD-PLAN §2.20 / Block 2 skipped_cycle_participants
            # contract, then terminate this branch.
            if current_uid not in skipped_cycle_set:
                skipped_cycle.append(current_uid)
                skipped_cycle_set.add(current_uid)
            continue

        current_hpd = _resolve_hours_per_day(current_task, schedule)
        nodes[current_uid] = _build_node(current_task, current_cpm, current_hpd)

        for rel in incoming.get(current_uid, []):
            slack_min = _link_slack_minutes(rel, cpm_result, cal)
            if slack_min is None:
                # Non-traversable edge: _link_slack_minutes returns
                # None when either end has skipped_due_to_cycle=True
                # or when a required early date is missing. Edge-level
                # cycle recording per BUILD-PLAN §2.21 (AM11) / Codex
                # PR #33 new P2 finding: when the drop is caused by a
                # cycle participant on either side, the predecessor
                # UID is recorded on skipped_cycle so the forensic-
                # visibility contract captures participants that
                # terminate a branch at the edge level. Focus UID is
                # handled separately by the visit-level raise; already-
                # recorded UIDs are deduped against skipped_cycle_set.
                # The edge itself is still dropped — no DrivingPathEdge,
                # NonDrivingPredecessor, or ConstraintDrivenPredecessor
                # entry is emitted for it.
                pred_uid = rel.predecessor_unique_id
                pred_cpm = cpm_result.tasks.get(pred_uid)
                pred_in_cycle = (
                    pred_cpm is not None and pred_cpm.skipped_due_to_cycle
                )
                succ_in_cycle = current_cpm.skipped_due_to_cycle
                if (
                    (pred_in_cycle or succ_in_cycle)
                    and pred_uid != focus_uid
                    and pred_uid not in skipped_cycle_set
                ):
                    skipped_cycle.append(pred_uid)
                    skipped_cycle_set.add(pred_uid)
                continue

            pred_task = tasks[rel.predecessor_unique_id]
            # Calendar factor for this edge: the predecessor's
            # hours-per-day is the node-bearing side of the edge on
            # the backward walk (the pred is what we'll recurse to).
            pred_hpd = _resolve_hours_per_day(pred_task, schedule)
            lag_days = minutes_to_days(float(rel.lag_minutes), pred_hpd)
            slack_days = minutes_to_days(float(slack_min), pred_hpd)

            if abs(slack_min) <= _ZERO_SLACK_TOLERANCE_MIN:
                edges.append(
                    DrivingPathEdge(
                        predecessor_uid=rel.predecessor_unique_id,
                        predecessor_name=pred_task.name,
                        successor_uid=current_uid,
                        successor_name=current_task.name,
                        relation_type=rel.relation_type,
                        lag_days=lag_days,
                        relationship_slack_days=slack_days,
                        calendar_hours_per_day=pred_hpd,
                    )
                )
                # Per §4 and §5: every zero-slack incoming edge is a
                # driving edge. Enqueue the predecessor for recursion
                # — no tie-break, no drop.
                queue.append(rel.predecessor_unique_id)
            elif slack_min > 0:
                non_driving.append(
                    NonDrivingPredecessor(
                        predecessor_uid=rel.predecessor_unique_id,
                        predecessor_name=pred_task.name,
                        successor_uid=current_uid,
                        successor_name=current_task.name,
                        relation_type=rel.relation_type,
                        lag_days=lag_days,
                        slack_days=slack_days,
                        calendar_hours_per_day=pred_hpd,
                    )
                )
            else:
                # Negative relationship slack — third bucket per
                # BUILD-PLAN §2.20. Predecessor's CPM dates are held by
                # a hard constraint or by negative-float propagation
                # from a missed deadline.
                constraint_driven.append(
                    _build_constraint_driven_predecessor(
                        rel=rel,
                        pred_task=pred_task,
                        succ_task=current_task,
                        lag_days=lag_days,
                        slack_days=slack_days,
                        hours_per_day=pred_hpd,
                    )
                )

    # Deterministic ordering for test assertions and commit-diff
    # stability. Semantic ordering is unordered — renderers are free
    # to reorder for display.
    edges.sort(key=lambda e: (e.successor_uid, e.predecessor_uid))
    non_driving.sort(key=lambda n: (n.successor_uid, n.predecessor_uid))

    return DrivingPathResult(
        focus_point_uid=focus_uid,
        focus_point_name=focus_task.name,
        nodes=nodes,
        edges=edges,
        non_driving_predecessors=non_driving,
        constraint_driven_predecessors=sorted(
            constraint_driven,
            key=lambda p: (p.successor_uid, p.predecessor_uid),
        ),
        skipped_cycle_participants=sorted(skipped_cycle),
    )


# ----------------------------------------------------------------------
# Cross-version trace — Block 7.3 lands the implementation
# ----------------------------------------------------------------------


def trace_driving_path_cross_version(
    period_a: Schedule,
    period_b: Schedule,
    focus_spec: int | FocusPointAnchor,
    period_a_cpm_result: CPMResult,
    period_b_cpm_result: CPMResult,
) -> DrivingPathCrossVersionResult:
    """Trace driving paths in both periods from a shared Focus Point.

    Period A slack is the sole but-for reference per
    ``driving-slack-and-paths §9``. Period B's trace is kept on the
    result for UI display / drill-down but Period B slack is never
    used to derive the added / removed / retained sets.

    Added / removed / retained semantics are framed from Period A's
    perspective:

    * ``added_predecessor_uids`` — UIDs in Period B's
      :attr:`DrivingPathResult.nodes` but not in Period A's.
    * ``removed_predecessor_uids`` — UIDs in Period A's nodes but not
      in Period B's.
    * ``retained_predecessor_uids`` — UIDs in both.

    Edges carry their own identity tuple
    ``(predecessor_uid, successor_uid, relation_type)``. ``added`` /
    ``removed`` / ``retained`` edge classifications use the same
    set-algebra on that tuple.

    The Focus Point UID is excluded from the added/removed/retained
    UID sets — structurally it is always retained (the walk
    terminates at it by definition in both periods).

    Args:
        period_a: Earlier schedule revision. Read-only.
        period_b: Later schedule revision. Read-only.
        focus_spec: Integer ``Task.unique_id`` shared across both
            periods (UniqueID is cross-version stable per
            BUILD-PLAN §2.7), or a :class:`FocusPointAnchor`. When
            an anchor resolves to different UIDs in the two
            schedules, :class:`DrivingPathError` is raised — the
            operator must pass an explicit integer UID to compare
            two different focus milestones.
        period_a_cpm_result: CPM output for Period A.
        period_b_cpm_result: CPM output for Period B.

    Returns:
        :class:`DrivingPathCrossVersionResult` — frozen, adjacency-
        map shape.

    Raises:
        DrivingPathError: Either CPM result is ``None``, or the
            anchor resolves to different UIDs across the two
            schedules.
        FocusPointError: The anchor cannot be resolved in one or
            both schedules.
    """
    # Constraint-driven predecessor cross-version diff is deferred to M11
    # manipulation-scoring scope per M10.1 scope cap (BUILD-PLAN §2.20).
    if period_a_cpm_result is None or period_b_cpm_result is None:
        raise DrivingPathError(
            "trace_driving_path_cross_version requires non-None "
            "cpm_result objects for both periods"
        )

    a_uid = resolve_focus_point(period_a, focus_spec)
    b_uid = resolve_focus_point(period_b, focus_spec)
    if a_uid != b_uid:
        raise DrivingPathError(
            f"focus_spec {focus_spec!r} resolves to different UIDs "
            f"across periods (period_a={a_uid}, period_b={b_uid}). "
            "Pass an explicit integer UID to compare chains with "
            "different anchors explicitly."
        )
    focus_uid = a_uid

    a_result = trace_driving_path(period_a, focus_uid, period_a_cpm_result)
    b_result = trace_driving_path(period_b, focus_uid, period_b_cpm_result)

    a_uids = set(a_result.nodes.keys()) - {focus_uid}
    b_uids = set(b_result.nodes.keys()) - {focus_uid}
    added_uids = b_uids - a_uids
    removed_uids = a_uids - b_uids
    retained_uids = a_uids & b_uids

    # Edge identity is (predecessor_uid, successor_uid, relation_type).
    # Index both period's edges by identity; iterate once per period
    # so each edge is classified exactly once.
    a_edge_by_id = {
        (e.predecessor_uid, e.successor_uid, e.relation_type): e
        for e in a_result.edges
    }
    b_edge_by_id = {
        (e.predecessor_uid, e.successor_uid, e.relation_type): e
        for e in b_result.edges
    }
    a_ids = set(a_edge_by_id.keys())
    b_ids = set(b_edge_by_id.keys())

    # Period A copy is carried for retained / removed (§9 but-for
    # reference); Period B copy for added.
    retained_edges = [a_edge_by_id[k] for k in sorted(a_ids & b_ids)]
    removed_edges = [a_edge_by_id[k] for k in sorted(a_ids - b_ids)]
    added_edges = [b_edge_by_id[k] for k in sorted(b_ids - a_ids)]

    return DrivingPathCrossVersionResult(
        period_a_result=a_result,
        period_b_result=b_result,
        added_predecessor_uids=added_uids,
        removed_predecessor_uids=removed_uids,
        retained_predecessor_uids=retained_uids,
        added_edges=added_edges,
        removed_edges=removed_edges,
        retained_edges=retained_edges,
    )


__all__ = [
    "trace_driving_path",
    "trace_driving_path_cross_version",
]
