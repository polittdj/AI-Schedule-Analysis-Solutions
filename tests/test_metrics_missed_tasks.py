"""Unit tests for DCMA Metric 11 (Missed Tasks) — M7 Block 3.

Coverage: known-offender golden, rolling-wave exemption, LOE
exemption, no-baseline and no-status-date indicator-only paths,
mutation-invariance.
"""

from __future__ import annotations

from datetime import timedelta

from app.metrics import MetricOptions, Severity
from app.metrics.missed_tasks import MissedTasksMetric, run_missed_tasks
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.metric_schedules import (
    STATUS_DATE,
    missed_tasks_known_schedule,
    missed_tasks_loe_exempt_schedule,
    missed_tasks_no_baseline_schedule,
    missed_tasks_no_status_date_schedule,
    missed_tasks_rolling_wave_exempt_schedule,
)


class TestKnownGolden:
    def test_numerator_denominator_are_hand_calculable(self) -> None:
        r = run_missed_tasks(missed_tasks_known_schedule())
        # 10 baseline-due tasks (T1..T10); T3 missed (no actual_finish);
        # T11..T15 have baseline after status → excluded from denom.
        assert r.denominator == 10
        assert r.numerator == 1
        assert {o.unique_id for o in r.offenders} == {3}
        assert r.severity is Severity.FAIL  # 10% > 5%
        assert r.computed_value == 10.0

    def test_offender_evidence_includes_baseline_and_status(self) -> None:
        r = run_missed_tasks(missed_tasks_known_schedule())
        offender = next(o for o in r.offenders if o.unique_id == 3)
        assert "baseline_finish" in offender.value
        assert "status_date" in offender.value


class TestRollingWaveExemption:
    def test_rolling_wave_task_is_exempt_from_numerator(self) -> None:
        r = run_missed_tasks(missed_tasks_rolling_wave_exempt_schedule())
        assert r.severity is Severity.PASS
        assert r.numerator == 0
        # Denominator stays 5 — exemption is a numerator detour.
        assert r.denominator == 5


class TestLoeExemption:
    def test_loe_task_is_exempt_from_numerator(self) -> None:
        r = run_missed_tasks(missed_tasks_loe_exempt_schedule())
        assert r.severity is Severity.PASS
        assert r.numerator == 0
        assert r.denominator == 5

    def test_loe_name_pattern_exempts_numerator(self) -> None:
        # Same fixture but drop the is_loe flag — name-based fallback
        # via MetricOptions.loe_name_patterns still exempts.
        sched = missed_tasks_loe_exempt_schedule()
        new_tasks = []
        for t in sched.tasks:
            new_t = t.model_copy(update={
                "is_loe": False,
                "name": (
                    f"T{t.unique_id} LOE tag" if t.unique_id == 3 else t.name
                ),
            })
            new_tasks.append(new_t)
        new_sched = Schedule(
            name=sched.name,
            status_date=sched.status_date,
            project_start=sched.project_start,
            tasks=new_tasks,
            calendars=sched.calendars,
        )
        r = run_missed_tasks(
            new_sched,
            options=MetricOptions(loe_name_patterns=("loe tag",)),
        )
        assert r.severity is Severity.PASS
        assert r.numerator == 0


class TestNoBaseline:
    def test_no_baseline_returns_indicator_only(self) -> None:
        r = run_missed_tasks(missed_tasks_no_baseline_schedule())
        assert r.severity is Severity.WARN
        assert r.computed_value is None
        assert "no baseline available" in r.notes
        assert r.numerator == 0
        assert r.denominator == 0

    def test_no_baseline_does_not_raise(self) -> None:
        # Explicit guard — §2.15 says raise is reserved for CPM
        # prerequisites; missing baseline must not raise.
        run_missed_tasks(missed_tasks_no_baseline_schedule())


class TestNoStatusDate:
    def test_missing_status_date_indicator_only(self) -> None:
        r = run_missed_tasks(missed_tasks_no_status_date_schedule())
        assert r.severity is Severity.WARN
        assert r.computed_value is None
        assert "no status_date" in r.notes


class TestVacuousPass:
    def test_no_baseline_due_tasks_returns_pass(self) -> None:
        # Every task has baseline_finish after status_date.
        tasks = [
            Task(
                unique_id=i,
                task_id=i,
                name=f"T{i}",
                duration_minutes=480,
                baseline_start=STATUS_DATE + timedelta(days=i),
                baseline_finish=STATUS_DATE + timedelta(days=i + 1),
                baseline_duration_minutes=480,
                start=STATUS_DATE + timedelta(days=i),
                finish=STATUS_DATE + timedelta(days=i + 1),
            )
            for i in range(1, 4)
        ]
        sched = Schedule(
            name="vacuous",
            status_date=STATUS_DATE,
            project_start=STATUS_DATE - timedelta(days=30),
            tasks=tasks,
            calendars=[Calendar(name="Standard")],
        )
        r = run_missed_tasks(sched)
        assert r.severity is Severity.PASS
        assert r.denominator == 0
        assert r.numerator == 0
        assert "vacuous PASS" in r.notes


class TestThresholdOverride:
    def test_override_flips_verdict_to_pass(self) -> None:
        r = run_missed_tasks(
            missed_tasks_known_schedule(),
            options=MetricOptions(missed_tasks_threshold_pct=20.0),
        )
        # 10% <= 20% → PASS
        assert r.severity is Severity.PASS
        assert r.threshold.is_overridden is True


class TestProvenance:
    def test_metric_id_and_citation(self) -> None:
        r = run_missed_tasks(missed_tasks_known_schedule())
        assert r.metric_id == "DCMA-11"
        assert r.threshold.source_skill_section == "dcma-14-point-assessment §4.11"


class TestBaseMetricWrapper:
    def test_class_form_matches_functional(self) -> None:
        sched = missed_tasks_known_schedule()
        assert run_missed_tasks(sched) == MissedTasksMetric().run(sched)


class TestMutationInvariance:
    def test_schedule_unchanged(self) -> None:
        sched = missed_tasks_known_schedule()
        before = sched.model_dump_json()
        run_missed_tasks(sched)
        assert sched.model_dump_json() == before
