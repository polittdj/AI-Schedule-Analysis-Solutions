"""Unit tests for ``app.metrics.high_duration`` — DCMA Metric 8.

Threshold authority: ``dcma-14-point-assessment §4.8``; DECM sheet
*Metrics*, Guideline 6. Boundary coverage per BUILD-PLAN §5 M6
AC 2 / AC 4 (44.0 WD does not flag; rolling-wave tasks are exempt).
"""

from __future__ import annotations

import pytest

from app.metrics.base import Severity
from app.metrics.exceptions import InvalidThresholdError
from app.metrics.high_duration import HighDurationMetric, run_high_duration
from app.metrics.options import MetricOptions
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.metric_schedules import (
    empty_schedule,
    high_duration_boundary_schedule,
    high_duration_excluded_population_schedule,
    high_duration_golden_fail_schedule,
    high_duration_pass_schedule,
    high_duration_rolling_wave_schedule,
)


class TestEmptyAndExcluded:
    def test_empty_schedule_passes_vacuously(self) -> None:
        result = run_high_duration(empty_schedule())
        assert result.severity is Severity.PASS
        assert result.denominator == 0
        assert result.numerator == 0
        assert "no eligible tasks" in result.notes

    def test_all_excluded_denominator_is_live_tasks_only(self) -> None:
        result = run_high_duration(
            high_duration_excluded_population_schedule()
        )
        assert result.severity is Severity.PASS
        # 3 excluded (summary/LOE/done) + 2 eligible (1 WD each).
        assert result.denominator == 2
        assert result.numerator == 0


class TestHappyPath:
    def test_pass_schedule(self) -> None:
        result = run_high_duration(high_duration_pass_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 20
        assert result.offenders == ()


class TestGoldenFail:
    def test_golden_fail_ratio(self) -> None:
        result = run_high_duration(high_duration_golden_fail_schedule())
        assert result.severity is Severity.FAIL
        assert result.numerator == 3
        assert result.denominator == 20
        assert result.computed_value == pytest.approx(15.0)

    def test_offender_uids_match_seeded_long_durations(self) -> None:
        result = run_high_duration(high_duration_golden_fail_schedule())
        offender_uids = sorted(o.unique_id for o in result.offenders)
        assert offender_uids == [4, 10, 16]

    def test_offenders_carry_duration_days(self) -> None:
        result = run_high_duration(high_duration_golden_fail_schedule())
        for o in result.offenders:
            assert o.unique_id > 0
            assert o.name
            assert "WD" in o.value
            # 24000 min / 480 min per WD = 50.00 WD.
            assert "50.00" in o.value


class TestBoundarySemantics:
    """AC 2 / AC 4 — strict ``>`` and rolling-wave exemption."""

    def test_44_wd_exactly_does_not_flag(self) -> None:
        result = run_high_duration(high_duration_boundary_schedule())
        # UID 1: 44 WD exactly → no flag. UID 2: 21121 min → flag.
        assert result.numerator == 1
        assert {o.unique_id for o in result.offenders} == {2}
        assert result.computed_value == pytest.approx(5.0)
        # 5% exactly is <= 5% → PASS.
        assert result.severity is Severity.PASS


class TestRollingWaveExemption:
    """AC 4 — ``is_rolling_wave=True`` exempts a task from the
    numerator; the same task without the flag is counted."""

    def test_rolling_wave_task_is_exempt(self) -> None:
        result = run_high_duration(high_duration_rolling_wave_schedule())
        # UID 5 (rolling wave, 60 WD) — exempt.
        # UID 6 (plain, 60 WD) — counted.
        assert {o.unique_id for o in result.offenders} == {6}
        assert result.numerator == 1
        assert result.denominator == 20  # exemption does not shrink the pool

    def test_rolling_wave_exemption_cites_ac4_semantics(self) -> None:
        """A one-task schedule — duration 60 WD, is_rolling_wave=True —
        must yield numerator=0. Same task with the flag off must
        yield numerator=1."""
        exempt = Task(
            unique_id=1, task_id=1, name="RW",
            duration_minutes=28800, is_rolling_wave=True,
        )
        not_exempt = Task(
            unique_id=1, task_id=1, name="RW-not",
            duration_minutes=28800,
        )
        r_exempt = run_high_duration(
            Schedule(project_calendar_hours_per_day=8.0, name="a", tasks=[exempt])
        )
        r_not_exempt = run_high_duration(
            Schedule(project_calendar_hours_per_day=8.0, name="b", tasks=[not_exempt])
        )
        assert r_exempt.numerator == 0
        assert r_not_exempt.numerator == 1


class TestRemainingDurationPreferred:
    """§4.8 — Metric 8 scores remaining duration. A task with 60 WD
    total duration but only 30 WD remaining must NOT flag."""

    def test_short_remaining_overrides_long_total(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="remaining-wins",
            tasks=[
                Task(
                    unique_id=1,
                    task_id=1,
                    name="Partially complete",
                    duration_minutes=28800,  # 60 WD total
                    remaining_duration_minutes=14400,  # 30 WD remaining
                    actual_duration_minutes=14400,
                    percent_complete=50.0,
                )
            ],
        )
        result = run_high_duration(sched)
        assert result.numerator == 0


class TestCustomThresholdOverride:
    def test_custom_wd_ceiling_flips_pass_to_fail(self) -> None:
        result = run_high_duration(
            high_duration_boundary_schedule(),
            MetricOptions(high_duration_threshold_working_days=30.0),
        )
        # Both boundary tasks now exceed 30 WD → 2/20 = 10% FAIL.
        assert result.numerator == 2
        assert result.severity is Severity.FAIL
        assert result.threshold.is_overridden is True

    def test_custom_pct_threshold_changes_pass_fail(self) -> None:
        result = run_high_duration(
            high_duration_boundary_schedule(),
            MetricOptions(high_duration_threshold_pct=4.0),
        )
        # 5% > 4% → FAIL.
        assert result.severity is Severity.FAIL


class TestCalendarScaling:
    def test_10h_day_scales_threshold(self) -> None:
        cal = Calendar(name="Ten", hours_per_day=10.0)
        tasks = [
            Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=600)
            for i in range(1, 20)
        ]
        # UID 20 carries 45 WD on a 10h/day calendar = 45*600 = 27000 min.
        tasks.append(
            Task(unique_id=20, task_id=20, name="Long",
                 duration_minutes=27000)
        )
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="cal10", tasks=tasks, calendars=[cal],
            default_calendar_name="Ten",
        )
        result = run_high_duration(sched)
        assert result.numerator == 1
        assert {o.unique_id for o in result.offenders} == {20}


