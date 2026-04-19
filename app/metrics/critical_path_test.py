"""DCMA Metric 12 — Critical Path Test (structural).

**Formula** (``dcma-14-point-assessment §4.12``):

Verify that an unbroken chain of zero-total-slack tasks connects the
project start milestone to the project finish milestone via
predecessor relations. If such a chain exists, the CPT passes; if
the critical path has a gap (a positive-slack break or a missing
link), the CPT fails.

**Protocol rationale.** DCMA's canonical CPT (skill §4.12) adds 600
working days to a critical task's remaining duration, re-runs CPM on
a copied schedule, and asserts that the project finish shifts by the
full delay. Phase 1 ships the **structural** variant: we verify the
critical-path topology directly from ``CPMResult`` without the
+600-WD probe. Rationale (BUILD-PLAN §5 M7 scope notes, §9.1
ledger):

* The M4 CPM engine already emits ``total_slack_minutes`` and
  ``critical_path_uids``; the structural check reuses them.
* A structural break surfaces the same forensic question (the
  critical path is broken) with cleaner evidence — the gap task's
  ``unique_id`` and slack value — and without the mutation risk of
  a +600-WD rebuild.
* The +600-WD probe remains a Phase 2 cross-check; it is not the
  Phase 1 implementation.

**Endpoint convention.**

* **Project start milestone:** the unique task with
  ``is_milestone=True`` and no incoming predecessor relation.
* **Project finish milestone:** the unique task with
  ``is_milestone=True`` and no outgoing successor relation.

When multiple endpoint candidates exist (e.g., the schedule has
several detached milestones), the earliest-by-``early_start`` wins
for start and the latest-by-``early_finish`` wins for finish. When
neither a start milestone nor a finish milestone can be identified
— typically a schedule without bracketing milestones — the metric
returns an indicator-only WARN rather than raising; downstream
narrative flags the inspection gap.

**Traversal.** Backward BFS from the finish milestone, following
each predecessor whose task is critical
(``total_slack_minutes <= 0`` OR present in
``CPMResult.critical_path_uids``). If the traversal reaches the
start milestone, the chain is unbroken and the metric PASSes.
Otherwise the last reachable critical task(s) with no critical
predecessor are reported as gap evidence and the metric FAILs.

**Result encoding.** Binary pass/fail via ``MetricResult`` with:

* ``numerator=1, denominator=1`` on PASS; ``numerator=0,
  denominator=1`` on FAIL. ``computed_value=100.0`` on PASS,
  ``0.0`` on FAIL.
* ``threshold.direction="structural-pass-fail"`` (new string
  literal) so downstream consumers can switch on the structural
  case without comparing floats (BUILD-PLAN §3.10).
* ``threshold.value=1.0`` and ``threshold.is_overridden=False``
  because CPT has no numeric threshold.

**Mutation invariance.** The metric reads ``Schedule`` relations
and ``CPMResult.tasks`` read-only; no copy, no rebuild. M5 + M6 +
M7 mutation-invariance tests cover this contract (BUILD-PLAN §3.5;
``tests/_utils.cpm_result_snapshot``).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.engine.result import CPMResult
from app.metrics.base import (
    BaseMetric,
    MetricResult,
    Offender,
    Severity,
    ThresholdConfig,
)
from app.metrics.exceptions import MissingCPMResultError
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule
from app.models.task import Task

_METRIC_ID = "DCMA-12"
_METRIC_NAME = "Critical Path Test"
_SOURCE_SKILL = "dcma-14-point-assessment §4.12"
_SOURCE_DECM = (
    "DECM sheet Metrics, Guideline 6 — Critical Path Test "
    "(structural zero-slack chain; DECM does not publish a row, "
    "threshold is binary pass/fail per DCMA protocol)"
)


def _predecessors_map(schedule: Schedule) -> dict[int, list[int]]:
    """Return ``{successor_uid: [predecessor_uids...]}``."""
    out: dict[int, list[int]] = defaultdict(list)
    for r in schedule.relations:
        out[r.successor_unique_id].append(r.predecessor_unique_id)
    return out


def _successors_map(schedule: Schedule) -> dict[int, list[int]]:
    """Return ``{predecessor_uid: [successor_uids...]}``."""
    out: dict[int, list[int]] = defaultdict(list)
    for r in schedule.relations:
        out[r.predecessor_unique_id].append(r.successor_unique_id)
    return out


def _find_endpoints(
    schedule: Schedule,
    cpm_result: CPMResult,
) -> tuple[int | None, int | None]:
    """Identify the project start and finish milestone UIDs.

    Start milestone = ``is_milestone=True`` with no incoming
    relation. Finish milestone = ``is_milestone=True`` with no
    outgoing relation. Ties broken by CPM early_start (min for start,
    max for finish).
    """
    pred_map = _predecessors_map(schedule)
    succ_map = _successors_map(schedule)

    start_candidates: list[Task] = []
    finish_candidates: list[Task] = []
    for t in schedule.tasks:
        if not t.is_milestone:
            continue
        if not pred_map.get(t.unique_id):
            start_candidates.append(t)
        if not succ_map.get(t.unique_id):
            finish_candidates.append(t)

    def _early_start(t: Task) -> datetime:
        tc = cpm_result.tasks.get(t.unique_id)
        if tc is not None and tc.early_start is not None:
            return tc.early_start
        return t.early_start or t.start or datetime.max

    def _early_finish(t: Task) -> datetime:
        tc = cpm_result.tasks.get(t.unique_id)
        if tc is not None and tc.early_finish is not None:
            return tc.early_finish
        return t.early_finish or t.finish or datetime.min

    start_uid: int | None = None
    finish_uid: int | None = None
    if start_candidates:
        start_uid = min(start_candidates, key=_early_start).unique_id
    if finish_candidates:
        finish_uid = max(finish_candidates, key=_early_finish).unique_id
    return start_uid, finish_uid


def _is_critical(uid: int, cpm_result: CPMResult) -> bool:
    """A task is critical iff its total slack is ≤ 0 or it appears
    in the engine's ``critical_path_uids`` set."""
    if uid in cpm_result.critical_path_uids:
        return True
    tc = cpm_result.tasks.get(uid)
    if tc is None:
        return False
    return tc.total_slack_minutes <= 0


