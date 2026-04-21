"""Task-specific driving-path tracer — Milestone 10.

Backward walk from an operator-nominated Focus Point along
zero-relationship-slack edges per ``driving-slack-and-paths §5``.
Emits an ordered chain + parallel per-link slack list + non-driving
predecessor secondary list. Cross-version mode reports driving-
predecessor added / removed / retained from Period A to B; Period A
slack is the sole but-for reference per ``driving-slack-and-paths §9``.

Authority:

* SSI driving-slack methodology — ``driving-slack-and-paths §2``.
* Per-link relationship-slack formulas —
  ``driving-slack-and-paths §3`` (reused via
  :func:`app.engine.relations.link_driving_slack_minutes`).
* Backward walk + multi-branch termination —
  ``driving-slack-and-paths §§5, 7``.
* Period A slack rule — ``driving-slack-and-paths §9``.
* UniqueID-only matching — BUILD-PLAN §2.7;
  ``mpp-parsing-com-automation §5``.

Non-mutation invariant: neither ``Schedule`` nor ``CPMResult`` is
mutated by any function in this module. Tests snapshot
``Schedule.model_dump()`` and :func:`tests._utils.cpm_result_snapshot`
before / after every trace call.
"""

from __future__ import annotations

from collections import defaultdict

from app.engine.driving_path_types import (
    DrivingPathCrossVersionResult,
    DrivingPathLink,
    DrivingPathNode,
    DrivingPathResult,
    FocusPointAnchor,
    NonDrivingPredecessor,
)
from app.engine.exceptions import DrivingPathError
from app.engine.focus_point import resolve_focus_point
from app.engine.relations import link_driving_slack_minutes
from app.engine.result import CPMResult
from app.models.calendar import Calendar
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task


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


