"""Tests for the frozen comparator delta contract (Block 1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.engine.delta import (
    ComparatorResult,
    DeltaType,
    FieldDelta,
    RelationshipDelta,
    RelationshipPresence,
    TaskDelta,
    TaskPresence,
)

# -----------------------------------------------------------------------
# Enum value and exhaustiveness tests
# -----------------------------------------------------------------------


def test_delta_type_values() -> None:
    assert {d.value for d in DeltaType} == {"VALUE_CHANGE", "ADDED", "REMOVED"}


def test_task_presence_values() -> None:
    assert {p.value for p in TaskPresence} == {
        "MATCHED",
        "ADDED_IN_B",
        "DELETED_FROM_A",
    }


def test_relationship_presence_values() -> None:
    assert {p.value for p in RelationshipPresence} == {
        "MATCHED",
        "ADDED_IN_B",
        "DELETED_FROM_A",
    }


# -----------------------------------------------------------------------
# FieldDelta
# -----------------------------------------------------------------------


def test_field_delta_value_change_roundtrip() -> None:
    fd = FieldDelta(
        field_name="total_slack_minutes",
        period_a_value=480,
        period_b_value=0,
        delta_type=DeltaType.VALUE_CHANGE,
    )
    assert fd.field_name == "total_slack_minutes"
    assert fd.period_a_value == 480
    assert fd.period_b_value == 0
    assert fd.delta_type is DeltaType.VALUE_CHANGE


def test_field_delta_added_has_none_a() -> None:
    fd = FieldDelta(
        field_name="actual_finish",
        period_a_value=None,
        period_b_value=datetime(2026, 3, 14, 16, 0, tzinfo=UTC),
        delta_type=DeltaType.ADDED,
    )
    assert fd.period_a_value is None
    assert fd.delta_type is DeltaType.ADDED


def test_field_delta_removed_has_none_b() -> None:
    fd = FieldDelta(
        field_name="constraint_date",
        period_a_value=datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
        period_b_value=None,
        delta_type=DeltaType.REMOVED,
    )
    assert fd.period_b_value is None
    assert fd.delta_type is DeltaType.REMOVED


def test_field_delta_is_frozen() -> None:
    fd = FieldDelta(
        field_name="finish",
        period_a_value=None,
        period_b_value=None,
        delta_type=DeltaType.VALUE_CHANGE,
    )
    with pytest.raises(ValidationError):
        fd.field_name = "something_else"  # type: ignore[misc]


def test_field_delta_rejects_missing_required() -> None:
    with pytest.raises(ValidationError):
        FieldDelta(  # type: ignore[call-arg]
            field_name="finish",
            period_a_value=None,
            period_b_value=None,
        )


# -----------------------------------------------------------------------
# TaskDelta
# -----------------------------------------------------------------------


def _fd_sample() -> FieldDelta:
    return FieldDelta(
        field_name="total_slack_minutes",
        period_a_value=480,
        period_b_value=0,
        delta_type=DeltaType.VALUE_CHANGE,
    )


def test_task_delta_matched_accepts_tuple_of_field_deltas() -> None:
    td = TaskDelta(
        unique_id=42,
        presence=TaskPresence.MATCHED,
        period_a_name="Foundation",
        period_b_name="Foundation",
        field_deltas=(_fd_sample(),),
        is_legitimate_actual=False,
    )
    assert td.unique_id == 42
    assert td.presence is TaskPresence.MATCHED
    assert len(td.field_deltas) == 1
    assert isinstance(td.field_deltas, tuple)


def test_task_delta_rejects_non_int_unique_id() -> None:
    with pytest.raises(ValidationError):
        TaskDelta(
            unique_id="abc",  # type: ignore[arg-type]
            presence=TaskPresence.MATCHED,
            period_a_name="x",
            period_b_name="x",
            field_deltas=(),
            is_legitimate_actual=False,
        )


def test_task_delta_is_frozen() -> None:
    td = TaskDelta(
        unique_id=1,
        presence=TaskPresence.MATCHED,
        period_a_name="A",
        period_b_name="A",
        field_deltas=(),
        is_legitimate_actual=False,
    )
    with pytest.raises(ValidationError):
        td.unique_id = 2  # type: ignore[misc]


def test_task_delta_field_deltas_coerces_to_tuple() -> None:
    td = TaskDelta(
        unique_id=1,
        presence=TaskPresence.MATCHED,
        period_a_name="A",
        period_b_name="A",
        field_deltas=[_fd_sample()],  # type: ignore[arg-type]
        is_legitimate_actual=False,
    )
    assert isinstance(td.field_deltas, tuple)


def test_task_delta_added_in_b_has_none_a_name() -> None:
    td = TaskDelta(
        unique_id=7,
        presence=TaskPresence.ADDED_IN_B,
        period_a_name=None,
        period_b_name="New task",
        field_deltas=(),
        is_legitimate_actual=False,
    )
    assert td.period_a_name is None
    assert td.period_b_name == "New task"


# -----------------------------------------------------------------------
# RelationshipDelta
# -----------------------------------------------------------------------


def test_relationship_delta_accepts_matched() -> None:
    rd = RelationshipDelta(
        predecessor_unique_id=1,
        successor_unique_id=2,
        presence=RelationshipPresence.MATCHED,
        field_deltas=(
            FieldDelta(
                field_name="lag_minutes",
                period_a_value=0,
                period_b_value=240,
                delta_type=DeltaType.VALUE_CHANGE,
            ),
        ),
    )
    assert rd.predecessor_unique_id == 1
    assert rd.successor_unique_id == 2
    assert rd.presence is RelationshipPresence.MATCHED
    assert len(rd.field_deltas) == 1


def test_relationship_delta_is_frozen() -> None:
    rd = RelationshipDelta(
        predecessor_unique_id=1,
        successor_unique_id=2,
        presence=RelationshipPresence.MATCHED,
        field_deltas=(),
    )
    with pytest.raises(ValidationError):
        rd.predecessor_unique_id = 99  # type: ignore[misc]


# -----------------------------------------------------------------------
# ComparatorResult
# -----------------------------------------------------------------------


def test_comparator_result_accepts_full_shape() -> None:
    td = TaskDelta(
        unique_id=1,
        presence=TaskPresence.MATCHED,
        period_a_name="A",
        period_b_name="A",
        field_deltas=(),
        is_legitimate_actual=False,
    )
    result = ComparatorResult(
        period_a_status_date=datetime(2026, 3, 1, tzinfo=UTC),
        period_b_status_date=datetime(2026, 3, 31, tzinfo=UTC),
        task_deltas=(td,),
        relationship_deltas=(),
        added_task_uids=frozenset({4, 5}),
        deleted_task_uids=frozenset({9}),
        matched_task_count=1,
    )
    assert result.matched_task_count == 1
    assert 4 in result.added_task_uids
    assert 9 in result.deleted_task_uids


def test_comparator_result_is_frozen() -> None:
    result = ComparatorResult(
        period_a_status_date=None,
        period_b_status_date=None,
        task_deltas=(),
        relationship_deltas=(),
        added_task_uids=frozenset(),
        deleted_task_uids=frozenset(),
        matched_task_count=0,
    )
    with pytest.raises(ValidationError):
        result.matched_task_count = 99  # type: ignore[misc]


def test_comparator_result_coerces_set_to_frozenset() -> None:
    result = ComparatorResult(
        period_a_status_date=None,
        period_b_status_date=None,
        task_deltas=(),
        relationship_deltas=(),
        added_task_uids={1, 2, 3},  # type: ignore[arg-type]
        deleted_task_uids=frozenset(),
        matched_task_count=0,
    )
    assert isinstance(result.added_task_uids, frozenset)


def test_comparator_result_allows_naive_status_dates_rejected_at_schedule_layer() -> None:
    # ComparatorResult itself does not enforce tz-aware; the Schedule
    # model validator guarantees tz-awareness upstream. This test
    # documents that the comparator output mirrors whatever the
    # Schedule provides rather than silently rewrapping.
    dt_aware = datetime(2026, 3, 1, tzinfo=UTC)
    result = ComparatorResult(
        period_a_status_date=dt_aware,
        period_b_status_date=None,
        task_deltas=(),
        relationship_deltas=(),
        added_task_uids=frozenset(),
        deleted_task_uids=frozenset(),
        matched_task_count=0,
    )
    assert result.period_a_status_date == dt_aware
    assert result.period_b_status_date is None