def _threshold_config() -> ThresholdConfig:
    return ThresholdConfig(
        value=1.0,
        direction="structural-pass-fail",
        source_skill_section=_SOURCE_SKILL,
        source_decm_row=_SOURCE_DECM,
        is_overridden=False,
    )


def run_critical_path_test(
    schedule: Schedule,
    cpm_result: CPMResult | None = None,
    options: MetricOptions | None = None,
) -> MetricResult:
    """Compute DCMA Metric 12 (Critical Path Test, structural).

    Raises :class:`~app.metrics.exceptions.MissingCPMResultError`
    when ``cpm_result is None`` — the metric cannot compute without
    engine output. See module docstring for the endpoint-identifying
    convention and traversal rules.
    """
    # options unused today — reserved for future CPT knobs; accept it
    # to match the metric calling convention. Touching it preserves
    # call-site homogeneity without invoking MetricOptions validation.
    del options
    if cpm_result is None:
        raise MissingCPMResultError(_METRIC_ID)

    threshold = _threshold_config()

    start_uid, finish_uid = _find_endpoints(schedule, cpm_result)
    if start_uid is None or finish_uid is None:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.WARN,
            threshold=threshold,
            numerator=0,
            denominator=1,
            offenders=(),
            computed_value=None,
            notes=(
                "project endpoint milestones not identifiable "
                "(requires start + finish milestones with no "
                "predecessor / successor respectively)"
            ),
        )

    tasks_by_uid = {t.unique_id: t for t in schedule.tasks}

    # Backward BFS from the finish milestone, following critical
    # predecessors. Mark every critical task we reach.
    reachable: set[int] = set()
    stack: list[int] = [finish_uid]
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        if cur == start_uid:
            continue
        pred_map = _predecessors_map(schedule)
        for p in pred_map.get(cur, []):
            if _is_critical(p, cpm_result) and p not in reachable:
                stack.append(p)

    if not _is_critical(finish_uid, cpm_result):
        # The finish milestone itself isn't critical — the chain is
        # broken at the top. Record the finish as the gap.
        finish_task = tasks_by_uid.get(finish_uid)
        fname = finish_task.name if finish_task else ""
        tc = cpm_result.tasks.get(finish_uid)
        ts = tc.total_slack_minutes if tc else 0
        offenders = (
            Offender(
                unique_id=finish_uid,
                name=fname,
                value=(
                    f"project finish milestone is NOT critical "
                    f"(total_slack_minutes={ts})"
                ),
            ),
        )
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.FAIL,
            threshold=threshold,
            numerator=0,
            denominator=1,
            offenders=offenders,
            computed_value=0.0,
            notes=(
                "CPT failed — project finish milestone not on "
                "critical path"
            ),
        )

    if start_uid in reachable:
        return MetricResult(
            metric_id=_METRIC_ID,
            metric_name=_METRIC_NAME,
            severity=Severity.PASS,
            threshold=threshold,
            numerator=1,
            denominator=1,
            offenders=(),
            computed_value=100.0,
            notes=(
                f"zero-slack chain reaches start_uid={start_uid} "
                f"from finish_uid={finish_uid}"
            ),
        )

    # FAIL — gap on the backward walk. Identify dead-end reachable
    # critical tasks with no critical predecessor.
    gap_offenders: list[Offender] = []
    pred_map = _predecessors_map(schedule)
    for uid in sorted(reachable):
        if uid == start_uid:
            continue
        preds = pred_map.get(uid, [])
        has_critical_pred = any(_is_critical(p, cpm_result) for p in preds)
        if not has_critical_pred:
            task = tasks_by_uid.get(uid)
            tc = cpm_result.tasks.get(uid)
            ts = tc.total_slack_minutes if tc else 0
            gap_offenders.append(
                Offender(
                    unique_id=uid,
                    name=task.name if task else "",
                    value=(
                        f"gap: no critical predecessor; "
                        f"total_slack_minutes={ts}"
                    ),
                )
            )

    return MetricResult(
        metric_id=_METRIC_ID,
        metric_name=_METRIC_NAME,
        severity=Severity.FAIL,
        threshold=threshold,
        numerator=0,
        denominator=1,
        offenders=tuple(gap_offenders),
        computed_value=0.0,
        notes=(
            f"CPT failed — zero-slack chain from finish_uid={finish_uid} "
            f"did not reach start_uid={start_uid}"
        ),
    )


class CriticalPathTestMetric(BaseMetric):
    """Class wrapper around :func:`run_critical_path_test`.

    Exposes the CPMResult argument as a keyword to match the M6
    High-Float / Negative-Float wrapper convention.
    """

    metric_id = _METRIC_ID
    metric_name = _METRIC_NAME
    source_skill_section = _SOURCE_SKILL
    source_decm_row = _SOURCE_DECM

    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
        cpm_result: CPMResult | None = None,
    ) -> MetricResult:
        return run_critical_path_test(schedule, cpm_result, options)