class TestFrozenContractAndProvenance:
    def test_result_carries_skill_and_decm_citation(self) -> None:
        result = run_high_duration(high_duration_pass_schedule())
        assert result.threshold.source_skill_section == (
            "dcma-14-point-assessment §4.8"
        )
        assert "High Duration" in result.threshold.source_decm_row

    def test_two_invocations_produce_equal_results(self) -> None:
        s1 = high_duration_golden_fail_schedule()
        s2 = high_duration_golden_fail_schedule()
        assert run_high_duration(s1) == run_high_duration(s2)

    def test_schedule_not_mutated(self) -> None:
        sched = high_duration_golden_fail_schedule()
        before = sched.model_dump_json()
        run_high_duration(sched)
        assert sched.model_dump_json() == before

    def test_class_wrapper_matches_function(self) -> None:
        sched = high_duration_golden_fail_schedule()
        assert HighDurationMetric().run(sched) == run_high_duration(sched)


class TestInvalidOptions:
    def test_negative_wd_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(high_duration_threshold_working_days=-10.0)

    def test_over_100_pct_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(high_duration_threshold_pct=200.0)


def test_notes_carry_wd_ceiling_and_hours_per_day() -> None:
    result = run_high_duration(high_duration_golden_fail_schedule())
    assert "hours_per_day" in result.notes
    assert "44.0 WD" in result.notes


class TestExclusionHelperCoverage:
    """Closes residual LOE/calendar-fallback branches."""

    def test_loe_by_name_fallback_drops_offender(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="loe-name",
            tasks=[
                Task(
                    unique_id=1, task_id=1,
                    name="Project Management LOE",
                    duration_minutes=28800,  # 60 WD — would flag.
                ),
                Task(unique_id=2, task_id=2, name="Live", duration_minutes=480),
            ],
        )
        result = run_high_duration(
            sched, MetricOptions(loe_name_patterns=("loe",))
        )
        assert result.denominator == 1
        assert result.numerator == 0

    def test_mismatched_default_calendar_falls_back_to_first(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="mismatched",
            default_calendar_name="Missing",
            tasks=[
                Task(unique_id=1, task_id=1, name="T",
                     duration_minutes=28800),
            ],
            calendars=[Calendar(name="Other", hours_per_day=8.0)],
        )
        result = run_high_duration(sched)
        assert result.severity is Severity.FAIL

    def test_schedule_without_calendars_falls_back_to_8h(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="no-cal",
            tasks=[
                Task(unique_id=1, task_id=1, name="T",
                     duration_minutes=28800),
            ],
            calendars=[],
        )
        result = run_high_duration(sched)
        assert result.severity is Severity.FAIL
