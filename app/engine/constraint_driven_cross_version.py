"""Constraint-driven cross-version comparator — Milestone 11 Block 3.

Compares the constraint-driven predecessor edges (BUILD-PLAN §2.20 /
AM10 three-bucket partition) across two schedule versions and emits a
:class:`~app.contracts.manipulation_scoring.ConstraintDrivenCrossVersionResult`
for the M11 scoring engine (Block 4).

This module is purpose-built for M11. It does NOT call the M9/M10
cross-version wrapper
(:func:`app.engine.driving_path.trace_driving_path_cross_version`).
When pre-computed :class:`~app.engine.driving_path_types.DrivingPathResult`
objects are not supplied, the facade calls
:func:`app.engine.driving_path.trace_driving_path` directly once per
period.

Authority:

* BUILD-PLAN §2.22 (AM12, 4/23/2026) subsection (f) — status-date
  windowing rule: exclude predecessor edges whose Period A finish
  falls on or before Period B ``status_date``.
* BUILD-PLAN §2.23 (AM13, 4/24/2026) — comparative-metric anchor
  correction. Replaces the two pre-AM13 ``*_status_date_days_offset``
  float fields with five absolute-date / working-days-elapsed fields
  on :class:`ConstraintDrivenCrossVersionResult`.
* BUILD-PLAN §2.20 (AM10) — three-bucket partition; the
  ``ConstraintDrivenPredecessor`` container this module operates on.
* BUILD-PLAN §2.21 (AM11) — M10.2 ``skipped_cycle_participants``;
  the cycle-skip override that retains edges whose predecessor's
  CPM dates are non-authoritative.
* ``forensic-manipulation-patterns §§4.4, 4.5, 9`` — constraint
  injection, constraint removal hiding slip, cross-version erosion.
* ``driving-slack-and-paths §9`` — Period A slack but-for rule.
  Period B's ``status_date`` is the authoritative anchor for both
  periods per AM12 §f (Period A is measured against where Period B
  stands).

Scope boundary (BUILD-PLAN §2.22 Block 3): this module performs set
algebra over successor UIDs and emits filtered per-successor
predecessor dicts plus the five AM13 anchor fields. It does NOT
compute manipulation scores, severity tiers, or
:class:`~app.contracts.manipulation_scoring.SlackState` transitions
— those belong to Block 4.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.contracts.manipulation_scoring import ConstraintDrivenCrossVersionResult
from app.engine.calendar_math import working_minutes_between
from app.engine.driving_path import trace_driving_path
from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathResult,
)
from app.engine.units import minutes_to_days
from app.engine.windowing import is_legitimate_actual
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task


def _tasks_by_uid(schedule: Schedule) -> dict[int, Task]:
    """Index a schedule's tasks by ``unique_id``.

    Mirrors the private helper in :mod:`app.engine.driving_path` but
    duplicated here so Block 3 does not depend on a private symbol
    from the frozen M10 module.
    """
    return {t.unique_id: t for t in schedule.tasks}


def _resolve_schedule_calendar(schedule: Schedule) -> Calendar | None:
    """Resolve a schedule's working-time calendar or return ``None``.

    Returns ``None`` when the schedule carries no calendars at all;
    this is the "no resolvable calendar" branch for the AM13
    ``period_working_days_elapsed`` derivation. When calendars are
    present, prefers a name match on ``default_calendar_name`` and
    falls back to the first calendar — matching the resolution order
    used by :func:`app.engine.driving_path._schedule_calendar`
    without reimplementing the synthetic-default fallback that is
    only meaningful for CPM computation.
    """
    if not schedule.calendars:
        return None
    for cal in schedule.calendars:
        if cal.name == schedule.default_calendar_name:
            return cal
    return schedule.calendars[0]


def _compute_working_days_elapsed(
    schedule_b: Schedule,
    period_a_status_date: datetime | None,
    period_b_status_date: datetime | None,
) -> float | None:
    """Working-days-elapsed between the two status dates using B's calendar.

    Returns ``None`` when either status date is ``None`` or when
    :func:`_resolve_schedule_calendar` cannot resolve a calendar for
    Schedule B. Does NOT clamp negative results — a caller reasons
    about direction.

    Rationale: Period B's calendar is the current-period anchor;
    Period A's calendar may be stale if calendars were replaced in
    the interim (AM13).
    """
    if period_a_status_date is None or period_b_status_date is None:
        return None
    cal = _resolve_schedule_calendar(schedule_b)
    if cal is None:
        return None
    minutes = working_minutes_between(
        period_a_status_date, period_b_status_date, cal
    )
    return minutes_to_days(
        float(minutes), schedule_b.project_calendar_hours_per_day
    )


class ConstraintDrivenCrossVersionComparator:
    """Compares constraint-driven predecessor edges across two schedule versions.

    Constructor takes both :class:`~app.models.schedule.Schedule`
    objects and both pre-computed
    :class:`~app.engine.driving_path_types.DrivingPathResult` objects
    (one per period). :meth:`compare` is parameterless and returns a
    :class:`~app.contracts.manipulation_scoring.ConstraintDrivenCrossVersionResult`.

    Purpose-built for M11. Does NOT reuse the M9/M10 cross-version
    wrapper. The facade
    :func:`compare_constraint_driven_cross_version` calls
    :func:`app.engine.driving_path.trace_driving_path` directly twice
    when DPRs are not supplied; the default expectation is that DPRs
    are supplied pre-computed.
    """

    def __init__(
        self,
        schedule_a: Schedule,
        schedule_b: Schedule,
        dpr_a: DrivingPathResult,
        dpr_b: DrivingPathResult,
    ) -> None:
        self._schedule_a = schedule_a
        self._schedule_b = schedule_b
        self._dpr_a = dpr_a
        self._dpr_b = dpr_b

    def compare(self) -> ConstraintDrivenCrossVersionResult:
        """Run the comparison and emit the result."""
        period_a_status_date = self._schedule_a.status_date
        period_b_status_date = self._schedule_b.status_date

        preds_by_succ_a = self._filtered_predecessors_by_successor(
            self._dpr_a,
            self._schedule_a,
            period_b_status_date,
            self._skipped_cycle_union(),
        )
        preds_by_succ_b = self._filtered_predecessors_by_successor(
            self._dpr_b,
            self._schedule_b,
            period_b_status_date,
            self._skipped_cycle_union(),
        )

        cd_uids_a = set(preds_by_succ_a.keys())
        cd_uids_b = set(preds_by_succ_b.keys())

        added = cd_uids_b - cd_uids_a
        removed = cd_uids_a - cd_uids_b
        retained = cd_uids_a & cd_uids_b

        period_working_days_elapsed = _compute_working_days_elapsed(
            self._schedule_b,
            period_a_status_date,
            period_b_status_date,
        )

        return ConstraintDrivenCrossVersionResult(
            period_a_result=self._dpr_a,
            period_b_result=self._dpr_b,
            period_a_status_date=period_a_status_date,
            period_b_status_date=period_b_status_date,
            period_a_project_start=self._schedule_a.project_start,
            period_b_project_start=self._schedule_b.project_start,
            period_working_days_elapsed=period_working_days_elapsed,
            added_constraint_driven_uids=added,
            removed_constraint_driven_uids=removed,
            retained_constraint_driven_uids=retained,
            period_a_predecessors_by_successor=preds_by_succ_a,
            period_b_predecessors_by_successor=preds_by_succ_b,
        )

    def _skipped_cycle_union(self) -> set[int]:
        """Union of ``skipped_cycle_participants`` across both DPRs.

        Per Section 6 of the Block 3 scope: cycle-skip participants
        are authoritative on either period; a predecessor UID
        appearing in either set suffices to override the
        ``is_legitimate_actual`` exclusion.
        """
        return set(self._dpr_a.skipped_cycle_participants) | set(
            self._dpr_b.skipped_cycle_participants
        )

    @staticmethod
    def _filtered_predecessors_by_successor(
        dpr: DrivingPathResult,
        schedule: Schedule,
        period_b_status_date: datetime | None,
        skipped_cycle_union: set[int],
    ) -> dict[int, tuple[ConstraintDrivenPredecessor, ...]]:
        """Group and filter a DPR's constraint-driven predecessors.

        Applies the AM12 §f + AM13 status-date filter:

        * If ``period_b_status_date`` is ``None``: retain every edge
          (cannot apply the filter without a Period B anchor).
        * If the predecessor task is missing from ``schedule``:
          retain the edge.
        * If the predecessor UID appears in ``skipped_cycle_union``:
          retain the edge (cycle-skip override — predecessor's CPM
          dates are non-authoritative, so the legitimate-actual
          predicate would be misleading).
        * If :func:`app.engine.windowing.is_legitimate_actual` fires
          for the predecessor task against ``period_b_status_date``:
          exclude the edge.
        * Otherwise: retain the edge.

        Returns a mapping from successor UID to a tuple of surviving
        predecessors, preserving M10.1 emission order (ascending by
        ``(successor_uid, predecessor_uid)`` per the
        :class:`DrivingPathResult` contract). A successor UID whose
        every predecessor was filtered out does NOT appear as a key.
        """
        tasks = _tasks_by_uid(schedule)
        surviving: dict[int, list[ConstraintDrivenPredecessor]] = defaultdict(list)

        for pred in dpr.constraint_driven_predecessors:
            if not _edge_survives_filter(
                pred,
                tasks,
                period_b_status_date,
                skipped_cycle_union,
            ):
                continue
            surviving[pred.successor_uid].append(pred)

        return {uid: tuple(preds) for uid, preds in surviving.items()}


def _edge_survives_filter(
    pred: ConstraintDrivenPredecessor,
    tasks_by_uid: dict[int, Task],
    period_b_status_date: datetime | None,
    skipped_cycle_union: set[int],
) -> bool:
    """Return True iff the constraint-driven edge survives the AM12/AM13 filter.

    Delegates the legitimate-actual comparison to
    :func:`app.engine.windowing.is_legitimate_actual` — the helper is
    the canonical site for the "Period A finish ≤ Period B
    ``status_date``" predicate (skill authority:
    ``forensic-manipulation-patterns §3.2``;
    ``driving-slack-and-paths §10``).
    """
    # Cannot apply the filter without a Period B anchor.
    if period_b_status_date is None:
        return True

    # Cycle-skip override: a predecessor whose CPM dates were skipped
    # carries non-authoritative finishes and must not be filtered out
    # on the basis of those finishes (BUILD-PLAN §2.21).
    if pred.predecessor_uid in skipped_cycle_union:
        return True

    predecessor_task = tasks_by_uid.get(pred.predecessor_uid)
    if predecessor_task is None:
        return True

    # is_legitimate_actual's 4-arg contract was designed for the M9
    # delta-row comparator; here the predecessor task plays both the
    # Period A and Period B roles (it is the single task whose finish
    # is compared) and ``period_b_status_date`` is the sole cutoff.
    # Passing the cutoff for both status_date args satisfies the
    # helper's non-None boundary while leaving the authoritative
    # "Period A finish ≤ Period B status_date" comparison intact.
    if is_legitimate_actual(
        predecessor_task,
        predecessor_task,
        period_b_status_date,
        period_b_status_date,
    ):
        return False

    return True


def compare_constraint_driven_cross_version(
    schedule_a: Schedule,
    schedule_b: Schedule,
    dpr_a: DrivingPathResult | None = None,
    dpr_b: DrivingPathResult | None = None,
    *,
    focus_uid: int | None = None,
) -> ConstraintDrivenCrossVersionResult:
    """Facade for the constraint-driven cross-version comparator.

    Constructs and runs a :class:`ConstraintDrivenCrossVersionComparator`.
    If ``dpr_a`` or ``dpr_b`` is ``None``, computes the missing DPR
    via :func:`app.engine.driving_path.trace_driving_path` directly —
    never via the M9/M10 cross-version wrapper.

    Args:
        schedule_a: Period A schedule. Read-only.
        schedule_b: Period B schedule. Read-only.
        dpr_a: Pre-computed Period A driving-path result, or ``None``
            to compute on demand.
        dpr_b: Pre-computed Period B driving-path result, or ``None``
            to compute on demand.
        focus_uid: Focus Point UID passed to
            :func:`trace_driving_path` when a DPR is computed on
            demand. The default expectation is that DPRs are supplied
            pre-computed; this argument is only consulted on the
            lazy path.

    Returns:
        :class:`ConstraintDrivenCrossVersionResult` — the Block 3
        frozen emission consumed by the M11 scoring engine.
    """
    if dpr_a is None:
        dpr_a = trace_driving_path(schedule_a, focus_uid)
    if dpr_b is None:
        dpr_b = trace_driving_path(schedule_b, focus_uid)
    comparator = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    )
    return comparator.compare()


__all__ = [
    "ConstraintDrivenCrossVersionComparator",
    "compare_constraint_driven_cross_version",
]
