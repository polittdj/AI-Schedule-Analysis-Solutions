"""Unit tests for ``app.metrics.high_float`` — DCMA Metric 6.

Threshold authority: ``dcma-14-point-assessment §4.6``; DECM sheet
*Metrics*, Guideline 6. Boundary coverage per BUILD-PLAN §5 M6 AC 2
(44.0 WD does not flag; 44.01 WD does).
"""

from __future__ import annotations

import pytest

from app.engine.result import CPMResult, TaskCPMResult
from app.metrics.base import Severity
from app.metrics.exceptions import InvalidThresholdError, MissingCPMResultError
from app.metrics.high_float import HighFloatMetric, run_high_float
from app.metrics.options import MetricOptions
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot
from tests.fixtures.metric_schedules import (
    high_float_boundary_with_cpm,
    high_float_empty_with_cpm,
    high_float_excluded_population_with_cpm,
    high_float_fail_with_cpm,
    high_float_pass_with_cpm,
)


class TestContractRaisesWhenCPMMissing:
    """CPM-consuming metrics raise MissingCPMResultError on None
    rather than silently reporting PASS (M5 exception hierarchy
    contract)."""

    def test_missing_cpm_result_raises(self) -> None:
        sched, _ = high_float_pass_with_cpm()
        with pytest.raises(MissingCPMResultError):
            run_high_float(sched, cpm_result=None)


class TestEmptyAndExcluded:
    def test_empty_schedule_passes_vacuously(self) -> None:
        sched, cpm = high_float_empty_with_cpm()
        result = run_high_float(sched, cpm)
        assert result.severity is Severity.PASS
        assert result.denominator == 0
        assert result.numerator == 0
        assert "no eligible tasks" in result.notes

    def test_all_excluded_passes_vacuously(self) -> None:
        sched, cpm = high_float_excluded_population_with_cpm()
        result = run_high_float(sched, cpm)
        assert result.severity is Severity.PASS
        # 2 eligible live tasks after exclusions (UIDs 4, 5).
        assert result.denominator == 2
        assert result.numerator == 0


class TestHappyPath:
    def test_pass_schedule(self) -> None:
        sched, cpm = high_float_pass_with_cpm()
        result = run_high_float(sched, cpm)
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 20
        assert result.offenders == ()


class TestGoldenFail:
    def test_golden_fail_ratio(self) -> None:
        sched, cpm = high_float_fail_with_cpm()
        result = run_high_float(sched, cpm)
        assert result.severity is Severity.FAIL
        assert result.numerator == 2
        assert result.denominator == 20
        assert result.computed_value == pytest.approx(10.0)

    def test_offender_uids_match_seeded_flags(self) -> None:
        sched, cpm = high_float_fail_with_cpm()
        result = run_high_float(sched, cpm)
        offender_uids = sorted(o.unique_id for o in result.offenders)
        # UIDs 5 and 15 carry TF=21125 min in the fixture.
        assert offender_uids == [5, 15]

    def test_offenders_carry_name_and_tf_days(self) -> None:
        sched, cpm = high_float_fail_with_cpm()
        result = run_high_float(sched, cpm)
        for o in result.offenders:
            assert o.unique_id > 0
            assert o.name
            assert "WD" in o.value
            # 21125 min / 480 min/WD = 44.01 WD (rounded to 2 dp).
            assert "44.01" in o.value


class TestBoundarySemantics:
    """AC 2 — strict ``>`` comparison.

    A task with TF = 44.0 WD does NOT flag; 44.01 WD does.
    """

    def test_44_wd_exactly_does_not_flag(self) -> None:
        sched, cpm = high_float_boundary_with_cpm()
        result = run_high_float(sched, cpm)
        # 1 task at 21121 min flags; 1 task at 21120 min (exactly
        # 44.0 WD) must NOT flag per AC 2.
        assert result.numerator == 1
        # Offender must be UID 15 (21121 min), not UID 5 (21120 min).
        assert {o.unique_id for o in result.offenders} == {15}

    def test_custom_threshold_days_lowers_the_ceiling(self) -> None:
        """If a client pins the WD ceiling at 30, the boundary task
        at 44 WD flags."""
        sched, cpm = high_float_boundary_with_cpm()
        result = run_high_float(
            sched, cpm,
            MetricOptions(high_float_threshold_working_days=30.0),
        )
        assert result.numerator == 2
        assert result.threshold.is_overridden is True


class TestCycleSkippedExclusion:
    """A cycle-skipped task has no defensible slack — excluded from
    the eligible population rather than counted at zero. Otherwise
    the cycle-broken branch would silently look clean."""

    def test_cycle_skipped_tasks_drop_from_denominator(self) -> None:
        tasks = [Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
                 for i in range(1, 6)]
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="cycle-sched",
            tasks=tasks,
            relations=[],
        )
        # UID 3 is skipped; give the others clean non-flagging TF.
        cpm = CPMResult(
            tasks={
                1: TaskCPMResult(unique_id=1, total_slack_minutes=0),
                2: TaskCPMResult(unique_id=2, total_slack_minutes=0),
                3: TaskCPMResult(
                    unique_id=3,
                    total_slack_minutes=0,
                    skipped_due_to_cycle=True,
                ),
                4: TaskCPMResult(unique_id=4, total_slack_minutes=0),
                5: TaskCPMResult(unique_id=5, total_slack_minutes=0),
            },
            cycles_detected=frozenset({3}),
        )
        result = run_high_float(sched, cpm)
        assert result.denominator == 4
        assert 3 not in {o.unique_id for o in result.offenders}


