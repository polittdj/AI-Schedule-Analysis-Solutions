"""SSI worked-example reconstruction — Milestone 10 AC #1.

Reshaped in Block 7 (2026-04-22) for the adjacency-map contract per
BUILD-PLAN AM8. Reconstructs the four-tier driving chain from the SSI
paper (``driving-slack-and-paths §2`` final paragraph / slide 22):

    Y → X → Predecessor 3 → Focus Point

with FS links, zero lag, and zero relationship slack on every link.
Under the adjacency-map contract the "chain" surfaces as four nodes
plus three edges; each edge has ``relationship_slack_days ≈ 0``.
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
from tests._utils import cpm_result_snapshot

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _ssi_four_tier_schedule() -> Schedule:
    tasks = [
        Task(unique_id=1, task_id=1, name="Y", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Predecessor 3",
            duration_minutes=480,
        ),
        Task(
            unique_id=4,
            task_id=4,
            name="Focus Point",
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
    return Schedule(
        name="ssi_four_tier",
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# AC #1 — four-tier SSI driving sub-graph
# ----------------------------------------------------------------------


def test_ssi_four_tier_chain() -> None:
    """SSI slide 22: Y → X → Predecessor 3 → Focus Point."""
    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)

    result = trace_driving_path(s, 4, cpm)

    # Adjacency map — four nodes, focus keyed at UID 4.
    assert set(result.nodes.keys()) == {1, 2, 3, 4}
    assert result.focus_point_uid == 4
    assert result.focus_point_name == "Focus Point"
    assert {result.nodes[uid].name for uid in (1, 2, 3, 4)} == {
        "Y",
        "X",
        "Predecessor 3",
        "Focus Point",
    }

    # Three FS edges, all zero relationship slack, all zero lag,
    # sorted by (successor_uid, predecessor_uid).
    assert len(result.edges) == 3
    assert [(e.predecessor_uid, e.successor_uid) for e in result.edges] == [
        (1, 2),
        (2, 3),
        (3, 4),
    ]
    for edge in result.edges:
        assert edge.relation_type == RelationType.FS
        assert edge.relationship_slack_days == pytest.approx(0.0)
        assert edge.lag_days == pytest.approx(0.0)

    # No non-driving predecessors on the clean chain.
    assert result.non_driving_predecessors == []


def test_ssi_four_tier_per_tier_driving_slack() -> None:
    """Per-tier DS = 0 on the clean chain (``§2`` final paragraph)."""
    from app.engine.paths import driving_slack_to_focus

    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)

    ds_map = driving_slack_to_focus(s, cpm, focus_uid=4)
    assert ds_map[1] == 0
    assert ds_map[2] == 0
    assert ds_map[3] == 0
    assert ds_map[4] == 0


def test_ssi_chain_is_critical_path() -> None:
    """Every task on the SSI chain is on the CPM critical path."""
    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)
    for uid in (1, 2, 3, 4):
        assert cpm.tasks[uid].on_critical_path is True


# ----------------------------------------------------------------------
# Multi-branch: non-driving predecessor lands on non_driving list
# ----------------------------------------------------------------------


def test_ssi_multi_branch_non_driving() -> None:
    """Q feeds X with positive slack; Q lands on non_driving_predecessors.

    Y is 2 WD; Q is 1 WD from the same anchor, so Q.EF is 1 WD earlier
    than Y.EF and the Q → X edge carries 1 day of positive slack. Y
    remains the sole driving predecessor of X.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="Y", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Predecessor 3",
            duration_minutes=480,
        ),
        Task(
            unique_id=4,
            task_id=4,
            name="Focus Point",
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
    s = Schedule(
        name="ssi_multi_branch",
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 4, cpm)

    # Sub-graph is unchanged — Q is not a driver and does not appear
    # in nodes.
    assert set(result.nodes.keys()) == {1, 2, 3, 4}
    assert len(result.edges) == 3

    # One non-driving predecessor: Q → X, slack = 1 day.
    assert len(result.non_driving_predecessors) == 1
    ndp = result.non_driving_predecessors[0]
    assert ndp.predecessor_uid == 5
    assert ndp.predecessor_name == "Q"
    assert ndp.successor_uid == 2
    assert ndp.successor_name == "X"
    assert ndp.relation_type == RelationType.FS
    assert ndp.slack_days == pytest.approx(1.0)


def test_ssi_mutation_invariance() -> None:
    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)
    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    trace_driving_path(s, 4, cpm)
    trace_driving_path(s, 3, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before
