"""DCMA Metric 3 — Lags.

**Formula** (``dcma-14-point-assessment §4.3``):

    numerator   = count of relations with ``lag_minutes > 0``
    denominator = count of relations with ``lag_minutes >= 0``
                  (leads excluded — that is DCMA Metric 2's job per
                  LG5)
    percentage  = numerator / denominator * 100
    threshold   = ≤ 5% (configurable via
                  MetricOptions.lags_threshold_pct)

**DECM cross-reference.** ``acumen-reference §4.4`` maps this metric
to DECM row ``06A205a`` — "lag usage", threshold ``X/Y ≤ 10%``.
The DCMA protocol tightens the DECM ceiling to 5% per
``dcma-14-point-assessment §4.3``; both citations travel on the
result so operators running DECM-tuned programmes can see the
difference.

**Denominator semantics.** Per gotcha LG5, the metric's denominator
excludes negative-lag relations so M2 (Leads) and M3 (Lags) do not
double-count the same offender. A relation contributes to either
M2 or M3 but never both. A zero-lag relation contributes to the
M3 denominator (it is "non-lead") but not to the numerator.

**Carve-out deferral.** The 09NOV09 protocol adds a 5-working-day
carve-out for MSP/OpenPlan schedules (``§4.3``; P6 does not receive
the carve-out). The Milestone 5 prompt locks the simpler
`positive-lag / total` formulation; the carve-out is a
:class:`MetricOptions` extension slated for follow-up once the tool
supports per-file tool-provenance detection. BUILD-PLAN §5 M5
Test-strategy AC3 ("5-day carve-out") is flagged as a scope defer
on the PR — the default metric today does not carve out sub-5-day
lags.
"""

from __future__ import annotations

from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.options import MetricOptions
from app.models.enums import RelationType
from app.models.schedule import Schedule

_METRIC_ID = "DCMA-3"
_METRIC_NAME = "Lags"
_SOURCE_SKILL = "dcma-14-point-assessment §4.3"
_SOURCE_DECM = (
    "06A205a (Guideline 6 row 33) — lag usage; DECM X/Y ≤ 10%, DCMA X/Y ≤ 5%"
)


def _name_by_uid(schedule: Schedule) -> dict[int, str]:
    return {t.unique_id: t.name for t in schedule.tasks}


def _rel_type_label(rt: RelationType) -> str:
    return rt.name


def run_lags(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 3 (Lags).

    See module docstring for formula, threshold, and denominator
    policy.
    """
    opts = options if options is not None else MetricOptions()
    threshold = ThresholdConfig(
        value=opts.lags_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.lags_threshold_pct != 5.0,
    )

    non_lead_relations = [r for r in schedule.relations if r.lag_minutes >= 0]
    denominator = len(non_lead_relations)

    if denominator == 0:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes="no non-lead relations",
        )

    names = _name_by_uid(schedule)
    offenders: list[Offender] = []
    for r in non_lead_relations:
        if r.lag_minutes > 0:
            offenders.append(
                Offender(
                    unique_id=r.predecessor_unique_id,
                    name=names.get(r.predecessor_unique_id, ""),
                    successor_unique_id=r.successor_unique_id,
                    successor_name=names.get(r.successor_unique_id, ""),
                    relation_type=_rel_type_label(r.relation_type),
                    value=f"{r.lag_minutes} min",
                )
            )

    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = Severity.PASS if pct <= opts.lags_threshold_pct else Severity.FAIL

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=severity,
        threshold=threshold,
        numerator=numerator,
        denominator=denominator,
        offenders=tuple(offenders),
        computed_value=pct,
    )


class LagsMetric(BaseMetric):
    """Class wrapper around :func:`run_lags`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_lags(schedule, options)
