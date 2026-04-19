"""Unit tests for ``app.metrics.options.MetricOptions``.

Verifies defaults match ``dcma-14-point-assessment §§4.1–4.4`` and
that bad overrides surface :class:`InvalidThresholdError` rather
than silently producing a misleading metric output.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.exceptions import InvalidThresholdError
from app.metrics.options import MetricOptions


class TestDefaults:
    def test_logic_threshold_is_five_pct(self) -> None:
        assert MetricOptions().logic_threshold_pct == 5.0

    def test_leads_threshold_is_zero_pct(self) -> None:
        assert MetricOptions().leads_threshold_pct == 0.0

    def test_lags_threshold_is_five_pct(self) -> None:
        assert MetricOptions().lags_threshold_pct == 5.0

    def test_fs_threshold_is_ninety_pct(self) -> None:
        assert MetricOptions().fs_threshold_pct == 90.0

    def test_exclusion_flags_default_true(self) -> None:
        opt = MetricOptions()
        assert opt.exclude_loe is True
        assert opt.exclude_summary is True
        assert opt.exclude_completed is True
        assert opt.exclude_milestones_from_logic is True

    def test_loe_name_patterns_empty_by_default(self) -> None:
        assert MetricOptions().loe_name_patterns == ()


class TestImmutability:
    def test_options_is_frozen(self) -> None:
        opt = MetricOptions()
        with pytest.raises(dataclasses.FrozenInstanceError):
            opt.logic_threshold_pct = 7.0  # type: ignore[misc]


class TestOverrideValidation:
    def test_negative_logic_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(logic_threshold_pct=-0.1)

    def test_above_100_logic_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(logic_threshold_pct=100.5)

    def test_non_numeric_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(logic_threshold_pct="five")  # type: ignore[arg-type]

    def test_boundary_zero_accepted(self) -> None:
        MetricOptions(leads_threshold_pct=0.0)

    def test_boundary_hundred_accepted(self) -> None:
        MetricOptions(fs_threshold_pct=100.0)

    def test_each_threshold_validated(self) -> None:
        for kw in (
            "logic_threshold_pct",
            "leads_threshold_pct",
            "lags_threshold_pct",
            "fs_threshold_pct",
        ):
            with pytest.raises(InvalidThresholdError):
                MetricOptions(**{kw: -5.0})


class TestOverrideValues:
    def test_logic_override_persists(self) -> None:
        opt = MetricOptions(logic_threshold_pct=7.0)
        assert opt.logic_threshold_pct == 7.0

    def test_loe_pattern_persists(self) -> None:
        opt = MetricOptions(loe_name_patterns=("loe", "level of effort"))
        assert opt.loe_name_patterns == ("loe", "level of effort")


class TestM7Thresholds:
    def test_invalid_dates_default_zero(self) -> None:
        assert MetricOptions().invalid_dates_threshold_pct == 0.0

    def test_missed_tasks_default_five(self) -> None:
        assert MetricOptions().missed_tasks_threshold_pct == 5.0

    def test_cpli_default_0_95(self) -> None:
        assert MetricOptions().cpli_threshold_value == 0.95

    def test_bei_default_0_95(self) -> None:
        assert MetricOptions().bei_threshold_value == 0.95

    def test_cpli_non_numeric_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(cpli_threshold_value="nope")  # type: ignore[arg-type]

    def test_cpli_zero_rejected(self) -> None:
        # 0.0 is outside the permissible (0, 2.0] range.
        with pytest.raises(InvalidThresholdError):
            MetricOptions(cpli_threshold_value=0.0)

    def test_cpli_above_range_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(cpli_threshold_value=2.5)

    def test_bei_non_numeric_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(bei_threshold_value="nope")  # type: ignore[arg-type]

    def test_bei_negative_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(bei_threshold_value=-0.1)

    def test_bei_above_range_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(bei_threshold_value=2.5)

    def test_invalid_dates_above_100_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(invalid_dates_threshold_pct=150.0)

    def test_missed_tasks_negative_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(missed_tasks_threshold_pct=-1.0)
