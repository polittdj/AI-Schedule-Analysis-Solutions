"""Integration test for Milestone 10 driving-path analysis.

Reshaped in Block 7 (2026-04-22) for the adjacency-map contract per
BUILD-PLAN AM8. Exercises the public API via the engine re-exports
(``app.engine.trace_driving_path``,
``app.engine.trace_driving_path_cross_version``,
``app.engine.render_acumen_table``, ``app.engine.resolve_focus_point``,
``app.engine.FocusPointAnchor``) on a paired synthetic schedule
covering:

* Single-schedule trace on a three-tier chain with a non-driving
  predecessor branch + Acumen-table rendering.
* Cross-version trace where Period B removes one predecessor and
  adds another.
* UniqueID-only matching under a rename-all regression.

Every call is wrapped in mutation-invariance assertions per
BUILD-PLAN §2.13: both schedules and both ``CPMResult`` snapshots
round-trip byte-identical.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine import (
    DrivingPathCrossVersionResult,
    DrivingPathResult,
    FocusPointAnchor,
    compute_cpm,
    render_acumen_table,
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


def _sched(tasks: list[Task], relations: list[Relation], *, name: str) -> Schedule:
    return Schedule(
        name=name,
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def _period_a() -> Schedule:
    """Three-tier chain A → B → C → Finish + non-driving Q feeding B."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(unique_id=5, task_id=5, name="Q", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=2,
            successor_unique_id=3,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=3,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=5,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    return _sched(tasks, relations, name="period_a")


