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
