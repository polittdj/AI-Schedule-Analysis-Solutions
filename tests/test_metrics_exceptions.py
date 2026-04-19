"""Unit tests for ``app.metrics.exceptions``.

Validates the three-class hierarchy (``MetricError`` base,
``MissingCPMResultError``, ``InvalidThresholdError``) and the message
shapes the narrative layer relies on.
"""

from __future__ import annotations

import pytest

from app.metrics.exceptions import (
    InvalidThresholdError,
    MetricError,
    MissingCPMResultError,
)


class TestMetricError:
    def test_metric_error_is_an_exception(self) -> None:
        assert issubclass(MetricError, Exception)

    def test_subclasses_inherit_from_metric_error(self) -> None:
        assert issubclass(MissingCPMResultError, MetricError)
        assert issubclass(InvalidThresholdError, MetricError)


class TestMissingCPMResultError:
    def test_carries_metric_id(self) -> None:
        with pytest.raises(MissingCPMResultError) as excinfo:
            raise MissingCPMResultError("DCMA-7")
        assert excinfo.value.metric_id == "DCMA-7"

    def test_message_names_metric(self) -> None:
        err = MissingCPMResultError("DCMA-7")
        assert "DCMA-7" in str(err)
        assert "CPMResult" in str(err)


class TestInvalidThresholdError:
    def test_carries_metric_and_field(self) -> None:
        err = InvalidThresholdError("DCMA-3", "lags_threshold_pct", -1.0)
        assert err.metric_id == "DCMA-3"
        assert err.option_name == "lags_threshold_pct"
        assert err.value == -1.0

    def test_message_names_field_and_value(self) -> None:
        err = InvalidThresholdError("DCMA-3", "lags_threshold_pct", -1.0)
        msg = str(err)
        assert "DCMA-3" in msg
        assert "lags_threshold_pct" in msg
        assert "-1.0" in msg
