"""DCMA metric package — Milestones 5 + 6 (metrics 1–8, 10).

Pure-computation layer over :class:`~app.models.schedule.Schedule`
and :class:`~app.engine.result.CPMResult`. No I/O, no COM, no
network (BUILD-PLAN §2 locked decisions; M5 / M6 locked-design
constraints).

M5 shipped metrics 1–4 (Logic, Leads, Lags, Relationship Types).
M6 adds metrics 5, 6, 7, 8, and 10 (Hard Constraints, High Float,
Negative Float, High Duration, Resources). Metric 9 (Invalid Dates)
and metrics 11–14 (Missed Tasks, CPT, CPLI, BEI) land in M7.

Forensic authority: ``dcma-14-point-assessment/SKILL.md`` is the
governing skill for every threshold, denominator, and exclusion
rule. Every threshold is also cross-cited to
``docs/sources/DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*) so
DECM-fluent analysts can map metric output back to the EVMS-row
vocabulary they expect to see.

Public API — see ``app/metrics/README.md`` for the threshold
citation table, the CPM-consumer table, the grouping rationale for
Metric 10, the LOE-detection policy, and the indicator-not-verdict
framing.
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
from app.metrics.hard_constraints import (
    HardConstraintsMetric,
    run_hard_constraints,
)
from app.metrics.high_duration import (
    HighDurationMetric,
    run_high_duration,
)
from app.metrics.high_float import HighFloatMetric, run_high_float
from app.metrics.lags import LagsMetric, run_lags
from app.metrics.leads import LeadsMetric, run_leads
from app.metrics.logic import LogicMetric, run_logic
from app.metrics.negative_float import (
    NegativeFloatMetric,
    run_negative_float,
)
from app.metrics.options import MetricOptions
from app.metrics.relationship_types import (
    RelationshipTypesMetric,
    run_relationship_types,
)
from app.metrics.resources import ResourcesMetric, run_resources

__all__ = [
    "BaseMetric",
    "HardConstraintsMetric",
    "HighDurationMetric",
    "HighFloatMetric",
    "InvalidThresholdError",
    "LagsMetric",
    "LeadsMetric",
    "LogicMetric",
    "MetricError",
    "MetricOptions",
    "MetricResult",
    "MissingCPMResultError",
    "NegativeFloatMetric",
    "Offender",
    "RelationshipTypesMetric",
    "ResourcesMetric",
    "Severity",
    "ThresholdConfig",
    "run_hard_constraints",
    "run_high_duration",
    "run_high_float",
    "run_lags",
    "run_leads",
    "run_logic",
    "run_negative_float",
    "run_relationship_types",
    "run_resources",
]
