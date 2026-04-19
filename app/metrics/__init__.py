"""DCMA metric package — Milestones 5 + 6 + 7 (metrics 1–14).

Pure-computation layer over :class:`~app.models.schedule.Schedule`
and :class:`~app.engine.result.CPMResult`. No I/O, no COM, no
network (BUILD-PLAN §2 locked decisions; M5 / M6 / M7 locked-design
constraints).

M5 shipped metrics 1–4 (Logic, Leads, Lags, Relationship Types).
M6 added metrics 5, 6, 7, 8, and 10 (Hard Constraints, High Float,
Negative Float, High Duration, Resources). M7 adds metrics 9, 11,
12, 13, and 14 (Invalid Dates, Missed Tasks, Critical Path Test,
CPLI, BEI) plus the :mod:`app.metrics.baseline` plumbing module.

Forensic authority: ``dcma-14-point-assessment/SKILL.md`` is the
governing skill for every threshold, denominator, and exclusion
rule. Every threshold is also cross-cited to
``docs/sources/DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*) so
DECM-fluent analysts can map metric output back to the EVMS-row
vocabulary they expect to see.

Public API — see ``app/metrics/README.md`` for the threshold
citation table, the CPM-consumer table, the grouping rationale for
Metrics 9–14, the LOE-detection policy, the baseline-plumbing
contract, and the indicator-not-verdict framing.
"""

from __future__ import annotations

from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.baseline import (
    BaselineComparison,
    baseline_critical_path_length_minutes,
    baseline_slip_minutes,
    has_baseline,
    has_baseline_coverage,
    tasks_with_baseline_finish_by,
)
from app.metrics.baseline_execution_index import BEIMetric, run_bei
from app.metrics.critical_path_length_index import CPLIMetric, run_cpli
from app.metrics.critical_path_test import (
    CriticalPathTestMetric,
    run_critical_path_test,
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
from app.metrics.invalid_dates import (
    InvalidDateKind,
    InvalidDatesMetric,
    run_invalid_dates,
)
from app.metrics.lags import LagsMetric, run_lags
from app.metrics.leads import LeadsMetric, run_leads
from app.metrics.logic import LogicMetric, run_logic
from app.metrics.missed_tasks import MissedTasksMetric, run_missed_tasks
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
    "BEIMetric",
    "BaseMetric",
    "BaselineComparison",
    "CPLIMetric",
    "CriticalPathTestMetric",
    "HardConstraintsMetric",
    "HighDurationMetric",
    "HighFloatMetric",
    "InvalidDateKind",
    "InvalidDatesMetric",
    "InvalidThresholdError",
    "LagsMetric",
    "LeadsMetric",
    "LogicMetric",
    "MetricError",
    "MetricOptions",
    "MetricResult",
    "MissedTasksMetric",
    "MissingCPMResultError",
    "NegativeFloatMetric",
    "Offender",
    "RelationshipTypesMetric",
    "ResourcesMetric",
    "Severity",
    "ThresholdConfig",
    "baseline_critical_path_length_minutes",
    "baseline_slip_minutes",
    "has_baseline",
    "has_baseline_coverage",
    "run_bei",
    "run_cpli",
    "run_critical_path_test",
    "run_hard_constraints",
    "run_high_duration",
    "run_high_float",
    "run_invalid_dates",
    "run_lags",
    "run_leads",
    "run_logic",
    "run_missed_tasks",
    "run_negative_float",
    "run_relationship_types",
    "run_resources",
    "tasks_with_baseline_finish_by",
]
