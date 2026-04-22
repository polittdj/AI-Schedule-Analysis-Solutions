"""Cross-version driving-path trace — Milestone 10 AC #4.

Reshaped in Block 7 (2026-04-22) for the adjacency-map contract per
BUILD-PLAN AM8. Exercises
:func:`app.engine.driving_path.trace_driving_path_cross_version` and
enforces the Period A slack rule per ``driving-slack-and-paths §9``:
added / removed / retained UID and edge sets are framed from Period
A's perspective, and Period B slack is descriptive only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path_cross_version
from app.engine.driving_path_types import FocusPointAnchor
from app.engine.exceptions import DrivingPathError, FocusPointError
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _sched(
    tasks: list[Task], relations: list[Relation], *, name: str
) -> Schedule:
    return Schedule(
        name=name,
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def _linear_chain(name: str) -> Schedule:
    """A → B → C → Finish milestone (FS zero-lag)."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    return _sched(tasks, relations, name=name)


# ----------------------------------------------------------------------
# Identical / added / removed / mixed cases
# ----------------------------------------------------------------------


def test_identical_schedules_retained_only() -> None:
    a = _linear_chain("period_a")
    b = _linear_chain("period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)

    assert result.period_a_result.focus_point_uid == 4
    assert result.period_b_result.focus_point_uid == 4
    assert result.added_predecessor_uids == set()
    assert result.removed_predecessor_uids == set()
    assert result.retained_predecessor_uids == {1, 2, 3}
    # Edges are identical — three retained, zero added, zero removed.
    assert len(result.retained_edges) == 3
    assert result.added_edges == []
    assert result.removed_edges == []


def test_predecessor_added_in_b() -> None:
    """Period B inserts D (UID 10) between B and C."""
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=10, task_id=5, name="D", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=10),
        Relation(predecessor_unique_id=10, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    assert result.added_predecessor_uids == {10}
    assert result.removed_predecessor_uids == set()
    assert result.retained_predecessor_uids == {1, 2, 3}
    # Edge B→C (2→3) was removed; edges B→D (2→10) and D→C (10→3)
    # were added; edges A→B (1→2) and C→Finish (3→4) are retained.
    added_ids = {
        (e.predecessor_uid, e.successor_uid) for e in result.added_edges
    }
    removed_ids = {
        (e.predecessor_uid, e.successor_uid) for e in result.removed_edges
    }
    retained_ids = {
        (e.predecessor_uid, e.successor_uid) for e in result.retained_edges
    }
    assert added_ids == {(2, 10), (10, 3)}
    assert removed_ids == {(2, 3)}
    assert retained_ids == {(1, 2), (3, 4)}


def test_predecessor_removed_in_b() -> None:
    """Period B drops task B from the driving sub-graph."""
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    assert result.added_predecessor_uids == set()
    assert result.removed_predecessor_uids == {2}
    assert result.retained_predecessor_uids == {1, 3}


def test_mixed_added_and_removed() -> None:
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(unique_id=10, task_id=5, name="D", duration_minutes=480),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=10),
        Relation(predecessor_unique_id=10, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    assert result.added_predecessor_uids == {10}
    assert result.removed_predecessor_uids == {2}
    assert result.retained_predecessor_uids == {1, 3}


# ----------------------------------------------------------------------
# Period A slack rule — §9 but-for semantics
# ----------------------------------------------------------------------


def test_period_a_slack_rule_frames_delta_from_a_perspective() -> None:
    """Period A drives through X only; Period B drives through X + Y.

    Period A: X (2 WD) drives Focus; Y (1 WD) has positive slack
    (non-driving). A's sub-graph is {X, Focus}.
    Period B: X shortened to 1 WD. X and Y both drive Focus. B's
    sub-graph is {X, Y, Focus}.

    Framed from Period A's perspective (§9): Y was added to the
    driving sub-graph. The new Block 7.2 walk retains BOTH X and Y
    on Period B's edges (no tie-break drop), so Y correctly surfaces
    as added. This is the corrected F1/F4 behavior — under the AM7
    tie-break Y would have been suppressed in Period B and the
    delta would have been empty, which hid the forensic signal.
    """
    a_tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Focus",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    a_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    a = _sched(a_tasks, a_rels, name="period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Focus",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 3, cpm_a, cpm_b)

    # Period A sub-graph: X drives Focus; Y is non-driving.
    assert set(result.period_a_result.nodes.keys()) == {1, 3}
    assert len(result.period_a_result.non_driving_predecessors) == 1
    # Period B sub-graph: X and Y both drive Focus — per §4, both
    # retained.
    assert set(result.period_b_result.nodes.keys()) == {1, 2, 3}

    # Deltas framed from A's perspective: Y is added.
    assert result.retained_predecessor_uids == {1}
    assert result.added_predecessor_uids == {2}
    assert result.removed_predecessor_uids == set()

    # Edge deltas: X→Focus retained; Y→Focus added (was non-driving
    # in A, now driving in B).
    retained_edge_ids = {
        (e.predecessor_uid, e.successor_uid) for e in result.retained_edges
    }
    added_edge_ids = {
        (e.predecessor_uid, e.successor_uid) for e in result.added_edges
    }
    assert retained_edge_ids == {(1, 3)}
    assert added_edge_ids == {(2, 3)}
    assert result.removed_edges == []


def test_period_a_slack_rule_detects_driver_substitution() -> None:
    """Period A: X drives; Period B: X → Focus removed, Y drives."""
    a_tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Focus",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    a_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    a = _sched(a_tasks, a_rels, name="period_a")

    b_tasks = list(a_tasks)
    b_rels = [Relation(predecessor_unique_id=2, successor_unique_id=3)]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 3, cpm_a, cpm_b)

    assert set(result.period_a_result.nodes.keys()) == {1, 3}
    assert set(result.period_b_result.nodes.keys()) == {2, 3}
    assert result.removed_predecessor_uids == {1}
    assert result.added_predecessor_uids == {2}
    assert result.retained_predecessor_uids == set()