def _period_b() -> Schedule:
    """Period B: drop B from the chain, add D (UID 10) between A and C."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(unique_id=5, task_id=5, name="Q", duration_minutes=480),
        Task(unique_id=10, task_id=6, name="D", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=10,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=10,
            successor_unique_id=3,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=3,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=5,
            successor_unique_id=3,
            relation_type=RelationType.FS,
        ),
    ]
    return _sched(tasks, relations, name="period_b")


def _period_b_renamed() -> Schedule:
    """Period B with every task name swapped out."""
    tasks = [
        Task(unique_id=1, task_id=1, name="Alpha", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Bravo", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Charlie", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Delta",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(unique_id=5, task_id=5, name="Echo", duration_minutes=480),
        Task(unique_id=10, task_id=6, name="Foxtrot", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=10),
        Relation(predecessor_unique_id=10, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
        Relation(predecessor_unique_id=5, successor_unique_id=3),
    ]
    return _sched(tasks, relations, name="period_b_renamed")


# ----------------------------------------------------------------------
# Public-API import surface
# ----------------------------------------------------------------------


def test_public_api_exposes_m10_surface() -> None:
    from app.engine import (
        DrivingPathCrossVersionResult,
        DrivingPathEdge,
        DrivingPathError,
        DrivingPathNode,
        DrivingPathResult,
        FocusPointAnchor,
        FocusPointError,
        NonDrivingPredecessor,
        render_acumen_table,
        resolve_focus_point,
        trace_driving_path,
        trace_driving_path_cross_version,
    )

    assert DrivingPathResult is not None
    assert DrivingPathCrossVersionResult is not None
    assert DrivingPathEdge is not None
    assert DrivingPathNode is not None
    assert NonDrivingPredecessor is not None
    assert FocusPointAnchor.PROJECT_FINISH == "project_finish"
    assert callable(trace_driving_path)
    assert callable(trace_driving_path_cross_version)
    assert callable(resolve_focus_point)
    assert callable(render_acumen_table)
    assert issubclass(DrivingPathError, Exception)
    assert issubclass(FocusPointError, Exception)


def test_public_api_does_not_expose_removed_driving_path_link() -> None:
    """Block 7: DrivingPathLink was removed from the public API."""
    import app.engine

    assert not hasattr(app.engine, "DrivingPathLink")
    assert "DrivingPathLink" not in app.engine.__all__


# ----------------------------------------------------------------------
# Single-schedule integration — chain + non-driving branch + renderer
# ----------------------------------------------------------------------


def test_integration_single_schedule_trace() -> None:
    a = _period_a()
    cpm = compute_cpm(a)
    a_before = a.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(a, FocusPointAnchor.PROJECT_FINISH, cpm)

    assert isinstance(result, DrivingPathResult)
    # Sub-graph: A → B → C → Finish; Q non-driving (feeds B with positive slack).
    assert set(result.nodes.keys()) == {1, 2, 3, 4}
    assert result.focus_point_uid == 4
    assert result.focus_point_name == "Finish"
    assert len(result.edges) == 3
    for edge in result.edges:
        assert edge.relation_type == RelationType.FS
        assert edge.relationship_slack_days == pytest.approx(0.0)
    # Exactly one non-driving predecessor: Q → B.
    assert len(result.non_driving_predecessors) == 1
    ndp = result.non_driving_predecessors[0]
    assert ndp.predecessor_uid == 5
    assert ndp.successor_uid == 2
    assert ndp.slack_days > 0

    # Acumen-table renderer returns one row per node.
    rows = render_acumen_table(result)
    assert len(rows) == len(result.nodes)
    row_uids = {r["unique_id"] for r in rows}
    assert row_uids == {1, 2, 3, 4}
    # The B row carries the non-driving predecessor count.
    row_b = next(r for r in rows if r["unique_id"] == 2)
    assert row_b["non_driving_predecessor_count"] == 1

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

    result = trace_driving_path_cross_version(a, b, focus, cpm_a, cpm_b)

    assert isinstance(result, DrivingPathCrossVersionResult)
    assert result.period_a_result.focus_point_uid == 4
    assert result.period_b_result.focus_point_uid == 4
    # A predecessors (excluding focus): {1, 2, 3}.
    # B predecessors (excluding focus): {1, 10, 3}.
    assert result.added_predecessor_uids == {10}
    assert result.removed_predecessor_uids == {2}
    assert result.retained_predecessor_uids == {1, 3}

    # Mutation invariance.
    assert a.model_dump(mode="json") == a_before
    assert b.model_dump(mode="json") == b_before
    assert cpm_result_snapshot(cpm_a) == cpm_a_before
    assert cpm_result_snapshot(cpm_b) == cpm_b_before


# ----------------------------------------------------------------------
# UniqueID-only matching — rename-all regression
# ----------------------------------------------------------------------


def test_integration_rename_regression() -> None:
    a = _period_a()
    b_plain = _period_b()
    b_renamed = _period_b_renamed()

    cpm_a = compute_cpm(a)
    cpm_b_plain = compute_cpm(b_plain)
    cpm_b_renamed = compute_cpm(b_renamed)

    plain = trace_driving_path_cross_version(a, b_plain, 4, cpm_a, cpm_b_plain)
    renamed = trace_driving_path_cross_version(
        a, b_renamed, 4, cpm_a, cpm_b_renamed
    )

    assert plain.added_predecessor_uids == renamed.added_predecessor_uids
    assert plain.removed_predecessor_uids == renamed.removed_predecessor_uids
    assert plain.retained_predecessor_uids == renamed.retained_predecessor_uids
    # Period A node UIDs identical (same input).
    assert set(plain.period_a_result.nodes.keys()) == set(
        renamed.period_a_result.nodes.keys()
    )
    # Period B node UIDs match despite every name changing.
    assert set(plain.period_b_result.nodes.keys()) == set(
        renamed.period_b_result.nodes.keys()
    )
    # Names are captured independently per period.
    assert plain.period_b_result.nodes[1].name == "A"
    assert renamed.period_b_result.nodes[1].name == "Alpha"
    assert plain.period_b_result.nodes[10].name == "D"
    assert renamed.period_b_result.nodes[10].name == "Foxtrot"
