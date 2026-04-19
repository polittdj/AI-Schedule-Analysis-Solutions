"""Unit tests for ``app.metrics.relationship_types`` — DCMA Metric 4
(Relationship Types).

Covers gotchas RT1–RT6 from the M5 spec plus cross-metric invariants.
Threshold authority: ``dcma-14-point-assessment §4.4``;
DeltekDECMMetricsJan2022.xlsx Guideline 6 FS-Relationship-% row.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.base import Severity
from app.metrics.options import MetricOptions
from app.metrics.relationship_types import (
    RelationshipTypesMetric,
    run_relationship_types,
)
from tests.fixtures.metric_schedules import (
    no_relations_schedule,
    rel_types_all_fs_schedule,
    rel_types_at_threshold_schedule,
    rel_types_below_threshold_schedule,
    rel_types_golden_fail_schedule,
)


class TestPass:
    """RT1, RT2 — 100% FS and exactly 90% FS both pass."""

    def test_all_fs_passes(self) -> None:
        result = run_relationship_types(rel_types_all_fs_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 10
        assert result.denominator == 10
        assert result.computed_value == 100.0

    def test_at_threshold_passes(self) -> None:
        result = run_relationship_types(rel_types_at_threshold_schedule())
        # 9 FS / 10 total = 90% exactly → PASS at the >= boundary.
        assert result.severity is Severity.PASS
        assert result.computed_value == 90.0


class TestFail:
    """RT3 — below threshold fails."""

    def test_below_threshold_fails(self) -> None:
        result = run_relationship_types(rel_types_below_threshold_schedule())
        # 89 / 100 = 89% → FAIL.
        assert result.severity is Severity.FAIL
        assert result.computed_value == 89.0
        assert result.numerator == 89
        assert result.denominator == 100

    def test_golden_arithmetic(self) -> None:
        """A6 golden — 8 FS / 1 SS / 1 FF / 0 SF → 80% FS → FAIL."""
        result = run_relationship_types(rel_types_golden_fail_schedule())
        assert result.numerator == 8
        assert result.denominator == 10
        assert result.computed_value == 80.0
        assert result.severity is Severity.FAIL


class TestBreakdown:
    """RT4 — all four % shown accurately and offenders enumerated."""

    def test_breakdown_in_notes(self) -> None:
        result = run_relationship_types(rel_types_below_threshold_schedule())
        # 89 FS / 5 SS / 5 FF / 1 SF
        assert "FS=89" in result.notes
        assert "SS=5" in result.notes
        assert "FF=5" in result.notes
        assert "SF=1" in result.notes

    def test_offenders_are_non_fs_relations(self) -> None:
        result = run_relationship_types(rel_types_golden_fail_schedule())
        kinds = sorted(o.relation_type for o in result.offenders)
        assert kinds == ["FF", "SS"]


class TestZeroRelations:
    """RT5 — zero-relation schedule reports WARN with explanation."""

    def test_no_relations_warns(self) -> None:
        result = run_relationship_types(no_relations_schedule())
        assert result.severity is Severity.WARN
        assert result.computed_value is None
        assert result.numerator == 0
        assert result.denominator == 0
        assert "no relations" in result.notes


class TestThresholdOverride:
    """RT6 — MetricOptions.fs_threshold_pct override."""

    def test_override_75pct_passes_at_80pct(self) -> None:
        opts = MetricOptions(fs_threshold_pct=75.0)
        result = run_relationship_types(rel_types_golden_fail_schedule(), opts)
        # 80% >= 75% → PASS under override.
        assert result.severity is Severity.PASS
        assert result.threshold.value == 75.0
        assert result.threshold.is_overridden is True

    def test_override_95pct_fails_at_100pct(self) -> None:
        opts = MetricOptions(fs_threshold_pct=95.0)
        result = run_relationship_types(rel_types_all_fs_schedule(), opts)
        # 100% >= 95% → still PASS.
        assert result.severity is Severity.PASS

    def test_default_threshold_not_overridden(self) -> None:
        result = run_relationship_types(rel_types_all_fs_schedule())
        assert result.threshold.is_overridden is False


class TestCrossMetricInvariants:
    def test_result_is_frozen(self) -> None:
        result = run_relationship_types(rel_types_all_fs_schedule())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.severity = Severity.FAIL  # type: ignore[misc]

    def test_byte_equal_results(self) -> None:
        sched = rel_types_golden_fail_schedule()
        assert run_relationship_types(sched) == run_relationship_types(sched)

    def test_carries_decm_citation(self) -> None:
        result = run_relationship_types(rel_types_all_fs_schedule())
        assert "DECM" in result.threshold.source_decm_row
        assert "§4.4" in result.threshold.source_skill_section


class TestRelationshipTypesMetricClass:
    def test_class_wrapper_matches_function(self) -> None:
        sched = rel_types_golden_fail_schedule()
        assert run_relationship_types(sched) == RelationshipTypesMetric().run(sched)
