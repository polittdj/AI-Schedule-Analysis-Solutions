"""Unit tests for DCMA Metric 12 (Critical Path Test, structural) —
M7 Block 4.

Coverage: linear PASS, gap FAIL with evidence, parallel-critical
branches, CPMResult=None raises, missing endpoints indicator-only,
mutation invariance on both Schedule and CPMResult (per §3.5 /
BUILD-PLAN recommendation for Metric 12).
"""

from __future__ import annotations

import pytest

from app.metrics import Severity
from app.metrics.critical_path_test import (
    CriticalPathTestMetric,
    run_critical_path_test,
)
from app.metrics.exceptions import MissingCPMResultError
from tests._utils import cpm_result_snapshot
from tests.fixtures.metric_schedules import (
    cpt_finish_not_critical_schedule,
    cpt_gap_fail_schedule,
    cpt_linear_pass_schedule,
    cpt_no_endpoints_schedule,
    cpt_parallel_critical_paths_schedule,
)


class TestLinearPass:
    def test_simple_linear_schedule_passes(self) -> None:
        sched, cpm = cpt_linear_pass_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.severity is Severity.PASS
        assert r.numerator == 1
        assert r.denominator == 1
        assert r.computed_value == 100.0
        assert r.offenders == ()

    def test_notes_mention_start_and_finish_uids(self) -> None:
        sched, cpm = cpt_linear_pass_schedule()
        r = run_critical_path_test(sched, cpm)
        assert "start_uid=100" in r.notes
        assert "finish_uid=200" in r.notes


class TestGapFail:
    def test_float_break_in_middle_fails(self) -> None:
        sched, cpm = cpt_gap_fail_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.severity is Severity.FAIL
        assert r.numerator == 0
        assert r.computed_value == 0.0

    def test_gap_evidence_identifies_the_gap_task(self) -> None:
        sched, cpm = cpt_gap_fail_schedule()
        r = run_critical_path_test(sched, cpm)
        # T4 is the first backward-walk task whose only predecessor
        # (T3) is non-critical.
        gap_uids = {o.unique_id for o in r.offenders}
        assert 4 in gap_uids


class TestParallelCriticalPaths:
    def test_parallel_branches_both_pass(self) -> None:
        sched, cpm = cpt_parallel_critical_paths_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.severity is Severity.PASS
        assert r.numerator == 1


class TestMissingCPMResult:
    def test_none_raises_missing_cpm_result_error(self) -> None:
        sched, _ = cpt_linear_pass_schedule()
        with pytest.raises(MissingCPMResultError):
            run_critical_path_test(sched, None)


class TestNoEndpoints:
    def test_schedule_without_milestones_returns_warn(self) -> None:
        sched, cpm = cpt_no_endpoints_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.severity is Severity.WARN
        assert r.computed_value is None
        assert "endpoint milestones not identifiable" in r.notes


class TestFinishNotCritical:
    def test_finish_milestone_with_positive_slack_fails(self) -> None:
        sched, cpm = cpt_finish_not_critical_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.severity is Severity.FAIL
        gap_uids = {o.unique_id for o in r.offenders}
        assert 200 in gap_uids
        assert r.offenders[0].value.startswith("project finish milestone")


class TestMutationInvariance:
    def test_schedule_unchanged(self) -> None:
        sched, cpm = cpt_gap_fail_schedule()
        before = sched.model_dump_json()
        run_critical_path_test(sched, cpm)
        assert sched.model_dump_json() == before

    def test_cpm_result_unchanged(self) -> None:
        sched, cpm = cpt_gap_fail_schedule()
        before = cpm_result_snapshot(cpm)
        run_critical_path_test(sched, cpm)
        assert cpm_result_snapshot(cpm) == before


class TestProvenance:
    def test_metric_id_and_structural_direction(self) -> None:
        sched, cpm = cpt_linear_pass_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.metric_id == "DCMA-12"
        assert r.threshold.direction == "structural-pass-fail"
        assert r.threshold.value == 1.0


class TestBaseMetricWrapper:
    def test_class_form_matches_functional(self) -> None:
        sched, cpm = cpt_linear_pass_schedule()
        a = run_critical_path_test(sched, cpm)
        b = CriticalPathTestMetric().run(sched, cpm_result=cpm)
        assert a == b
