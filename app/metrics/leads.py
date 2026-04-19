"""DCMA Metric 2 — Leads.

**Formula** (``dcma-14-point-assessment §4.2``):

    numerator   = count of relations with ``lag_minutes < 0``
                  (a negative lag is a "lead")
    denominator = count of all relations
    percentage  = numerator / denominator * 100
    threshold   = 0% — zero tolerance (configurable via
                  MetricOptions.leads_threshold_pct)

**DECM cross-reference.** Leads aggregate to DECM ``06A205`` group
(lag usage) with the threshold expressed as a strict ``X/Y = 0%`` —
see ``acumen-reference §4.4`` and ``DeltekDECMMetricsJan2022.xlsx``
sheet *Metrics*, Guideline 6 rows 33-35.

**Forensic read.** Leads are the canonical "compression" tactic
(``dcma-14-point-assessment §4.2`` — "manufacture end-date
compliance without re-sequencing"). Per gotcha LD4, a lead on a
relationship where both tasks are 100%-complete is still reported —
the historical record of the compression tactic matters to the
forensic narrative even though the manipulation is no longer
correctable.

**Empty schedule.** A schedule with zero relations produces
numerator=0 and denominator=0. The metric reports PASS with the
``"no relations"`` note; no division-by-zero occurs because the
denominator-zero branch short-circuits before the ratio is taken.
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

_METRIC_ID = "DCMA-2"
_METRIC_NAME = "Leads"
_SOURCE_SKILL = "dcma-14-point-assessment §4.2"
_SOURCE_DECM = "06A205 (Guideline 6 row 33) — lag usage; leads scored at X/Y = 0%"


def _name_by_uid(schedule: Schedule) -> dict[int, str]:
    return {t.unique_id: t.name for t in schedule.tasks}


def _rel_type_label(rt: RelationType) -> str:
    return rt.name


def run_leads(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 2 (Leads).

    See module docstring for formula, threshold, and forensic
    rationale.
    """
    opts = options if options is not None else MetricOptions()
    threshold = ThresholdConfig(
        value=opts.leads_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.leads_threshold_pct != 0.0,
    )

    total = len(schedule.relations)
    if total == 0:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes="no relations",
        )

    names = _name_by_uid(schedule)
    offenders: list[Offender] = []
    for r in schedule.relations:
        if r.lag_minutes < 0:
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
    pct = (numerator / total) * 100.0
    severity = Severity.PASS if pct <= opts.leads_threshold_pct else Severity.FAIL

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=severity,
        threshold=threshold,
        numerator=numerator,
        denominator=total,
        offenders=tuple(offenders),
        computed_value=pct,
    )


class LeadsMetric(BaseMetric):
    """Class wrapper around :func:`run_leads`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_leads(schedule, options)
