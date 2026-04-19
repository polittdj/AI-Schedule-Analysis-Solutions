"""Unit tests for ``app.metrics.negative_float`` — DCMA Metric 7.

Threshold authority: ``dcma-14-point-assessment §4.7``; DECM sheet
*Metrics*, Guideline 6 (Negative Float). BUILD-PLAN §5 M6 AC 3 pins
the 0% threshold as absolute.
"""

from __future__ import annotations

import pytest

from app.engine.result import CPMResult, TaskCPMResult
from app.metrics.base import Severity
from app.metrics.exceptions import InvalidThresholdError, MissingCPMResultError
from app.metrics.negative_float import NegativeFloatMetric, run_negative_float
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot
from tests.fixtures.metric_schedules import (
    negative_float_empty_with_cpm,
    negative_float_fail_with_cpm,
    negative_float_multi_fail_with_cpm,
    negative_float_pass_with_cpm,
    negative_float_with_cycle_skipped_with_cpm,
)


class TestContractRaisesWhenCPMMissing:
    def test_missing_cpm_result_raises(self) -> None:
        sched, _ = negative_float_pass_with_cpm()
        with pytest.raises(MissingCPMResultError):
            run_negative_float(sched, cpm_result=None)


class TestEmptyAndHappyPath:
    def test_empty_schedule_passes_vacuously(self) -> None:
        sched, cpm = negative_float_empty_with_cpm()
        result = run_negative_float(sched, cpm)
        assert result.severity is Severity.PASS
        assert result.denominator == 0
        assert "no eligible tasks" in result.notes

    def test_pass_schedule(self) -> None:
        sched, cpm = negative_float_pass_with_cpm()
        result = run_negative_float(sched, cpm)
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 10
        assert result.computed_value == 0.0


class TestAbsoluteThreshold:
    """AC 3 — any negative-float task flags (0% is absolute)."""

    def test_single_negative_float_task_fails(self) -> None:
        sched, cpm = negative_float_fail_with_cpm()
        result = run_negative_float(sched, cpm)
        assert result.severity is Severity.FAIL
        assert result.numerator == 1
        assert result.denominator == 20
        assert result.computed_value == pytest.approx(5.0)

    def test_offender_carries_tf_days_negative(self) -> None:
        sched, cpm = negative_float_fail_with_cpm()
        result = run_negative_float(sched, cpm)
        assert {o.unique_id for o in result.offenders} == {7}
        # -480 min / 480 = -1.0 WD.
        assert result.offenders[0].value == "-1.00 WD"


class TestMultiOffender:
    """Multiple offenders must all appear; ordering follows
    task-insertion order, which is deterministic by UniqueID in the
    fixture builder."""

    def test_three_negative_float_offenders(self) -> None:
        sched, cpm = negative_float_multi_fail_with_cpm()
        result = run_negative_float(sched, cpm)
        assert result.severity is Severity.FAIL
        assert result.numerator == 3
        offender_uids = [o.unique_id for o in result.offenders]
        assert offender_uids == [3, 8, 17]

    def test_offender_tf_days_match_seeded_values(self) -> None:
        sched, cpm = negative_float_multi_fail_with_cpm()
        result = run_negative_float(sched, cpm)
        by_uid = {o.unique_id: o.value for o in result.offenders}
        assert by_uid == {
            3: "-0.50 WD",
            8: "-2.00 WD",
            17: "-5.00 WD",
        }


class TestCycleSkippedExclusion:
    def test_cycle_skipped_tasks_drop_from_denominator(self) -> None:
        sched, cpm = negative_float_with_cycle_skipped_with_cpm()
        result = run_negative_float(sched, cpm)
        # 9 tasks eligible (1 skipped), 0 negative → PASS.
        assert result.denominator == 9
        assert result.severity is Severity.PASS


class TestCustomThresholdOverride:
    """A client who permits a tiny negative-float share turns the
    single-offender case into PASS when 5% is within the tolerance."""

    def test_5pct_override_flips_single_offender_to_pass(self) -> None:
        sched, cpm = negative_float_fail_with_cpm()
        result = run_negative_float(
            sched, cpm,
            MetricOptions(negative_float_threshold_pct=5.0),
        )
        assert result.severity is Severity.PASS
        assert result.threshold.is_overridden is True
        assert result.threshold.value == 5.0


class TestExclusionProtocol:
    """§3 exclusions drop summary / LOE / 100%-complete tasks."""

    def test_excluded_negative_float_task_does_not_flag(self) -> None:
        sched = Schedule(
            name="excluded-neg",
            tasks=[
                Task(
                    unique_id=1, task_id=1, name="Summary neg",
                    duration_minutes=480, is_summary=True,
                ),
                Task(unique_id=2, task_id=2, name="Live", duration_minutes=480),
            ],
        )
        cpm = CPMResult(
            tasks={
                1: TaskCPMResult(unique_id=1, total_slack_minutes=-480),
                2: TaskCPMResult(unique_id=2, total_slack_minutes=0),
            }
        )
        result = run_negative_float(sched, cpm)
        assert result.denominator == 1
        assert result.numerator == 0


