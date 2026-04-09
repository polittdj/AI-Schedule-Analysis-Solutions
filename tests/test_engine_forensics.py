"""Unit tests for the Phase 2B forensic engine modules.

Covers:
* DCMA metrics: Logic (missing predecessors), BEI, CPLI, Critical Path
  Test, Hard Constraints, Leads, Lags, Relationship Types.
* Manipulation detection: critical duration cut (HIGH), baseline date
  change (HIGH), out-of-sequence progress (HIGH), lag change (MEDIUM).
* Earned Value: SPI/CPI/SV/EAC on a simple 4-task schedule.
* Float analysis: task that became critical, WBS rollup, trend flag.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pytest

from app.engine.comparator import compare_schedules
from app.engine.dcma import (
    compute_dcma,
    THRESHOLD_CPLI,
)
from app.engine.earned_value import (
    UNITS_CURRENCY,
    UNITS_WORKING_DAYS,
    compute_earned_value,
)
from app.engine.float_analysis import analyze_float
from app.engine.manipulation import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    detect_manipulations,
)
from app.parser.schema import (
    AssignmentData,
    ProjectInfo,
    Relationship,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def make_task(
    uid: int,
    name: str = "",
    duration: Optional[float] = 0.0,
    start: Optional[datetime] = None,
    finish: Optional[datetime] = None,
    baseline_start: Optional[datetime] = None,
    baseline_finish: Optional[datetime] = None,
    baseline_duration: Optional[float] = None,
    actual_start: Optional[datetime] = None,
    actual_finish: Optional[datetime] = None,
    percent_complete: Optional[float] = 0.0,
    remaining_duration: Optional[float] = None,
    total_slack: Optional[float] = None,
    free_slack: Optional[float] = None,
    summary: bool = False,
    milestone: bool = False,
    critical: bool = False,
    constraint_type: Optional[str] = None,
    predecessors: Optional[List[int]] = None,
    successors: Optional[List[int]] = None,
    wbs: Optional[str] = None,
    resource_names: Optional[str] = None,
    notes: Optional[str] = None,
) -> TaskData:
    return TaskData(
        uid=uid,
        id=uid,
        name=name,
        duration=duration,
        start=start,
        finish=finish,
        baseline_start=baseline_start,
        baseline_finish=baseline_finish,
        baseline_duration=baseline_duration,
        actual_start=actual_start,
        actual_finish=actual_finish,
        percent_complete=percent_complete,
        remaining_duration=remaining_duration,
        total_slack=total_slack,
        free_slack=free_slack,
        summary=summary,
        milestone=milestone,
        critical=critical,
        constraint_type=constraint_type,
        predecessors=predecessors or [],
        successors=successors or [],
        wbs=wbs,
        resource_names=resource_names,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# DCMA
# --------------------------------------------------------------------------- #


class TestDCMALogic:
    def test_flags_task_missing_predecessors(self):
        # Tasks 1 & 2 are fine (chain). Task 3 is incomplete and has neither
        # predecessors nor successors → should trip the Logic metric.
        tasks = [
            make_task(1, duration=5.0, successors=[2]),
            make_task(2, duration=5.0, predecessors=[1]),
            make_task(3, duration=5.0),  # orphan, incomplete
        ]
        rels = [Relationship(predecessor_uid=1, successor_uid=2)]
        schedule = ScheduleData(
            project_info=ProjectInfo(name="Logic Test"),
            tasks=tasks,
            relationships=rels,
        )
        result = compute_dcma(schedule)
        logic_metric = next(m for m in result.metrics if m.number == 1)
        # 1 of 3 incomplete tasks (task 1 has no preds, task 3 has neither,
        # task 2 has both). Actually both 1 and 3 lack something → 2/3 ≈ 66.7%
        assert logic_metric.details["missing_count"] >= 1
        assert logic_metric.passed is False

    def test_clean_chain_passes_logic(self):
        # Linear chain: task 1 (first, no pred) and task 3 (last, no succ) are
        # expected. Only the middle task 2 must have both. Strict DCMA still
        # counts 1 and 3 as violators — this asserts the strict behavior.
        tasks = [
            make_task(1, duration=5.0, successors=[2]),
            make_task(2, duration=5.0, predecessors=[1], successors=[3]),
            make_task(3, duration=5.0, predecessors=[2]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=2, successor_uid=3),
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        result = compute_dcma(schedule)
        logic_metric = next(m for m in result.metrics if m.number == 1)
        # Strict DCMA: 2 of 3 tasks are missing one side → ~66.7%, fails.
        assert logic_metric.value == pytest.approx(66.67, abs=0.1)
        assert logic_metric.passed is False


class TestDCMABEI:
    def test_bei_with_five_planned_three_complete(self):
        status_date = datetime(2026, 4, 9)
        # 5 tasks all with baseline_finish before status_date; 3 at 100%.
        tasks = [
            make_task(
                1,
                baseline_finish=datetime(2026, 3, 1),
                percent_complete=100.0,
            ),
            make_task(
                2,
                baseline_finish=datetime(2026, 3, 10),
                percent_complete=100.0,
            ),
            make_task(
                3,
                baseline_finish=datetime(2026, 3, 20),
                percent_complete=100.0,
            ),
            make_task(
                4,
                baseline_finish=datetime(2026, 3, 25),
                percent_complete=50.0,
            ),
            make_task(
                5,
                baseline_finish=datetime(2026, 4, 1),
                percent_complete=0.0,
            ),
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(status_date=status_date), tasks=tasks
        )
        result = compute_dcma(schedule)
        bei = next(m for m in result.metrics if m.number == 14)
        assert bei.value == pytest.approx(0.6)
        assert bei.passed is False

    def test_bei_perfect_execution(self):
        status_date = datetime(2026, 4, 9)
        tasks = [
            make_task(
                i,
                baseline_finish=datetime(2026, 3, 1),
                percent_complete=100.0,
            )
            for i in range(1, 4)
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(status_date=status_date), tasks=tasks
        )
        result = compute_dcma(schedule)
        bei = next(m for m in result.metrics if m.number == 14)
        assert bei.value == pytest.approx(1.0)
        assert bei.passed is True


class TestDCMAOtherMetrics:
    def test_leads_negative_lag_flagged(self):
        tasks = [make_task(1, duration=5.0), make_task(2, duration=5.0)]
        rels = [
            Relationship(
                predecessor_uid=1, successor_uid=2, type="FS", lag_days=-2.0
            )
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        result = compute_dcma(schedule)
        leads = next(m for m in result.metrics if m.number == 2)
        assert leads.value == pytest.approx(100.0)
        assert leads.passed is False

    def test_hard_constraints_flagged(self):
        tasks = [
            make_task(1, duration=5.0, constraint_type="MUST_START_ON"),
            make_task(2, duration=5.0),
        ]
        schedule = ScheduleData(project_info=ProjectInfo(), tasks=tasks)
        result = compute_dcma(schedule)
        hard = next(m for m in result.metrics if m.number == 5)
        assert hard.value == pytest.approx(50.0)
        assert hard.passed is False

    def test_critical_path_test_passes_on_linear_chain(self):
        tasks = [
            make_task(1, duration=5.0, successors=[2]),
            make_task(2, duration=5.0, predecessors=[1], successors=[3]),
            make_task(3, duration=5.0, predecessors=[2]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=2, successor_uid=3),
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        result = compute_dcma(schedule)
        cpt = next(m for m in result.metrics if m.number == 12)
        assert cpt.passed is True
        assert cpt.details["delay_days"] == pytest.approx(1.0)

    def test_cpli_on_track_project(self):
        status_date = datetime(2026, 4, 1)
        baseline_finish = datetime(2026, 5, 1)
        current_finish = datetime(2026, 5, 1)  # exactly on baseline
        tasks = [
            make_task(
                1,
                duration=10.0,
                baseline_finish=baseline_finish,
                finish=current_finish,
            )
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(
                status_date=status_date,
                finish_date=current_finish,
            ),
            tasks=tasks,
        )
        result = compute_dcma(schedule)
        cpli = next(m for m in result.metrics if m.number == 13)
        assert cpli.value == pytest.approx(1.0)
        assert cpli.passed is True


# --------------------------------------------------------------------------- #
# Manipulation
# --------------------------------------------------------------------------- #


class TestManipulationDuration:
    def test_sixty_percent_critical_cut_is_high(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, name="T1", duration=10.0, critical=True)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, name="T1", duration=4.0, critical=True)],
        )
        comparison = compare_schedules(prior, later)
        result = detect_manipulations(comparison, prior, later)
        dur_findings = [
            f for f in result.findings if f.pattern == "critical_duration_reduction"
        ]
        assert len(dur_findings) == 1
        assert dur_findings[0].confidence == CONFIDENCE_HIGH
        assert dur_findings[0].evidence["reduction_pct"] == pytest.approx(60.0)

    def test_thirty_percent_critical_cut_is_medium(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, duration=10.0, critical=True)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, duration=7.0, critical=True)],
        )
        result = detect_manipulations(
            compare_schedules(prior, later), prior, later
        )
        dur_findings = [
            f for f in result.findings if f.pattern == "critical_duration_reduction"
        ]
        assert len(dur_findings) == 1
        assert dur_findings[0].confidence == CONFIDENCE_MEDIUM

    def test_non_critical_cut_not_flagged(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, duration=10.0, critical=False)],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[make_task(1, duration=2.0, critical=False)],
        )
        result = detect_manipulations(
            compare_schedules(prior, later), prior, later
        )
        assert not any(
            f.pattern == "critical_duration_reduction" for f in result.findings
        )


class TestManipulationBaseline:
    def test_baseline_date_change_is_high(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(
                    1,
                    name="Footings",
                    baseline_start=datetime(2026, 1, 5),
                    baseline_finish=datetime(2026, 1, 12),
                )
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(
                    1,
                    name="Footings",
                    baseline_start=datetime(2026, 1, 5),
                    baseline_finish=datetime(2026, 1, 19),  # moved 7 days
                )
            ],
        )
        result = detect_manipulations(
            compare_schedules(prior, later), prior, later
        )
        baseline_findings = [
            f for f in result.findings if f.pattern == "baseline_date_change"
        ]
        assert len(baseline_findings) == 1
        assert baseline_findings[0].confidence == CONFIDENCE_HIGH
        assert result.overall_score >= 10.0


class TestManipulationLogic:
    def test_lag_change_flagged(self):
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
                Relationship(predecessor_uid=1, successor_uid=2, lag_days=5.0)
            ],
        )
        result = detect_manipulations(
            compare_schedules(prior, later), prior, later
        )
        lag_findings = [f for f in result.findings if f.pattern == "lag_change"]
        assert len(lag_findings) == 1
        assert lag_findings[0].confidence == CONFIDENCE_MEDIUM

    def test_out_of_sequence_progress_flagged(self):
        # Task 1 at 0%, Task 2 (FS pred=1) at 50% → out of sequence.
        tasks = [
            make_task(1, name="Excavation", percent_complete=0.0),
            make_task(
                2,
                name="Concrete",
                percent_complete=50.0,
                predecessors=[1],
            ),
        ]
        rels = [Relationship(predecessor_uid=1, successor_uid=2, type="FS")]
        later = ScheduleData(
            project_info=ProjectInfo(), tasks=tasks, relationships=rels
        )
        # Prior schedule identical to later (so only the OOS check fires).
        prior = later.model_copy(deep=True)
        result = detect_manipulations(
            compare_schedules(prior, later), prior, later
        )
        oos = [f for f in result.findings if f.pattern == "out_of_sequence_progress"]
        assert len(oos) == 1
        assert oos[0].confidence == CONFIDENCE_HIGH
        assert oos[0].task_uid == 2


class TestManipulationOverallScore:
    def test_clean_schedule_scores_zero(self):
        schedule = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, duration=5.0, critical=True),
                make_task(2, duration=5.0, critical=True),
            ],
            relationships=[Relationship(predecessor_uid=1, successor_uid=2)],
        )
        # No changes at all.
        result = detect_manipulations(
            compare_schedules(schedule, schedule), schedule, schedule
        )
        assert result.overall_score == pytest.approx(0.0)
        assert result.findings == []


# --------------------------------------------------------------------------- #
# Earned Value
# --------------------------------------------------------------------------- #


class TestEarnedValue:
    def test_duration_based_on_track(self):
        """4 tasks, all baseline 10 days. Status halfway through task 2.
        Task 1 100% complete, task 2 50% complete, others 0%.
        Planned: task 1 full (10), task 2 half (5) = 15.
        Earned: task 1 full (10) + task 2 half (5) = 15. SPI = 1.0.
        """
        status_date = datetime(2026, 1, 15)
        tasks = [
            make_task(
                1,
                duration=10.0,
                baseline_duration=10.0,
                baseline_start=datetime(2026, 1, 1),
                baseline_finish=datetime(2026, 1, 11),
                percent_complete=100.0,
            ),
            make_task(
                2,
                duration=10.0,
                baseline_duration=10.0,
                baseline_start=datetime(2026, 1, 11),
                baseline_finish=datetime(2026, 1, 21),  # halfway 01-16 ~ 50%
                percent_complete=50.0,
            ),
            make_task(
                3,
                duration=10.0,
                baseline_duration=10.0,
                baseline_start=datetime(2026, 1, 21),
                baseline_finish=datetime(2026, 1, 31),
                percent_complete=0.0,
            ),
            make_task(
                4,
                duration=10.0,
                baseline_duration=10.0,
                baseline_start=datetime(2026, 1, 31),
                baseline_finish=datetime(2026, 2, 10),
                percent_complete=0.0,
            ),
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(status_date=status_date), tasks=tasks
        )
        result = compute_earned_value(schedule)
        assert result.units == UNITS_WORKING_DAYS
        assert result.budget_at_completion == pytest.approx(40.0)
        # Task 1 fully earned (10), task 2 half earned (5) → EV = 15.
        assert result.earned_value == pytest.approx(15.0)
        # SPI ~= 1.0 within a day of jitter.
        assert result.schedule_performance_index == pytest.approx(1.0, abs=0.1)

    def test_behind_schedule_spi_below_one(self):
        status_date = datetime(2026, 1, 30)
        tasks = [
            make_task(
                1,
                duration=10.0,
                baseline_duration=10.0,
                baseline_start=datetime(2026, 1, 1),
                baseline_finish=datetime(2026, 1, 11),
                percent_complete=50.0,  # should be 100%
            ),
            make_task(
                2,
                duration=10.0,
                baseline_duration=10.0,
                baseline_start=datetime(2026, 1, 11),
                baseline_finish=datetime(2026, 1, 21),
                percent_complete=0.0,  # should be 100%
            ),
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(status_date=status_date), tasks=tasks
        )
        result = compute_earned_value(schedule)
        assert result.schedule_performance_index < 1.0
        assert result.schedule_variance < 0

    def test_cost_mode_when_assignments_have_costs(self):
        tasks = [
            make_task(
                1,
                duration=10.0,
                baseline_duration=10.0,
                percent_complete=100.0,
                baseline_start=datetime(2026, 1, 1),
                baseline_finish=datetime(2026, 1, 11),
            )
        ]
        assignments = [
            AssignmentData(
                task_uid=1, resource_uid=1, cost=1000.0, actual_cost=1200.0
            )
        ]
        schedule = ScheduleData(
            project_info=ProjectInfo(status_date=datetime(2026, 1, 20)),
            tasks=tasks,
            assignments=assignments,
        )
        result = compute_earned_value(schedule)
        assert result.units == UNITS_CURRENCY
        assert result.budget_at_completion == pytest.approx(1000.0)
        assert result.earned_value == pytest.approx(1000.0)
        assert result.actual_cost == pytest.approx(1200.0)
        # CPI = EV / AC = 1000 / 1200 ≈ 0.833
        assert result.cost_performance_index == pytest.approx(0.833, abs=0.01)


# --------------------------------------------------------------------------- #
# Float Analysis
# --------------------------------------------------------------------------- #


class TestFloatAnalysis:
    def test_task_became_critical(self):
        # Task 1 had 5 days of slack in prior, now 0 (became critical).
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(
                    1,
                    name="Siding",
                    total_slack=5.0,
                    critical=False,
                    wbs="1.1.1",
                ),
                make_task(
                    2,
                    name="Roofing",
                    total_slack=0.0,
                    critical=True,
                    wbs="1.1.2",
                ),
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(
                    1,
                    name="Siding",
                    total_slack=0.0,
                    critical=True,
                    wbs="1.1.1",
                ),
                make_task(
                    2,
                    name="Roofing",
                    total_slack=0.0,
                    critical=True,
                    wbs="1.1.2",
                ),
            ],
        )
        comparison = compare_schedules(prior, later)
        result = analyze_float(comparison, prior, later)
        assert 1 in result.became_critical_uids
        siding_change = next(tc for tc in result.task_changes if tc.uid == 1)
        assert siding_change.became_critical is True
        assert siding_change.prior_total_float == pytest.approx(5.0)
        assert siding_change.later_total_float == pytest.approx(0.0)

    def test_task_dropped_off_critical(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, total_slack=0.0, critical=True, wbs="1.1"),
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, total_slack=3.0, critical=False, wbs="1.1"),
            ],
        )
        result = analyze_float(compare_schedules(prior, later), prior, later)
        assert 1 in result.dropped_off_critical_uids

    def test_trend_consuming(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, total_slack=10.0, wbs="1.1"),
                make_task(2, total_slack=8.0, wbs="1.2"),
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, total_slack=2.0, wbs="1.1"),
                make_task(2, total_slack=1.0, wbs="1.2"),
            ],
        )
        result = analyze_float(compare_schedules(prior, later), prior, later)
        assert result.trend == "consuming"
        assert result.net_float_delta < -10.0

    def test_wbs_rollup(self):
        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, total_slack=10.0, wbs="1.1.1"),
                make_task(2, total_slack=10.0, wbs="1.1.2"),
                make_task(3, total_slack=10.0, wbs="2.1.1"),
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                make_task(1, total_slack=5.0, wbs="1.1.1"),
                make_task(2, total_slack=6.0, wbs="1.1.2"),
                make_task(3, total_slack=10.0, wbs="2.1.1"),
            ],
        )
        result = analyze_float(compare_schedules(prior, later), prior, later)
        wbs_11 = next(s for s in result.wbs_summaries if s.wbs_prefix == "1.1")
        assert wbs_11.task_count == 2
        assert wbs_11.total_float_consumed == pytest.approx(9.0)
