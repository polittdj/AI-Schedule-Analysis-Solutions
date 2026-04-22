"""Unit tests for :func:`app.engine.driving_path.trace_driving_path`.

Reshaped in Block 7 (2026-04-22) for the adjacency-map contract per
BUILD-PLAN AM8. The chain + parallel-links contract is gone; assertions
operate on ``result.nodes`` (dict keyed by UID),
``result.edges`` (list of :class:`DrivingPathEdge`), and
``result.non_driving_predecessors``.

SSI-anchored worked-example tests live in
``tests/test_engine_driving_path_ssi_example.py``; true multi-branch
scenarios live in
``tests/test_engine_driving_path_true_multi_branch.py``; this module
covers the trace function's behavior on general topologies — linear
chains, branching, zero-predecessor focus, all four relationship
types, lags and leads, error paths, and mutation-invariance.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path
from app.engine.driving_path_types import FocusPointAnchor
from app.engine.exceptions import DrivingPathError, FocusPointError
from app.models.calendar import Calendar
from app.models.enums import ConstraintType, RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _sched(tasks: list[Task], relations: list[Relation], *, name: str = "s") -> Schedule:
    return Schedule(
        name=name,
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# Simple linear chains
# ----------------------------------------------------------------------


def test_linear_fs_chain_two_tasks() -> None:
    """A → B (FS, zero lag). Trace from B: nodes {1, 2}, one edge 1→2."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="linear2")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert set(result.nodes.keys()) == {1, 2}
    assert result.nodes[1].name == "A"
    assert result.nodes[2].name == "B"
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.predecessor_uid == 1
    assert edge.successor_uid == 2
    assert edge.relation_type == RelationType.FS
    assert edge.relationship_slack_days == pytest.approx(0.0)
    assert result.non_driving_predecessors == []


def test_linear_fs_chain_three_tasks() -> None:
    """A → B → C. Trace from C: nodes {1, 2, 3}, two edges."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = _sched(tasks, relations, name="linear3")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    assert set(result.nodes.keys()) == {1, 2, 3}
    assert len(result.edges) == 2
    for edge in result.edges:
        assert edge.relationship_slack_days == pytest.approx(0.0)
    # Deterministic ordering: sorted by (successor_uid, predecessor_uid).
    assert [(e.predecessor_uid, e.successor_uid) for e in result.edges] == [
        (1, 2),
        (2, 3),
    ]
    assert result.non_driving_predecessors == []


def test_zero_predecessors_terminates_immediately() -> None:
    """Focus task with no incoming relations: single-node sub-graph."""
    tasks = [
        Task(unique_id=1, task_id=1, name="Alone", duration_minutes=480),
    ]
    s = _sched(tasks, [], name="alone")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 1, cpm)
    assert set(result.nodes.keys()) == {1}
    assert result.edges == []
    assert result.non_driving_predecessors == []


# ----------------------------------------------------------------------
# Branching: driving vs non-driving predecessors
# ----------------------------------------------------------------------


def test_branching_non_driving_predecessor() -> None:
    """Focus has two predecessors — one driving, one non-driving.

    X (2 WD) drives Focus; Y (1 WD) has positive slack on the Y→Focus
    edge so Y lands on non_driving_predecessors.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Focus", duration_minutes=480),
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
    ]
    s = _sched(tasks, relations, name="branch")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    # X drives Focus; Y is in nodes only if we reached it — Y does
    # not drive Focus, so nodes = {1, 3}.
    assert set(result.nodes.keys()) == {1, 3}
    assert len(result.edges) == 1
    assert result.edges[0].predecessor_uid == 1
    assert result.edges[0].successor_uid == 3
    assert result.edges[0].relationship_slack_days == pytest.approx(0.0)
    assert len(result.non_driving_predecessors) == 1
    ndp = result.non_driving_predecessors[0]
    assert ndp.predecessor_uid == 2
    assert ndp.predecessor_name == "Y"
    assert ndp.successor_uid == 3
    assert ndp.successor_name == "Focus"
    # Y finishes 1 WD before X — slack = 1 day on 8h/day calendar.
    assert ndp.slack_days == pytest.approx(1.0)


