"""DCMA Metric 1 — Missing Logic.

**Formula** (``dcma-14-point-assessment §4.1``):

    numerator   = count of incomplete tasks with zero predecessors
                  OR zero successors
    denominator = count of incomplete tasks (excluding summary, LOE,
                  and 100%-complete tasks per §3)
    percentage  = numerator / denominator * 100
    threshold   = ≤ 5% (configurable via
                  MetricOptions.logic_threshold_pct)

**DECM cross-reference.** The check aggregates two DECM rows that
DECM splits but DCMA reports as one (``acumen-reference §4.4``):

* ``06A204b`` (Guideline 6, row 32) — dangling logic / missing
  predecessors and successors. Threshold ``X/Y = 0%`` in DECM, which
  is a stricter restatement; the DCMA protocol relaxes it to ≤5%.

The metric uses the DCMA 09NOV09 ≤5% threshold by default
(``dcma-14-point-assessment §4.1``).

**Project-endpoint exclusion.** The first/last milestones of the
network are excluded from the missing-predecessor / missing-successor
check because they legitimately have one-sided relations
(``dcma-14-point-assessment §4.1``). Detection is structural — see
:func:`_project_endpoints` — so it does not depend on naming
conventions.

**Forensic read.** A high Missing-Logic rate is the canonical
manipulation precursor (``forensic-manipulation-patterns §10``)
because an unconnected tail cannot propagate slip — see
``dcma-14-point-assessment §4.1`` "Forensic read".
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
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-1"
_METRIC_NAME = "Missing Logic"
_SOURCE_SKILL = "dcma-14-point-assessment §4.1"
_SOURCE_DECM = "06A204b (Guideline 6 row 32) — dangling logic / missing predecessors-successors"


def _is_loe(task: Task, options: MetricOptions) -> bool:
    """Return True when ``task`` should be treated as Level-of-Effort.

    Honors :attr:`Task.is_loe` (set by the parser if a custom MS
    Project field is present) and falls back to a case-insensitive
    name-substring check against
    :attr:`MetricOptions.loe_name_patterns` when the operator opts
    in. Default ``loe_name_patterns`` is empty — name-based detection
    is off until the operator turns it on.
    """
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _is_excluded(task: Task, options: MetricOptions) -> bool:
    """Return True when ``task`` should be dropped from the
    Missing-Logic denominator entirely.

    Per ``dcma-14-point-assessment §3``: summary, LOE, and 100%
    complete tasks are excluded. Milestones are *not* excluded here
    — only the project endpoint milestones (start/finish) are
    excluded, and the endpoint detection runs separately.
    """
    if options.exclude_summary and task.is_summary:
        return True
    if options.exclude_loe and _is_loe(task, options):
        return True
    if options.exclude_completed and task.percent_complete >= 100.0:
        return True
    return False


def _project_endpoints(
    tasks: list[Task],
    relations: list[Relation],
) -> set[int]:
    """Return UniqueIDs that are project start or project finish
    milestones — i.e. milestones that, by network structure, have
    only one side of a relation.

    A "project start" milestone is a task with ``is_milestone=True``
    and zero predecessors in the network. A "project finish"
    milestone is a task with ``is_milestone=True`` and zero
    successors. Per ``dcma-14-point-assessment §4.1`` these
    legitimately carry one-sided logic and must not flag as Missing
    Logic.

    Returns ``set()`` for empty schedules.
    """
    if not tasks:
        return set()
    has_pred: set[int] = set()
    has_succ: set[int] = set()
    for r in relations:
        has_succ.add(r.predecessor_unique_id)
        has_pred.add(r.successor_unique_id)
    endpoints: set[int] = set()
    for t in tasks:
        if not t.is_milestone:
            continue
        if t.unique_id not in has_pred or t.unique_id not in has_succ:
            endpoints.add(t.unique_id)
    return endpoints


def run_logic(
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 1 (Missing Logic).

    See module docstring for formula, threshold, and exclusions.
    """
    opts = options if options is not None else MetricOptions()
    threshold = ThresholdConfig(
        value=opts.logic_threshold_pct,
        direction="<=",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=opts.logic_threshold_pct != 5.0,
    )

    # Build the eligible-task population per §3 exclusions.
    eligible: list[Task] = [
        t for t in schedule.tasks if not _is_excluded(t, opts)
    ]

    if not eligible:
        # L5 / L6: empty schedule or all tasks complete → vacuous PASS.
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes="no eligible tasks (empty schedule or all complete)",
        )

    endpoints: set[int] = (
        _project_endpoints(schedule.tasks, schedule.relations)
        if opts.exclude_milestones_from_logic
        else set()
    )

    # Map UID -> set of predecessor UIDs and set of successor UIDs.
    pred_map: dict[int, set[int]] = {t.unique_id: set() for t in eligible}
    succ_map: dict[int, set[int]] = {t.unique_id: set() for t in eligible}
    for r in schedule.relations:
        if r.successor_unique_id in pred_map:
            pred_map[r.successor_unique_id].add(r.predecessor_unique_id)
        if r.predecessor_unique_id in succ_map:
            succ_map[r.predecessor_unique_id].add(r.successor_unique_id)

    offenders: list[Offender] = []
    for t in eligible:
        if t.unique_id in endpoints:
            continue
        missing_pred = len(pred_map[t.unique_id]) == 0
        missing_succ = len(succ_map[t.unique_id]) == 0
        if missing_pred and missing_succ:
            label = "missing_predecessor_and_successor"
        elif missing_pred:
            label = "missing_predecessor"
        elif missing_succ:
            label = "missing_successor"
        else:
            continue
        offenders.append(
            Offender(unique_id=t.unique_id, name=t.name, value=label)
        )

    denominator = len(eligible) - sum(1 for t in eligible if t.unique_id in endpoints)
    if denominator <= 0:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=0,
            denominator=0,
            offenders=(),
            computed_value=0.0,
            notes="only project endpoint milestones present; vacuous PASS",
        )

    numerator = len(offenders)
    pct = (numerator / denominator) * 100.0
    severity = Severity.PASS if pct <= opts.logic_threshold_pct else Severity.FAIL

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


class LogicMetric(BaseMetric):
    """Class wrapper around :func:`run_logic`.

    Lets a metric registry hold a homogeneous list of metric
    instances; the function form is preferred for direct callers.
    """

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        return run_logic(schedule, options)
