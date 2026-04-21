"""Integration test for Milestone 10 driving-path analysis.

Exercises the public API via the engine re-exports
(``app.engine.trace_driving_path``,
``app.engine.trace_driving_path_cross_version``,
``app.engine.resolve_focus_point``, ``app.engine.FocusPointAnchor``)
on a paired synthetic schedule covering:

* Single-schedule trace on a three-tier chain with a non-driving
  predecessor branch.
* Cross-version trace where Period B removes one predecessor and
  adds another.
* UniqueID-only matching under a rename-all regression.

Every call is wrapped in mutation-invariance assertions per
BUILD-PLAN §2.13: both schedules and both ``CPMResult`` snapshots
round-trip byte-identical.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.engine import (
    DrivingPathCrossVersionResult,
    DrivingPathResult,
    FocusPointAnchor,
    compute_cpm,
    resolve_focus_point,
    trace_driving_path,
    trace_driving_path_cross_version,
)
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot


ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _period_a() -> Schedule:
    """Period A: three-tier chain A → B → C → Finish + non-driving
    task Q feeding B."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Finish",
             duration_minutes=0, is_milestone=True),
        Task(unique_id=5, task_id=5, name="Q", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=3, successor_unique_id=4,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=5, successor_unique_id=2,
                 relation_type=RelationType.FS),
    ]
    return Schedule(
        name="period_a", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )


