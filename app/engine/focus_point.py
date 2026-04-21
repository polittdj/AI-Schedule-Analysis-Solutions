"""Focus Point resolver for task-specific driving-path analysis.

Milestone 10. Maps an operator nomination — either an explicit
``Task.unique_id`` integer or a
:class:`~app.engine.driving_path_types.FocusPointAnchor` enum — to
the UniqueID of a concrete task on a ``Schedule``.

Authority:

* SSI Focus Point terminology — ``driving-slack-and-paths §2``.
* Project-finish as a special-case focus — the project critical
  path is the driving path whose Focus Point is the project finish
  milestone per ``driving-slack-and-paths §1``.
* UniqueID as sole cross-version identifier — BUILD-PLAN §2.7;
  ``mpp-parsing-com-automation §5``.

This module is read-only. The resolver does not mutate the
``Schedule`` argument and does not depend on ``CPMResult`` — Focus
Point resolution is a pre-CPM step (the caller runs CPM *after*
picking the focus), so the resolver uses raw ``Task`` dates only.
"""

from __future__ import annotations

from datetime import datetime

from app.engine.driving_path_types import FocusPointAnchor
from app.engine.exceptions import FocusPointError
from app.models.schedule import Schedule
from app.models.task import Task


def _tasks_by_uid(schedule: Schedule) -> dict[int, Task]:
    return {t.unique_id: t for t in schedule.tasks}


def _tasks_with_no_outgoing(schedule: Schedule) -> list[Task]:
    """Tasks that have zero outgoing relations.

    A candidate project-finish milestone is a task that nothing
    depends on — i.e. no Relation uses it as a predecessor. The
    same pattern drives the M4 critical-path sinks.
    """
    predecessor_uids = {r.predecessor_unique_id for r in schedule.relations}
    return [t for t in schedule.tasks if t.unique_id not in predecessor_uids]


def _tasks_with_no_incoming(schedule: Schedule) -> list[Task]:
    """Tasks that have zero incoming relations.

    Symmetric to :func:`_tasks_with_no_outgoing`: a candidate
    project-start milestone is a task that depends on nothing.
    """
    successor_uids = {r.successor_unique_id for r in schedule.relations}
    return [t for t in schedule.tasks if t.unique_id not in successor_uids]


def _latest_finish_key(task: Task) -> tuple[int, datetime, int]:
    """Sort key for project-finish disambiguation.

    Milestones rank above non-milestones, then later finish dates,
    then lower UniqueID as a deterministic tiebreaker. ``finish``
    is the best-available forecast finish date on the pre-CPM
    ``Schedule`` (``Task.finish`` is the COM-captured forecast); a
    ``None`` finish sorts earliest via the ``datetime.min`` fallback
    so CPM has something to run on.
    """
    # datetime.min is naive; replace with a sentinel tz-aware value.
    from datetime import UTC

    sentinel = datetime(1, 1, 1, tzinfo=UTC)
    finish = task.finish or sentinel
    return (int(task.is_milestone), finish, task.unique_id)


def _earliest_start_key(task: Task) -> tuple[int, datetime, int]:
    """Sort key for project-start disambiguation.

    Milestones rank above non-milestones, then earlier start dates
    (negated so ``max()`` picks the earliest), then lower UniqueID.
    """
    from datetime import UTC

    sentinel_late = datetime(9999, 12, 31, tzinfo=UTC)
    start = task.start or sentinel_late
    # Negated epoch so lower (earlier) start dates rank higher.
    return (int(task.is_milestone), -int(start.timestamp()), task.unique_id)


def resolve_focus_point(
    schedule: Schedule,
    focus_spec: int | FocusPointAnchor,
) -> int:
    """Resolve a Focus Point nomination to a concrete ``Task.unique_id``.

    Args:
        schedule: The schedule to search. The resolver is read-only
            — the input is not mutated.
        focus_spec: Either an integer ``Task.unique_id`` (direct
            nomination) or a
            :class:`~app.engine.driving_path_types.FocusPointAnchor`
            (predefined anchor — ``PROJECT_FINISH`` or
            ``PROJECT_START``).

    Returns:
        The UniqueID of the resolved focus task.

    Raises:
        FocusPointError: The ``focus_spec`` cannot be resolved.
            Diagnostic ``detail`` covers:

            * integer UID: no task in the schedule has that UID;
            * ``PROJECT_FINISH`` / ``PROJECT_START``: the schedule
              has zero tasks, or zero candidate anchors (every task
              has at least one outgoing / incoming relation).

    Tie-break rules:

    * ``PROJECT_FINISH`` — when multiple tasks have zero outgoing
      relations, the resolver prefers (1) milestones over non-
      milestones, (2) the latest ``Task.finish`` forecast,
      (3) the highest ``Task.unique_id`` as a deterministic
      fallback.
    * ``PROJECT_START`` — symmetric: (1) milestones preferred,
      (2) earliest ``Task.start`` forecast, (3) highest
      ``Task.unique_id``.

    The tie-break rules are documented in-line rather than surfaced
    as a configurable option; forensic defensibility (BUILD-PLAN §6
    AC bar #3) prefers a documented deterministic choice over an
    opaque configuration.
    """
    if isinstance(focus_spec, int) and not isinstance(focus_spec, FocusPointAnchor):
        return _resolve_by_uid(schedule, focus_spec)
    if isinstance(focus_spec, FocusPointAnchor):
        return _resolve_by_anchor(schedule, focus_spec)
    raise FocusPointError(
        f"focus_spec must be int or FocusPointAnchor, got {type(focus_spec).__name__}"
    )


def _resolve_by_uid(schedule: Schedule, uid: int) -> int:
    if uid in _tasks_by_uid(schedule):
        return uid
    raise FocusPointError(
        f"no task with unique_id={uid} in schedule "
        f"(known UIDs: {sorted(_tasks_by_uid(schedule))[:10]}"
        f"{'...' if len(schedule.tasks) > 10 else ''})"
    )


def _resolve_by_anchor(schedule: Schedule, anchor: FocusPointAnchor) -> int:
    if not schedule.tasks:
        raise FocusPointError(
            f"cannot resolve {anchor.value} on empty schedule (zero tasks)"
        )
    if anchor == FocusPointAnchor.PROJECT_FINISH:
        candidates = _tasks_with_no_outgoing(schedule)
        if not candidates:
            raise FocusPointError(
                "cannot resolve project_finish: every task has at least one "
                "outgoing relation (schedule has no sink task)"
            )
        winner = max(candidates, key=_latest_finish_key)
        return winner.unique_id
    if anchor == FocusPointAnchor.PROJECT_START:
        candidates = _tasks_with_no_incoming(schedule)
        if not candidates:
            raise FocusPointError(
                "cannot resolve project_start: every task has at least one "
                "incoming relation (schedule has no source task)"
            )
        winner = max(candidates, key=_earliest_start_key)
        return winner.unique_id
    # Defensive — StrEnum membership is exhaustively enumerated above.
    raise FocusPointError(f"unknown FocusPointAnchor: {anchor!r}")


__all__ = ["resolve_focus_point"]
