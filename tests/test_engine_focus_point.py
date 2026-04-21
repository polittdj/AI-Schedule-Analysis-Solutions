"""Tests for the Milestone 10 Focus Point resolver.

Covers direct UID resolution, PROJECT_FINISH / PROJECT_START anchor
resolution with tie-break rules, empty-schedule and all-cyclic
error paths, and mutation-invariance of the input ``Schedule``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.driving_path_types import FocusPointAnchor
from app.engine.exceptions import EngineError, FocusPointError
from app.engine.focus_point import resolve_focus_point
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task


ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _linear_schedule() -> Schedule:
    """A → B → C (FS). C is the sink, A is the source."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480,
             start=ANCHOR, finish=ANCHOR),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480,
             start=ANCHOR, finish=ANCHOR),
        Task(
            unique_id=3, task_id=3, name="C_finish",
            duration_minutes=0, is_milestone=True,
            start=datetime(2026, 4, 22, 16, 0, tzinfo=UTC),
            finish=datetime(2026, 4, 22, 16, 0, tzinfo=UTC),
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.FS),
    ]
    return Schedule(
        name="linear", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# Direct UID resolution
# ----------------------------------------------------------------------


def test_direct_uid_returns_itself_when_present() -> None:
    s = _linear_schedule()
    assert resolve_focus_point(s, 2) == 2


def test_direct_uid_returns_focus_uid_for_sink() -> None:
    s = _linear_schedule()
    assert resolve_focus_point(s, 3) == 3


def test_direct_uid_raises_on_missing_uid() -> None:
    s = _linear_schedule()
    with pytest.raises(FocusPointError, match="unique_id=999"):
        resolve_focus_point(s, 999)


def test_focus_point_error_is_an_engine_error() -> None:
    # Catchable via the general EngineError base — the M10 API lets
    # callers unify catch blocks across engine-layer failures.
    s = _linear_schedule()
    with pytest.raises(EngineError):
        resolve_focus_point(s, 12345)


# ----------------------------------------------------------------------
# PROJECT_FINISH anchor
# ----------------------------------------------------------------------


def test_project_finish_on_linear_schedule_returns_terminal_task() -> None:
    s = _linear_schedule()
    assert (
        resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)
        == 3
    )


def test_project_finish_prefers_milestone_over_non_milestone_sink() -> None:
    """Two sinks: one milestone, one non-milestone. Milestone wins."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(
            unique_id=2, task_id=2, name="NonMilestoneSink",
            duration_minutes=480,
            finish=datetime(2027, 1, 1, 16, 0, tzinfo=UTC),
        ),
        Task(
            unique_id=3, task_id=3, name="MilestoneSink",
            duration_minutes=0, is_milestone=True,
            finish=datetime(2026, 4, 30, 16, 0, tzinfo=UTC),
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=1, successor_unique_id=3),
    ]
    s = Schedule(
        name="two_sinks", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    # Milestone (3) wins despite earlier finish.
    assert (
        resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)
        == 3
    )


def test_project_finish_prefers_latest_finish_among_milestones() -> None:
    """Two milestone sinks; later finish wins."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(
            unique_id=2, task_id=2, name="EarlyMilestone",
            duration_minutes=0, is_milestone=True,
            finish=datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
        ),
        Task(
            unique_id=3, task_id=3, name="LateMilestone",
            duration_minutes=0, is_milestone=True,
            finish=datetime(2026, 6, 1, 16, 0, tzinfo=UTC),
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=1, successor_unique_id=3),
    ]
    s = Schedule(
        name="two_milestone_sinks", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    assert (
        resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)
        == 3
    )


def test_project_finish_tiebreak_uses_higher_uid_when_finish_equal() -> None:
    """Two sinks with identical finish — higher UID wins."""
    finish = datetime(2026, 5, 1, 16, 0, tzinfo=UTC)
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(
            unique_id=2, task_id=2, name="S2",
            duration_minutes=0, is_milestone=True, finish=finish,
        ),
        Task(
            unique_id=3, task_id=3, name="S3",
            duration_minutes=0, is_milestone=True, finish=finish,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=1, successor_unique_id=3),
    ]
    s = Schedule(
        name="tie_sinks", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    assert (
        resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)
        == 3
    )


def test_project_finish_on_empty_schedule_raises() -> None:
    s = Schedule(name="empty", calendars=[_std_cal()])
    with pytest.raises(FocusPointError, match="empty schedule"):
        resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)


def test_project_finish_with_no_sink_raises() -> None:
    """A mini-cycle means every task has outgoing relations.

    The Schedule G10/G11 validators don't reject cycles (the CPM
    engine handles them leniently), but every task in a cycle has
    outgoing relations so no PROJECT_FINISH candidate exists.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
    ]
    s = Schedule(
        name="cyclic", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    with pytest.raises(FocusPointError, match="no sink"):
        resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)


# ----------------------------------------------------------------------
# PROJECT_START anchor
# ----------------------------------------------------------------------


def test_project_start_on_linear_schedule_returns_source_task() -> None:
    s = _linear_schedule()
    assert resolve_focus_point(s, FocusPointAnchor.PROJECT_START) == 1


def test_project_start_prefers_milestone_over_non_milestone_source() -> None:
    tasks = [
        Task(
            unique_id=1, task_id=1, name="NonMilestoneSource",
            duration_minutes=480,
            start=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        ),
        Task(
            unique_id=2, task_id=2, name="MilestoneSource",
            duration_minutes=0, is_milestone=True,
            start=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        ),
        Task(unique_id=3, task_id=3, name="Sink", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = Schedule(
        name="two_sources", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    # Milestone wins.
    assert (
        resolve_focus_point(s, FocusPointAnchor.PROJECT_START)
        == 2
    )


def test_project_start_prefers_earliest_start_among_milestones() -> None:
    tasks = [
        Task(
            unique_id=1, task_id=1, name="EarlyMilestone",
            duration_minutes=0, is_milestone=True,
            start=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        ),
        Task(
            unique_id=2, task_id=2, name="LateMilestone",
            duration_minutes=0, is_milestone=True,
            start=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        ),
        Task(unique_id=3, task_id=3, name="Sink", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = Schedule(
        name="two_milestone_sources", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    assert (
        resolve_focus_point(s, FocusPointAnchor.PROJECT_START)
        == 1
    )


def test_project_start_on_empty_schedule_raises() -> None:
    s = Schedule(name="empty", calendars=[_std_cal()])
    with pytest.raises(FocusPointError, match="empty schedule"):
        resolve_focus_point(s, FocusPointAnchor.PROJECT_START)


def test_project_start_with_no_source_raises() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
    ]
    s = Schedule(
        name="cyclic", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    with pytest.raises(FocusPointError, match="no source"):
        resolve_focus_point(s, FocusPointAnchor.PROJECT_START)


# ----------------------------------------------------------------------
# Invalid argument handling
# ----------------------------------------------------------------------


def test_resolve_rejects_non_int_non_anchor_argument() -> None:
    s = _linear_schedule()
    with pytest.raises(FocusPointError, match="must be int or FocusPointAnchor"):
        resolve_focus_point(s, "project_finish")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Mutation invariance
# ----------------------------------------------------------------------


def test_resolve_does_not_mutate_schedule() -> None:
    s = _linear_schedule()
    before = s.model_dump(mode="json")
    resolve_focus_point(s, FocusPointAnchor.PROJECT_FINISH)
    resolve_focus_point(s, FocusPointAnchor.PROJECT_START)
    resolve_focus_point(s, 2)
    assert s.model_dump(mode="json") == before
