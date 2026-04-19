"""Unit tests for DCMA Metric 13 (CPLI) — M7 Block 5.

Coverage: on-track PASS, slip FAIL, no-baseline indicator-only,
CPMResult=None raises, mutation-invariance.
"""

from __future__ import annotations

import pytest

from app.metrics import MetricOptions, Severity
from app.metrics.critical_path_length_index import CPLIMetric, run_cpli
from app.metrics.exceptions import MissingCPMResultError
from tests._utils import cpm_result_snapshot
from tests.fixtures.metric_schedules import (
    cpli_no_baseline_schedule,
    cpli_on_track_schedule,
    cpli_slip_fail_schedule,
)


class TestOnTrack:
    def test_on_track_schedule_passes_with_cpli_1_0(self) -> None:
        sched, cpm = cpli_on_track_schedule()
        r = run_cpli(sched, cpm)
        assert r.severity is Severity.PASS
        assert r.computed_value == pytest.approx(1.0)

    def test_offender_row_carries_cpli_evidence(self) -> None:
        sched, cpm = cpli_on_track_schedule()
        r = run_cpli(sched, cpm)
        assert len(r.offenders) == 1
        assert "CPLI=" in r.offenders[0].value
        assert "baseline_cp_length" in r.offenders[0].value


class TestSlipFail:
    def test_3_day_slip_on_10_day_cp_yields_cpli_below_threshold(
        self,
    ) -> None:
        sched, cpm = cpli_slip_fail_schedule()
        r = run_cpli(sched, cpm)
        assert r.severity is Severity.FAIL
        # CPLI ≈ 0.70 per fixture hand-calc.
        assert r.computed_value == pytest.approx(0.7, abs=1e-6)
        assert r.computed_value < 0.95


class TestNoBaseline:
    def test_indicator_only_warn_when_no_baseline(self) -> None:
        sched, cpm = cpli_no_baseline_schedule()
        r = run_cpli(sched, cpm)
        assert r.severity is Severity.WARN
        assert r.computed_value is None
        assert "no baseline" in r.notes


class TestMissingCPMResult:
    def test_none_raises(self) -> None:
        sched, _ = cpli_on_track_schedule()
        with pytest.raises(MissingCPMResultError):
            run_cpli(sched, None)


class TestOverride:
    def test_override_changes_verdict(self) -> None:
        sched, cpm = cpli_slip_fail_schedule()
        r = run_cpli(
            sched,
            cpm,
            options=MetricOptions(cpli_threshold_value=0.5),
        )
        # 0.70 >= 0.50 → PASS under override
        assert r.severity is Severity.PASS
        assert r.threshold.is_overridden is True


class TestMutationInvariance:
    def test_schedule_unchanged(self) -> None:
        sched, cpm = cpli_slip_fail_schedule()
        before = sched.model_dump_json()
        run_cpli(sched, cpm)
        assert sched.model_dump_json() == before

    def test_cpm_result_unchanged(self) -> None:
        sched, cpm = cpli_slip_fail_schedule()
        before = cpm_result_snapshot(cpm)
        run_cpli(sched, cpm)
        assert cpm_result_snapshot(cpm) == before


class TestProvenance:
    def test_metric_id_and_direction(self) -> None:
        sched, cpm = cpli_on_track_schedule()
        r = run_cpli(sched, cpm)
        assert r.metric_id == "DCMA-13"
        assert r.threshold.direction == ">="
        assert r.threshold.value == 0.95


class TestBaseMetricWrapper:
    def test_class_form_matches_functional(self) -> None:
        sched, cpm = cpli_on_track_schedule()
        assert run_cpli(sched, cpm) == CPLIMetric().run(sched, cpm_result=cpm)


class TestEdgeCases:
    def test_missing_project_finish_returns_indicator_only(self) -> None:
        # Build a schedule with valid baselines but project_finish=None.
        sched, cpm = cpli_on_track_schedule()
        mutated = sched.model_copy(update={"project_finish": None})
        r = run_cpli(mutated, cpm)
        assert r.severity is Severity.WARN
        assert "project_finish unavailable" in r.notes

    def test_cp_length_none_when_critical_milestone_has_no_baseline(
        self,
    ) -> None:
        # A critical milestone without a baseline makes
        # baseline_critical_path_length_minutes return None even
        # though has_baseline_coverage (which exempts milestones)
        # returns True.
        from datetime import timedelta

        from app.engine.result import CPMResult, TaskCPMResult
        from app.models.calendar import Calendar
        from app.models.schedule import Schedule
        from app.models.task import Task
        from tests.fixtures.metric_schedules import ANCHOR

        tasks = [
            Task(
                unique_id=100,
                task_id=100,
                name="Start",
                duration_minutes=0,
                is_milestone=True,
            ),
            Task(
                unique_id=1,
                task_id=1,
                name="Only",
                duration_minutes=480,
                baseline_start=ANCHOR,
                baseline_finish=ANCHOR + timedelta(days=1),
                baseline_duration_minutes=480,
            ),
        ]
        sched = Schedule(
            name="cp_none_edge",
            status_date=ANCHOR,
            project_start=ANCHOR,
            project_finish=ANCHOR + timedelta(days=5),
            tasks=tasks,
            calendars=[Calendar(name="Standard")],
        )
        cpm = CPMResult(
            tasks={
                100: TaskCPMResult(unique_id=100, total_slack_minutes=0),
                1: TaskCPMResult(unique_id=1, total_slack_minutes=0),
            },
            critical_path_uids=frozenset({100, 1}),
        )
        r = run_cpli(sched, cpm)
        assert r.severity is Severity.WARN
        assert "baseline critical-path length" in r.notes

    def test_calendar_fallback_when_name_mismatches(self) -> None:
        # Schedule.default_calendar_name points at a calendar that
        # doesn't exist → helper falls back to the first calendar.
        sched, cpm = cpli_on_track_schedule()
        mutated = sched.model_copy(
            update={"default_calendar_name": "Nonexistent"}
        )
        r = run_cpli(mutated, cpm)
        # Result still computed; calendar fallback lands on the first.
        assert r.computed_value == pytest.approx(1.0)

