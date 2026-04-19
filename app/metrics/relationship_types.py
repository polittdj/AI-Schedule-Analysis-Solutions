"""DCMA Metric 4 — Relationship Types.

**Formula** (``dcma-14-point-assessment §4.4``):

    fs_count    = count of relations with type FS
    ss_count    = count of relations with type SS
    ff_count    = count of relations with type FF
    sf_count    = count of relations with type SF
    total       = sum of the four
    fs_pct      = fs_count / total * 100
    threshold   = ≥ 90% FS (configurable via
                  MetricOptions.fs_threshold_pct)

The 09NOV09 protocol counts **relationships**, not activities
carrying relationships (``dcma-14-point-assessment §3``;
[RW p.5]). Earlier protocol revisions counted activities and
double-counted tasks with multiple outgoing links; this metric
follows the 09NOV09 rule.

**DECM cross-reference.** ``acumen-reference §4.4`` notes that DECM
maps Metric 4 to its "FS Relationship %" row at the same ≥90%
threshold. Source row in the DeltekDECM workbook is sheet
*Metrics* under Guideline 6 (relationship-types row, FS share).

**Zero-relations guard.** Per gotcha RT5, a schedule with no
relations cannot compute a meaningful FS-share. The metric returns
:attr:`Severity.WARN` with an explanatory note rather than dividing
by zero or fabricating a false PASS.

**Forensic read.** A drop in FS share between schedule revisions is
a re-baselining signature (``forensic-manipulation-patterns §4.2``);
M11 will consume the per-type counts emitted here.
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

_METRIC_ID = "DCMA-4"
_METRIC_NAME = "Relationship Types"
_SOURCE_SKILL = "dcma-14-point-assessment §4.4"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — FS Relationship %; threshold ≥ 90%"
)


def _name_by_uid(schedule: Schedule) -> dict[int, str]:
    return {t.unique_id: t.name for t in schedule.tasks}


def _format_breakdown(fs: int, ss: int, ff: int, sf: int, total: int) -> str:
    if total == 0:
        return "FS=0 SS=0 FF=0 SF=0 (total=0)"

    def pct(n: int) -> str:
        return f"{(n / total) * 100:.2f}%"

    return (
        f"FS={fs} ({pct(fs)}) "
        f"SS={ss} ({pct(ss)}) "
        f"FF={ff} ({pct(ff)}) "
        f"SF={sf} ({pct(sf)})"
    )


def run_relationship_types(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 4 (Relationship Types).

    See module docstring for formula, threshold, and zero-relations
    behaviour.
    """
    opts = options if options is not None else MetricOptions()
    threshold = ThresholdConfig(
        value=opts.fs_threshold_pct,
        direction=">=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.fs_threshold_pct != 90.0,
    )

    counts: dict[RelationType, int] = {
        RelationType.FS: 0,
        RelationType.SS: 0,
        RelationType.FF: 0,
        RelationType.SF: 0,
    }
    for r in schedule.relations:
        counts[r.relation_type] += 1
    total = sum(counts.values())

    if total == 0:
        # RT5 — division-by-zero guard. WARN, not PASS, because a
        # zero-relations schedule cannot have a meaningful FS share.
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.WARN,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=None,
            notes="no relations — FS share undefined",
        )

    fs_count = counts[RelationType.FS]
    fs_pct = (fs_count / total) * 100.0
    severity = (
        Severity.PASS if fs_pct >= opts.fs_threshold_pct else Severity.FAIL
    )

    names = _name_by_uid(schedule)
    offenders: list[Offender] = []
    for r in schedule.relations:
        if r.relation_type is RelationType.FS:
            continue
        offenders.append(
            Offender(
                unique_id=r.predecessor_unique_id,
                name=names.get(r.predecessor_unique_id, ""),
                successor_unique_id=r.successor_unique_id,
                successor_name=names.get(r.successor_unique_id, ""),
                relation_type=r.relation_type.name,
                value=r.relation_type.name,
            )
        )

    notes = _format_breakdown(
        fs=counts[RelationType.FS],
        ss=counts[RelationType.SS],
        ff=counts[RelationType.FF],
        sf=counts[RelationType.SF],
        total=total,
    )

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=severity,
        threshold=threshold,
        numerator=fs_count,
        denominator=total,
        offenders=tuple(offenders),
        computed_value=fs_pct,
        notes=notes,
    )


class RelationshipTypesMetric(BaseMetric):
    """Class wrapper around :func:`run_relationship_types`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_relationship_types(schedule, options)
