"""Tests for the constraint-driven cross-version comparator — M11 Block 3.

Exercises :mod:`app.engine.constraint_driven_cross_version` against the
Section 8 test floor (≥24 tests across eight categories). Scope is
deliberately narrow — this block stops at set algebra + filtered
per-successor dicts. No scoring, no severity tier, no SlackState
state-machine coverage (Block 4).

Authority:

* BUILD-PLAN §2.22 (AM12) subsection (f) — status-date windowing.
* BUILD-PLAN §2.23 (AM13) — absolute-date / working-days-elapsed
  anchor fields on
  :class:`~app.contracts.manipulation_scoring.ConstraintDrivenCrossVersionResult`.
* BUILD-PLAN §2.20 (AM10) — three-bucket partition origin of the
  :class:`~app.engine.driving_path_types.ConstraintDrivenPredecessor`
  rows this module operates on.
* BUILD-PLAN §2.21 (AM11) — M10.2 ``skipped_cycle_participants``
  cycle-skip override.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.contracts.manipulation_scoring import ConstraintDrivenCrossVersionResult
from app.engine.constraint_driven_cross_version import (
    ConstraintDrivenCrossVersionComparator,
    compare_constraint_driven_cross_version,
)
from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathNode,
    DrivingPathResult,
)
from app.models.calendar import Calendar
from app.models.enums import ConstraintType, RelationType
from app.models.schedule import Schedule
from app.models.task import Task

# Anchor datetimes used across the small deterministic fixtures. Every
# timestamp is tz-aware per the schedule / task validators (G1, G9).
_ANCHOR = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
_PRE_STATUS = datetime(2026, 1, 5, 16, 0, tzinfo=UTC)
_STATUS_A = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
_STATUS_B = datetime(2026, 2, 15, 8, 0, tzinfo=UTC)
_POST_STATUS = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)


# ----------------------------------------------------------------------
# Fixture builders — small, deterministic, no external I/O.
# ----------------------------------------------------------------------


def _make_cdp(
    pred_uid: int,
    succ_uid: int,
    *,
    slack_days: float = -1.0,
    constraint_type: ConstraintType = ConstraintType.MUST_START_ON,
    constraint_date: datetime | None = None,
    rationale: str = "negative slack held by hard constraint",
) -> ConstraintDrivenPredecessor:
    """Build a :class:`ConstraintDrivenPredecessor` with sensible defaults.

    Defaults to MSO with a non-``None`` constraint_date (required by
    the Task-level G7 rule when the constraint is date-bearing). The
    comparator itself never inspects ``predecessor_constraint_date``,
    but a realistic CDP record keeps the fixture grounded.
    """
    if constraint_date is None and constraint_type != ConstraintType.AS_SOON_AS_POSSIBLE:
        constraint_date = _ANCHOR
    return ConstraintDrivenPredecessor(
        predecessor_uid=pred_uid,
        predecessor_name=f"P{pred_uid}",
        successor_uid=succ_uid,
        successor_name=f"S{succ_uid}",
        relation_type=RelationType.FS,
        lag_days=0.0,
        slack_days=slack_days,
        calendar_hours_per_day=8.0,
        predecessor_constraint_type=constraint_type,
        predecessor_constraint_date=constraint_date,
        rationale=rationale,
    )


def _make_dpr(
    focus_uid: int = 1,
    *,
    constraint_driven_predecessors: list[ConstraintDrivenPredecessor] | None = None,
    skipped_cycle_participants: list[int] | None = None,
) -> DrivingPathResult:
    """Build a minimal :class:`DrivingPathResult`.

    Carries only the focus node and whichever CDP rows / cycle-skip
    entries the test supplies. ``edges`` and
    ``non_driving_predecessors`` remain empty — this block does not
    exercise those.
    """
    focus_node = DrivingPathNode(
        unique_id=focus_uid,
        name=f"Focus{focus_uid}",
        early_start=_ANCHOR,
        early_finish=_ANCHOR,
        late_start=_ANCHOR,
        late_finish=_ANCHOR,
        total_float_days=0.0,
        calendar_hours_per_day=8.0,
    )
    return DrivingPathResult(
        focus_point_uid=focus_uid,
        focus_point_name=f"Focus{focus_uid}",
        nodes={focus_uid: focus_node},
        edges=[],
        non_driving_predecessors=[],
        constraint_driven_predecessors=constraint_driven_predecessors or [],
        skipped_cycle_participants=skipped_cycle_participants or [],
    )


def _make_task(
    uid: int,
    *,
    name: str | None = None,
    finish: datetime | None = None,
) -> Task:
    """Build a minimal ASAP-constrained :class:`Task`.

    ASAP never carries a constraint_date (G6), so the default leaves
    ``constraint_date=None``. ``finish`` is the forecast finish the
    :func:`is_legitimate_actual` predicate consults.
    """
    return Task(
        unique_id=uid,
        task_id=uid,
        name=name or f"T{uid}",
        duration_minutes=480,
        finish=finish,
        constraint_type=ConstraintType.AS_SOON_AS_POSSIBLE,
    )


def _make_schedule(
    tasks: list[Task],
    *,
    status_date: datetime | None = None,
    project_start: datetime | None = _ANCHOR,
    calendars: list[Calendar] | None = None,
    hours_per_day: float = 8.0,
) -> Schedule:
    """Build a minimal :class:`Schedule` with a single Standard calendar.

    ``calendars`` defaults to a single ``Standard`` calendar; pass an
    explicit empty list to simulate a schedule with no resolvable
    calendar (used by the AM13 working-days-elapsed edge-case test).
    """
    if calendars is None:
        calendars = [Calendar(name="Standard")]
    return Schedule(
        name="test-schedule",
        status_date=status_date,
        project_start=project_start,
        project_calendar_hours_per_day=hours_per_day,
        tasks=tasks,
        calendars=calendars,
    )


# ----------------------------------------------------------------------
# Set algebra correctness (6 tests)
# ----------------------------------------------------------------------


def test_added_only() -> None:
    """A constraint-driven edge present only in Period B places the
    successor UID in ``added_constraint_driven_uids`` — the canonical
    B−A case."""
    dpr_a = _make_dpr()
    dpr_b = _make_dpr(constraint_driven_predecessors=[_make_cdp(100, 42)])
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert result.added_constraint_driven_uids == {42}
    assert result.removed_constraint_driven_uids == set()
    assert result.retained_constraint_driven_uids == set()


def test_removed_only() -> None:
    """A constraint-driven edge present only in Period A places the
    successor UID in ``removed_constraint_driven_uids`` — the
    canonical A−B case."""
    dpr_a = _make_dpr(constraint_driven_predecessors=[_make_cdp(100, 42)])
    dpr_b = _make_dpr()
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert result.added_constraint_driven_uids == set()
    assert result.removed_constraint_driven_uids == {42}
    assert result.retained_constraint_driven_uids == set()


def test_retained_both() -> None:
    """A successor UID that carries a constraint-driven edge in both
    periods lands in ``retained_constraint_driven_uids`` — the
    canonical A∩B case."""
    dpr_a = _make_dpr(constraint_driven_predecessors=[_make_cdp(100, 42)])
    dpr_b = _make_dpr(constraint_driven_predecessors=[_make_cdp(101, 42)])
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert result.added_constraint_driven_uids == set()
    assert result.removed_constraint_driven_uids == set()
    assert result.retained_constraint_driven_uids == {42}


def test_empty_period_a() -> None:
    """With no constraint-driven edges in Period A, every Period B
    successor UID flows through to ``added``."""
    dpr_a = _make_dpr()
    dpr_b = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, 42),
            _make_cdp(200, 43),
        ]
    )
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert result.added_constraint_driven_uids == {42, 43}
    assert result.removed_constraint_driven_uids == set()
    assert result.retained_constraint_driven_uids == set()


def test_empty_period_b() -> None:
    """With no constraint-driven edges in Period B, every Period A
    successor UID flows through to ``removed``."""
    dpr_a = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, 42),
            _make_cdp(200, 43),
        ]
    )
    dpr_b = _make_dpr()
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert result.added_constraint_driven_uids == set()
    assert result.removed_constraint_driven_uids == {42, 43}
    assert result.retained_constraint_driven_uids == set()


def test_focus_uid_not_excluded() -> None:
    """A focus UID carrying a constraint-driven edge DOES surface in
    the set-algebra output — explicit regression against the M10
    cross-version focus-exclusion behavior. Block 3 does not strip
    the focus UID; a forensic tool must surface a focus task held
    by a hard constraint."""
    focus_uid = 42
    # Period B introduces a constraint-driven edge onto the focus
    # itself; Period A has no such edge.
    dpr_a = _make_dpr(focus_uid=focus_uid)
    dpr_b = _make_dpr(
        focus_uid=focus_uid,
        constraint_driven_predecessors=[_make_cdp(100, focus_uid)],
    )
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert focus_uid in result.added_constraint_driven_uids
    assert focus_uid not in result.removed_constraint_driven_uids
    assert focus_uid not in result.retained_constraint_driven_uids


# ----------------------------------------------------------------------
# Status-date filter (4 tests)
# ----------------------------------------------------------------------


def test_filter_excludes_pre_status_date_predecessor() -> None:
    """A predecessor whose finish is ≤ ``period_b_status_date`` is a
    legitimate actual and MUST be filtered out of the Period A edge
    set per AM12 §f."""
    pred_uid = 100
    succ_uid = 42
    predecessor_task = _make_task(pred_uid, finish=_PRE_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid)]
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_A
    )
    schedule_b = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_B
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    # Edge filtered → successor dropped from the Period A cd_uids set
    # → neither removed nor retained surfaces succ_uid.
    assert succ_uid not in result.removed_constraint_driven_uids
    assert succ_uid not in result.retained_constraint_driven_uids
    assert succ_uid not in result.period_a_predecessors_by_successor


def test_filter_retains_post_status_date_predecessor() -> None:
    """A predecessor whose finish is strictly AFTER
    ``period_b_status_date`` is a future forecast and MUST be
    retained."""
    pred_uid = 100
    succ_uid = 42
    predecessor_task = _make_task(pred_uid, finish=_POST_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid)]
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_A
    )
    schedule_b = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_B
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    assert succ_uid in result.removed_constraint_driven_uids
    assert result.period_a_predecessors_by_successor[succ_uid][0].predecessor_uid == pred_uid


def test_filter_retains_when_period_b_status_date_is_none() -> None:
    """Without a Period B status_date the filter cannot fire — every
    constraint-driven edge is retained (the comparator cannot
    classify a change as retrospective statusing without a cutoff).

    A predecessor whose finish would otherwise qualify as a
    legitimate actual (finish ≤ any plausible cutoff) is retained
    here precisely because no cutoff is supplied.
    """
    pred_uid = 100
    succ_uid = 42
    predecessor_task = _make_task(pred_uid, finish=_PRE_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid)]
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_A
    )
    # Period B has no status_date — the filter is disabled.
    schedule_b = _make_schedule(
        [predecessor_task, successor_task], status_date=None
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    assert succ_uid in result.removed_constraint_driven_uids
    assert result.period_a_predecessors_by_successor[succ_uid][0].predecessor_uid == pred_uid


def test_filter_uses_is_legitimate_actual_helper() -> None:
    """The windowing predicate is reused — not reimplemented. The
    comparator module imports :func:`is_legitimate_actual` and must
    call it when evaluating a candidate edge. Patching the helper at
    the comparator-module namespace confirms delegation.
    """
    pred_uid = 100
    succ_uid = 42
    predecessor_task = _make_task(pred_uid, finish=_PRE_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid)]
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_A
    )
    schedule_b = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_B
    )

    with patch(
        "app.engine.constraint_driven_cross_version.is_legitimate_actual",
        return_value=False,
    ) as mock_helper:
        result = ConstraintDrivenCrossVersionComparator(
            schedule_a, schedule_b, dpr_a, dpr_b
        ).compare()

    assert mock_helper.called
    # Helper patched to False → edge retained despite pre-status finish.
    assert succ_uid in result.removed_constraint_driven_uids


# ----------------------------------------------------------------------
# Skipped-cycle override (3 tests)
# ----------------------------------------------------------------------


def test_skipped_cycle_overrides_exclusion_period_a() -> None:
    """A predecessor UID in Period A's
    ``skipped_cycle_participants`` is non-authoritative on its CPM
    dates — the legitimate-actual predicate would use stale data —
    so the edge is RETAINED regardless of the predicate's vote.
    """
    pred_uid = 100
    succ_uid = 42
    # Predecessor finish would otherwise qualify as legitimate actual.
    predecessor_task = _make_task(pred_uid, finish=_PRE_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid)],
        skipped_cycle_participants=[pred_uid],
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_A
    )
    schedule_b = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_B
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    # Cycle-skip override wins → edge retained → successor surfaces.
    assert succ_uid in result.removed_constraint_driven_uids


def test_skipped_cycle_overrides_exclusion_period_b() -> None:
    """A predecessor UID in Period B's
    ``skipped_cycle_participants`` triggers the same override when
    evaluating a Period B edge."""
    pred_uid = 100
    succ_uid = 42
    predecessor_task = _make_task(pred_uid, finish=_PRE_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr()
    dpr_b = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid)],
        skipped_cycle_participants=[pred_uid],
    )

    schedule_a = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_A
    )
    schedule_b = _make_schedule(
        [predecessor_task, successor_task], status_date=_STATUS_B
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    assert succ_uid in result.added_constraint_driven_uids


def test_skipped_cycle_on_either_period_suffices() -> None:
    """The cycle-skip override is a UNION across both periods — a
    predecessor in A's set but not B's still retains a B-side edge,
    and vice versa. Cycle-skip membership is a forensic visibility
    flag; it must not be dropped by either period's filter."""
    pred_uid = 100
    succ_uid_a = 42
    succ_uid_b = 43
    predecessor_task = _make_task(pred_uid, finish=_PRE_STATUS)
    successor_task_a = _make_task(succ_uid_a)
    successor_task_b = _make_task(succ_uid_b)

    # A has the cycle-skip entry; a B-side edge with the same pred_uid
    # must still be retained thanks to the union.
    dpr_a = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid_a)],
        skipped_cycle_participants=[pred_uid],
    )
    dpr_b = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid_b)],
        skipped_cycle_participants=[],
    )

    schedule_a = _make_schedule(
        [predecessor_task, successor_task_a, successor_task_b],
        status_date=_STATUS_A,
    )
    schedule_b = _make_schedule(
        [predecessor_task, successor_task_a, successor_task_b],
        status_date=_STATUS_B,
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    # A's edge retained (cycle-skip on A), B's edge retained (union).
    assert succ_uid_a in result.removed_constraint_driven_uids
    assert succ_uid_b in result.added_constraint_driven_uids

    # Symmetric case — cycle-skip on B, a Period A edge is retained.
    dpr_a2 = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid_a)],
        skipped_cycle_participants=[],
    )
    dpr_b2 = _make_dpr(
        constraint_driven_predecessors=[_make_cdp(pred_uid, succ_uid_b)],
        skipped_cycle_participants=[pred_uid],
    )
    result2 = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a2, dpr_b2
    ).compare()
    assert succ_uid_a in result2.removed_constraint_driven_uids
    assert succ_uid_b in result2.added_constraint_driven_uids


