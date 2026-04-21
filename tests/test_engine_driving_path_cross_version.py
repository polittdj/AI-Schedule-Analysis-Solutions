"""Cross-version driving-path trace — Milestone 10 AC #4.

Exercises :func:`app.engine.driving_path.trace_driving_path_cross_version`
and enforces the Period A slack rule per ``driving-slack-and-paths §9``:
the added / removed / retained predecessor UID sets are framed from
Period A's perspective, and Period B slack is descriptive only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path_cross_version
from app.engine.driving_path_types import FocusPointAnchor
from app.engine.exceptions import DrivingPathError, FocusPointError
from app.models.calendar import Calendar
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _linear_chain(name: str) -> Schedule:
    """A → B → C → Finish milestone (FS zero-lag)."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Finish",
             duration_minutes=0, is_milestone=True),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    return Schedule(
        name=name, project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# Identical / added / removed / mixed cases
# ----------------------------------------------------------------------


def test_identical_schedules_retained_only() -> None:
    """Two byte-identical schedules: no added, no removed, all
    retained."""
    a = _linear_chain("period_a")
    b = _linear_chain("period_b")
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)

    assert result.focus_unique_id == 4
    assert result.added_predecessor_uids == frozenset()
    assert result.removed_predecessor_uids == frozenset()
    # Chain predecessors (excluding focus): 1, 2, 3.
    assert result.retained_predecessor_uids == frozenset({1, 2, 3})


def test_predecessor_added_in_b() -> None:
    """Period B inserts a new task D in front of C.

    Period A: A → B → C → Finish.
    Period B: A → B → D → C → Finish  (D is added, with UID 10).
    """
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=10, task_id=5, name="D", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Finish",
             duration_minutes=0, is_milestone=True),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=10),
        Relation(predecessor_unique_id=10, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    assert result.added_predecessor_uids == frozenset({10})
    assert result.removed_predecessor_uids == frozenset()
    assert result.retained_predecessor_uids == frozenset({1, 2, 3})


def test_predecessor_removed_in_b() -> None:
    """Period B drops task B from the chain.

    Period A: A → B → C → Finish.
    Period B: A → C → Finish.
    """
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Finish",
             duration_minutes=0, is_milestone=True),
    ]
    # In Period B, B is an orphaned task with no relations — and
    # A drives C directly.
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    assert result.added_predecessor_uids == frozenset()
    # B (UID 2) was on A's chain but is not on B's chain.
    assert result.removed_predecessor_uids == frozenset({2})
    assert result.retained_predecessor_uids == frozenset({1, 3})


def test_mixed_added_and_removed() -> None:
    """One predecessor added, one removed, the rest retained."""
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Finish",
             duration_minutes=0, is_milestone=True),
        Task(unique_id=10, task_id=5, name="D", duration_minutes=480),
    ]
    # B drops B from the chain (replaced by D between A and C).
    # A → D → C → Finish with B orphaned.
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=10),
        Relation(predecessor_unique_id=10, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)
    assert result.added_predecessor_uids == frozenset({10})
    assert result.removed_predecessor_uids == frozenset({2})
    assert result.retained_predecessor_uids == frozenset({1, 3})


# ----------------------------------------------------------------------
# Period A slack rule — §9 but-for semantics
# ----------------------------------------------------------------------


def test_period_a_slack_rule() -> None:
    """Construct a case where Period B slack would suggest a
    different but-for driver; verify the added / removed UID sets
    are computed against Period A's chain, not Period B's.

    Period A: X (2 WD) and Y (1 WD) both feed Focus via FS. X is
    the driver (longer duration = later EF); Y is non-driving with
    positive slack on its link to Focus.

    Period B: X's duration is reduced to 1 WD; now X and Y both
    finish together and both drive Focus. If we used Period B
    slack to frame the delta, we'd say "Y is now a driver" and
    count Y as an "added" predecessor. Under the Period A rule,
    Y was not on A's chain and is not on B's chain (the walk's
    tie-break picks the lowest UID, which is X), so Y remains
    in neither set — the delta correctly attributes "nothing
    changed structurally on the chain."

    The concrete assertion: X stays retained, the chain is the
    same, and added / removed are empty despite Period B's
    slack profile being objectively different.
    """
    # Period A: X (2 WD, UID 1) drives; Y (1 WD, UID 2) non-driving.
    a_tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Focus",
             duration_minutes=0, is_milestone=True),
    ]
    a_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    a = Schedule(
        name="period_a", project_start=ANCHOR, tasks=a_tasks,
        relations=a_rels, calendars=[_std_cal()],
    )

    # Period B: X shortened to 1 WD; X and Y both drive Focus.
    b_tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Focus",
             duration_minutes=0, is_milestone=True),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 3, cpm_a, cpm_b)

    # Period A chain: X → Focus.
    assert [n.unique_id for n in result.period_a_result.chain] == [1, 3]
    # Period B chain: tie-break picks lowest UID (X).
    assert [n.unique_id for n in result.period_b_result.chain] == [1, 3]
    # Deltas: both chains have the same predecessor set {X}.
    assert result.retained_predecessor_uids == frozenset({1})
    assert result.added_predecessor_uids == frozenset()
    assert result.removed_predecessor_uids == frozenset()


