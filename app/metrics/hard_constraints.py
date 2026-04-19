"""DCMA Metric 5 — Hard Constraints.

**Formula** (``dcma-14-point-assessment §4.5``):

    numerator   = count of eligible tasks whose ``constraint_type``
                  is one of the four 09NOV09 hard constraints:
                  MSO, MFO, SNLT, FNLT.
    denominator = count of eligible tasks (excluding summary, LOE,
                  and 100%-complete tasks per §3).
    percentage  = numerator / denominator * 100
    threshold   = ≤ 5% (configurable via
                  MetricOptions.hard_constraints_threshold_pct)

**DECM cross-reference.** ``acumen-reference §4.4`` maps Metric 5 to
the DECM ``Hard Constraints`` row under Guideline 6 of
``DeltekDECMMetricsJan2022.xlsx`` (sheet *Metrics*).

**09NOV09 hard-constraint list.** Per ``§4.5`` and BUILD-PLAN §5 M6
AC 1, only four constraint types are counted:

* ``MUST_START_ON`` (MSO)
* ``MUST_FINISH_ON`` (MFO)
* ``START_NO_LATER_THAN`` (SNLT)
* ``FINISH_NO_LATER_THAN`` (FNLT)

``START_NO_EARLIER_THAN`` (SNET) and ``FINISH_NO_EARLIER_THAN`` (FNET)
are **soft** constraints — they cannot push a task later than CPM
would otherwise — and are excluded. ``AS_LATE_AS_POSSIBLE`` (ALAP)
is not counted here either; it carries its own manipulation signal
path in Milestone 11 per ``forensic-manipulation-patterns §5.3``.

**Forensic read.** A hard-constrained task overrides CPM logic — the
date drives even when upstream slip would otherwise push the task
right. A rising Metric-5 rate across versions is a classic "pin the
milestone" tactic (``forensic-manipulation-patterns §4.1``); the M11
manipulation engine consumes this metric's offender list without
re-deriving it.
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
from app.models.enums import HARD_CONSTRAINTS
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-5"
_METRIC_NAME = "Hard Constraints"
_SOURCE_SKILL = "dcma-14-point-assessment §4.5"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Hard Constraints "
    "(MSO/MFO/SNLT/FNLT per 09NOV09); threshold ≤ 5%"
)


def _is_loe(task: Task, options: MetricOptions) -> bool:
    """Return True when ``task`` should be treated as Level-of-Effort.

    Honors :attr:`Task.is_loe` and falls back to the opt-in
    :attr:`MetricOptions.loe_name_patterns` list. Default behaviour
    mirrors :mod:`app.metrics.logic`.
    """
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _is_excluded(task: Task, options: MetricOptions) -> bool:
    """Return True when ``task`` should be dropped from the Metric-5
    denominator per ``dcma-14-point-assessment §3`` (summary, LOE,
    100% complete)."""
    if options.exclude_summary and task.is_summary:
        return True
    if options.exclude_loe and _is_loe(task, options):
        return True
    if options.exclude_completed and task.percent_complete >= 100.0:
        return True
    return False


def run_hard_constraints(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 5 (Hard Constraints).

    See module docstring for formula, threshold, and the 09NOV09
    hard-constraint enumeration.
    """
    opts = options if options is not None else MetricOptions()
    # Threshold citation: dcma-14-point-assessment §4.5; DECM sheet
    # Metrics, Guideline 6 (Hard Constraints).
    threshold = ThresholdConfig(
        value=opts.hard_constraints_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.hard_constraints_threshold_pct != 5.0,
    )

    eligible: list[Task] = [
        t for t in schedule.tasks if not _is_excluded(t, opts)
    ]

    if not eligible:
        # Empty schedule or every task excluded → vacuous PASS with a
        # note rather than a spurious division-by-zero.
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes="no eligible tasks (empty schedule or all excluded)",
        )

    offenders: list[Offender] = []
    for t in eligible:
        # HARD_CONSTRAINTS is the 09NOV09 four-constraint frozenset
        # defined in app.models.enums (MSO/MFO/SNLT/FNLT). SNET/FNET
        # and ALAP are explicitly excluded by AC 1.
        if t.constraint_type in HARD_CONSTRAINTS:
            offenders.append(
                Offender(
                    unique_id=t.unique_id,
                    name=t.name,
                    value=t.constraint_type.name,
                )
            )

    denominator = len(eligible)
    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = (
        Severity.PASS
        if pct <= opts.hard_constraints_threshold_pct
        else Severity.FAIL
    )

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


class HardConstraintsMetric(BaseMetric):
    """Class wrapper around :func:`run_hard_constraints`."""

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_hard_constraints(schedule, options)
