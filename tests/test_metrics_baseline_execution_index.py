"""Unit tests for DCMA Metric 14 (BEI) — M7 Block 6.

Coverage: on-track PASS, slip FAIL, rolling-wave / LOE exemptions,
zero-denominator indicator-only, no-baseline indicator-only, Edwards
§5.1 worked example, mutation-invariance.
"""

from __future__ import annotations

import pytest

from app.metrics import MetricOptions, Severity
from app.metrics.baseline_execution_index import BEIMetric, run_bei
from tests.fixtures.metric_schedules import (
    bei_edwards_worked_example_schedule,
    bei_loe_exempt_schedule,
    bei_no_baseline_schedule,
    bei_no_status_date_schedule,
    bei_on_track_schedule,
    bei_rolling_wave_exempt_schedule,
    bei_slip_fail_schedule,
    bei_zero_denominator_schedule,
)


class TestOnTrack:
    def test_all_hit_gives_bei_1_0(self) -> None:
        r = run_bei(bei_on_track_schedule())
        assert r.severity is Severity.PASS
        assert r.computed_value == pytest.approx(1.0)
        assert r.numerator == 5
        assert r.denominator == 5


class TestSlipFail:
    def test_10_task_slip_fixture_gives_0_7(self) -> None:
        r = run_bei(bei_slip_fail_schedule())
        assert r.severity is Severity.FAIL
        # 7/10 per fixture hand-calc.
        assert r.computed_value == pytest.approx(0.7, abs=1e-6)
        assert r.numerator == 7
        assert r.denominator == 10

    def test_incomplete_baseline_due_tasks_are_offenders(self) -> None:
        r = run_bei(bei_slip_fail_schedule())
        missed = {o.unique_id for o in r.offenders}
        assert missed == {8, 9, 10}


class TestRollingWaveExemption:
    def test_rolling_wave_excluded_from_numerator_only(self) -> None:
        r = run_bei(bei_rolling_wave_exempt_schedule())
        # Denominator 3, numerator 2 (rolling-wave in denominator only).
        assert r.denominator == 3
        assert r.numerator == 2
        assert r.computed_value == pytest.approx(2 / 3)
        assert r.severity is Severity.FAIL


class TestLoeExemption:
    def test_loe_excluded_from_numerator_only(self) -> None:
        r = run_bei(bei_loe_exempt_schedule())
        assert r.denominator == 3
        assert r.numerator == 2


class TestZeroDenominator:
    def test_zero_denominator_is_indicator_only(self) -> None:
        r = run_bei(bei_zero_denominator_schedule())
        assert r.severity is Severity.WARN
        assert r.computed_value is None
        assert "zero denominator" in r.notes


class TestNoBaseline:
    def test_no_baseline_is_indicator_only(self) -> None:
        r = run_bei(bei_no_baseline_schedule())
        assert r.severity is Severity.WARN
        assert r.computed_value is None
        assert "no baseline available" in r.notes


class TestNoStatusDate:
    def test_no_status_date_is_indicator_only(self) -> None:
        r = run_bei(bei_no_status_date_schedule())
        assert r.severity is Severity.WARN
        assert "no status_date" in r.notes


class TestEdwardsWorkedExample:
    def test_proxy_of_skill_5_1_example(self) -> None:
        # Fixture: 8 baseline-due, 6 completed by status, 2 not; the
        # late-baseline early-finisher is excluded from both
        # numerator and denominator. BEI = 6/8 = 0.75 FAIL.
        r = run_bei(bei_edwards_worked_example_schedule())
        assert r.numerator == 6
        assert r.denominator == 8
        assert r.computed_value == pytest.approx(0.75)
        assert r.severity is Severity.FAIL
        # The early-finisher (UID 9) must not appear anywhere.
        offender_uids = {o.unique_id for o in r.offenders}
        assert 9 not in offender_uids


class TestOverride:
    def test_threshold_override_flips_verdict(self) -> None:
        r = run_bei(
            bei_slip_fail_schedule(),
            options=MetricOptions(bei_threshold_value=0.50),
        )
        assert r.severity is Severity.PASS
        assert r.threshold.is_overridden is True


class TestMutationInvariance:
    def test_schedule_unchanged(self) -> None:
        sched = bei_slip_fail_schedule()
        before = sched.model_dump_json()
        run_bei(sched)
        assert sched.model_dump_json() == before


class TestProvenance:
    def test_metric_id_and_direction(self) -> None:
        r = run_bei(bei_on_track_schedule())
        assert r.metric_id == "DCMA-14"
        assert r.threshold.direction == ">="
        assert r.threshold.value == 0.95


class TestBaseMetricWrapper:
    def test_class_form_matches_functional(self) -> None:
        sched = bei_on_track_schedule()
        assert run_bei(sched) == BEIMetric().run(sched)
