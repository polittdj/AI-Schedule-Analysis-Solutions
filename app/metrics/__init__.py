"""DCMA metric package — Milestone 5 (metrics 1–4: Logic, Leads,
Lags, Relationship Types).

Pure-computation layer over :class:`~app.models.schedule.Schedule`
(later milestones add :class:`~app.engine.result.CPMResult`-consuming
metrics). No I/O, no COM, no network (BUILD-PLAN §2 locked
decisions; M5 locked-design constraints).

Forensic authority: ``dcma-14-point-assessment/SKILL.md`` is the
governing skill for every threshold, denominator, and exclusion
rule. Every threshold is also cross-cited to
``docs/sources/DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*) so
DECM-fluent analysts can map metric output back to the EVMS-row
vocabulary they expect to see.

Public API — see ``app/metrics/README.md`` for the threshold
citation table, the LOE-detection policy, and the
indicator-not-verdict framing.
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
from app.metrics.lags import LagsMetric, run_lags
from app.metrics.leads import LeadsMetric, run_leads
from app.metrics.logic import LogicMetric, run_logic
from app.metrics.options import MetricOptions
from app.metrics.relationship_types import (
    RelationshipTypesMetric,
    run_relationship_types,
)

__all__ = [
    "BaseMetric",
    "InvalidThresholdError",
    "LagsMetric",
    "LeadsMetric",
    "LogicMetric",
    "MetricError",
    "MetricOptions",
    "MetricResult",
    "MissingCPMResultError",
    "Offender",
    "RelationshipTypesMetric",
    "Severity",
    "ThresholdConfig",
    "run_lags",
    "run_leads",
    "run_logic",
    "run_relationship_types",
]