# ----------------------------------------------------------------------
# M10.1 integration (3 tests)
# ----------------------------------------------------------------------


def test_m10_1_input_order_preserved() -> None:
    """Predecessor tuple order within a successor's dict entry
    matches M10.1's ``(successor_uid, predecessor_uid)``-ascending
    emission order. The tracer sorts
    :attr:`DrivingPathResult.constraint_driven_predecessors` at
    construction; the comparator must preserve that order within each
    successor's tuple."""
    succ_uid = 42
    # Input ordered by predecessor_uid ascending (M10.1 emission).
    dpr_a = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, succ_uid),
            _make_cdp(200, succ_uid),
            _make_cdp(300, succ_uid),
        ]
    )
    dpr_b = _make_dpr()
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    preds = result.period_a_predecessors_by_successor[succ_uid]
    assert tuple(p.predecessor_uid for p in preds) == (100, 200, 300)


def test_partial_filter_preserves_successor() -> None:
    """When status-date filtering removes some but not all of a
    successor's constraint-driven predecessors, the successor
    REMAINS in the post-filter cd_uids set — the set is defined by
    the surviving edges, not the pre-filter population."""
    succ_uid = 42
    # Three edges on one successor. One predecessor finished before
    # the Period B status_date (excluded); the other two finish after
    # it (retained).
    pred_excluded = _make_task(100, finish=_PRE_STATUS)
    pred_retained_1 = _make_task(200, finish=_POST_STATUS)
    pred_retained_2 = _make_task(300, finish=_POST_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, succ_uid),
            _make_cdp(200, succ_uid),
            _make_cdp(300, succ_uid),
        ]
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [pred_excluded, pred_retained_1, pred_retained_2, successor_task],
        status_date=_STATUS_A,
    )
    schedule_b = _make_schedule(
        [pred_excluded, pred_retained_1, pred_retained_2, successor_task],
        status_date=_STATUS_B,
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    # Successor still present in the Period A cd_uids set.
    assert succ_uid in result.removed_constraint_driven_uids
    # Only the two retained predecessors survive, in M10.1 order.
    surviving = result.period_a_predecessors_by_successor[succ_uid]
    assert tuple(p.predecessor_uid for p in surviving) == (200, 300)


def test_full_filter_drops_successor() -> None:
    """When every constraint-driven edge on a successor is filtered
    out, the successor UID does NOT appear as a key in the
    per-successor dict and does NOT land in any of the three set-
    algebra sets."""
    succ_uid = 42
    pred_excluded_1 = _make_task(100, finish=_PRE_STATUS)
    pred_excluded_2 = _make_task(200, finish=_PRE_STATUS)
    successor_task = _make_task(succ_uid)

    dpr_a = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, succ_uid),
            _make_cdp(200, succ_uid),
        ]
    )
    dpr_b = _make_dpr()

    schedule_a = _make_schedule(
        [pred_excluded_1, pred_excluded_2, successor_task],
        status_date=_STATUS_A,
    )
    schedule_b = _make_schedule(
        [pred_excluded_1, pred_excluded_2, successor_task],
        status_date=_STATUS_B,
    )

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr_a, dpr_b
    ).compare()

    assert succ_uid not in result.period_a_predecessors_by_successor
    assert succ_uid not in result.added_constraint_driven_uids
    assert succ_uid not in result.removed_constraint_driven_uids
    assert succ_uid not in result.retained_constraint_driven_uids