def _link_slack(
    rel: Relation,
    tasks: dict[int, Task],
    cpm_result: CPMResult,
    cal: Calendar,
) -> int | None:
    """Compute relationship slack for a single relation.

    Returns ``None`` when slack cannot be computed — e.g. either end
    of the link is in a cycle and was skipped by the CPM pass
    (``skipped_due_to_cycle=True`` or the early dates are ``None``).
    The caller treats ``None`` as a non-traversable edge; the
    driving-path walk cannot rely on an undefined slack.
    """
    pred_result = cpm_result.tasks.get(rel.predecessor_unique_id)
    succ_result = cpm_result.tasks.get(rel.successor_unique_id)
    if pred_result is None or succ_result is None:
        return None
    if pred_result.skipped_due_to_cycle or succ_result.skipped_due_to_cycle:
        return None
    if (
        pred_result.early_start is None
        or pred_result.early_finish is None
        or succ_result.early_start is None
        or succ_result.early_finish is None
    ):
        return None
    if (
        rel.predecessor_unique_id not in tasks
        or rel.successor_unique_id not in tasks
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


# ----------------------------------------------------------------------
# Single-schedule trace
# ----------------------------------------------------------------------


def trace_driving_path(
    schedule: Schedule,
    focus_spec: int | FocusPointAnchor,
    cpm_result: CPMResult | None = None,
) -> DrivingPathResult:
    """Trace the driving path to a nominated Focus Point.

    Backward-walks the logic network from the Focus Point along
    zero-relationship-slack edges (``driving-slack-and-paths §5``).
    Returns an ordered chain (earliest ancestor → focus), a parallel
    links list, and a non-driving-predecessor secondary list.

    Period A slack rule (``driving-slack-and-paths §9``): this
    function treats ``schedule`` as Period A for but-for analysis.
    Cross-version comparisons must use
    :func:`trace_driving_path_cross_version` — the returned
    :class:`DrivingPathResult` carries no Period B context.

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
        :class:`DrivingPathResult` — frozen Pydantic v2 contract.

    Raises:
        DrivingPathError: ``cpm_result`` is ``None``.
        FocusPointError: ``focus_spec`` cannot be resolved.

    Tie-break: when a chain task has two or more zero-slack incoming
    edges (multiple driving predecessors), the walk follows the
    predecessor with the lowest ``Task.unique_id``; the non-followed
    driver(s) land on ``non_driving_predecessors`` with
    ``relationship_slack_minutes = 0`` so the UI can surface the
    multi-branch case (BUILD-PLAN §5 M10 Block 0 reconciliation).
    """
    if cpm_result is None:
        raise DrivingPathError(
            "trace_driving_path requires a non-None cpm_result; the CPM "
            "engine is the sole producer of CPM data per BUILD-PLAN §2.17"
        )
    focus_uid = resolve_focus_point(schedule, focus_spec)

    tasks = _tasks_by_uid(schedule)
    focus_task = tasks.get(focus_uid)
    if focus_task is None:
        # Defensive — resolve_focus_point already validated
        # membership, but cross-version reuse calls this with a UID
        # derived from the other period's resolver; the per-period
        # membership check lands here.
        raise DrivingPathError(
            f"focus_uid={focus_uid} is not a task in this schedule"
        )

    cal = _schedule_calendar(schedule)
    incoming = _incoming_relations(schedule.relations)

    chain_reverse: list[DrivingPathNode] = [
        DrivingPathNode(unique_id=focus_task.unique_id, name=focus_task.name)
    ]
    links_reverse: list[DrivingPathLink] = []
    non_driving: list[NonDrivingPredecessor] = []
    visited: set[int] = {focus_uid}

    current_uid = focus_uid
    while True:
        current_task = tasks[current_uid]
        incoming_rels = incoming.get(current_uid, [])
        # Deterministic ordering: sort by (pred_uid, relation_type)
        # so the same schedule always produces the same trace.
        incoming_rels = sorted(
            incoming_rels,
            key=lambda r: (r.predecessor_unique_id, int(r.relation_type)),
        )

        drivers: list[tuple[Relation, int]] = []
        for rel in incoming_rels:
            slack = _link_slack(rel, tasks, cpm_result, cal)
            if slack is None:
                # Non-traversable edge — treat as not a driver and
                # do NOT record on non_driving_predecessors (the
                # slack value would be meaningless there).
                continue
            if slack == 0:
                drivers.append((rel, slack))
            else:
                pred_task = tasks.get(rel.predecessor_unique_id)
                if pred_task is None:
                    continue
                non_driving.append(
                    NonDrivingPredecessor(
                        predecessor_unique_id=rel.predecessor_unique_id,
                        predecessor_name=pred_task.name,
                        successor_unique_id=current_uid,
                        successor_name=current_task.name,
                        relation_type=rel.relation_type,
                        relationship_slack_minutes=slack,
                    )
                )

        if not drivers:
            # Terminate the walk — no zero-slack predecessor.
            break

        # Tie-break: follow the lowest-UID driver. Alternates land on
        # non_driving_predecessors with slack = 0 so the UI can show
        # parallel drivers without widening the contract.
        drivers.sort(key=lambda dp: dp[0].predecessor_unique_id)
        followed_rel, followed_slack = drivers[0]
        alternates = drivers[1:]
        for alt_rel, alt_slack in alternates:
            alt_pred = tasks.get(alt_rel.predecessor_unique_id)
            if alt_pred is None:
                continue
            non_driving.append(
                NonDrivingPredecessor(
                    predecessor_unique_id=alt_rel.predecessor_unique_id,
                    predecessor_name=alt_pred.name,
                    successor_unique_id=current_uid,
                    successor_name=current_task.name,
                    relation_type=alt_rel.relation_type,
                    relationship_slack_minutes=alt_slack,
                )
            )

        next_uid = followed_rel.predecessor_unique_id
        if next_uid in visited:
            # Defensive — a cyclic driving chain would loop forever.
            # CPM lenient mode skips cycles (slack is None for edges
            # into a cyclic node), so this branch fires only on
            # pathological input that bypasses CPM. Break cleanly
            # rather than raising; the chain up to this point is
            # still forensically valid.
            break
        visited.add(next_uid)
        next_task = tasks[next_uid]
        chain_reverse.append(
            DrivingPathNode(unique_id=next_uid, name=next_task.name)
        )
        links_reverse.append(
            DrivingPathLink(
                predecessor_unique_id=next_uid,
                successor_unique_id=current_uid,
                relation_type=followed_rel.relation_type,
                lag_minutes=followed_rel.lag_minutes,
                relationship_slack_minutes=followed_slack,
            )
        )
        current_uid = next_uid

    # Reverse so chain runs earliest-ancestor → focus.
    chain = tuple(reversed(chain_reverse))
    links = tuple(reversed(links_reverse))

    return DrivingPathResult(
        focus_unique_id=focus_uid,
        focus_name=focus_task.name,
        chain=chain,
        links=links,
        non_driving_predecessors=tuple(non_driving),
    )


# ----------------------------------------------------------------------
# Cross-version trace (Block 5 — stub signature so Block 3 exports
# cleanly once Block 5 lands; implementation follows in Block 5)
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
    used to derive the added / removed / retained UID sets.

    Added / removed / retained semantics are framed from Period A's
    perspective:

    * ``added_predecessor_uids`` — UIDs in Period B's chain but not
      in Period A's.
    * ``removed_predecessor_uids`` — UIDs in Period A's chain but not
      in Period B's.
    * ``retained_predecessor_uids`` — UIDs in both chains.

    The Focus Point UID itself is excluded from all three sets
    (structurally it is always "retained").

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
        :class:`DrivingPathCrossVersionResult` — frozen.

    Raises:
        DrivingPathError: Either CPM result is ``None``, or the
            anchor resolves to different UIDs across the two
            schedules.
        FocusPointError: The anchor cannot be resolved in one or
            both schedules.
    """
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

    a_trace = trace_driving_path(period_a, focus_uid, period_a_cpm_result)
    b_trace = trace_driving_path(period_b, focus_uid, period_b_cpm_result)

    a_chain_uids = {n.unique_id for n in a_trace.chain} - {focus_uid}
    b_chain_uids = {n.unique_id for n in b_trace.chain} - {focus_uid}

    return DrivingPathCrossVersionResult(
        focus_unique_id=focus_uid,
        period_a_result=a_trace,
        period_b_result=b_trace,
        added_predecessor_uids=frozenset(b_chain_uids - a_chain_uids),
        removed_predecessor_uids=frozenset(a_chain_uids - b_chain_uids),
        retained_predecessor_uids=frozenset(a_chain_uids & b_chain_uids),
    )


__all__ = [
    "trace_driving_path",
    "trace_driving_path_cross_version",
]
