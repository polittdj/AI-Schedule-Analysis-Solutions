"""Unit tests for ``app.metrics.lags`` — DCMA Metric 3 (Lags).

Covers gotchas LG1–LG5 from the M5 spec plus cross-metric invariants.
Threshold authority: ``dcma-14-point-assessment §4.3``; DeltekDECM
row 06A205a.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.base import Severity
from app.metrics.lags import LagsMetric, run_lags
from app.metrics.options import MetricOptions
from tests.fixtures.metric_schedules import (
    empty_schedule,
    lags_below_threshold_schedule,
    lags_golden_fail_schedule,
    lags_pass_schedule,
    lags_with_leads_schedule,
    no_relations_schedule,
)


class TestPass:
    """LG1 — zero positive lags → PASS."""

    def test_no_lags_passes(self) -> None:
        result = run_lags(lags_pass_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 20
        assert result.computed_value == 0.0

    def test_empty_schedule_passes(self) -> None:
        result = run_lags(empty_schedule())
        assert result.severity is Severity.PASS
        assert result.denominator == 0
        assert "no non-lead" in result.notes

    def test_no_relations_passes(self) -> None:
        result = run_lags(no_relations_schedule())
        assert result.severity is Severity.PASS


class TestThresholdBoundary:
    """LG2 — positive lags under / at the threshold → PASS."""

    def test_below_threshold_passes(self) -> None:
        result = run_lags(lags_below_threshold_schedule())
        # 1 / 20 = 5.0% == threshold → PASS (<=).
        assert result.severity is Severity.PASS
        assert result.computed_value == 5.0

    def test_boundary_plus_epsilon_fails(self) -> None:
        # Configure a tighter threshold so the same 5.0% fixture fails.
        opts = MetricOptions(lags_threshold_pct=4.99)
        result = run_lags(lags_below_threshold_schedule(), opts)
        assert result.severity is Severity.FAIL


class TestFail:
    """LG3 — positive lags above threshold → FAIL."""

    def test_golden_arithmetic(self) -> None:
        """A6 golden — 20 relations, 2 positive lags → 10% > 5% → FAIL."""
        result = run_lags(lags_golden_fail_schedule())
        assert result.numerator == 2
        assert result.denominator == 20
        assert result.computed_value == pytest.approx(10.0, rel=1e-9)
        assert result.severity is Severity.FAIL

    def test_golden_offenders(self) -> None:
        result = run_lags(lags_golden_fail_schedule())
        offender_uids = {o.unique_id for o in result.offenders}
        # Lags set on relations starting at pred UID 3 and 7.
        assert offender_uids == {3, 7}
        for o in result.offenders:
            assert o.value == "1440 min"
            assert o.relation_type == "FS"


class TestThresholdOverride:
    """LG4 — MetricOptions.lags_threshold_pct override."""

    def test_tighter_threshold_fails_at_5pct(self) -> None:
        opts = MetricOptions(lags_threshold_pct=1.0)
        result = run_lags(lags_below_threshold_schedule(), opts)
        # 5% > 1% → FAIL.
        assert result.severity is Severity.FAIL
        assert result.threshold.value == 1.0
        assert result.threshold.is_overridden is True

    def test_default_threshold_not_overridden(self) -> None:
        result = run_lags(lags_pass_schedule())
        assert result.threshold.is_overridden is False


class TestDenominatorExcludesLeads:
    """LG5 — leads are not counted in Metric 3's denominator."""

    def test_leads_excluded_from_denominator(self) -> None:
        result = run_lags(lags_with_leads_schedule())
        # Fixture: 20 relations; 1 lead (UID 5), 1 positive lag (UID 10).
        # Denominator = 20 − 1 = 19; numerator = 1; 1/19 ≈ 5.263% > 5%
        # → FAIL.
        assert result.denominator == 19
        assert result.numerator == 1
        assert result.severity is Severity.FAIL
        assert result.computed_value == pytest.approx(100.0 / 19, rel=1e-9)

    def test_lg5_policy_note_emitted_when_leads_present(self) -> None:
        # Fixture has 1 lead among 20 relations → note must cite the
        # excluded lead count and the literal DCMA §4.3 denominator.
        result = run_lags(lags_with_leads_schedule())
        assert "LG5" in result.notes
        assert "1 lead" in result.notes
        assert "20" in result.notes
        assert "§4.3" in result.notes

    def test_lg5_policy_note_absent_when_no_leads(self) -> None:
        # No leads in the fixture → note must be empty so operators do
        # not see spurious policy chatter.
        result = run_lags(lags_pass_schedule())
        assert result.notes == ""


class TestCrossMetricInvariants:
    def test_result_is_frozen(self) -> None:
        result = run_lags(lags_pass_schedule())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.severity = Severity.FAIL  # type: ignore[misc]

    def test_byte_equal_results(self) -> None:
        sched = lags_golden_fail_schedule()
        assert run_lags(sched) == run_lags(sched)

    def test_carries_decm_citation(self) -> None:
        result = run_lags(lags_pass_schedule())
        assert "06A205a" in result.threshold.source_decm_row
        assert "§4.3" in result.threshold.source_skill_section


class TestLagsMetricClass:
    def test_class_wrapper_matches_function(self) -> None:
        sched = lags_golden_fail_schedule()
        assert run_lags(sched) == LagsMetric().run(sched)
