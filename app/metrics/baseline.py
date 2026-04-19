"""Baseline comparison plumbing for the baseline-dependent DCMA
metrics shipped in M7 (Metric 11 Missed Tasks, Metric 13 CPLI,
Metric 14 BEI).

The baseline is consumed read-only from :class:`~app.models.task.Task`
fields (:attr:`baseline_start`, :attr:`baseline_finish`,
:attr:`baseline_duration_minutes`), populated by the Milestone 3
COM adapter from ``Task.BaselineStart`` / ``Task.BaselineFinish`` /
``Task.BaselineDuration``. Baseline is **not** a separate
:class:`~app.models.schedule.Schedule` object — Phase 1 assumes a
single schedule file carries both current and baseline fields, per
``mpp-parsing-com-automation §4``. A downstream phase may change this
(e.g., importing a separate baseline file); the plumbing here is the
single consumption surface the M7 metrics rely on, so a change
reverberates once.

No-baseline behaviour is **graceful** per BUILD-PLAN §2.15. Helpers
return ``None`` / ``False`` rather than raising; the baseline-required
metrics translate that into an indicator-only
:class:`~app.metrics.base.MetricResult` with a "no baseline
available" note so the narrative layer can explain the gap.

Authority:

* Baseline field names match M2 shipped model (``Task.baseline_start``
  / ``Task.baseline_finish`` / ``Task.baseline_duration_minutes``).
* Indicator-only framing — ``dcma-14-point-assessment §6 Rule 1``
  and BUILD-PLAN §2.15.
* UniqueID-only matching — BUILD-PLAN §2.7,
  ``mpp-parsing-com-automation §5``.

The module is pure-compute: no I/O, no COM, no network.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from app.engine.result import CPMResult
from app.models.schedule import Schedule
from app.models.task import Task


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    """Immutable UniqueID-keyed view over baseline fields.

    A light snapshot the narrative layer (M12) and the manipulation
    engine (M11) can pass around without re-reading ``Schedule.tasks``.
    The view is built once with :meth:`from_schedule` and is
    read-only; mutation-invariance (BUILD-PLAN §2.13) is preserved
    because :class:`Task` instances referenced here are the same
    Pydantic models the caller already holds.

    Keyed by ``Task.unique_id`` (BUILD-PLAN §2.7 — UniqueID is the
    only stable cross-version identifier).
    """

    baselines: Mapping[int, tuple[datetime | None, datetime | None, int]]
    """Mapping of ``unique_id`` → ``(baseline_start, baseline_finish,
    baseline_duration_minutes)``. Wrapped in
    :class:`types.MappingProxyType` so mutation of the dict is
    impossible at Python level."""

    @classmethod
    def from_schedule(cls, schedule: Schedule) -> BaselineComparison:
        """Build a :class:`BaselineComparison` from a :class:`Schedule`.

        Only tasks are snapshotted; milestones and summary tasks are
        included (they legitimately carry baseline dates). Callers
        filter at their own layer.
        """
        rows: dict[int, tuple[datetime | None, datetime | None, int]] = {}
        for t in schedule.tasks:
            rows[t.unique_id] = (
                t.baseline_start,
                t.baseline_finish,
                t.baseline_duration_minutes,
            )
        return cls(baselines=MappingProxyType(rows))

    def has(self, unique_id: int) -> bool:
        """True when the UniqueID has a populated ``baseline_finish``."""
        row = self.baselines.get(unique_id)
        return row is not None and row[1] is not None


def has_baseline(task: Task) -> bool:
    """Return True when the task carries a populated
    :attr:`~app.models.task.Task.baseline_finish`.

    The baseline-dependent metrics (11, 13, 14) key on
    ``baseline_finish`` because it is the date the DCMA formulas
    compare against the ``status_date``. A task with
    ``baseline_start`` set but ``baseline_finish = None`` is treated
    as unbaselined — the comparison is not well-defined.
    """
    return task.baseline_finish is not None


def baseline_slip_minutes(task: Task) -> int | None:
    """Return the signed baseline-finish slip in calendar minutes.

    ``current_finish - baseline_finish`` where ``current_finish`` is
    :attr:`Task.actual_finish` when the task has finished, otherwise
    :attr:`Task.finish` (the forecast). Positive values indicate the
    task is forecast (or actually finished) **later** than its
    baseline — conventional schedule-slip sign.

    Returns ``None`` when either the baseline or the current-finish
    source is missing; a baseline-required metric should translate
    that into an indicator-only result per BUILD-PLAN §2.15.

    The returned value is **calendar minutes**, not working minutes.
    Working-time precision at weekend / holiday boundaries is a
    Phase 2 refinement (§9.1 ledger); Phase 1 forensic interpretation
    tolerates the approximation because slip-sign alone drives the
    PASS / FAIL verdict and working-minute refinement does not flip
    signs away from exact-zero.
    """
    if task.baseline_finish is None:
        return None
    current = task.actual_finish if task.actual_finish is not None else task.finish
    if current is None:
        return None
    delta = current - task.baseline_finish
    return int(delta.total_seconds() // 60)


def tasks_with_baseline_finish_by(
    schedule: Schedule,
    cutoff: datetime,
) -> list[Task]:
    """Return tasks whose ``baseline_finish`` is ``<=`` ``cutoff``.

    The denominator population for Metric 11 (Missed Tasks) and
    Metric 14 (BEI). Tasks without a populated ``baseline_finish``
    are excluded — a task without a baseline cannot be "baseline-due
    by" anything. Summary tasks are included: the caller filters
    them out per the metric's own exclusion policy.

    ``cutoff`` must be timezone-aware (Task date fields are G1
    tz-aware); callers supply ``schedule.status_date`` or similar.
    """
    return [
        t
        for t in schedule.tasks
        if t.baseline_finish is not None and t.baseline_finish <= cutoff
    ]


def has_baseline_coverage(schedule: Schedule) -> bool:
    """Return True only when every non-milestone non-summary task
    carries a populated :attr:`Task.baseline_finish`.

    Used by the baseline-required metrics to decide whether to emit
    a computed result or an indicator-only "no baseline available"
    result. Milestones are exempt because zero-duration marker
    tasks often legitimately lack a baseline date in practice;
    summary tasks are exempt because their baseline is a roll-up.

    A schedule with zero tasks returns True vacuously — there is
    nothing to be missing a baseline for.
    """
    for t in schedule.tasks:
        if t.is_milestone or t.is_summary:
            continue
        if t.baseline_finish is None:
            return False
    return True


def baseline_critical_path_length_minutes(
    schedule: Schedule,
    cpm_result: CPMResult,
) -> int | None:
    """Return the calendar-minute span of the baseline critical path.

    Phase 1 approximation (§9.1 ledger): the span from the earliest
    ``baseline_start`` to the latest ``baseline_finish`` across tasks
    on the **current** critical path (``cpm_result.critical_path_uids``).
    Returns ``None`` when:

    * the CPM result has an empty critical-path set (e.g., every task
      cycle-skipped), or
    * any critical-path task lacks ``baseline_start`` /
      ``baseline_finish`` (we cannot honestly report a span with
      missing endpoints), or
    * the computed span is non-positive (pathological baseline
      where finish precedes start).

    The "baseline critical path" is approximated by the current
    critical path's baseline dates rather than by a separate CPM pass
    on projected baseline fields. Rationale: a proper baseline CPM
    would need baseline durations + baseline relations + baseline
    calendars; in practice the baseline relations are identical to
    current relations (the logic network does not change when a
    schedule is baselined), so the current critical-path UID set is
    a defensible stand-in for Phase 1. A full baseline-CPM variant
    lives in Phase 2 (§9.1 ledger).

    Returned minutes are **calendar** minutes for consistency with
    :func:`baseline_slip_minutes`. Metric 13 (CPLI) consumes both in
    the same unit.
    """
    if not cpm_result.critical_path_uids:
        return None

    by_uid = {t.unique_id: t for t in schedule.tasks}
    starts: list[datetime] = []
    finishes: list[datetime] = []
    for uid in cpm_result.critical_path_uids:
        t = by_uid.get(uid)
        if t is None:
            # A UID in the CPM result that isn't in the schedule is
            # a contract violation; we refuse to paper over it.
            return None
        if t.baseline_start is None or t.baseline_finish is None:
            return None
        starts.append(t.baseline_start)
        finishes.append(t.baseline_finish)

    if not starts or not finishes:
        return None

    span = max(finishes) - min(starts)
    minutes = int(span.total_seconds() // 60)
    if minutes <= 0:
        return None
    return minutes


__all__ = [
    "BaselineComparison",
    "baseline_critical_path_length_minutes",
    "baseline_slip_minutes",
    "has_baseline",
    "has_baseline_coverage",
    "tasks_with_baseline_finish_by",
]
