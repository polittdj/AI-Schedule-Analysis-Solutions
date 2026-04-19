"""Metric exception hierarchy.

Mirrors the engine's split (``app.engine.exceptions``) — structured
errors raised when a metric cannot run safely, with the metric's
ordinary indicator-not-verdict output reserved for the
``MetricResult``. Forensic-defensibility (BUILD-PLAN §6 AC bar #3,
``dcma-14-point-assessment §6 Rule 1``) means a defective input fails
loudly instead of silently producing a misleading percentage.

Authority:

* Indicator-not-verdict framing — ``dcma-14-point-assessment §6 Rule 1``.
* DCMA threshold provenance — ``dcma-14-point-assessment §4`` and
  ``DeltekDECMMetricsJan2022.xlsx`` (rows cited per metric).
"""

from __future__ import annotations


class MetricError(Exception):
    """Base class for all DCMA metric errors.

    Catching ``MetricError`` captures every metric-raised exception
    without trapping unrelated ``Exception`` subclasses raised by
    Pydantic, the engine, or the standard library.
    """


class MissingCPMResultError(MetricError):
    """Raised when a metric needs CPM output but received ``None``.

    Metrics 1–4 (M5 scope) consume only ``Schedule`` data and do not
    need a :class:`~app.engine.result.CPMResult`. M6 / M7 metrics
    (slack, critical-path) will, and the same hierarchy is reused
    there. The class is defined here so the M5 PR ships the public
    API the next milestone consumes.
    """

    def __init__(self, metric_id: str) -> None:
        self.metric_id = metric_id
        super().__init__(
            f"metric {metric_id!r} requires a CPMResult but none was supplied "
            "(dcma-14-point-assessment §4)"
        )


class InvalidThresholdError(MetricError):
    """Raised when a :class:`MetricOptions` override is structurally invalid.

    ``MetricOptions`` lets clients override the protocol thresholds
    (BUILD-PLAN §5 M5: thresholds are configurable per
    client-acceptance specifications). An override outside the
    permissible range — a negative percentage, a value above 100 for
    a percent-of-total metric — is a configuration error, not a
    metric finding.
    """

    def __init__(self, metric_id: str, option_name: str, value: object) -> None:
        self.metric_id = metric_id
        self.option_name = option_name
        self.value = value
        super().__init__(
            f"invalid threshold for metric {metric_id!r}: "
            f"{option_name}={value!r} (DeltekDECMMetricsJan2022.xlsx threshold range)"
        )