class TestCalendarScaling:
    """Non-8h/day calendar must be honored for the minutes→WD
    conversion — a hard-coded 480 would misfire."""

    def test_10_hour_day_calendar_rescales_threshold(self) -> None:
        cal = Calendar(name="Ten", hours_per_day=10.0)
        tasks = [Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
                 for i in range(1, 11)]
        sched = Schedule(
project_calendar_hours_per_day=8.0,name="cal10", tasks=tasks, calendars=[cal],
                         default_calendar_name="Ten")
        # 45 WD on a 10h/day calendar = 45 * 10 * 60 = 27000 min.
        # 44 WD on a 10h/day calendar = 26400 min.
        cpm = CPMResult(
            tasks={
                **{i: TaskCPMResult(unique_id=i, total_slack_minutes=0)
                   for i in range(1, 10)},
                10: TaskCPMResult(unique_id=10, total_slack_minutes=27000),
            }
        )
        result = run_high_float(sched, cpm)
        assert result.numerator == 1
        # UID 10 flags because 27000 / 600 = 45 WD > 44 WD ceiling.
        assert {o.unique_id for o in result.offenders} == {10}


class TestFrozenContractAndProvenance:
    def test_result_carries_skill_and_decm_citation(self) -> None:
        sched, cpm = high_float_pass_with_cpm()
        result = run_high_float(sched, cpm)
        assert result.threshold.source_skill_section == (
            "dcma-14-point-assessment §4.6"
        )
        assert "High Float" in result.threshold.source_decm_row

    def test_two_invocations_produce_equal_results(self) -> None:
        s, c = high_float_fail_with_cpm()
        r1 = run_high_float(s, c)
        r2 = run_high_float(s, c)
        assert r1 == r2

    def test_schedule_not_mutated(self) -> None:
        sched, cpm = high_float_fail_with_cpm()
        before = sched.model_dump_json()
        run_high_float(sched, cpm)
        assert sched.model_dump_json() == before

    def test_cpm_result_not_mutated(self) -> None:
        """Metric reads ``cpm_result.tasks[...]`` without mutating
        the CPMResult or its tasks dict (BUILD-PLAN §5 M4 AC10)."""
        sched, cpm = high_float_fail_with_cpm()
        before = cpm_result_snapshot(cpm)
        run_high_float(sched, cpm)
        assert cpm_result_snapshot(cpm) == before

    def test_class_wrapper_matches_function(self) -> None:
        sched, cpm = high_float_fail_with_cpm()
        wrapper_result = HighFloatMetric().run(sched, cpm_result=cpm)
        assert wrapper_result == run_high_float(sched, cpm)


class TestLoeByNameFallback:
    """Closes the LOE name-pattern fallback branch in
    :func:`app.metrics.high_float._is_loe` (lines 75-76)."""

    def test_loe_name_pattern_fallback_excludes_task(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="loe-name",
            tasks=[
                Task(
                    unique_id=1, task_id=1,
                    name="Project Management LOE",
                    duration_minutes=480,
                ),
                Task(unique_id=2, task_id=2, name="Live", duration_minutes=480),
            ],
        )
        cpm = CPMResult(
            tasks={
                1: TaskCPMResult(unique_id=1, total_slack_minutes=0),
                2: TaskCPMResult(unique_id=2, total_slack_minutes=0),
            }
        )
        result = run_high_float(
            sched, cpm,
            MetricOptions(loe_name_patterns=("loe",)),
        )
        # The LOE-by-name task is excluded → denominator=1, numerator=0.
        assert result.denominator == 1
        assert result.numerator == 0


class TestCalendarFallbackToFirst:
    """Closes the mismatched-default-calendar fallback branch in
    :func:`app.metrics.high_float._calendar_hours_per_day` (line
    102) — when ``default_calendar_name`` does not match any
    calendar, the helper falls back to the first calendar rather
    than the hard-coded 8.0 final fallback."""

    def test_mismatched_default_calendar_falls_back_to_first(self) -> None:
        # default_calendar_name points at a missing calendar → the
        # helper must return the first calendar's hours_per_day (10h)
        # rather than the final 8.0 fallback. 44 WD @ 10h = 26400 min;
        # a task at 26401 min therefore flags.
        cal = Calendar(name="First", hours_per_day=10.0)
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="mismatched-cal",
            default_calendar_name="Does Not Exist",
            tasks=[
                Task(unique_id=1, task_id=1, name="T", duration_minutes=480),
            ],
            calendars=[cal],
        )
        cpm = CPMResult(
            tasks={1: TaskCPMResult(unique_id=1, total_slack_minutes=26401)}
        )
        result = run_high_float(sched, cpm)
        assert result.severity is Severity.FAIL
        assert result.numerator == 1
        # Note echoes hours_per_day from the first-calendar fallback,
        # not 8.0.
        assert "hours_per_day=10.0" in result.notes


class TestInvalidOptions:
    def test_negative_pct_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(high_float_threshold_pct=-1.0)

    def test_negative_wd_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(high_float_threshold_working_days=-5.0)

    def test_non_numeric_wd_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(
                high_float_threshold_working_days="forty-four",  # type: ignore[arg-type]
            )


def test_notes_carry_hours_per_day_for_narrative_layer() -> None:
    sched, cpm = high_float_fail_with_cpm()
    result = run_high_float(sched, cpm)
    assert "hours_per_day" in result.notes
    assert "44.0 WD" in result.notes
