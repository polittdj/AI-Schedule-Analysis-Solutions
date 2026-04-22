"""Unit tests for ``app.metrics.base``.

Verifies the shared metric primitives: :class:`Severity` enum,
:class:`Offender` and :class:`MetricResult` dataclasses (frozen, M5
CM1), :class:`ThresholdConfig`, and :class:`BaseMetric` contract.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule


class TestSeverity:
    def test_three_states(self) -> None:
        assert Severity.PASS.value == "PASS"
        assert Severity.WARN.value == "WARN"
        assert Severity.FAIL.value == "FAIL"

    def test_string_round_trip(self) -> None:
        assert Severity("PASS") is Severity.PASS
        assert Severity("FAIL") is Severity.FAIL


class TestOffender:
    def test_minimal_construction(self) -> None:
        o = Offender(unique_id=42)
        assert o.unique_id == 42
        assert o.name == ""
        assert o.successor_unique_id is None
        assert o.relation_type == ""
        assert o.value == ""

    def test_relation_offender(self) -> None:
        o = Offender(
            unique_id=1,
            name="A",
            successor_unique_id=2,
            successor_name="B",
            relation_type="FS",
            value="-2400 min",
        )
        assert o.successor_unique_id == 2
        assert o.relation_type == "FS"
        assert o.value == "-2400 min"

    def test_offender_is_frozen(self) -> None:
        o = Offender(unique_id=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            o.unique_id = 2  # type: ignore[misc]


class TestThresholdConfig:
    def test_minimal(self) -> None:
        t = ThresholdConfig(
            value=5.0,
            direction="<=",
            source_skill_section="dcma-14-point-assessment §4.1",
            source_decm_row="06A204b — Logic / Missing Logic",
        )
        assert t.value == 5.0
        assert t.direction == "<="
        assert t.is_overridden is False

    def test_threshold_is_frozen(self) -> None:
        t = ThresholdConfig(
            value=5.0,
            direction="<=",
            source_skill_section="x",
            source_decm_row="y",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.value = 7.0  # type: ignore[misc]


class TestMetricResult:
    def _build(self) -> MetricResult:
        threshold = ThresholdConfig(
            value=5.0,
            direction="<=",
            source_skill_section="dcma-14-point-assessment §4.1",
            source_decm_row="06A204b — Logic / Missing Logic",
        )
        return MetricResult(
            metric_id="DCMA-1",
            metric_name="Missing Logic",
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=10,
            computed_value=0.0,
        )

    def test_result_is_frozen(self) -> None:
        r = self._build()
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.severity = Severity.FAIL  # type: ignore[misc]

    def test_result_carries_provenance(self) -> None:
        r = self._build()
        assert r.metric_id == "DCMA-1"
        assert "06A204b" in r.threshold.source_decm_row
        assert "§4.1" in r.threshold.source_skill_section


class TestBaseMetric:
    def test_base_metric_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseMetric()  # type: ignore[abstract]

    def test_subclass_must_implement_run(self) -> None:
        class Half(BaseMetric):
            metric_id = "DCMA-X"

        with pytest.raises(TypeError):
            Half()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self) -> None:
        class Stub(BaseMetric):
            metric_id = "DCMA-X"

            def run(
                self,
                schedule: Schedule,
                options: MetricOptions | None = None,
            ) -> MetricResult:
                return MetricResult(
                    metric_id="DCMA-X",
                    metric_name="Stub",
                    severity=Severity.PASS,
                    threshold=ThresholdConfig(
                        value=0.0,
                        direction="<=",
                        source_skill_section="x",
                        source_decm_row="y",
                    ),
                    numerator=0,
                    denominator=0,
                )

        stub = Stub()
        result = stub.run(Schedule(project_calendar_hours_per_day=8.0))
        assert result.metric_id == "DCMA-X"