# ----------------------------------------------------------------------
# M10.2 integration (2 tests)
# ----------------------------------------------------------------------


def test_dpr_skipped_cycle_participants_reachable_via_result() -> None:
    """:attr:`DrivingPathResult.skipped_cycle_participants` must be
    reachable via ``result.period_a_result`` and
    ``result.period_b_result`` — Block 4 reads them directly off the
    attached DPRs rather than a flattened copy on this result."""
    dpr_a = _make_dpr(skipped_cycle_participants=[111, 222])
    dpr_b = _make_dpr(skipped_cycle_participants=[333])
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert list(result.period_a_result.skipped_cycle_participants) == [111, 222]
    assert list(result.period_b_result.skipped_cycle_participants) == [333]


def test_no_flattened_skipped_cycle_field() -> None:
    """The Block 3 result deliberately does NOT introduce a top-
    level ``skipped_cycle_participants`` attribute. The M10.2 data
    stays on each DPR; flattening would force callers to guess which
    period a UID came from."""
    fields = ConstraintDrivenCrossVersionResult.model_fields
    assert "skipped_cycle_participants" not in fields

    sched = _make_schedule([])
    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, _make_dpr(), _make_dpr()
    ).compare()
    assert not hasattr(result, "skipped_cycle_participants")


# ----------------------------------------------------------------------
# Edge cases (4 tests)
# ----------------------------------------------------------------------


