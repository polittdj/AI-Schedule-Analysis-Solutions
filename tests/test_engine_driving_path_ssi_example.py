"""SSI worked-example reconstruction — Milestone 10 AC #1.

Reconstructs the four-tier driving chain from the SSI paper
(``driving-slack-and-paths §2`` final paragraph / slide 22):

    Y → X → Predecessor 3 → Focus Point

with FS links, zero lag, and zero relationship slack on every link.
The skill's §2 worked example cites three specific predecessors in
front of a "Focus Point 2023-12-15" milestone (slides 14–22) with
per-tier DS values DS(Pred 3) = 0, DS(Pred 2) = 2, DS(Pred 1) = 4.
The multi-tier Y → X → Pred 3 → Focus chain from slide 22 is a
separate illustration: four zero-slack FS links, DS = 0 at every
tier.

Per BUILD-PLAN §5 M10 Block 0 reconciliation, the fixture
reconstructs the four-tier chain from first principles (zero-lag FS
means predecessor EF = successor ES, so working-minute gap == 0 on
every link); per-tier DS values emerge from the CPM forward /
backward pass and are asserted directly.

Multi-branch extension: a non-driving predecessor Q is added
feeding X. Q's finish is early enough that the Q → X edge has
positive relationship slack, so X's driving predecessor is still
Y — the walk follows the zero-slack edge and the non-driving edge
lands on ``non_driving_predecessors`` with the expected slack.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
    """SSI slide-22 four-tier chain: Y → X → Predecessor 3 → Focus.

    Every edge is FS with zero lag. Each task is 1 working day
    (480 minutes) so the forward pass places them back-to-back and
    every relationship slack is zero.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="Y", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Predecessor 3",
             duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Focus Point",
             duration_minutes=0, is_milestone=True),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=3, successor_unique_id=4,
                 relation_type=RelationType.FS),
    ]
    return Schedule(
        name="ssi_four_tier", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# AC #1 — four-tier SSI chain
# ----------------------------------------------------------------------


def test_ssi_four_tier_chain() -> None:
    """SSI slide 22: Y → X → Predecessor 3 → Focus Point."""
    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)

    result = trace_driving_path(s, 4, cpm)

    # Chain shape — four nodes, earliest-ancestor first, focus last.
    assert len(result.chain) == 4
    assert [n.name for n in result.chain] == [
        "Y", "X", "Predecessor 3", "Focus Point",
    ]
    assert result.chain[0].unique_id == 1
    assert result.chain[-1].unique_id == 4
    assert result.focus_unique_id == 4
    assert result.focus_name == "Focus Point"

    # Three FS links, all zero relationship slack, all zero lag.
    assert len(result.links) == 3
    for link in result.links:
        assert link.relation_type == RelationType.FS
        assert link.relationship_slack_minutes == 0
        assert link.lag_minutes == 0

    # No non-driving predecessors on the clean chain.
    assert result.non_driving_predecessors == ()


def test_ssi_four_tier_per_tier_driving_slack() -> None:
    """Per-tier DS value emerging from the CPM pass.

    On the clean four-tier chain (no competing logic and no
    constraint on Focus Point), every upstream task has zero
    driving slack to the focus — the hallmark of a pure driving
    chain (``driving-slack-and-paths §2`` final paragraph).
    """
    from app.engine.paths import driving_slack_to_focus

    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)

    ds_map = driving_slack_to_focus(s, cpm, focus_uid=4)
    # UIDs 1 (Y), 2 (X), 3 (Pred 3), and 4 (Focus Point itself).
    assert ds_map[1] == 0
    assert ds_map[2] == 0
    assert ds_map[3] == 0
    assert ds_map[4] == 0


def test_ssi_chain_is_critical_path() -> None:
    """Every task on the SSI chain is also on the CPM critical path.

    Per SSI slide 12, DS-to-project-finish is the most accurate
    critical-path test. With no competing chains and no late
    constraint, every driving predecessor has TS = 0 and lands
    in ``cpm_result.critical_path_uids``.
    """
    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)
    for uid in (1, 2, 3, 4):
        assert cpm.tasks[uid].on_critical_path is True


# ----------------------------------------------------------------------
# Multi-branch: non-driving predecessor terminates its branch
# ----------------------------------------------------------------------


def test_ssi_multi_branch_non_driving() -> None:
    """Extend the chain with a non-driving predecessor Q feeding X.

    Q runs 1 working day starting from the project anchor; X runs
    1 working day starting after Y finishes. Q's finish is 1 WD
    earlier than Y's, so the Q → X edge carries 480 minutes of
    positive relationship slack. The walk's driving predecessor
    for X is still Y (zero slack); Q lands on
    non_driving_predecessors with 480 minutes of slack.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="Y", duration_minutes=960),  # 2 WD
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Predecessor 3",
             duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Focus Point",
             duration_minutes=0, is_milestone=True),
        Task(unique_id=5, task_id=5, name="Q", duration_minutes=480),  # 1 WD
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=3, successor_unique_id=4,
                 relation_type=RelationType.FS),
        # Non-driving predecessor: Q feeds X.
        Relation(predecessor_unique_id=5, successor_unique_id=2,
                 relation_type=RelationType.FS),
    ]
    s = Schedule(
        name="ssi_multi_branch", project_start=ANCHOR, tasks=tasks,
        relations=relations, calendars=[_std_cal()],
    )
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 4, cpm)

    # Chain is unchanged — Q is not in the chain.
    assert [n.name for n in result.chain] == [
        "Y", "X", "Predecessor 3", "Focus Point",
    ]
    # One non-driving predecessor: Q → X with 480 min of slack
    # (Y runs 2 WD, Q runs 1 WD from the same anchor, so Q's EF
    # is 1 WD earlier than Y's and thus 1 WD earlier than X.ES).
    assert len(result.non_driving_predecessors) == 1
    ndp = result.non_driving_predecessors[0]
    assert ndp.predecessor_unique_id == 5
    assert ndp.predecessor_name == "Q"
    assert ndp.successor_unique_id == 2
    assert ndp.successor_name == "X"
    assert ndp.relation_type == RelationType.FS
    assert ndp.relationship_slack_minutes == 480  # 1 WD


def test_ssi_mutation_invariance() -> None:
    """The SSI fixture is not mutated by the trace call."""
    s = _ssi_four_tier_schedule()
    cpm = compute_cpm(s)
    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    trace_driving_path(s, 4, cpm)
    # Trace from an interim focus, too.
    trace_driving_path(s, 3, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before
