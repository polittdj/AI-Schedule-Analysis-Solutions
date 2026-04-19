"""End-to-end CPM engine tests.

Covers BUILD-PLAN §5 M4 gotchas E2, E3, E14, E15, E17, E18, E21 and
the forward/backward pass wiring of the smaller modules.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import CPMEngine, compute_cpm
from app.engine.exceptions import CircularDependencyError, MissingCalendarError
from app.engine.options import CPMOptions
from app.models.calendar import Calendar
from app.models.enums import ConstraintType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.schedules import (
    ANCHOR,
    complex_with_exceptions,
    medium_mixed_relations,
    small_fs_chain,
)

# ---- E2 — empty schedule -----------------------------------------


def test_empty_schedule_no_op() -> None:
    s = Schedule(name="empty")
    result = compute_cpm(s)
    assert result.tasks == {}
    assert result.project_start is None
    assert result.project_finish is None
    assert result.cycles_detected == frozenset()


# ---- E3 — independent tasks --------------------------------------


def test_independent_tasks_each_anchor_on_project_start() -> None:
    """Tasks with no relations each start at project_start."""
    s = Schedule(
        name="indep",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
            Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    assert result.tasks[1].early_start == ANCHOR
    assert result.tasks[2].early_start == ANCHOR


# ---- Small FS chain ----------------------------------------------


def test_small_fs_chain_forward_pass() -> None:
    """Under the E12 boundary-roll convention, a 1-day task starting
    Mon 08:00 finishes Tue 08:00 (equivalent working-time instant to
    Mon 16:00). This is the canonical form emitted by the engine."""
    s = small_fs_chain()
    result = compute_cpm(s)
    assert result.tasks[1].early_start == ANCHOR
    assert result.tasks[1].early_finish == datetime(2026, 4, 21, 8, tzinfo=UTC)
    assert result.tasks[2].early_start == datetime(2026, 4, 21, 8, tzinfo=UTC)
    assert result.tasks[2].early_finish == datetime(2026, 4, 22, 8, tzinfo=UTC)
    assert result.tasks[3].early_start == datetime(2026, 4, 22, 8, tzinfo=UTC)
    assert result.tasks[3].early_finish == datetime(2026, 4, 23, 8, tzinfo=UTC)
    assert result.project_finish == datetime(2026, 4, 23, 8, tzinfo=UTC)


def test_small_fs_chain_every_task_critical() -> None:
    s = small_fs_chain()
    result = compute_cpm(s)
    assert result.critical_path_uids == frozenset({1, 2, 3})
    for r in result.tasks.values():
        assert r.total_slack_minutes == 0


def test_small_fs_chain_backward_pass() -> None:
    s = small_fs_chain()
    result = compute_cpm(s)
    # On the critical chain LS == ES and LF == EF.
    for uid in (1, 2, 3):
        r = result.tasks[uid]
        assert r.late_start == r.early_start
        assert r.late_finish == r.early_finish


# ---- E14 — zero-duration milestone -------------------------------


def test_milestone_es_equals_ef() -> None:
    s = Schedule(
        name="ms",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
            Task(unique_id=2, task_id=2, name="M", duration_minutes=0,
                 is_milestone=True),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    r = result.tasks[2]
    assert r.early_start == r.early_finish
    # Milestone inherits predecessor EF as its own start/finish
    # (A finishes Mon EOD = Tue 08:00 in canonical form).
    assert r.early_start == datetime(2026, 4, 21, 8, tzinfo=UTC)


# ---- E15 — multi-predecessor takes MAX ---------------------------


def test_multiple_predecessors_successor_takes_max() -> None:
    # A (1d) EF = Tue 08:00; B (3d) EF = Thu 08:00.
    # C depends on both → ES = max = Thu 08:00.
    s = Schedule(
        name="multi-pred",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
            Task(unique_id=2, task_id=2, name="B", duration_minutes=480 * 3),
            Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=3),
            Relation(predecessor_unique_id=2, successor_unique_id=3),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    assert result.tasks[3].early_start == datetime(2026, 4, 23, 8, tzinfo=UTC)


# ---- E17 — disconnected subgraphs --------------------------------


def test_disconnected_subgraphs_computed_independently() -> None:
    # Graph 1: 1→2; Graph 2: 3→4.
    s = Schedule(
        name="disconnected",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
            for i in (1, 2, 3, 4)
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
            Relation(predecessor_unique_id=3, successor_unique_id=4),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    assert result.tasks[1].early_start == ANCHOR
    assert result.tasks[3].early_start == ANCHOR
    assert result.tasks[2].early_finish == datetime(2026, 4, 22, 8, tzinfo=UTC)
    assert result.tasks[4].early_finish == datetime(2026, 4, 22, 8, tzinfo=UTC)


# ---- E18 — project finish override -------------------------------


def test_project_finish_override_extends_backward_pass() -> None:
    s = small_fs_chain()
    # Without override: critical chain has 0 TS.
    # With override far future: every task has positive TS.
    override = datetime(2026, 5, 1, 16, tzinfo=UTC)
    result = compute_cpm(s, CPMOptions(project_finish_override=override))
    for r in result.tasks.values():
        assert r.total_slack_minutes > 0


# ---- E21 — negative slack -----------------------------------------


def test_negative_slack_when_finish_override_is_earlier_than_critical() -> None:
    """TS may be negative — required by DCMA §4.7 Metric 7."""
    s = small_fs_chain()
    # Chain naturally ends Wed 16:00; pull override to Tue 16:00 →
    # negative slack throughout.
    override = datetime(2026, 4, 21, 16, tzinfo=UTC)
    result = compute_cpm(s, CPMOptions(project_finish_override=override))
    assert result.tasks[3].total_slack_minutes < 0
    assert 3 in result.critical_path_uids  # TS <= 0 is critical.


# ---- Cycle handling ----------------------------------------------


def test_lenient_cycle_returns_result_with_cycles_detected() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=1),
    ]
    s = Schedule(
        name="cycle",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    assert result.cycles_detected == frozenset({1, 2, 3})
    for uid in (1, 2, 3):
        assert result.tasks[uid].skipped_due_to_cycle


def test_strict_cycle_raises() -> None:
    tasks = [Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
             for i in (1, 2)]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
    ]
    s = Schedule(
        name="strict-cycle",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[Calendar(name="Standard")],
    )
    with pytest.raises(CircularDependencyError):
        compute_cpm(s, CPMOptions(strict_cycles=True))


def test_lenient_cycle_preserves_acyclic_subgraph_floats() -> None:
    # 1<->2 cycle; 3->4 acyclic.
    tasks = [Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
             for i in (1, 2, 3, 4)]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    s = Schedule(
        name="mix",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    assert result.tasks[3].early_start == ANCHOR
    assert result.tasks[3].total_slack_minutes == 0
    assert result.tasks[4].total_slack_minutes == 0


# ---- Constraint integration --------------------------------------


def test_mso_locks_es_in_forward_pass() -> None:
    """E8: MSO locks ES regardless of predecessors."""
    mso_date = datetime(2026, 4, 24, 8, tzinfo=UTC)  # Friday
    s = Schedule(
        name="mso",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
            Task(
                unique_id=2, task_id=2, name="B", duration_minutes=480,
                constraint_type=ConstraintType.MUST_START_ON,
                constraint_date=mso_date,
            ),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    assert result.tasks[2].early_start == mso_date
    assert result.tasks[2].early_finish == datetime(2026, 4, 27, 8, tzinfo=UTC)


def test_mso_override_predecessor_emits_violation() -> None:
    """E8: when MSO lock date precedes predecessor-driven ES, the
    engine honors the MSO lock AND emits a ConstraintViolation so
    the M12 delay-claim exporter can report the logical infeasibility
    (driving-slack-and-paths §8 CPM discipline).
    """
    # Predecessor is a 3-day task starting Mon 4/20, finishing Thu 4/23.
    # Successor has MSO = Mon 4/20 (3 working days before predecessor
    # releases) so the MSO lock overrides the FS link.
    mso_date = datetime(2026, 4, 20, 8, tzinfo=UTC)
    s = Schedule(
        name="mso-override",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480 * 3),
            Task(
                unique_id=2, task_id=2, name="B", duration_minutes=480,
                constraint_type=ConstraintType.MUST_START_ON,
                constraint_date=mso_date,
            ),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)

    # MSO lock still wins.
    assert result.tasks[2].early_start == mso_date

    overrides = [v for v in result.violations if v.unique_id == 2]
    kinds = {v.kind for v in overrides}
    assert "MSO_OVERRIDE_PREDECESSOR" in kinds

    v = next(v for v in overrides if v.kind == "MSO_OVERRIDE_PREDECESSOR")
    assert v.constraint_date == mso_date
    # Predecessor EF = Thu 4/23 08:00 → successor pred-driven ES = Thu 4/23 08:00.
    assert v.computed_date == datetime(2026, 4, 23, 8, tzinfo=UTC)
    assert v.computed_date > v.constraint_date


def test_mfo_override_predecessor_emits_violation() -> None:
    """E8: 2-task FS chain where predecessor EF forces successor EF
    past MFO. Engine respects the MFO lock AND records the override."""
    # Predecessor: 3 days → finishes Thu 4/23 08:00.
    # Successor: 1 day, MFO = Tue 4/21 16:00 (well before pred finish).
    mfo_date = datetime(2026, 4, 21, 16, tzinfo=UTC)
    s = Schedule(
        name="mfo-override",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480 * 3),
            Task(
                unique_id=2, task_id=2, name="B", duration_minutes=480,
                constraint_type=ConstraintType.MUST_FINISH_ON,
                constraint_date=mfo_date,
            ),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)

    # MFO lock wins — EF snapped to the MFO date.
    assert result.tasks[2].early_finish == mfo_date

    overrides = [v for v in result.violations if v.unique_id == 2]
    kinds = {v.kind for v in overrides}
    assert "MFO_OVERRIDE_PREDECESSOR" in kinds

    v = next(v for v in overrides if v.kind == "MFO_OVERRIDE_PREDECESSOR")
    assert v.constraint_date == mfo_date
    # Predecessor EF = Thu 4/23 08:00, successor 1-day duration → pred-driven
    # EF = Fri 4/24 08:00 (E12 boundary-roll convention).
    assert v.computed_date == datetime(2026, 4, 24, 8, tzinfo=UTC)
    assert v.computed_date > v.constraint_date


def test_fnlt_breach_emits_violation_not_exception() -> None:
    """E11: FNLT breach is a recorded violation."""
    fnlt = datetime(2026, 4, 20, 16, tzinfo=UTC)
    s = Schedule(
        name="fnlt",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480 * 3),
            Task(
                unique_id=2, task_id=2, name="B",
                duration_minutes=480,
                constraint_type=ConstraintType.FINISH_NO_LATER_THAN,
                constraint_date=fnlt,
            ),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)
    violation_kinds = {v.kind for v in result.violations}
    assert "FNLT_BREACHED" in violation_kinds


def test_backward_pass_multi_successor_uses_min() -> None:
    """E16: predecessor LF = MIN across successor-derived bounds.

    Fixture — one predecessor P feeds three FS successors (S1, S2, S3)
    with different durations and no onward links, so each successor's
    LF anchors on the project finish and each yields a different
    successor-driven LS:

      ANCHOR = Mon 2026-04-20 08:00 (an 8-hour working day).

      P   (1d)  ES=Mon 4/20 08, EF=Tue 4/21 08
      S1  (1d)  ES=Tue 4/21 08, EF=Wed 4/22 08
      S2  (3d)  ES=Tue 4/21 08, EF=Fri 4/24 08
      S3  (5d)  ES=Tue 4/21 08, EF=Tue 4/28 08   ← project finish

      Backward pass, anchor_finish = Tue 4/28 08:
        S3 LS = anchor - 5d = Tue 4/21 08   (Tue 4/28 - Mon 4/27 - Fri 4/24
                                              - Thu 4/23 - Wed 4/22 - Tue 4/21)
        S2 LS = anchor - 3d = Thu 4/23 08   (Tue 4/28 - Mon 4/27 - Fri 4/24
                                              - Thu 4/23)
        S1 LS = anchor - 1d = Mon 4/27 08

      P's FS successor-derived LF bounds (FS: LF(pred) <= LS(succ)):
        via S1 -> Mon 4/27 08
        via S2 -> Thu 4/23 08
        via S3 -> Tue 4/21 08   ← MIN

      P LF = MIN = Tue 4/21 08  -> TS(P) = 0 (on-critical).
    """
    s = Schedule(
        name="multi-succ",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="P", duration_minutes=480),
            Task(unique_id=2, task_id=2, name="S1", duration_minutes=480),
            Task(unique_id=3, task_id=3, name="S2", duration_minutes=480 * 3),
            Task(unique_id=4, task_id=4, name="S3", duration_minutes=480 * 5),
        ],
        relations=[
            Relation(predecessor_unique_id=1, successor_unique_id=2),
            Relation(predecessor_unique_id=1, successor_unique_id=3),
            Relation(predecessor_unique_id=1, successor_unique_id=4),
        ],
        calendars=[Calendar(name="Standard")],
    )
    result = compute_cpm(s)

    # S3 drives the project finish.
    expected_finish = datetime(2026, 4, 28, 8, tzinfo=UTC)
    assert result.project_finish == expected_finish

    # MIN aggregation: P LF equals S3 LS, not S1 LS or S2 LS.
    assert result.tasks[1].late_finish == datetime(2026, 4, 21, 8, tzinfo=UTC)
    # Sanity — the two non-driving successors do have later LS values.
    assert result.tasks[2].late_start == datetime(2026, 4, 27, 8, tzinfo=UTC)
    assert result.tasks[3].late_start == datetime(2026, 4, 23, 8, tzinfo=UTC)
    assert result.tasks[4].late_start == datetime(2026, 4, 21, 8, tzinfo=UTC)

    # P is on the critical path by driving S3; S1 and S2 have slack.
    assert result.tasks[1].on_critical_path is True
    assert result.tasks[4].on_critical_path is True
    assert result.tasks[2].total_slack_minutes > 0
    assert result.tasks[3].total_slack_minutes > 0


# ---- Calendar-synthesis gating (Block C4) ------------------------


def test_calendar_synthesis_default_allows_empty_calendars() -> None:
    """Default CPMOptions synthesizes a Standard calendar on empty
    calendar lists so minimal fixtures continue to compute. The
    flip to strict mode is tracked for M5."""
    s = Schedule(
        name="no-cal",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        ],
        # No calendars — relies on synthesis.
    )
    # Default CPMOptions has auto_synthesize_calendar=True.
    result = compute_cpm(s)
    assert 1 in result.tasks
    assert result.tasks[1].early_start == ANCHOR


def test_calendar_synthesis_off_raises_on_empty_calendars() -> None:
    """With auto_synthesize_calendar=False the engine must not
    fabricate a calendar — the absence is a forensic signal
    (driving-slack-and-paths §8 CPM discipline)."""
    s = Schedule(
        name="no-cal-strict",
        project_start=ANCHOR,
        tasks=[
            Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        ],
    )
    opts = CPMOptions(auto_synthesize_calendar=False)
    with pytest.raises(MissingCalendarError):
        compute_cpm(s, opts)


# ---- Medium fixture smoke tests ----------------------------------


def test_medium_fixture_produces_all_task_results() -> None:
    s = medium_mixed_relations()
    result = compute_cpm(s)
    assert set(result.tasks.keys()) == {i for i in range(1, 11)}
    for r in result.tasks.values():
        assert r.early_start is not None
        assert r.early_finish is not None
        assert r.late_start is not None
        assert r.late_finish is not None


def test_medium_fixture_project_finish_beyond_project_start() -> None:
    s = medium_mixed_relations()
    result = compute_cpm(s)
    assert result.project_finish is not None
    assert result.project_start is not None
    assert result.project_finish > result.project_start


# ---- Complex fixture with calendar exception ---------------------


def test_complex_fixture_with_christmas_exception_holds() -> None:
    s = complex_with_exceptions()
    result = compute_cpm(s)
    # 51 tasks (50 work + 1 finish milestone).
    assert len(result.tasks) == 51
    # No task's EF lands on Christmas Day 2026.
    christmas = datetime(2026, 12, 25, tzinfo=UTC).date()
    for r in result.tasks.values():
        if r.early_finish is not None:
            assert r.early_finish.date() != christmas


# ---- Near-critical classification (E19) --------------------------


def test_near_critical_uses_options_threshold() -> None:
    """E19 / A7: configurable threshold is wired through."""
    # 5-task FS chain: critical is the full chain. Add one parallel
    # branch with slack exactly 5 working days (2400 min).
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in (1, 2, 3, 4, 5, 6)
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
        Relation(predecessor_unique_id=4, successor_unique_id=5),
        Relation(predecessor_unique_id=1, successor_unique_id=6),
        Relation(predecessor_unique_id=6, successor_unique_id=5),
    ]
    s = Schedule(
        name="nc",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[Calendar(name="Standard")],
    )
    # Default threshold 10d → branch counts as near-critical.
    default_result = compute_cpm(s)
    assert 6 in default_result.near_critical_uids
    # Threshold 1d → branch no longer near-critical.
    strict = compute_cpm(s, CPMOptions(near_critical_threshold_days=1.0))
    assert 6 not in strict.near_critical_uids


# ---- Engine class interface -------------------------------------


def test_engine_class_and_helper_produce_equal_results() -> None:
    s = small_fs_chain()
    a = CPMEngine(s).compute()
    b = compute_cpm(s)
    assert a.project_finish == b.project_finish
    assert set(a.tasks.keys()) == set(b.tasks.keys())
