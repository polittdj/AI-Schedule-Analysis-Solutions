"""DCMA metric package — Milestone 5 (metrics 1–4).

Public API is finalized in Block 6; this Block-1 stub exposes only
the shared primitives required for the base / options / exceptions
test suites to import.
"""

from __future__ import annotations

from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.exceptions import (
    InvalidThresholdError,
    MetricError,
    MissingCPMResultError,
)
from app.metrics.options import MetricOptions

__all__ = [
    "BaseMetric",
    "InvalidThresholdError",
    "MetricError",
    "MetricOptions",
    "MetricResult",
    "MissingCPMResultError",
    "Offender",
    "Severity",
    "ThresholdConfig",
]
