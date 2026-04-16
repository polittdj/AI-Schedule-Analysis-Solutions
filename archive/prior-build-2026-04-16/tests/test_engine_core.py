"""Unit tests for the Phase 2A forensic engine.

Covers:
* CPM forward/backward pass on a hand-computed 5-task linear chain
* CPM on a two-path network (one critical, one with float)
* CPM with lag and non-FS relationships
* Comparator slip detection, duration change, added/deleted, completed
* Delay analysis first-mover identification and cascade tracing
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pytest

from app.engine.comparator import compare_schedules
from app.engine.cpm import CRITICAL_EPSILON, compute_cpm
from app.engine.delay_analysis import analyze_delays
from app.parser.schema import (
    ProjectInfo,
    Relationship,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def make_task(
    uid: int,
    name: str = "",
    duration: Optional[float] = 0.0,
    start: Optional[datetime] = None,
    finish: Optional[datetime] = None,
    percent_complete: Optional[float] = 0.0,
    summary: bool = False,
    milestone: bool = False,
    critical: bool = False,
    total_slack: Optional[float] = None,
    free_slack: Optional[float] = None,
    predecessors: Optional[List[int]] = None,
    successors: Optional[List[int]] = None,
    notes: Optional[str] = None,
    **kwargs,
) -> TaskData:
    return TaskData(
        uid=uid,
        id=uid,
        name=name,
        duration=duration,
        start=start,
        finish=finish,
        percent_complete=percent_complete,
        summary=summary,
        milestone=milestone,
        critical=critical,
        total_slack=total_slack,
        free_slack=free_slack,
        predecessors=predecessors or [],
        successors=successors or [],
        notes=notes,
        **kwargs,
    )


def linear_chain_schedule() -> ScheduleData:
    """5-task linear chain: T1(5d)→T2(3d)→T3(7d)→T4(2d)→T5(4d), total 21d."""
    tasks = [
        make_task(1, name="T1", duration=5.0),
        make_task(2, name="T2", duration=3.0),
        make_task(3, name="T3", duration=7.0),
        make_task(4, name="T4", duration=2.0),
        make_task(5, name="T5", duration=4.0),
    ]
    rels = [
        Relationship(predecessor_uid=1, successor_uid=2),
        Relationship(predecessor_uid=2, successor_uid=3),
        Relationship(predecessor_uid=3, successor_uid=4),
        Relationship(predecessor_uid=4, successor_uid=5),
    ]
    return ScheduleData(
        project_info=ProjectInfo(name="LinearChain"),
        tasks=tasks,
        relationships=rels,
    )


def two_path_schedule() -> ScheduleData:
    """
    T1(2d) ─┬─► T2(10d) ─┐
            │             ├─► T4(3d)
            └─► T3(4d) ───┘

    Critical path: T1 → T2 → T4 (total 15 days).
    T3 has 6 days of total float.
    """
    tasks = [
        make_task(1, name="Start", duration=2.0),
        make_task(2, name="Long", duration=10.0),
        make_task(3, name="Short", duration=4.0),
        make_task(4, name="End", duration=3.0),
    ]
    rels = [
        Relationship(predecessor_uid=1, successor_uid=2),
        Relationship(predecessor_uid=1, successor_uid=3),
        Relationship(predecessor_uid=2, successor_uid=4),
        Relationship(predecessor_uid=3, successor_uid=4),
    ]
    return ScheduleData(
        project_info=ProjectInfo(name="TwoPath"),
        tasks=tasks,
        relationships=rels,
    )


# --------------------------------------------------------------------------- #
# CPM
# --------------------------------------------------------------------------- #


class TestCPMLinearChain:
    def test_project_duration(self):
        results = compute_cpm(linear_chain_schedule())
        # 5 + 3 + 7 + 2 + 4 = 21
        assert results.project_duration_days == pytest.approx(21.0)

    def test_forward_pass_values(self):
        results = compute_cpm(linear_chain_schedule())
        # ES/EF values hand-computed:
        # T1: 0→5, T2: 5→8, T3: 8→15, T4: 15→17, T5: 17→21
        expected = {
            1: (0.0, 5.0),
            2: (5.0, 8.0),
            3: (8.0, 15.0),
            4: (15.0, 17.0),
            5: (17.0, 21.0),
        }
        for uid, (es, ef) in expected.items():
            tf = results.task_floats[uid]
            assert tf.early_start == pytest.approx(es), f"task {uid} ES"
            assert tf.early_finish == pytest.approx(ef), f"task {uid} EF"

    def test_backward_pass_values(self):
        results = compute_cpm(linear_chain_schedule())
        # With no float in a linear chain, LS == ES and LF == EF.
        for uid in range(1, 6):
            tf = results.task_floats[uid]
            assert tf.late_start == pytest.approx(tf.early_start), f"task {uid} LS"
            assert tf.late_finish == pytest.approx(tf.early_finish), f"task {uid} LF"

    def test_all_tasks_critical(self):
        results = compute_cpm(linear_chain_schedule())
        for uid in range(1, 6):
            assert results.task_floats[uid].total_float == pytest.approx(0.0)
            assert results.task_floats[uid].critical is True

    def test_critical_path_order(self):
        results = compute_cpm(linear_chain_schedule())
        assert results.critical_path_uids == [1, 2, 3, 4, 5]


class TestCPMTwoPath:
    def test_project_duration(self):
        results = compute_cpm(two_path_schedule())
        # T1(2) + T2(10) + T4(3) = 15
        assert results.project_duration_days == pytest.approx(15.0)

    def test_critical_path(self):
        results = compute_cpm(two_path_schedule())
        assert results.critical_path_uids == [1, 2, 4]

    def test_non_critical_has_float(self):
        results = compute_cpm(two_path_schedule())
        # T3 ES=2, EF=6; LS must equal 8 (LF 12 - dur 4) because T4 needs
        # all its preds done by day 12 (=LS of T4). Total float = 8 - 2 = 6.
        tf3 = results.task_floats[3]
        assert tf3.total_float == pytest.approx(6.0)
        assert tf3.critical is False


class TestCPMLagAndTypes:
    def test_fs_with_lag(self):
        """T1(2d) -FS lag=3-> T2(5d): T2 ES=5, EF=10, project=10."""
        tasks = [make_task(1, duration=2.0), make_task(2, duration=5.0)]
        rels = [Relationship(predecessor_uid=1, successor_uid=2, type="FS", lag_days=3.0)]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        results = compute_cpm(schedule)
        assert results.project_duration_days == pytest.approx(10.0)
        assert results.task_floats[2].early_start == pytest.approx(5.0)

    def test_ss_relationship(self):
        """T1(10d) -SS lag=0-> T2(4d): T2 starts when T1 starts, T2 EF=4, T1 EF=10, project=10."""
        tasks = [make_task(1, duration=10.0), make_task(2, duration=4.0)]
        rels = [Relationship(predecessor_uid=1, successor_uid=2, type="SS")]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        results = compute_cpm(schedule)
        assert results.task_floats[2].early_start == pytest.approx(0.0)
        assert results.project_duration_days == pytest.approx(10.0)

    def test_summary_tasks_excluded(self):
        tasks = [
            make_task(10, name="Phase A", duration=0.0, summary=True),
            make_task(1, name="T1", duration=5.0),
            make_task(2, name="T2", duration=3.0),
        ]
        rels = [Relationship(predecessor_uid=1, successor_uid=2)]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        results = compute_cpm(schedule)
        assert 10 in results.excluded_summary_uids
        assert 10 not in results.task_floats
        assert results.project_duration_days == pytest.approx(8.0)

    def test_milestone_zero_duration(self):
        tasks = [
            make_task(1, duration=3.0),
            make_task(2, duration=0.0, milestone=True),
        ]
        rels = [Relationship(predecessor_uid=1, successor_uid=2)]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        results = compute_cpm(schedule)
        assert results.task_floats[2].early_finish == pytest.approx(3.0)
        assert results.project_duration_days == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# Comparator
# --------------------------------------------------------------------------- #


class TestComparator:
    def test_finish_slip_detected(self):
        prior = ScheduleData(
            project_info=ProjectInfo(name="proj"),
            tasks=[
                make_task(
                    1,
                    name="A",
                    start=datetime(2026, 1, 1),
                    finish=datetime(2026, 1, 10),
                    duration=10.0,
                )
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(name="proj"),
            tasks=[
                make_task(
                    1,
                    name="A",
                    start=datetime(2026, 1, 1),
                    finish=datetime(2026, 1, 17),
                    duration=10.0,
                )
            ],
        )
        result = compare_schedules(prior, later)
        delta = result.task_deltas[0]
        assert delta.finish_slip_days == pytest.approx(7.0)
        assert result.tasks_slipped_count == 1
        assert result.tasks_pulled_in_count == 0

    def test_start_slip_seven_days(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(
                    1, start=datetime(2026, 2, 1), finish=datetime(2026, 2, 5)
                )
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(
                    1, start=datetime(2026, 2, 8), finish=datetime(2026, 2, 12)
                )
            ],
        )
        result = compare_schedules(prior, later)
        assert result.task_deltas[0].start_slip_days == pytest.approx(7.0)

    def test_duration_change(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, duration=10.0)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, duration=15.0)],
        )
        result = compare_schedules(prior, later)
        assert result.task_deltas[0].duration_change_days == pytest.approx(5.0)

    def test_added_and_deleted_tasks(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1), make_task(2), make_task(3)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1), make_task(2), make_task(4)],
        )
        result = compare_schedules(prior, later)
        assert result.added_task_uids == [4]
        assert result.deleted_task_uids == [3]
        assert result.tasks_added_count == 1
        assert result.tasks_deleted_count == 1

    def test_completed_tasks(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, percent_complete=50.0)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, percent_complete=100.0)],
        )
        result = compare_schedules(prior, later)
        assert result.completed_task_uids == [1]
        assert result.tasks_completed_count == 1

    def test_logic_change_added_predecessor(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1), make_task(2), make_task(3)],
            relationships=[Relationship(predecessor_uid=1, successor_uid=3)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1), make_task(2), make_task(3)],
            relationships=[
                Relationship(predecessor_uid=1, successor_uid=3),
                Relationship(predecessor_uid=2, successor_uid=3),
            ],
        )
        result = compare_schedules(prior, later)
        delta_3 = next(d for d in result.task_deltas if d.uid == 3)
        assert 2 in delta_3.predecessors_added
        assert any(lc.kind == "added" for lc in result.logic_changes)

    def test_lag_change(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1), make_task(2)],
            relationships=[
                Relationship(predecessor_uid=1, successor_uid=2, lag_days=0.0)
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1), make_task(2)],
            relationships=[
                Relationship(predecessor_uid=1, successor_uid=2, lag_days=3.0)
            ],
        )
        result = compare_schedules(prior, later)
        delta_2 = next(d for d in result.task_deltas if d.uid == 2)
        assert len(delta_2.lag_changes) == 1
        assert delta_2.lag_changes[0].later_lag_days == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# Delay analysis
# --------------------------------------------------------------------------- #


class TestDelayAnalysis:
    def _build_slip_scenario(self) -> tuple[ScheduleData, ScheduleData]:
        """Linear critical chain with task 3 slipping 5 days.

        T1(5d) → T2(3d) → T3(7d) → T4(2d) → T5(4d)
        All tasks are on the critical path (marked critical=True to match
        what MSP would produce). In `later`, task 3 starts 5 days later and
        cascades the finish of T3/T4/T5 each by 5 days.
        """
        # Prior schedule: nothing slipped.
        prior_tasks = [
            make_task(
                1,
                name="Mobilization",
                duration=5.0,
                start=datetime(2026, 1, 5),
                finish=datetime(2026, 1, 9),
                critical=True,
            ),
            make_task(
                2,
                name="Excavation",
                duration=3.0,
                start=datetime(2026, 1, 12),
                finish=datetime(2026, 1, 14),
                critical=True,
                predecessors=[1],
            ),
            make_task(
                3,
                name="Concrete pour delay — weather event",
                duration=7.0,
                start=datetime(2026, 1, 15),
                finish=datetime(2026, 1, 23),
                critical=True,
                predecessors=[2],
                notes="Scheduled pour.",
            ),
            make_task(
                4,
                name="Formwork strip",
                duration=2.0,
                start=datetime(2026, 1, 26),
                finish=datetime(2026, 1, 27),
                critical=True,
                predecessors=[3],
            ),
            make_task(
                5,
                name="Backfill",
                duration=4.0,
                start=datetime(2026, 1, 28),
                finish=datetime(2026, 2, 2),
                critical=True,
                predecessors=[4],
            ),
        ]

        # Later schedule: T3 slips 5 days (weather). T4, T5 cascade by 5 days too.
        later_tasks = [
            make_task(
                1,
                name="Mobilization",
                duration=5.0,
                start=datetime(2026, 1, 5),
                finish=datetime(2026, 1, 9),
                critical=True,
                percent_complete=100.0,
            ),
            make_task(
                2,
                name="Excavation",
                duration=3.0,
                start=datetime(2026, 1, 12),
                finish=datetime(2026, 1, 14),
                critical=True,
                predecessors=[1],
                percent_complete=100.0,
            ),
            make_task(
                3,
                name="Concrete pour delay — weather event",
                duration=7.0,
                start=datetime(2026, 1, 20),  # slipped 5 days
                finish=datetime(2026, 1, 28),  # slipped 5 days
                critical=True,
                predecessors=[2],
                notes="Delayed 5 days by hurricane — unable to pour.",
            ),
            make_task(
                4,
                name="Formwork strip",
                duration=2.0,
                start=datetime(2026, 1, 31),
                finish=datetime(2026, 2, 1),
                critical=True,
                predecessors=[3],
            ),
            make_task(
                5,
                name="Backfill",
                duration=4.0,
                start=datetime(2026, 2, 2),
                finish=datetime(2026, 2, 7),
                critical=True,
                predecessors=[4],
            ),
        ]

        rels = [
            Relationship(predecessor_uid=i, successor_uid=i + 1)
            for i in range(1, 5)
        ]

        prior = ScheduleData(
            project_info=ProjectInfo(
                name="Bridge",
                finish_date=datetime(2026, 2, 2),
            ),
            tasks=prior_tasks,
            relationships=rels,
        )
        later = ScheduleData(
            project_info=ProjectInfo(
                name="Bridge",
                finish_date=datetime(2026, 2, 7),
            ),
            tasks=later_tasks,
            relationships=rels,
        )
        return prior, later

    def test_first_mover_identification(self):
        prior, later = self._build_slip_scenario()
        cmp_result = compare_schedules(prior, later)
        delay = analyze_delays(cmp_result, later)
        assert delay.first_mover_uid == 3
        assert delay.first_mover_slip_days == pytest.approx(5.0)

    def test_first_mover_categorized_as_weather(self):
        prior, later = self._build_slip_scenario()
        cmp_result = compare_schedules(prior, later)
        delay = analyze_delays(cmp_result, later)
        first_cause = next(rc for rc in delay.root_causes if rc.task_uid == 3)
        assert first_cause.category == "weather"
        assert first_cause.on_critical_path is True

    def test_cascade_chain_from_first_mover(self):
        prior, later = self._build_slip_scenario()
        cmp_result = compare_schedules(prior, later)
        delay = analyze_delays(cmp_result, later)
        # The cascade starting from task 3 should include downstream 4 and 5.
        chain_3 = next(c for c in delay.cascade_chains if c.root_uid == 3)
        assert set(chain_3.affected_uids) == {4, 5}

    def test_completion_slip_rolls_up(self):
        prior, later = self._build_slip_scenario()
        cmp_result = compare_schedules(prior, later)
        assert cmp_result.completion_date_slip_days == pytest.approx(5.0)