def _period_b() -> Schedule:
    """Period B: drop B from the chain, add D (UID 10) between A
    and C. Q is retained but now feeds C instead of B."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Finish",
             duration_minutes=0, is_milestone=True),
        Task(unique_id=5, task_id=5, name="Q", duration_minutes=480),
        Task(unique_id=10, task_id=6, name="D", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=10,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=10, successor_unique_id=3,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=3, successor_unique_id=4,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=5, successor_unique_id=3,
                 relation_type=RelationType.FS),
    ]
    return Schedule(
        name="period_b", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )


def _period_b_renamed() -> Schedule:
    """Period B with every task name swapped out — regression for
    UniqueID-only matching."""
    tasks = [
        Task(unique_id=1, task_id=1, name="Alpha", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Bravo", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Charlie", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Delta",
             duration_minutes=0, is_milestone=True),
        Task(unique_id=5, task_id=5, name="Echo", duration_minutes=480),
        Task(unique_id=10, task_id=6, name="Foxtrot", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=10),
        Relation(predecessor_unique_id=10, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
        Relation(predecessor_unique_id=5, successor_unique_id=3),
    ]
    return Schedule(
        name="period_b_renamed", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# Public-API import surface
# ----------------------------------------------------------------------


def test_public_api_exposes_m10_surface() -> None:
    """Every M10 symbol is available on the ``app.engine`` namespace."""
    from app.engine import (
        DrivingPathCrossVersionResult,
        DrivingPathError,
        DrivingPathLink,
        DrivingPathNode,
        DrivingPathResult,
        FocusPointAnchor,
        FocusPointError,
        NonDrivingPredecessor,
        resolve_focus_point,
        trace_driving_path,
        trace_driving_path_cross_version,
    )

    # Symbols are not None (i.e. the re-export resolved).
    assert DrivingPathResult is not None
    assert DrivingPathCrossVersionResult is not None
    assert DrivingPathLink is not None
    assert DrivingPathNode is not None
    assert NonDrivingPredecessor is not None
    assert FocusPointAnchor.PROJECT_FINISH == "project_finish"
    assert callable(trace_driving_path)
    assert callable(trace_driving_path_cross_version)
    assert callable(resolve_focus_point)
    assert issubclass(DrivingPathError, Exception)
    assert issubclass(FocusPointError, Exception)


# ----------------------------------------------------------------------
# Single-schedule integration — SSI-like chain + non-driving branch
# ----------------------------------------------------------------------


def test_integration_single_schedule_trace() -> None:
    a = _period_a()
    cpm = compute_cpm(a)
    a_before = a.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(a, FocusPointAnchor.PROJECT_FINISH, cpm)

    assert isinstance(result, DrivingPathResult)
    # Chain: A (2 WD) → B → C → Finish; Q is non-driving (shorter
    # duration, feeds B after A's EF).
    assert [n.unique_id for n in result.chain] == [1, 2, 3, 4]
    assert [n.name for n in result.chain] == ["A", "B", "C", "Finish"]
    for link in result.links:
        assert link.relation_type == RelationType.FS
        assert link.relationship_slack_minutes == 0
    # Exactly one non-driving predecessor: Q → B.
    assert len(result.non_driving_predecessors) == 1
    ndp = result.non_driving_predecessors[0]
    assert ndp.predecessor_unique_id == 5
    assert ndp.successor_unique_id == 2
    assert ndp.relationship_slack_minutes > 0

    # Mutation invariance.
    assert a.model_dump(mode="json") == a_before
    assert cpm_result_snapshot(cpm) == cpm_before


# ----------------------------------------------------------------------
# Cross-version integration — one added, one removed
# ----------------------------------------------------------------------


def test_integration_cross_version_trace() -> None:
    a = _period_a()
    b = _period_b()
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    a_before = a.model_dump(mode="json")
    b_before = b.model_dump(mode="json")
    cpm_a_before = cpm_result_snapshot(cpm_a)
    cpm_b_before = cpm_result_snapshot(cpm_b)

    focus = resolve_focus_point(a, FocusPointAnchor.PROJECT_FINISH)
    assert focus == 4

    result = trace_driving_path_cross_version(
        a, b, focus, cpm_a, cpm_b,
    )

    assert isinstance(result, DrivingPathCrossVersionResult)
    assert result.focus_unique_id == 4
    # Period A chain predecessors (excluding focus): {1, 2, 3}.
    # Period B chain predecessors (excluding focus): {1, 10, 3}.
    # Added: {10}. Removed: {2}. Retained: {1, 3}.
    assert result.added_predecessor_uids == frozenset({10})
    assert result.removed_predecessor_uids == frozenset({2})
    assert result.retained_predecessor_uids == frozenset({1, 3})

    # Mutation invariance on all four inputs.
    assert a.model_dump(mode="json") == a_before
    assert b.model_dump(mode="json") == b_before
    assert cpm_result_snapshot(cpm_a) == cpm_a_before
    assert cpm_result_snapshot(cpm_b) == cpm_b_before


# ----------------------------------------------------------------------
# UniqueID-only matching — rename-all regression
# ----------------------------------------------------------------------


def test_integration_rename_regression() -> None:
    """Rename every task in Period B; deltas are identical to the
    un-renamed Period B run.

    Per BUILD-PLAN §2.7, UniqueID is the only cross-version match
    key. This regression proves that Period B's chain identity does
    not depend on `Task.name`.
    """
    a = _period_a()
    b_plain = _period_b()
    b_renamed = _period_b_renamed()

    cpm_a = compute_cpm(a)
    cpm_b_plain = compute_cpm(b_plain)
    cpm_b_renamed = compute_cpm(b_renamed)

    plain = trace_driving_path_cross_version(
        a, b_plain, 4, cpm_a, cpm_b_plain,
    )
    renamed = trace_driving_path_cross_version(
        a, b_renamed, 4, cpm_a, cpm_b_renamed,
    )

    # All three UID sets unchanged.
    assert plain.added_predecessor_uids == renamed.added_predecessor_uids
    assert plain.removed_predecessor_uids == renamed.removed_predecessor_uids
    assert plain.retained_predecessor_uids == renamed.retained_predecessor_uids
    # Period A trace is identical (same input).
    assert [n.unique_id for n in plain.period_a_result.chain] == [
        n.unique_id for n in renamed.period_a_result.chain
    ]
    # Period B chain UIDs match despite every name changing.
    assert [n.unique_id for n in plain.period_b_result.chain] == [
        n.unique_id for n in renamed.period_b_result.chain
    ]
    # Names are captured independently per period.
    assert [n.name for n in plain.period_b_result.chain] == [
        "A", "D", "C", "Finish",
    ]
    assert [n.name for n in renamed.period_b_result.chain] == [
        "Alpha", "Foxtrot", "Charlie", "Delta",
    ]