def test_identical_schedules_produce_all_retained() -> None:
    """Feeding the same schedule and same DPR as both A and B yields
    retained == cd_uids_a == cd_uids_b, with added and removed both
    empty. The no-change regression bar."""
    dpr = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, 42),
            _make_cdp(200, 43),
        ]
    )
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr, dpr
    ).compare()

    assert result.retained_constraint_driven_uids == {42, 43}
    assert result.added_constraint_driven_uids == set()
    assert result.removed_constraint_driven_uids == set()


def test_disjoint_schedules_produce_no_retained() -> None:
    """With completely non-overlapping successor UIDs in A and B,
    the retained set is empty; every A UID lands in removed and
    every B UID in added."""
    dpr_a = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(100, 42),
            _make_cdp(200, 43),
        ]
    )
    dpr_b = _make_dpr(
        constraint_driven_predecessors=[
            _make_cdp(300, 50),
            _make_cdp(400, 51),
        ]
    )
    sched = _make_schedule([])

    result = ConstraintDrivenCrossVersionComparator(
        sched, sched, dpr_a, dpr_b
    ).compare()

    assert result.retained_constraint_driven_uids == set()
    assert result.added_constraint_driven_uids == {50, 51}
    assert result.removed_constraint_driven_uids == {42, 43}


