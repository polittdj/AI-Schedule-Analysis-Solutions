"""Unit tests for ``app.metrics.leads`` — DCMA Metric 2 (Leads).

Covers gotchas LD1–LD4 from the M5 spec plus cross-metric invariants
CM1, CM3, CM4. Threshold authority:
``dcma-14-point-assessment §4.2``; DeltekDECM row 06A205 (Guideline 6).
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.base import Severity
from app.metrics.leads import LeadsMetric, run_leads
from app.metrics.options import MetricOptions
from tests.fixtures.metric_schedules import (
    empty_schedule,
    leads_golden_fail_schedule,
    leads_on_completed_task_schedule,
    leads_pass_schedule,
    no_relations_schedule,
)


class TestPass:
    """LD1 — zero negative lags → PASS."""

    def test_no_leads_passes(self) -> None:
        result = run_leads(leads_pass_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 4
        assert result.computed_value == 0.0
        assert result.offenders == ()

    def test_empty_schedule_passes(self) -> None:
        result = run_leads(empty_schedule())
        assert result.severity is Severity.PASS
        assert result.denominator == 0
        assert "no relations" in result.notes

    def test_no_relations_schedule_passes(self) -> None:
        result = run_leads(no_relations_schedule())
        assert result.severity is Severity.PASS
        assert result.denominator == 0


class TestFail:
    """LD2 — one negative lag → FAIL at the 0% threshold."""

    def test_single_lead_fails(self) -> None:
        result = run_leads(leads_golden_fail_schedule())
        assert result.severity is Severity.FAIL
        assert result.numerator == 1
        assert result.denominator == 20

    def test_golden_arithmetic(self) -> None:
        """A6 golden — 20 relations, 1 lead → 5.0%, threshold 0% → FAIL."""
        result = run_leads(leads_golden_fail_schedule())
        assert result.computed_value == pytest.approx(5.0, rel=1e-9)


class TestOffenderShape:
    """LD3 — offender rows include pred UID, succ UID, rel type, lag."""

    def test_offender_carries_full_relation_info(self) -> None:
        result = run_leads(leads_golden_fail_schedule())
        (offender,) = result.offenders
        assert offender.unique_id == 5
        assert offender.successor_unique_id == 6
        assert offender.relation_type == "FS"
        assert offender.value == "-480 min"
        assert offender.name.startswith("T")
        assert offender.successor_name.startswith("T")


class TestCompletedRelation:
    """LD4 — a lead between 100%-complete tasks is still flagged."""

    def test_completed_relation_still_flags(self) -> None:
        result = run_leads(leads_on_completed_task_schedule())
        assert result.severity is Severity.FAIL
        assert result.numerator == 1
        offender = result.offenders[0]
        assert offender.value == "-240 min"


class TestThresholdOverride:
    """Operator override via MetricOptions.leads_threshold_pct."""

    def test_override_allows_leads(self) -> None:
        opts = MetricOptions(leads_threshold_pct=10.0)
        result = run_leads(leads_golden_fail_schedule(), opts)
        # 5.0% <= 10% → PASS under override.
        assert result.severity is Severity.PASS
        assert result.threshold.value == 10.0
        assert result.threshold.is_overridden is True

    def test_default_threshold_not_overridden(self) -> None:
        result = run_leads(leads_pass_schedule())
        assert result.threshold.is_overridden is False


class TestCrossMetricInvariants:
    def test_result_is_frozen(self) -> None:
        result = run_leads(leads_pass_schedule())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.severity = Severity.FAIL  # type: ignore[misc]

    def test_byte_equal_results(self) -> None:
        sched = leads_golden_fail_schedule()
        a = run_leads(sched)
        b = run_leads(sched)
        assert a == b

    def test_carries_decm_citation(self) -> None:
        result = run_leads(leads_pass_schedule())
        assert "06A205" in result.threshold.source_decm_row
        assert "§4.2" in result.threshold.source_skill_section


class TestLeadsMetricClass:
    def test_class_wrapper_matches_function(self) -> None:
        sched = leads_golden_fail_schedule()
        assert run_leads(sched) == LeadsMetric().run(sched)
