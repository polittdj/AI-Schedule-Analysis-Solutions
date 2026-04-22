"""Unit tests for DCMA Metric 9 (Invalid Dates) — M7 Block 2.

Coverage: the three invalid-date kinds (A/B/C), the no-offender PASS
path, the excluded-population guard (milestones + summary), the
LOE-is-universal guard, and the no-status-date reduced-mode path.
"""

from __future__ import annotations

from app.metrics import MetricOptions, Severity
from app.metrics.invalid_dates import (
    InvalidDateKind,
    InvalidDatesMetric,
    run_invalid_dates,
)
from tests.fixtures.metric_schedules import (
    invalid_dates_actual_after_status_schedule,
    invalid_dates_excluded_population_schedule,
    invalid_dates_forecast_before_status_schedule,
    invalid_dates_future_planned_task_schedule,
    invalid_dates_loe_flagged_schedule,
    invalid_dates_no_status_date_schedule,
    invalid_dates_pass_schedule,
    invalid_dates_temporal_inversion_schedule,
)


class TestHappyPath:
    def test_well_formed_schedule_passes(self) -> None:
        r = run_invalid_dates(invalid_dates_pass_schedule())
        assert r.severity is Severity.PASS
        assert r.numerator == 0
        assert r.denominator == 10
        assert r.computed_value == 0.0
        assert r.offenders == ()

    def test_empty_schedule_passes_vacuously(self) -> None:
        from tests.fixtures.metric_schedules import empty_schedule

        r = run_invalid_dates(empty_schedule())
        assert r.severity is Severity.PASS
        assert r.denominator == 0
        assert "no eligible tasks" in r.notes


class TestRuleA_ActualAfterStatus:
    def test_actual_after_status_flags(self) -> None:
        r = run_invalid_dates(invalid_dates_actual_after_status_schedule())
        assert r.severity is Severity.FAIL
        assert r.numerator == 1
        assert r.denominator == 3
        assert {o.unique_id for o in r.offenders} == {1}
        value = r.offenders[0].value
        assert InvalidDateKind.ACTUAL_AFTER_STATUS.value in value

    def test_actual_start_after_status_also_flags(self) -> None:
        # A task with actual_start after status_date (rare but
        # possible — data-entry error on a not-yet-started task).
        from datetime import timedelta

        from app.models.calendar import Calendar
        from app.models.schedule import Schedule
        from app.models.task import Task
        from tests.fixtures.metric_schedules import STATUS_DATE

        tasks = [
            Task(
                unique_id=1,
                task_id=1,
                name="FutureActualStart",
                duration_minutes=480,
                actual_start=STATUS_DATE + timedelta(days=2),  # after
            ),
        ]
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="rule_a_start",
            status_date=STATUS_DATE,
            project_start=STATUS_DATE - timedelta(days=30),
            tasks=tasks,
            calendars=[Calendar(name="Standard")],
        )
        r = run_invalid_dates(sched)
        assert r.severity is Severity.FAIL
        assert 1 in {o.unique_id for o in r.offenders}


class TestRuleB_ForecastBeforeStatus:
    def test_stale_forecast_flags(self) -> None:
        r = run_invalid_dates(invalid_dates_forecast_before_status_schedule())
        assert r.severity is Severity.FAIL
        assert r.numerator == 1
        assert r.denominator == 3
        offender = next(o for o in r.offenders if o.unique_id == 1)
        assert (
            InvalidDateKind.FORECAST_BEFORE_STATUS.value in offender.value
        )

    def test_in_progress_task_not_flagged_by_rule_b(self) -> None:
        # T3 in the fixture is in-progress; rule B only applies to
        # not-yet-started incomplete work.
        r = run_invalid_dates(invalid_dates_forecast_before_status_schedule())
        flagged_uids = {o.unique_id for o in r.offenders}
        assert 3 not in flagged_uids

    def test_future_planned_task_not_flagged(self) -> None:
        # Purely planned unstarted task with all dates after status
        # MUST NOT flag — that's the fixture regression.
        r = run_invalid_dates(invalid_dates_future_planned_task_schedule())
        assert r.severity is Severity.PASS
        assert r.numerator == 0


class TestRuleC_TemporalInversion:
    def test_inversion_flags(self) -> None:
        r = run_invalid_dates(invalid_dates_temporal_inversion_schedule())
        assert r.severity is Severity.FAIL
        assert r.numerator == 1
        assert r.denominator == 2
        offender = next(o for o in r.offenders if o.unique_id == 1)
        assert (
            InvalidDateKind.ACTUAL_FINISH_BEFORE_ACTUAL_START.value
            in offender.value
        )


class TestExclusions:
    def test_milestones_and_summaries_excluded(self) -> None:
        # Fixture seeds a milestone and a summary with actuals AFTER
        # status_date; only the eligible clean task should count, and
        # there should be zero offenders.
        r = run_invalid_dates(invalid_dates_excluded_population_schedule())
        assert r.severity is Severity.PASS
        # Denominator excludes milestone (UID 100) and summary (UID 1);
        # only T2 remains eligible.
        assert r.denominator == 1
        assert r.numerator == 0
        assert {o.unique_id for o in r.offenders} == set()

    def test_loe_task_is_flagged(self) -> None:
        # §3.12: Metric 9 applies to LOE. The LOE task has an actual
        # past the status date and MUST be in the offender list.
        r = run_invalid_dates(invalid_dates_loe_flagged_schedule())
        assert r.severity is Severity.FAIL
        assert 1 in {o.unique_id for o in r.offenders}


class TestNoStatusDate:
    def test_reduced_mode_runs_inversion_only(self) -> None:
        r = run_invalid_dates(invalid_dates_no_status_date_schedule())
        # Inversion still detected.
        assert r.severity is Severity.FAIL
        assert r.numerator == 1
        assert 1 in {o.unique_id for o in r.offenders}
        assert "no status_date" in r.notes


class TestOverrides:
    def test_threshold_override_is_recorded(self) -> None:
        r = run_invalid_dates(
            invalid_dates_actual_after_status_schedule(),
            options=MetricOptions(invalid_dates_threshold_pct=50.0),
        )
        # 1/3 ≈ 33% < 50% → PASS under override
        assert r.severity is Severity.PASS
        assert r.threshold.is_overridden is True

    def test_threshold_override_still_flags_over(self) -> None:
        r = run_invalid_dates(
            invalid_dates_actual_after_status_schedule(),
            options=MetricOptions(invalid_dates_threshold_pct=10.0),
        )
        # 1/3 ≈ 33% > 10% → FAIL
        assert r.severity is Severity.FAIL


class TestProvenance:
    def test_threshold_and_source_populated(self) -> None:
        r = run_invalid_dates(invalid_dates_pass_schedule())
        assert r.metric_id == "DCMA-9"
        assert r.threshold.source_skill_section == "dcma-14-point-assessment §4.9"
        assert "Invalid Dates" in r.threshold.source_decm_row
        assert r.threshold.value == 0.0
        assert r.threshold.direction == "<="


class TestBaseMetricWrapper:
    def test_class_form_matches_functional_form(self) -> None:
        sched = invalid_dates_actual_after_status_schedule()
        r_fn = run_invalid_dates(sched)
        r_cls = InvalidDatesMetric().run(sched)
        assert r_fn == r_cls


class TestMutationInvariance:
    def test_schedule_unchanged(self) -> None:
        sched = invalid_dates_actual_after_status_schedule()
        before = sched.model_dump_json()
        run_invalid_dates(sched)
        assert sched.model_dump_json() == before