def test_pairwise_disjointness_validator_fires_on_corrupt_construction() -> None:
    """Manually constructing a
    :class:`ConstraintDrivenCrossVersionResult` with a UID appearing
    in both ``added`` and ``retained`` violates the set-algebra
    pairwise disjointness invariant — the contract validator must
    raise. This is a regression bar on the frozen contract,
    triggered through the same construction path the comparator
    uses but with corrupt inputs."""
    dpr = _make_dpr()
    with pytest.raises(ValidationError) as exc_info:
        ConstraintDrivenCrossVersionResult(
            period_a_result=dpr,
            period_b_result=dpr,
            added_constraint_driven_uids={7, 8},
            retained_constraint_driven_uids={8, 9},
        )
    assert "8" in str(exc_info.value)


def test_facade_computes_dprs_when_none_supplied() -> None:
    """The facade's lazy path: when ``dpr_a`` or ``dpr_b`` is
    ``None``, the facade calls
    :func:`app.engine.driving_path.trace_driving_path` directly once
    per period. Patched here to return a stub DPR on each call; the
    test asserts the helper was called exactly twice and a valid
    result was produced."""
    stub_dpr = _make_dpr()
    sched = _make_schedule([])

    with patch(
        "app.engine.constraint_driven_cross_version.trace_driving_path",
        return_value=stub_dpr,
    ) as mock_trace:
        result = compare_constraint_driven_cross_version(sched, sched)

    assert mock_trace.call_count == 2
    assert isinstance(result, ConstraintDrivenCrossVersionResult)
    assert result.period_a_result is stub_dpr
    assert result.period_b_result is stub_dpr


