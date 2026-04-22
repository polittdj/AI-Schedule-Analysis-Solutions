"""Task-field comparator tests (Block 3).

Covers AC #1 (matched / added / deleted counts), AC #2 (legitimate-
actual tagging), AC #3 (per-field delta emission for the eight M9
fields), AC #4 (UniqueID-only matching regression — rename-all-in-B),
duplicate-UID guard, empty schedules, no-status-date handling, and
mutation-invariance.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.comparator import (
    ComparatorError,
    ComparatorOptions,
    compare_schedules,
)
from app.engine.delta import (
    ComparatorResult,
    DeltaType,
    RelationshipPresence,
    TaskPresence,
)
from app.models.enums import ConstraintType, RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


# -----------------------------------------------------------------------
# Builders
# -----------------------------------------------------------------------


def _task(
    uid: int,
    *,
    name: str | None = None,
    duration_minutes: int = 480,
    total_slack_minutes: int = 0,
    free_slack_minutes: int = 0,
    finish: datetime | None = None,
    baseline_finish: datetime | None = None,
    actual_start: datetime | None = None,
    actual_finish: datetime | None = None,
    constraint_type: ConstraintType = ConstraintType.AS_SOON_AS_POSSIBLE,
    constraint_date: datetime | None = None,
) -> Task:
    return Task(
        unique_id=uid,
        task_id=uid,
        name=name if name is not None else f"T{uid}",
        duration_minutes=duration_minutes,
        total_slack_minutes=total_slack_minutes,
        free_slack_minutes=free_slack_minutes,
        finish=finish,
        baseline_finish=baseline_finish,
        actual_start=actual_start,
        actual_finish=actual_finish,
        constraint_type=constraint_type,
        constraint_date=constraint_date,
    )


def _sched(
    *tasks: Task,
    status_date: datetime | None = None,
    name: str = "sched",
    relations: tuple[Relation, ...] = (),
) -> Schedule:
    return Schedule(
        project_calendar_hours_per_day=8.0,
        name=name,
        project_start=ANCHOR,
        status_date=status_date,
        tasks=list(tasks),
        relations=list(relations),
    )


# -----------------------------------------------------------------------
# AC #1: 50 / 40 / 5 / 5 counts
# -----------------------------------------------------------------------


def test_ac1_matched_added_deleted_counts() -> None:
    a_uids = set(range(1, 51))  # 1..50
    b_uids = (set(range(6, 51)) | {100, 101, 102, 103, 104})  # drop 1..5; add 100..104
    # intersection = 45 ... no, let's match the AC exactly: 40 matched,
    # 5 added, 5 deleted. We want |A| = 50, |B| = 50, |A ∩ B| = 40,
    # |B - A| = 10, |A - B| = 10? No — 40 + 10 + 10 = 60 ≠ 50 each.
    # Correct: |A| = 50, |B| = 50; matched = 40, added_in_B = 10,
    # deleted_from_A = 10 gives |A| = 40+10 = 50 and |B| = 40+10 = 50.
    # The AC says 5 added / 5 deleted — that would require |A| = 45
    # and |B| = 45. Re-reading AC: "50 tasks each, 40 matched, 5
    # added, 5 deleted". That arithmetic balances only if |A| = 45
    # and |B| = 45 (40 + 5 deleted = 45 on A; 40 + 5 added = 45 on B).
    # The AC text is loose about the 50-each claim; the comparator
    # must produce 40 matched + 5 added + 5 deleted = 50 records.
    # That is the testable count.
    a_uids = set(range(1, 46))  # 1..45
    b_uids = (set(range(6, 46)) | {100, 101, 102, 103, 104})  # drop 1..5; add 100..104
    a = _sched(*[_task(u) for u in sorted(a_uids)])
    b = _sched(*[_task(u) for u in sorted(b_uids)])
    result = compare_schedules(a, b)
    assert result.matched_task_count == 40
    assert len(result.added_task_uids) == 5
    assert len(result.deleted_task_uids) == 5
    assert len(result.task_deltas) == 50
    presences = [d.presence for d in result.task_deltas]
    assert presences.count(TaskPresence.MATCHED) == 40
    assert presences.count(TaskPresence.ADDED_IN_B) == 5
    assert presences.count(TaskPresence.DELETED_FROM_A) == 5


# -----------------------------------------------------------------------
# AC #2: legitimate-actual tagging
# -----------------------------------------------------------------------


def test_ac2_legitimate_actual_skill_example() -> None:
    status_a = datetime(2026, 3, 1, 16, 0, tzinfo=UTC)
    status_b = datetime(2026, 3, 31, 16, 0, tzinfo=UTC)
    a_finish = datetime(2026, 3, 15, 17, 0, tzinfo=UTC)

    t_a = _task(42, finish=a_finish, total_slack_minutes=480)
    t_b = _task(42, finish=a_finish, total_slack_minutes=0)  # change in TS
    a = _sched(t_a, status_date=status_a)
    b = _sched(t_b, status_date=status_b)

    result = compare_schedules(a, b)
    assert result.matched_task_count == 1
    matched = result.task_deltas[0]
    assert matched.is_legitimate_actual is True
    # A field delta on total_slack_minutes is still emitted; the tag
    # is additive, not a filter.
    slack_fd = next(
        fd for fd in matched.field_deltas if fd.field_name == "total_slack_minutes"
    )
    assert slack_fd.delta_type is DeltaType.VALUE_CHANGE
    assert slack_fd.period_a_value == 480
    assert slack_fd.period_b_value == 0


def test_change_outside_window_is_not_legitimate() -> None:
    status_a = datetime(2026, 3, 1, 16, 0, tzinfo=UTC)
    status_b = datetime(2026, 3, 31, 16, 0, tzinfo=UTC)
    a_finish = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)  # after B cutoff

    t_a = _task(7, finish=a_finish)
    t_b = _task(7, finish=a_finish, total_slack_minutes=240)
    a = _sched(t_a, status_date=status_a)
    b = _sched(t_b, status_date=status_b)

    result = compare_schedules(a, b)
    matched = result.task_deltas[0]
    assert matched.is_legitimate_actual is False


# -----------------------------------------------------------------------
# AC #4: UniqueID-only matching regression (rename every task in B)
# -----------------------------------------------------------------------


def test_ac4_rename_all_tasks_in_b_preserves_match() -> None:
    a = _sched(*[_task(u, name=f"A{u}") for u in range(1, 11)])
    b = _sched(*[_task(u, name=f"TOTALLY_DIFFERENT_{u}") for u in range(1, 11)])
    result = compare_schedules(a, b)
    assert result.matched_task_count == 10
    assert len(result.added_task_uids) == 0
    assert len(result.deleted_task_uids) == 0
    for delta in result.task_deltas:
        assert delta.presence is TaskPresence.MATCHED
        assert delta.period_a_name.startswith("A")
        assert delta.period_b_name.startswith("TOTALLY_DIFFERENT_")


# -----------------------------------------------------------------------
# AC #3: per-field delta emission
# -----------------------------------------------------------------------


def test_total_slack_minutes_delta() -> None:
    a = _sched(_task(1, total_slack_minutes=480))
    b = _sched(_task(1, total_slack_minutes=-120))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "total_slack_minutes"
    )
    assert fd.delta_type is DeltaType.VALUE_CHANGE
    assert fd.period_a_value == 480
    assert fd.period_b_value == -120


def test_free_slack_minutes_delta() -> None:
    a = _sched(_task(1, free_slack_minutes=0))
    b = _sched(_task(1, free_slack_minutes=960))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "free_slack_minutes"
    )
    assert fd.period_a_value == 0
    assert fd.period_b_value == 960


def test_baseline_finish_delta_value_change() -> None:
    ba_a = datetime(2026, 6, 1, 16, tzinfo=UTC)
    ba_b = datetime(2026, 6, 15, 16, tzinfo=UTC)
    a = _sched(_task(1, baseline_finish=ba_a))
    b = _sched(_task(1, baseline_finish=ba_b))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "baseline_finish"
    )
    assert fd.delta_type is DeltaType.VALUE_CHANGE


def test_finish_delta() -> None:
    f_a = datetime(2026, 6, 1, 16, tzinfo=UTC)
    f_b = datetime(2026, 6, 30, 16, tzinfo=UTC)
    a = _sched(_task(1, finish=f_a))
    b = _sched(_task(1, finish=f_b))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "finish"
    )
    assert fd.period_a_value == f_a
    assert fd.period_b_value == f_b


def test_constraint_type_delta() -> None:
    mso_date = datetime(2026, 5, 1, 16, tzinfo=UTC)
    a = _sched(_task(1, constraint_type=ConstraintType.AS_SOON_AS_POSSIBLE))
    b = _sched(
        _task(1, constraint_type=ConstraintType.MUST_START_ON,
              constraint_date=mso_date)
    )
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "constraint_type"
    )
    assert fd.delta_type is DeltaType.VALUE_CHANGE
    assert fd.period_a_value is ConstraintType.AS_SOON_AS_POSSIBLE
    assert fd.period_b_value is ConstraintType.MUST_START_ON


def test_duration_minutes_delta() -> None:
    a = _sched(_task(1, duration_minutes=1920))
    b = _sched(_task(1, duration_minutes=480))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "duration_minutes"
    )
    assert fd.period_a_value == 1920
    assert fd.period_b_value == 480


def test_actual_start_addition() -> None:
    a = _sched(_task(1, actual_start=None))
    b = _sched(_task(1, actual_start=datetime(2026, 4, 22, 8, tzinfo=UTC)))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "actual_start"
    )
    assert fd.delta_type is DeltaType.ADDED
    assert fd.period_a_value is None
    assert fd.period_b_value is not None


def test_actual_finish_addition() -> None:
    a = _sched(_task(1, actual_finish=None))
    b = _sched(_task(1, actual_finish=datetime(2026, 4, 28, 16, tzinfo=UTC)))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "actual_finish"
    )
    assert fd.delta_type is DeltaType.ADDED


def test_actual_finish_removal_is_removed() -> None:
    af = datetime(2026, 4, 28, 16, tzinfo=UTC)
    a = _sched(_task(1, actual_finish=af))
    b = _sched(_task(1, actual_finish=None))
    result = compare_schedules(a, b)
    fd = next(
        f for f in result.task_deltas[0].field_deltas
        if f.field_name == "actual_finish"
    )
    assert fd.delta_type is DeltaType.REMOVED
    assert fd.period_a_value == af
    assert fd.period_b_value is None


def test_unchanged_matched_task_emits_empty_field_deltas_by_default() -> None:
    a = _sched(_task(1, finish=datetime(2026, 5, 1, tzinfo=UTC)))
    b = _sched(_task(1, finish=datetime(2026, 5, 1, tzinfo=UTC)))
    result = compare_schedules(a, b)
    assert result.matched_task_count == 1
    assert len(result.task_deltas) == 1
    assert result.task_deltas[0].field_deltas == ()


def test_include_unchanged_matched_tasks_false_drops_quiet_matches() -> None:
    a = _sched(_task(1), _task(2, total_slack_minutes=0))
    b = _sched(_task(1), _task(2, total_slack_minutes=240))
    result = compare_schedules(
        a, b, options=ComparatorOptions(include_unchanged_matched_tasks=False)
    )
    # Quiet match (UID 1) dropped; UID 2 emitted.
    assert len(result.task_deltas) == 1
    assert result.task_deltas[0].unique_id == 2
    # matched_task_count still records the structural match count.
    assert result.matched_task_count == 2


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


def test_empty_schedules_both_sides() -> None:
    result = compare_schedules(_sched(), _sched())
    assert result.matched_task_count == 0
    assert result.task_deltas == ()
    assert result.relationship_deltas == ()
    assert result.added_task_uids == frozenset()
    assert result.deleted_task_uids == frozenset()


def test_single_task_schedule_pair() -> None:
    a = _sched(_task(7))
    b = _sched(_task(7))
    result = compare_schedules(a, b)
    assert result.matched_task_count == 1
    assert result.task_deltas[0].unique_id == 7
    assert result.task_deltas[0].field_deltas == ()


def test_schedule_with_no_status_date_matched_is_not_legitimate() -> None:
    # Block 2 documents this: missing status_date ⇒ is_legitimate_actual
    # is False regardless of finish-vs-status ordering.
    a = _sched(_task(1, finish=datetime(2026, 1, 1, tzinfo=UTC)))
    b = _sched(_task(1, finish=datetime(2026, 1, 1, tzinfo=UTC)))
    # Neither schedule sets status_date.
    result = compare_schedules(a, b)
    assert result.task_deltas[0].is_legitimate_actual is False


def test_duplicate_unique_id_raises_comparator_error() -> None:
    # Bypass the Schedule G10 validator (which rejects duplicate UIDs
    # at construction) by appending to Schedule.tasks post-construction
    # to exercise the comparator's runtime duplicate-UID defense path.
    a = _sched(_task(1), _task(2))
    a.tasks.append(_task(1, name="dup"))  # type: ignore[call-arg]
    b = _sched(_task(1))
    with pytest.raises(ComparatorError) as excinfo:
        compare_schedules(a, b)
    assert "duplicate Task.unique_id 1" in str(excinfo.value)
    assert "period_a" in str(excinfo.value)


# -----------------------------------------------------------------------
# Mutation-invariance
# -----------------------------------------------------------------------


def test_mutation_invariance_both_sides() -> None:
    f_a = datetime(2026, 5, 1, 16, tzinfo=UTC)
    f_b = datetime(2026, 6, 1, 16, tzinfo=UTC)
    a = _sched(
        _task(1, finish=f_a, total_slack_minutes=480),
        _task(2, finish=f_a, total_slack_minutes=0),
        status_date=datetime(2026, 3, 1, tzinfo=UTC),
    )
    b = _sched(
        _task(1, finish=f_b, total_slack_minutes=120),
        _task(2, finish=f_a, total_slack_minutes=0),
        _task(99, finish=f_b),  # added in B
        status_date=datetime(2026, 3, 31, tzinfo=UTC),
    )

    a_snapshot = a.model_dump()
    b_snapshot = b.model_dump()

    result = compare_schedules(a, b)
    assert isinstance(result, ComparatorResult)

    assert a.model_dump() == a_snapshot
    assert b.model_dump() == b_snapshot


# -----------------------------------------------------------------------
# Frozen output
# -----------------------------------------------------------------------


def test_comparator_result_is_frozen() -> None:
    result = compare_schedules(_sched(_task(1)), _sched(_task(1)))
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        result.matched_task_count = 99  # type: ignore[misc]


# -----------------------------------------------------------------------
# Block 4: relationship-change comparator
# -----------------------------------------------------------------------


def _rel(pred: int, succ: int, *, rt: RelationType = RelationType.FS,
         lag_minutes: int = 0) -> Relation:
    return Relation(
        predecessor_unique_id=pred,
        successor_unique_id=succ,
        relation_type=rt,
        lag_minutes=lag_minutes,
    )


def test_relationship_added_in_b() -> None:
    tasks = (_task(1), _task(2))
    a = _sched(*tasks, relations=())
    b = _sched(*tasks, relations=(_rel(1, 2),))
    result = compare_schedules(a, b)
    assert len(result.relationship_deltas) == 1
    rd = result.relationship_deltas[0]
    assert rd.presence is RelationshipPresence.ADDED_IN_B
    assert rd.predecessor_unique_id == 1
    assert rd.successor_unique_id == 2
    assert rd.field_deltas == ()


def test_relationship_deleted_from_a() -> None:
    tasks = (_task(1), _task(2))
    a = _sched(*tasks, relations=(_rel(1, 2),))
    b = _sched(*tasks, relations=())
    result = compare_schedules(a, b)
    assert len(result.relationship_deltas) == 1
    rd = result.relationship_deltas[0]
    assert rd.presence is RelationshipPresence.DELETED_FROM_A
    assert rd.field_deltas == ()


def test_relationship_type_change_emits_value_change() -> None:
    tasks = (_task(1), _task(2))
    a = _sched(*tasks, relations=(_rel(1, 2, rt=RelationType.FS),))
    b = _sched(*tasks, relations=(_rel(1, 2, rt=RelationType.SS),))
    result = compare_schedules(a, b)
    assert len(result.relationship_deltas) == 1
    rd = result.relationship_deltas[0]
    assert rd.presence is RelationshipPresence.MATCHED
    assert len(rd.field_deltas) == 1
    fd = rd.field_deltas[0]
    assert fd.field_name == "relation_type"
    assert fd.delta_type is DeltaType.VALUE_CHANGE
    assert fd.period_a_value is RelationType.FS
    assert fd.period_b_value is RelationType.SS


def test_relationship_lag_change_emits_value_change() -> None:
    tasks = (_task(1), _task(2))
    a = _sched(*tasks, relations=(_rel(1, 2, lag_minutes=0),))
    b = _sched(*tasks, relations=(_rel(1, 2, lag_minutes=3600),))
    result = compare_schedules(a, b)
    rd = result.relationship_deltas[0]
    assert rd.presence is RelationshipPresence.MATCHED
    lag_fd = next(fd for fd in rd.field_deltas if fd.field_name == "lag_minutes")
    assert lag_fd.delta_type is DeltaType.VALUE_CHANGE
    assert lag_fd.period_a_value == 0
    assert lag_fd.period_b_value == 3600


def test_relationship_no_changes_empty_deltas() -> None:
    tasks = (_task(1), _task(2))
    a = _sched(*tasks, relations=(_rel(1, 2, lag_minutes=120),))
    b = _sched(*tasks, relations=(_rel(1, 2, lag_minutes=120),))
    result = compare_schedules(a, b)
    # Matched relationship with no field-level changes still emits
    # a RelationshipDelta (MATCHED, empty field_deltas) so consumers
    # can count how many relations were seen on both sides.
    assert len(result.relationship_deltas) == 1
    assert result.relationship_deltas[0].presence is RelationshipPresence.MATCHED
    assert result.relationship_deltas[0].field_deltas == ()


def test_relationship_duplicate_pair_raises() -> None:
    tasks = (_task(1), _task(2))
    a = _sched(*tasks, relations=(_rel(1, 2, rt=RelationType.FS),))
    b = _sched(*tasks, relations=(_rel(1, 2, rt=RelationType.FS),))
    # Schedule model permits multiple links for the same pair via
    # list append; force a duplicate and verify the comparator
    # raises.
    b.relations.append(_rel(1, 2, rt=RelationType.SS))  # type: ignore[call-arg]
    with pytest.raises(ComparatorError) as excinfo:
        compare_schedules(a, b)
    assert "duplicate relationship pair" in str(excinfo.value)
    assert "period_b" in str(excinfo.value)


def test_relationship_mutation_invariance() -> None:
    tasks = (_task(1), _task(2), _task(3))
    a = _sched(*tasks, relations=(_rel(1, 2), _rel(2, 3, lag_minutes=0)))
    b = _sched(*tasks, relations=(_rel(1, 2, rt=RelationType.SS),
                                   _rel(2, 3, lag_minutes=480)))
    a_snapshot = a.model_dump()
    b_snapshot = b.model_dump()
    compare_schedules(a, b)
    assert a.model_dump() == a_snapshot
    assert b.model_dump() == b_snapshot
