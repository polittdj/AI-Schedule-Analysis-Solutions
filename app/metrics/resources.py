"""DCMA Metric 10 — Resources.

**Formula** (``dcma-14-point-assessment §4.10``):

    numerator   = count of eligible incomplete tasks with
                  ``resource_count == 0``.
    denominator = count of eligible incomplete tasks (excluding
                  summary, LOE, and 100%-complete tasks per §3).
    percentage  = numerator / denominator * 100
    threshold   = none — DECM leaves Metric 10 as a ratio without a
                  pass/fail threshold (BUILD-PLAN §5 M6 AC 5).

**Grouping rationale.** Metric 10 is a *simple ratio* (one
population, one predicate per task, no CPM consumption and no
date-comparison arithmetic). It is grouped in M6 with the other
simple-ratio metrics (Hard Constraints, High Float, High Duration)
rather than in M7 (Invalid Dates, Missed Tasks, CPT, CPLI, BEI)
which all require date-comparison logic against ``status_date`` or
cross-version comparator plumbing. Metric 9 is the M7 counterpart
that groups cleanly with the date-sensitive metrics; Metric 10
groups cleanly here. See BUILD-PLAN §5 M6 preamble.

**DECM cross-reference.** ``acumen-reference §4.4`` maps Metric 10
to the DECM ``Resources`` row under Guideline 6 of
``DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*). DECM does not
publish a pass/fail threshold for this row; the DCMA 09NOV09
protocol tracks it as a qualitative indicator.

**No pass/fail flag.** Per AC 5, :attr:`MetricResult.severity` is
set to :attr:`Severity.WARN` — an indicator state that instructs
the narrative layer to render the ratio without asserting
compliance or non-compliance. Downstream narrative copy frames it
as "X% of incomplete tasks have no resource assignment; review the
offender list." The :class:`ThresholdConfig` carries a zero-value,
zero-direction sentinel annotated with the ``"indicator-only"``
notes so the threshold carrier remains schema-stable across all ten
metrics.

**Indicator-not-verdict.** Per ``dcma-14-point-assessment §6
Rule 1`` — every metric is a forensic signal, never a standalone
finding of fault. Metric 10 is the most literal expression of this
rule in the whole protocol; the missing pass/fail flag is a feature,
not a limitation.

**Forensic read.** Zero-resource tasks fail to integrate with the
EVMS (``dcma-14-point-assessment §4.10``). A sustained high ratio
across versions is a candidate for delayed work authorization
("paper schedule vs. funded schedule") or a cost-side decoupling
that the schedule has not caught up with. Phase 3 (Earned Value)
will consume the offender list directly.
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
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-10"
_METRIC_NAME = "Resources"
_SOURCE_SKILL = "dcma-14-point-assessment §4.10"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Resources "
    "(resource_count == 0); no pass/fail threshold published"
)


def _is_loe(task: Task, options: MetricOptions) -> bool:
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _is_excluded(task: Task, options: MetricOptions) -> bool:
    if options.exclude_summary and task.is_summary:
        return True
    if options.exclude_loe and _is_loe(task, options):
        return True
    if options.exclude_completed and task.percent_complete >= 100.0:
        return True
    return False


def _indicator_threshold() -> ThresholdConfig:
    """Indicator-only threshold carrier for Metric 10.

    DECM publishes no pass/fail threshold for this row; the
    :class:`ThresholdConfig` is kept populated (with sentinel values)
    so consumers of :class:`MetricResult` can rely on the field
    always being present. The ``source_decm_row`` explains the
    sentinel in text so the narrative layer does not misrender.
    """
    return ThresholdConfig(
        value=0.0,
        direction="indicator-only",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=False,
    )


def run_resources(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 10 (Resources).

    Returns a :class:`MetricResult` with ``severity = Severity.WARN``
    (the indicator state) regardless of the numerator/denominator
    mix. See module docstring for the no-pass/fail rationale.
    """
    opts = options if options is not None else MetricOptions()
    threshold = _indicator_threshold()

    eligible: list[Task] = [
        t for t in schedule.tasks if not _is_excluded(t, opts)
    ]

    if not eligible:
        # Empty / all-excluded → vacuous WARN with an explanatory
        # note. Not PASS, because Metric 10 doesn't have a pass/fail
        # grade; WARN is the consistent indicator state.
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.WARN,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes=(
                "no eligible tasks (empty schedule or all excluded); "
                "indicator-only — no pass/fail threshold"
            ),
        )

    offenders: list[Offender] = [
        Offender(unique_id=t.unique_id, name=t.name, value="resource_count=0")
        for t in eligible
        if t.resource_count == 0
    ]

    denominator = len(eligible)
    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=Severity.WARN,  # AC 5 — indicator-only, no pass/fail
        threshold=threshold,
        numerator=numerator,
        denominator=denominator,
        offenders=tuple(offenders),
        computed_value=pct,
        notes=(
            "indicator-only — no pass/fail threshold "
            "(dcma-14-point-assessment §4.10)"
        ),
    )


class ResourcesMetric(BaseMetric):
    """Class wrapper around :func:`run_resources`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_resources(schedule, options)
