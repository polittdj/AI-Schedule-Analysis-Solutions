"""True multi-branch driving-path scenarios (F4 fix).

Block 7.6 (2026-04-22). The three-session audit cycle found that
M10's test suite lacked a scenario where a **non-focus** task has
two-or-more zero-relationship-slack incoming edges. The AM7 tie-
break rule (withdrawn by AM8) masked this gap. These tests exercise
the AM8 "no path is dropped" behavior per
``driving-slack-and-paths §4`` / §5 verbatim.

Scenarios:

* ``test_true_multi_branch_two_zero_slack_predecessors`` — Z has two
  zero-slack predecessors X and Y; both retained on edges.
* ``test_true_multi_branch_three_zero_slack_predecessors`` — Z has
  three zero-slack predecessors; all three retained on edges.
* ``test_true_multi_branch_diamond`` — shared ancestor A reaches F
  via two driving paths but appears exactly once in nodes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

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


def _edge_ids(result) -> set[tuple[int, int]]:
    return {(e.predecessor_uid, e.successor_uid) for e in result.edges}


# ----------------------------------------------------------------------
# Two zero-slack incoming edges on a non-focus task
# ----------------------------------------------------------------------


def test_true_multi_branch_two_zero_slack_predecessors() -> None:
    """X → Z and Y → Z, both FS zero-slack; Z → F (FS zero-slack).

    Topology:
        X ──FS,lag=0──┐
                      ▼
                      Z ──FS,lag=0──▶ F
                      ▲
        Y ──FS,lag=0──┘

    Under AM8 both X→Z and Y→Z appear on result.edges; neither
    lands on non_driving_predecessors.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Z", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="F",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=3,
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
    ]
    s = _sched(tasks, relations, name="two_branch")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 4, cpm)

    # nodes: X, Y, Z, F.
    assert set(result.nodes.keys()) == {1, 2, 3, 4}
    # edges: X→Z, Y→Z, Z→F — exactly three, both X→Z and Y→Z present.
    assert _edge_ids(result) == {(1, 3), (2, 3), (3, 4)}
    assert len(result.edges) == 3
    # F3 invariant: neither X nor Y parked on non-driving with slack=0.
    assert result.non_driving_predecessors == []
    # Deterministic edge ordering per (successor_uid, predecessor_uid).
    assert [(e.predecessor_uid, e.successor_uid) for e in result.edges] == [
        (1, 3),
        (2, 3),
        (3, 4),
    ]
    # Every edge relationship_slack_days ≈ 0.
    for edge in result.edges:
        assert edge.relationship_slack_days == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Three zero-slack incoming edges on a non-focus task
# ----------------------------------------------------------------------


def test_true_multi_branch_three_zero_slack_predecessors() -> None:
    """X, Y, W all drive Z; Z drives F. Four edges total."""
    tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="W", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Z", duration_minutes=480),
        Task(
            unique_id=5,
            task_id=5,
            name="F",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=2,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=3,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=4,
            successor_unique_id=5,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="three_branch")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 5, cpm)

    assert set(result.nodes.keys()) == {1, 2, 3, 4, 5}
    assert _edge_ids(result) == {(1, 4), (2, 4), (3, 4), (4, 5)}
    assert len(result.edges) == 4
    assert result.non_driving_predecessors == []


# ----------------------------------------------------------------------
# Diamond: shared ancestor A via two driving paths
# ----------------------------------------------------------------------


def test_true_multi_branch_diamond() -> None:
    """A → X → Z, A → Y → Z, Z → F; A appears in nodes exactly once.

    Topology (all FS, all zero lag, all zero-slack under CPM):
              ┌── X ──┐
              │       ▼
        A ────┤       Z ──▶ F
              │       ▲
              └── Y ──┘

    The backward walk from F reaches A via X and via Y. The
    adjacency-map shape deduplicates — A has a single entry in
    result.nodes — while every zero-slack edge still appears on
    result.edges.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Y", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Z", duration_minutes=480),
        Task(
            unique_id=5,
            task_id=5,
            name="F",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=3,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=2,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=3,
            successor_unique_id=4,
            relation_type=RelationType.FS,
        ),
        Relation(
            predecessor_unique_id=4,
            successor_unique_id=5,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="diamond")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 5, cpm)

    # A (UID 1) appears exactly once despite being reachable via two
    # driving paths.
    assert list(result.nodes.keys()).count(1) == 1
    assert set(result.nodes.keys()) == {1, 2, 3, 4, 5}
    # Five edges: A→X, A→Y, X→Z, Y→Z, Z→F.
    assert _edge_ids(result) == {(1, 2), (1, 3), (2, 4), (3, 4), (4, 5)}
    assert len(result.edges) == 5
    assert result.non_driving_predecessors == []
