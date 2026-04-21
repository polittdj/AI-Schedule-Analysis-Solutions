"""Unit tests for :func:`app.engine.driving_path.trace_driving_path`.

SSI-anchored worked-example tests live in
``tests/test_engine_driving_path_ssi_example.py``; this module covers
the trace function's behavior on general topologies — linear chains,
branching, zero-predecessor focus, all four relationship types, lags
and leads, error paths, and mutation-invariance.
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


# ----------------------------------------------------------------------
# Simple linear chains
# ----------------------------------------------------------------------


def test_linear_fs_chain_two_tasks() -> None:
    """A → B (FS, zero lag). Trace from B returns [A, B]."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS),
    ]
    s = Schedule(
        name="linear2", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert [n.unique_id for n in result.chain] == [1, 2]
    assert [n.name for n in result.chain] == ["A", "B"]
    assert len(result.links) == 1
    link = result.links[0]
    assert link.predecessor_unique_id == 1
    assert link.successor_unique_id == 2
    assert link.relation_type == RelationType.FS
    assert link.relationship_slack_minutes == 0
    assert result.non_driving_predecessors == ()


def test_linear_fs_chain_three_tasks() -> None:
    """A → B → C. Trace from C returns [A, B, C]."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = Schedule(
        name="linear3", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    assert [n.unique_id for n in result.chain] == [1, 2, 3]
    assert len(result.links) == 2
    for link in result.links:
        assert link.relationship_slack_minutes == 0
    assert result.non_driving_predecessors == ()


def test_zero_predecessors_terminates_immediately() -> None:
    """Focus task with no incoming relations: chain = [focus]."""
    tasks = [
        Task(unique_id=1, task_id=1, name="Alone", duration_minutes=480),
    ]
    s = Schedule(
        name="alone", project_start=ANCHOR, tasks=tasks,
        relations=[], calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 1, cpm)
    assert [n.unique_id for n in result.chain] == [1]
    assert result.links == ()
    assert result.non_driving_predecessors == ()


# ----------------------------------------------------------------------
# Branching: driving vs non-driving predecessors
# ----------------------------------------------------------------------


def test_branching_non_driving_predecessor() -> None:
    """Focus task has two predecessors: X (driving) and Y (non-driving).

    Topology:
        X (1 WD) ─FS─┐
                      ├─→ Focus (A)
        Y (1 WD) ─FS─┘   with Y's finish early enough that X drives.

    Built as:
        pre_X → X (duration 480) → Focus
                     (X is on the critical path)
        Y (duration 480) → Focus, but Y starts later so its EF lags.
    We make Y non-driving by putting a predecessor in front of it
    that causes Y's EF to be much earlier than X's, so the slack on
    the Y → Focus link is > 0.

    Simpler: place X and Y as independent sources; Y runs shorter
    so its finish is earlier than X's, leaving positive slack on
    the Y → Focus edge.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="X", duration_minutes=960),  # 2 WD
        Task(unique_id=2, task_id=2, name="Y", duration_minutes=480),  # 1 WD
        Task(unique_id=3, task_id=3, name="Focus", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=3,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.FS),
    ]
    s = Schedule(
        name="branch", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    # X (2 WD) finishes later than Y (1 WD), so X drives Focus.
    assert [n.unique_id for n in result.chain] == [1, 3]
    assert len(result.non_driving_predecessors) == 1
    ndp = result.non_driving_predecessors[0]
    assert ndp.predecessor_unique_id == 2
    assert ndp.predecessor_name == "Y"
    assert ndp.successor_unique_id == 3
    assert ndp.successor_name == "Focus"
    assert ndp.relationship_slack_minutes > 0
    # Y is 1 WD (480 min) earlier than X, so link slack == 480 min.
    assert ndp.relationship_slack_minutes == 480


def test_multi_driver_tie_break_lowest_uid_wins() -> None:
    """Two drivers with equal zero slack: lowest UID is followed.

    Topology:
        X (UID 1) ─FS─┐
                       ├─→ Focus (UID 3)
        Y (UID 2) ─FS─┘
    X and Y both run 2 WD from the same start, so both finish
    together and both drive Focus. The walk follows UID 1 and
    records UID 2 on non_driving_predecessors with slack = 0.
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
    s = Schedule(
        name="tie_drivers", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    assert [n.unique_id for n in result.chain] == [1, 3]
    # Alternate driver lands on non_driving with slack = 0.
    assert len(result.non_driving_predecessors) == 1
    alt = result.non_driving_predecessors[0]
    assert alt.predecessor_unique_id == 2
    assert alt.relationship_slack_minutes == 0


# ----------------------------------------------------------------------
# All four relation types traversable on zero-slack edges
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_type",
    [RelationType.FS, RelationType.SS, RelationType.FF],
)
def test_fs_ss_ff_traversable_on_zero_slack(rel_type: RelationType) -> None:
    """FS / SS / FF produce zero slack on a two-task schedule with no
    competing constraints; the predecessor drives the successor
    directly."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1, successor_unique_id=2,
            relation_type=rel_type,
        ),
    ]
    s = Schedule(
        name=f"rel_{rel_type.name}", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert len(result.chain) == 2
    assert result.links[0].relation_type == rel_type
    assert result.links[0].relationship_slack_minutes == 0


def test_sf_relation_traversable_on_zero_slack() -> None:
    """SF (Start-to-Finish): DS = EF(succ) - ES(pred) - lag.

    SF is structurally unusual — the successor's finish is
    constrained by the predecessor's start. For a zero-slack edge
    the successor must be scheduled to finish exactly when the
    predecessor starts, which requires the predecessor to have a
    later start than the successor's own anchor would allow. We
    simulate this by giving the predecessor a SNET constraint that
    pushes its start after the successor's natural finish.
    """
    snet_date = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)  # Wed 8am
    tasks = [
        Task(
            unique_id=1, task_id=1, name="A", duration_minutes=480,
            constraint_type=ConstraintType.START_NO_EARLIER_THAN,
            constraint_date=snet_date,
        ),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1, successor_unique_id=2,
            relation_type=RelationType.SF,
        ),
    ]
    s = Schedule(
        name="sf", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    # SF: succ.EF driven by pred.ES. With pred SNET Wed 8am and
    # succ 1 WD duration, succ.EF == Wed 8am, succ.ES == Tue 8am.
    # DS(SF) = EF(succ) - ES(pred) = Wed 8am - Wed 8am = 0.
    assert len(result.chain) == 2
    assert result.links[0].relation_type == RelationType.SF
    assert result.links[0].relationship_slack_minutes == 0


# ----------------------------------------------------------------------
# Non-zero lag with zero relationship slack
# ----------------------------------------------------------------------


def test_positive_lag_zero_slack_is_traversable() -> None:
    """A → B (FS, lag = 1 WD). B is scheduled 1 WD after A ends.

    The forward pass accounts for the lag, so the relationship
    slack equals zero and the edge is a driver.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1, successor_unique_id=2,
            relation_type=RelationType.FS, lag_minutes=480,
        ),
    ]
    s = Schedule(
        name="lag", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert [n.unique_id for n in result.chain] == [1, 2]
    assert result.links[0].lag_minutes == 480
    assert result.links[0].relationship_slack_minutes == 0


def test_negative_lag_lead_zero_slack_is_traversable() -> None:
    """A → B (FS, lead = -1 WD)."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1, successor_unique_id=2,
            relation_type=RelationType.FS, lag_minutes=-480,
        ),
    ]
    s = Schedule(
        name="lead", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert [n.unique_id for n in result.chain] == [1, 2]
    assert result.links[0].lag_minutes == -480
    assert result.links[0].relationship_slack_minutes == 0


# ----------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------


def test_cpm_result_none_raises_driving_path_error() -> None:
    tasks = [Task(unique_id=1, task_id=1, name="A", duration_minutes=480)]
    s = Schedule(name="s", project_start=ANCHOR, tasks=tasks,
                 calendars=[_std_cal()])
    with pytest.raises(DrivingPathError, match="non-None cpm_result"):
        trace_driving_path(s, 1, cpm_result=None)


def test_invalid_focus_uid_raises_focus_point_error() -> None:
    tasks = [Task(unique_id=1, task_id=1, name="A", duration_minutes=480)]
    s = Schedule(name="s", project_start=ANCHOR, tasks=tasks,
                 calendars=[_std_cal()])
    cpm = compute_cpm(s)
    with pytest.raises(FocusPointError):
        trace_driving_path(s, 999, cpm)


def test_project_finish_anchor_works() -> None:
    """Integer UID and FocusPointAnchor.PROJECT_FINISH both work."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Finish",
             duration_minutes=0, is_milestone=True),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = Schedule(
        name="finish_anchor", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    by_uid = trace_driving_path(s, 3, cpm)
    by_anchor = trace_driving_path(s, FocusPointAnchor.PROJECT_FINISH, cpm)
    assert [n.unique_id for n in by_uid.chain] == [
        n.unique_id for n in by_anchor.chain
    ]


def test_trace_with_int_uid() -> None:
    """Explicitly exercise the operator-configurable integer UID path."""
    tasks = [
        Task(unique_id=10, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=20, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=30, task_id=3, name="Interim_Target",
             duration_minutes=480),
        Task(unique_id=40, task_id=4, name="Beyond", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=10, successor_unique_id=20),
        Relation(predecessor_unique_id=20, successor_unique_id=30),
        Relation(predecessor_unique_id=30, successor_unique_id=40),
    ]
    s = Schedule(
        name="interim", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    # Focus on an interim milestone, not the project finish.
    result = trace_driving_path(s, 30, cpm)
    assert [n.unique_id for n in result.chain] == [10, 20, 30]
    assert result.focus_unique_id == 30


# ----------------------------------------------------------------------
# Mutation-invariance
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# Calendar fallback and cycle-edge handling
# ----------------------------------------------------------------------


def test_trace_with_default_calendar_name_mismatch_uses_first_calendar() -> None:
    """Default calendar name pointing to a non-existent calendar falls
    back to the first calendar in ``schedule.calendars``.

    Exercises the fallback branch in the private
    ``_schedule_calendar`` helper.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    s = Schedule(
        name="mismatch_cal", project_start=ANCHOR, tasks=tasks,
        relations=relations,
        default_calendar_name="NonExistent",
        calendars=[Calendar(name="Alt")],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    assert [n.unique_id for n in result.chain] == [1, 2]


def test_trace_on_schedule_with_cycle_skips_cyclic_edges() -> None:
    """A schedule with a cycle: tasks on the cycle are skipped by
    the CPM pass, and the driving-path walk treats edges into them
    as non-traversable (slack = None) and terminates cleanly.

    Topology: Focus ← D ← A → Focus, where A ↔ X form a 2-cycle.
    The M4 CPM engine in lenient mode marks A and X as
    skipped_due_to_cycle; trace_driving_path stops the walk when
    it hits the non-traversable edge.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="D", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Focus",
             duration_minutes=0, is_milestone=True),
    ]
    relations = [
        # Cycle between A and X.
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
        # D feeds Focus via A (but A is cyclic, so edge A→D is
        # non-traversable).
        Relation(predecessor_unique_id=1, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    s = Schedule(
        name="cyclic", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    # A and X are cyclic; D and Focus receive CPM dates.
    assert 1 in cpm.cycles_detected
    assert 2 in cpm.cycles_detected
    result = trace_driving_path(s, 4, cpm)
    # Focus's incoming edge (D → Focus) is traversable — D drives
    # Focus directly — but D's incoming edge (A → D) is non-
    # traversable because A is skipped. Walk terminates at D.
    assert [n.unique_id for n in result.chain] == [3, 4]
    # No non-driving predecessors were recorded on the cyclic
    # edge (slack = None is treated as not-a-driver and not-a-
    # non-driver; that is the forensically honest answer).
    assert result.non_driving_predecessors == ()


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
    s = Schedule(
        name="mut", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    trace_driving_path(s, 3, cpm)
    trace_driving_path(s, 2, cpm)
    trace_driving_path(s, FocusPointAnchor.PROJECT_FINISH, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before