class TestFrozenContractAndProvenance:
    def test_result_carries_skill_and_decm_citation(self) -> None:
        sched, cpm = negative_float_pass_with_cpm()
        result = run_negative_float(sched, cpm)
        assert result.threshold.source_skill_section == (
            "dcma-14-point-assessment §4.7"
        )
        assert "Negative Float" in result.threshold.source_decm_row

    def test_two_invocations_produce_equal_results(self) -> None:
        s, c = negative_float_fail_with_cpm()
        assert run_negative_float(s, c) == run_negative_float(s, c)

    def test_schedule_not_mutated(self) -> None:
        sched, cpm = negative_float_fail_with_cpm()
        before = sched.model_dump_json()
        run_negative_float(sched, cpm)
        assert sched.model_dump_json() == before

    def test_cpm_result_not_mutated(self) -> None:
        """Metric reads ``cpm_result.tasks[...]`` without mutating
        the CPMResult or its tasks dict (BUILD-PLAN §5 M4 AC10)."""
        sched, cpm = negative_float_fail_with_cpm()
        before = cpm_result_snapshot(cpm)
        run_negative_float(sched, cpm)
        assert cpm_result_snapshot(cpm) == before

    def test_class_wrapper_matches_function(self) -> None:
        s, c = negative_float_fail_with_cpm()
        assert NegativeFloatMetric().run(s, cpm_result=c) == run_negative_float(s, c)


class TestInvalidOptions:
    def test_negative_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(negative_float_threshold_pct=-0.5)

    def test_over_100_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(negative_float_threshold_pct=150.0)


class TestExclusionHelperCoverage:
    """Closes residual exclusion-path branches (LOE name pattern,
    100%-complete exclusion, mismatched-default-calendar fallback)."""

    def test_loe_name_pattern_fallback_excludes_task(self) -> None:
        sched = Schedule(
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
                1: TaskCPMResult(unique_id=1, total_slack_minutes=-240),
                2: TaskCPMResult(unique_id=2, total_slack_minutes=0),
            }
        )
        result = run_negative_float(
            sched, cpm,
            MetricOptions(loe_name_patterns=("loe",)),
        )
        # The LOE-by-name task is excluded → denominator=1, numerator=0.
        assert result.denominator == 1
        assert result.numerator == 0

    def test_completed_task_excluded_from_denominator(self) -> None:
        sched = Schedule(
            name="done-excluded",
            tasks=[
                Task(
                    unique_id=1, task_id=1, name="Done",
                    duration_minutes=480, percent_complete=100.0,
                ),
                Task(unique_id=2, task_id=2, name="Live", duration_minutes=480),
            ],
        )
        cpm = CPMResult(
            tasks={
                1: TaskCPMResult(unique_id=1, total_slack_minutes=-240),
                2: TaskCPMResult(unique_id=2, total_slack_minutes=0),
            }
        )
        result = run_negative_float(sched, cpm)
        assert result.denominator == 1
        assert result.numerator == 0

    def test_mismatched_default_calendar_falls_back_to_first(self) -> None:
        """When default_calendar_name points at a missing calendar,
        the metric falls back to the first calendar rather than
        exploding — narrative layer may annotate the mismatch."""
        from app.models.calendar import Calendar
        sched = Schedule(
            name="mismatched-cal",
            default_calendar_name="Does Not Exist",
            tasks=[
                Task(unique_id=1, task_id=1, name="T", duration_minutes=480),
            ],
            calendars=[Calendar(name="Other", hours_per_day=8.0)],
        )
        cpm = CPMResult(
            tasks={1: TaskCPMResult(unique_id=1, total_slack_minutes=-480)}
        )
        result = run_negative_float(sched, cpm)
        assert result.severity is Severity.FAIL
        assert result.numerator == 1

    def test_schedule_without_calendars_falls_back_to_8h(self) -> None:
        """Final fallback — no calendars at all, helper returns 8.0."""
        sched = Schedule(
            name="no-cal",
            tasks=[Task(unique_id=1, task_id=1, name="T", duration_minutes=480)],
            calendars=[],
        )
        cpm = CPMResult(
            tasks={1: TaskCPMResult(unique_id=1, total_slack_minutes=-480)}
        )
        result = run_negative_float(sched, cpm)
        assert result.severity is Severity.FAIL
        # -480 min at 8h/day = -1.00 WD.
        assert result.offenders[0].value == "-1.00 WD"