# ----------------------------------------------------------------------
# Edge-identity diffs consider relation_type
# ----------------------------------------------------------------------


def test_edge_identity_considers_relation_type() -> None:
    """Same UID pair with a changed relation_type is added+removed."""
    a_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(
            unique_id=2,
            task_id=2,
            name="Focus",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    a_rels = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        )
    ]
    b_tasks = list(a_tasks)
    b_rels = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FF,
        )
    ]
    a = _sched(a_tasks, a_rels, name="period_a")
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 2, cpm_a, cpm_b)

    # Same UID pair is in both sub-graphs — so UID-level retained
    # includes 1.
    assert result.retained_predecessor_uids == {1}
    # But the edge identity (which includes relation_type) differs —
    # FS is removed, FF is added.
    assert len(result.removed_edges) == 1
    assert result.removed_edges[0].relation_type == RelationType.FS
    assert len(result.added_edges) == 1
    assert result.added_edges[0].relation_type == RelationType.FF


# ----------------------------------------------------------------------
# UniqueID-only matching — rename regression
# ----------------------------------------------------------------------


def test_cross_version_ignores_name_changes() -> None:
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="Alpha", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="Bravo", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Charlie", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="Delta",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)

    assert result.retained_predecessor_uids == {1, 2, 3}
    assert result.added_predecessor_uids == set()
    assert result.removed_predecessor_uids == set()
    # Names are captured per-period on the node records.
    assert result.period_a_result.nodes[1].name == "A"
    assert result.period_b_result.nodes[1].name == "Alpha"
    assert result.period_a_result.nodes[4].name == "Finish"
    assert result.period_b_result.nodes[4].name == "Delta"


# ----------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------


def test_cross_version_rejects_none_cpm_result() -> None:
    a = _linear_chain("a")
    b = _linear_chain("b")
    cpm = compute_cpm(a)
    with pytest.raises(DrivingPathError, match="non-None"):
        trace_driving_path_cross_version(a, b, 4, cpm, None)  # type: ignore[arg-type]
    with pytest.raises(DrivingPathError, match="non-None"):
        trace_driving_path_cross_version(a, b, 4, None, cpm)  # type: ignore[arg-type]


def test_cross_version_rejects_anchor_divergence() -> None:
    a = _linear_chain("a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(
            unique_id=4,
            task_id=4,
            name="OldFinish",
            duration_minutes=0,
            is_milestone=True,
            finish=datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
        ),
        Task(
            unique_id=99,
            task_id=5,
            name="NewFinish",
            duration_minutes=0,
            is_milestone=True,
            finish=datetime(2026, 6, 1, 16, 0, tzinfo=UTC),
        ),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=99),
    ]
    b = _sched(b_tasks, b_rels, name="period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    with pytest.raises(DrivingPathError, match="different UIDs"):
        trace_driving_path_cross_version(
            a, b, FocusPointAnchor.PROJECT_FINISH, cpm_a, cpm_b
        )


def test_cross_version_rejects_missing_focus_uid() -> None:
    a = _linear_chain("a")
    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    b_rels = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    b = _sched(b_tasks, b_rels, name="b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)
    with pytest.raises(FocusPointError):
        trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)


# ----------------------------------------------------------------------
# Mutation-invariance
# ----------------------------------------------------------------------


def test_cross_version_does_not_mutate_schedules_or_cpm_results() -> None:
    a = _linear_chain("a")
    b = _linear_chain("b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    a_before = a.model_dump(mode="json")
    b_before = b.model_dump(mode="json")
    cpm_a_before = cpm_result_snapshot(cpm_a)
    cpm_b_before = cpm_result_snapshot(cpm_b)

    trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    trace_driving_path_cross_version(
        a, b, FocusPointAnchor.PROJECT_FINISH, cpm_a, cpm_b
    )

    assert a.model_dump(mode="json") == a_before
    assert b.model_dump(mode="json") == b_before
    assert cpm_result_snapshot(cpm_a) == cpm_a_before
    assert cpm_result_snapshot(cpm_b) == cpm_b_before