# ----------------------------------------------------------------------
# AM13 field presence (1 test)
# ----------------------------------------------------------------------


def test_am13_five_new_fields_present_with_correct_types() -> None:
    """The AM13 comparator result carries the five new absolute-
    date / working-days-elapsed fields, populated from the attached
    schedules when present. Type expectations:

    * ``period_a_status_date``: ``datetime | None`` — copied from
      ``schedule_a.status_date``.
    * ``period_b_status_date``: ``datetime | None`` — copied from
      ``schedule_b.status_date``.
    * ``period_a_project_start``: ``datetime | None`` — copied from
      ``schedule_a.project_start``.
    * ``period_b_project_start``: ``datetime | None`` — copied from
      ``schedule_b.project_start``.
    * ``period_working_days_elapsed``: ``float | None`` — computed
      on Schedule B's calendar when both status dates are present
      and a calendar is resolvable.
    """
    project_start_a = datetime(2025, 12, 1, 8, 0, tzinfo=UTC)
    project_start_b = datetime(2025, 12, 2, 8, 0, tzinfo=UTC)
    schedule_a = _make_schedule(
        [], status_date=_STATUS_A, project_start=project_start_a
    )
    schedule_b = _make_schedule(
        [], status_date=_STATUS_B, project_start=project_start_b
    )
    dpr = _make_dpr()

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr, dpr
    ).compare()

    assert result.period_a_status_date == _STATUS_A
    assert result.period_b_status_date == _STATUS_B
    assert result.period_a_project_start == project_start_a
    assert result.period_b_project_start == project_start_b
    assert isinstance(result.period_a_status_date, datetime)
    assert isinstance(result.period_b_status_date, datetime)
    assert isinstance(result.period_a_project_start, datetime)
    assert isinstance(result.period_b_project_start, datetime)

    # Jan 15 08:00 UTC → Feb 15 08:00 UTC on a Mon–Fri 8h/day calendar
    # is 23 working days (no holidays, no weekends on the endpoints
    # themselves fall inside working windows at 08:00 Thursday and
    # 08:00 Sunday respectively — snap-forward yields the Monday).
    # We don't pin the exact value here to avoid coupling to the
    # calendar-math implementation; asserting "float, non-None,
    # positive" is enough for field-presence coverage. Exact arithmetic
    # is exercised by tests/test_engine_calendar_math.py.
    assert isinstance(result.period_working_days_elapsed, float)
    assert result.period_working_days_elapsed > 0.0