def test_period_a_slack_rule_detects_driver_substitution() -> None:
    """Period A driver X is removed by relation change in Period B.

    Period A: X (driver) → Focus; Y (non-driver) → Focus.
    Period B: The X → Focus link is deleted. Y is now the driver.

    Expected:
      - removed_predecessor_uids == {X_uid} (X was on A's chain)
      - added_predecessor_uids == {Y_uid} (Y is on B's chain)
      - retained_predecessor_uids == frozenset()
    """
    # Period A: X (UID 1) drives Focus; Y (UID 2) feeds Focus
    # non-driving (shorter duration).
    a_tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Focus",
             duration_minutes=0, is_milestone=True),
    ]
    a_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    a = Schedule(
        name="period_a", project_start=ANCHOR, tasks=a_tasks,
        relations=a_rels, calendars=[_std_cal()],
    )
    # Period B: X → Focus removed; Y drives.
    b_tasks = list(a_tasks)
    b_rels = [
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 3, cpm_a, cpm_b)

    assert [n.unique_id for n in result.period_a_result.chain] == [1, 3]
    assert [n.unique_id for n in result.period_b_result.chain] == [2, 3]
    assert result.removed_predecessor_uids == frozenset({1})
    assert result.added_predecessor_uids == frozenset({2})
    assert result.retained_predecessor_uids == frozenset()


# ----------------------------------------------------------------------
# UniqueID-only matching — rename regression
# ----------------------------------------------------------------------


def test_cross_version_ignores_name_changes() -> None:
    """Renaming every task in Period B does not change the deltas.

    UniqueID is the cross-version key per BUILD-PLAN §2.7 — name
    changes are captured on the chain nodes (for UI drill-down) but
    never used for matching.
    """
    a = _linear_chain("period_a")

    b_tasks = [
        Task(unique_id=1, task_id=1, name="Alpha", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="Bravo", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Charlie", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Delta",
             duration_minutes=0, is_milestone=True),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    result = trace_driving_path_cross_version(a, b, 4, cpm_a, cpm_b)

    # All UIDs retained despite every name changing.
    assert result.retained_predecessor_uids == frozenset({1, 2, 3})
    assert result.added_predecessor_uids == frozenset()
    assert result.removed_predecessor_uids == frozenset()
    # Names are captured on the chain nodes independently per
    # period for UI drill-down.
    assert [n.name for n in result.period_a_result.chain] == [
        "A", "B", "C", "Finish",
    ]
    assert [n.name for n in result.period_b_result.chain] == [
        "Alpha", "Bravo", "Charlie", "Delta",
    ]


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
    """PROJECT_FINISH resolves to different UIDs across the two
    schedules: the trace function raises DrivingPathError rather
    than silently comparing different chains."""
    a = _linear_chain("a")

    # Period B has a different finish milestone: add a new task 99
    # with no outgoing relations (a later finish date) so the
    # anchor resolves differently.
    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="OldFinish",
             duration_minutes=0, is_milestone=True,
             finish=datetime(2026, 5, 1, 16, 0, tzinfo=UTC)),
        Task(unique_id=99, task_id=5, name="NewFinish",
             duration_minutes=0, is_milestone=True,
             finish=datetime(2026, 6, 1, 16, 0, tzinfo=UTC)),
    ]
    b_rels = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=99),
    ]
    b = Schedule(
        name="period_b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
    cpm_a = compute_cpm(a)
    cpm_b = compute_cpm(b)

    with pytest.raises(DrivingPathError, match="different UIDs"):
        trace_driving_path_cross_version(
            a, b, FocusPointAnchor.PROJECT_FINISH, cpm_a, cpm_b,
        )


def test_cross_version_rejects_missing_focus_uid() -> None:
    """Integer focus UID that doesn't exist in one period raises."""
    a = _linear_chain("a")
    b_tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    b_rels = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    b = Schedule(
        name="b", project_start=ANCHOR, tasks=b_tasks,
        relations=b_rels, calendars=[_std_cal()],
    )
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
        a, b, FocusPointAnchor.PROJECT_FINISH, cpm_a, cpm_b,
    )

    assert a.model_dump(mode="json") == a_before
    assert b.model_dump(mode="json") == b_before
    assert cpm_result_snapshot(cpm_a) == cpm_a_before
    assert cpm_result_snapshot(cpm_b) == cpm_b_before