def test_multi_driver_walk_retains_every_zero_slack_edge() -> None:
    """Two drivers with equal zero slack: BOTH retained per §4/§5.

    Previously M10 used a lowest-UID tie-break (AM7) and parked the
    alternate on non_driving_predecessors with slack=0. AM8 withdraws
    that rule — both drivers appear on edges.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=960),
        Task(unique_id=3, task_id=3, name="Focus", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = _sched(tasks, relations, name="parallel_drivers")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    assert set(result.nodes.keys()) == {1, 2, 3}
    assert len(result.edges) == 2
    edge_pairs = {(e.predecessor_uid, e.successor_uid) for e in result.edges}
    assert edge_pairs == {(1, 3), (2, 3)}
    # F3: the former escape hatch (slack=0 on non_driving) is now a
    # structural impossibility; no alternate is parked here.
    assert result.non_driving_predecessors == []


# ----------------------------------------------------------------------
# All four relation types traversable on zero-slack edges
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_type",
    [RelationType.FS, RelationType.SS, RelationType.FF],
)
def test_fs_ss_ff_traversable_on_zero_slack(rel_type: RelationType) -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=rel_type,
        ),
    ]
    s = _sched(tasks, relations, name=f"rel_{rel_type.name}")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert set(result.nodes.keys()) == {1, 2}
    assert len(result.edges) == 1
    assert result.edges[0].relation_type == rel_type
    assert result.edges[0].relationship_slack_days == pytest.approx(0.0)


def test_sf_relation_traversable_on_zero_slack() -> None:
    """SF (Start-to-Finish) zero-slack edge.

    Structurally unusual — successor's finish is constrained by
    predecessor's start. Simulate via a SNET constraint on the
    predecessor.
    """
    snet_date = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="A",
            duration_minutes=480,
            constraint_type=ConstraintType.START_NO_EARLIER_THAN,
            constraint_date=snet_date,
        ),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.SF,
        ),
    ]
    s = _sched(tasks, relations, name="sf")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert set(result.nodes.keys()) == {1, 2}
    assert len(result.edges) == 1
    assert result.edges[0].relation_type == RelationType.SF
    assert result.edges[0].relationship_slack_days == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Non-zero lag with zero relationship slack
# ----------------------------------------------------------------------


def test_positive_lag_zero_slack_is_traversable() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
            lag_minutes=480,
        ),
    ]
    s = _sched(tasks, relations, name="lag")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert set(result.nodes.keys()) == {1, 2}
    assert result.edges[0].lag_days == pytest.approx(1.0)
    assert result.edges[0].relationship_slack_days == pytest.approx(0.0)


def test_negative_lag_lead_zero_slack_is_traversable() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
            lag_minutes=-480,
        ),
    ]
    s = _sched(tasks, relations, name="lead")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert set(result.nodes.keys()) == {1, 2}
    assert result.edges[0].lag_days == pytest.approx(-1.0)
    assert result.edges[0].relationship_slack_days == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------


def test_cpm_result_none_raises_driving_path_error() -> None:
    tasks = [Task(unique_id=1, task_id=1, name="A", duration_minutes=480)]
    s = _sched(tasks, [], name="s")
    with pytest.raises(DrivingPathError, match="non-None cpm_result"):
        trace_driving_path(s, 1, cpm_result=None)


def test_invalid_focus_uid_raises_focus_point_error() -> None:
    tasks = [Task(unique_id=1, task_id=1, name="A", duration_minutes=480)]
    s = _sched(tasks, [], name="s")
    cpm = compute_cpm(s)
    with pytest.raises(FocusPointError):
        trace_driving_path(s, 999, cpm)


def test_project_finish_anchor_works() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = _sched(tasks, relations, name="finish_anchor")
    cpm = compute_cpm(s)
    by_uid = trace_driving_path(s, 3, cpm)
    by_anchor = trace_driving_path(s, FocusPointAnchor.PROJECT_FINISH, cpm)
    assert set(by_uid.nodes.keys()) == set(by_anchor.nodes.keys())
    assert by_uid.focus_point_uid == by_anchor.focus_point_uid == 3


def test_trace_with_int_uid() -> None:
    tasks = [
        Task(unique_id=10, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=20, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=30, task_id=3, name="Interim_Target", duration_minutes=480),
        Task(unique_id=40, task_id=4, name="Beyond", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=10, successor_unique_id=20),
        Relation(predecessor_unique_id=20, successor_unique_id=30),
        Relation(predecessor_unique_id=30, successor_unique_id=40),
    ]
    s = _sched(tasks, relations, name="interim")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 30, cpm)
    assert set(result.nodes.keys()) == {10, 20, 30}
    assert result.focus_point_uid == 30


# ----------------------------------------------------------------------
# Calendar fallback and cycle-edge handling
# ----------------------------------------------------------------------


def test_trace_with_default_calendar_name_mismatch_uses_first_calendar() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    s = Schedule(
        name="mismatch_cal",
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        default_calendar_name="NonExistent",
        calendars=[Calendar(name="Alt")],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert set(result.nodes.keys()) == {1, 2}


def test_trace_synthesises_calendar_when_schedule_has_none() -> None:
    """Empty schedule.calendars: helper synthesises a default Standard.

    Defensive branch — parser-generated schedules always carry at
    least one calendar, but the helper tolerates an empty list so
    unit-test fixtures don't have to supply one. CPM is called
    directly with the synthesised calendar path; the driving-path
    walk on a single-node focus schedule exercises line 87.
    """
    tasks = [Task(unique_id=1, task_id=1, name="A", duration_minutes=480)]
    s = Schedule(
        name="no_cals",
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=[],
        default_calendar_name="",  # falsy → helper falls through to "Standard"
        calendars=[Calendar(name="Standard")],
    )
    cpm = compute_cpm(s)
    # Now strip calendars from a copy (Pydantic model_copy) so the
    # tracer sees an empty list but CPM ran against a valid calendar.
    s_no_cal = s.model_copy(update={"calendars": []})
    result = trace_driving_path(s_no_cal, 1, cpm)
    assert set(result.nodes.keys()) == {1}


def test_trace_on_schedule_with_cycle_skips_cyclic_edges() -> None:
    """Cycle participants are skipped by CPM; walk stops cleanly."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="D", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Focus",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    s = _sched(tasks, relations, name="cyclic")
    cpm = compute_cpm(s)
    assert 1 in cpm.cycles_detected
    assert 2 in cpm.cycles_detected
    result = trace_driving_path(s, 4, cpm)
    # D drives Focus; A is cyclic so edge A→D is non-traversable.
    # Walk terminates at D — nodes = {3, 4}.
    assert set(result.nodes.keys()) == {3, 4}
    assert result.non_driving_predecessors == []