# ----------------------------------------------------------------------
# AM13 validator-raise / edge cases (2 tests)
# ----------------------------------------------------------------------


def test_am13_working_days_none_when_period_b_status_date_none() -> None:
    """``period_working_days_elapsed`` is ``None`` whenever a
    status date is missing on either side — the working-days-elapsed
    calculation has no anchor without both endpoints."""
    schedule_a = _make_schedule([], status_date=_STATUS_A)
    schedule_b = _make_schedule([], status_date=None)
    dpr = _make_dpr()

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr, dpr
    ).compare()

    assert result.period_b_status_date is None
    assert result.period_working_days_elapsed is None


def test_am13_working_days_none_when_period_b_calendar_missing() -> None:
    """``period_working_days_elapsed`` is ``None`` whenever Schedule
    B has no resolvable calendar — the working-days calculation
    depends on Period B's calendar (AM13 rationale: current-period
    reasoning, Period A calendar may be stale)."""
    schedule_a = _make_schedule([], status_date=_STATUS_A)
    # Empty calendars list → no resolvable calendar on Schedule B.
    schedule_b = _make_schedule([], status_date=_STATUS_B, calendars=[])
    dpr = _make_dpr()

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr, dpr
    ).compare()

    assert result.period_b_status_date == _STATUS_B
    assert result.period_working_days_elapsed is None


def test_am13_working_days_elapsed_pinned_value() -> None:
    """Pin the exact ``period_working_days_elapsed`` value emitted by
    the production ``working_minutes_between`` + ``minutes_to_days``
    chain on the Standard Mon–Fri 8h/day calendar between
    2026-01-15 08:00 UTC and 2026-02-15 08:00 UTC.

    Guards against silent Period-A-calendar substitution regressions
    and against any future drift in the calendar-math chain that
    would change the working-days-elapsed arithmetic without being
    caught by the looser
    :func:`test_am13_five_new_fields_present_with_correct_types`
    field-presence assertion.
    """
    schedule_a = _make_schedule([], status_date=_STATUS_A)
    schedule_b = _make_schedule([], status_date=_STATUS_B)
    dpr = _make_dpr()

    result = ConstraintDrivenCrossVersionComparator(
        schedule_a, schedule_b, dpr, dpr
    ).compare()

    assert result.period_working_days_elapsed == 22.0