# ----------------------------------------------------------------------
# Mutation-invariance
# ----------------------------------------------------------------------


def test_trace_does_not_mutate_schedule_or_cpm_result() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = _sched(tasks, relations, name="mut")
    cpm = compute_cpm(s)
    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    trace_driving_path(s, 3, cpm)
    trace_driving_path(s, 2, cpm)
    trace_driving_path(s, FocusPointAnchor.PROJECT_FINISH, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before


# ----------------------------------------------------------------------
# Node-level field coverage
# ----------------------------------------------------------------------


def test_nodes_carry_cpm_dates_and_calendar_factor() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    s = _sched(tasks, relations, name="nodes")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    node = result.nodes[1]
    assert node.early_start is not None
    assert node.early_finish is not None
    assert node.late_start is not None
    assert node.late_finish is not None
    # Project default calendar is 8h/day in our fixture.
    assert node.calendar_hours_per_day == 8.0
    # A is on the critical path; total_float_days == 0.
    assert node.total_float_days == pytest.approx(0.0)


def test_task_level_calendar_override_surfaces_on_node() -> None:
    """Task.calendar_hours_per_day overrides schedule project factor."""
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="A",
            duration_minutes=600,
            calendar_hours_per_day=10.0,
        ),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    s = _sched(tasks, relations, name="override")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert result.nodes[1].calendar_hours_per_day == 10.0
    assert result.nodes[2].calendar_hours_per_day == 8.0
    # Edge calendar factor comes from the predecessor — 10h/day.
    assert result.edges[0].calendar_hours_per_day == 10.0
