"""Cross-version schedule comparator — Milestone 9.

Matches two :class:`~app.models.schedule.Schedule` instances by
UniqueID and emits a :class:`~app.engine.delta.ComparatorResult`
carrying per-task and per-relationship deltas. Relationship deltas
land in Block 4.

Authority and invariants:

* UniqueID-only matching per BUILD-PLAN §2.7 and
  ``mpp-parsing-com-automation §5`` — ``Task.task_id`` and
  ``Task.name`` are never consulted. AC #4 regression renames every
  task in Period B and asserts matched-delta count is unchanged.
* Mutation-invariance per BUILD-PLAN §2.13 — the comparator does not
  mutate ``period_a`` or ``period_b``. Both inputs round-trip
  ``model_dump()`` byte-identical.
* Legitimate-actual tagging delegated to
  :func:`app.engine.windowing.is_legitimate_actual` — the
  skill-anchored Period A finish ≤ Period B status_date predicate
  per ``forensic-manipulation-patterns §3.2`` and
  ``driving-slack-and-paths §10``.
* Frozen output — :class:`~app.engine.delta.ComparatorResult` and
  its nested models are all Pydantic v2 ``ConfigDict(frozen=True)``.

The comparator does not raise on duplicate UniqueIDs within a single
``Schedule`` under normal conditions: the M2 model validator G10
rejects duplicates at ``Schedule`` construction time. Defense-in-
depth check surfaces any bypassed path as
:class:`ComparatorError`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.engine.delta import (
    ComparatorResult,
    DeltaType,
    FieldDelta,
    RelationshipDelta,
    RelationshipPresence,
    TaskDelta,
    TaskPresence,
)
from app.engine.exceptions import EngineError
from app.engine.windowing import is_legitimate_actual
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task


class ComparatorError(EngineError):
    """Raised on forensic-integrity violations during comparison.

    The comparator expects two pre-validated ``Schedule`` instances:
    the M2 model validators enforce G10 (unique UniqueIDs within a
    schedule). ``ComparatorError`` fires if the comparator detects a
    duplicate UniqueID during indexing — a sign that the caller
    bypassed model validation (direct dict construction or
    post-construction mutation).
    """


class ComparatorOptions(BaseModel):
    """Comparator configuration knobs.

    The default configuration produces the canonical M9 output shape
    described in BUILD-PLAN §5 M9. Knobs are added here only when a
    test or downstream consumer reveals a genuine need — the current
    shape is intentionally minimal.
    """

    model_config = ConfigDict(frozen=True)

    include_unchanged_matched_tasks: bool = True
    """When ``True`` (default), matched tasks with no field-level
    changes still emit a ``TaskDelta`` (with empty ``field_deltas``)
    so the ``matched_task_count`` invariant from AC #1 holds
    (``len(task_deltas) == matched + added + deleted``). Setting to
    ``False`` drops structurally-unchanged rows — useful for UI
    rendering where quiet matches are noise."""


# Per BUILD-PLAN §5 M9 AC #3 (post-Block-0 reconciliation), the
# task-field deltas cover these flat-field names on `Task`. The tuple
# ordering is the canonical emission order in `TaskDelta.field_deltas`;
# tests that inspect specific rows use this ordering.
_DATETIME_FIELDS: tuple[str, ...] = (
    "finish",
    "baseline_finish",
    "actual_start",
    "actual_finish",
)
_VALUE_FIELDS: tuple[str, ...] = (
    "total_slack_minutes",
    "free_slack_minutes",
    "duration_minutes",
    "constraint_type",
)


def _index_tasks_by_uid(schedule: Schedule, side: str) -> dict[int, Task]:
    """Build a ``unique_id → Task`` map, asserting uniqueness.

    The Schedule G10 validator has already ruled out duplicates at
    construction time; this defense-in-depth guard raises
    :class:`ComparatorError` if a bypassed path smuggled duplicates
    past the validator.
    """
    index: dict[int, Task] = {}
    for task in schedule.tasks:
        if task.unique_id in index:
            raise ComparatorError(
                f"duplicate Task.unique_id {task.unique_id} in "
                f"{side} schedule; Schedule validator G10 should have "
                "rejected this input"
            )
        index[task.unique_id] = task
    return index


def _classify_delta(a_value: Any, b_value: Any) -> DeltaType | None:
    """Map the (A, B) tuple to a :class:`DeltaType`, or ``None`` if
    the two values are equal."""
    if a_value == b_value:
        return None
    if a_value is None and b_value is not None:
        return DeltaType.ADDED
    if a_value is not None and b_value is None:
        return DeltaType.REMOVED
    return DeltaType.VALUE_CHANGE


def _field_delta(field_name: str, a_task: Task, b_task: Task) -> FieldDelta | None:
    """Return a :class:`FieldDelta` for ``field_name`` or ``None``."""
    a_value = getattr(a_task, field_name)
    b_value = getattr(b_task, field_name)
    delta_type = _classify_delta(a_value, b_value)
    if delta_type is None:
        return None
    return FieldDelta(
        field_name=field_name,
        period_a_value=a_value,
        period_b_value=b_value,
        delta_type=delta_type,
    )


def _diff_task_fields(a_task: Task, b_task: Task) -> tuple[FieldDelta, ...]:
    """Diff the M9-scope fields on a matched task pair.

    Emission order mirrors ``_DATETIME_FIELDS`` + ``_VALUE_FIELDS``;
    integer / enum fields cannot be ``None`` and so only ever emit
    ``VALUE_CHANGE`` rows.
    """
    deltas: list[FieldDelta] = []
    for name in _DATETIME_FIELDS:
        d = _field_delta(name, a_task, b_task)
        if d is not None:
            deltas.append(d)
    for name in _VALUE_FIELDS:
        d = _field_delta(name, a_task, b_task)
        if d is not None:
            deltas.append(d)
    return tuple(deltas)


def _build_matched_delta(
    uid: int,
    a_task: Task,
    b_task: Task,
    period_a_status_date: Any,
    period_b_status_date: Any,
) -> TaskDelta:
    field_deltas = _diff_task_fields(a_task, b_task)
    legit = is_legitimate_actual(
        a_task, b_task, period_a_status_date, period_b_status_date
    )
    return TaskDelta(
        unique_id=uid,
        presence=TaskPresence.MATCHED,
        period_a_name=a_task.name,
        period_b_name=b_task.name,
        field_deltas=field_deltas,
        is_legitimate_actual=legit,
    )


def _build_added_delta(uid: int, b_task: Task) -> TaskDelta:
    return TaskDelta(
        unique_id=uid,
        presence=TaskPresence.ADDED_IN_B,
        period_a_name=None,
        period_b_name=b_task.name,
        field_deltas=(),
        is_legitimate_actual=False,
    )


def _build_deleted_delta(uid: int, a_task: Task) -> TaskDelta:
    return TaskDelta(
        unique_id=uid,
        presence=TaskPresence.DELETED_FROM_A,
        period_a_name=a_task.name,
        period_b_name=None,
        field_deltas=(),
        is_legitimate_actual=False,
    )


# -----------------------------------------------------------------------
# Relationship diff (Block 4)
# -----------------------------------------------------------------------

# Field names diffed on matched relationships. The M2 Relation model
# carries a flat shape; matching is by (predecessor_unique_id,
# successor_unique_id) — see _index_relations_by_pair for the caveat
# on duplicate pairs with differing relation_type.
_RELATION_FIELDS: tuple[str, ...] = ("relation_type", "lag_minutes")


def _index_relations_by_pair(
    relations: list[Relation], side: str
) -> dict[tuple[int, int], Relation]:
    """Build a ``(predecessor_uid, successor_uid) → Relation`` map.

    The Relation model permits multiple links between the same pair
    with different ``relation_type`` values (see docstring on
    :class:`~app.models.schedule.Schedule.relations`: "A single task
    pair may carry multiple links of different types."). The M9
    comparator keys relationships by the pair so ``FS → SS`` edits
    surface as ``VALUE_CHANGE`` deltas on ``relation_type`` rather
    than as correlated delete + add pairs. Encountering two links on
    the same pair within a schedule therefore makes the matching
    ambiguous; the comparator raises :class:`ComparatorError` in
    that case.
    """
    index: dict[tuple[int, int], Relation] = {}
    for rel in relations:
        key = (rel.predecessor_unique_id, rel.successor_unique_id)
        if key in index:
            raise ComparatorError(
                f"duplicate relationship pair {key} in {side} schedule; "
                "M9 matches relationships by (predecessor, successor) pair "
                "and cannot disambiguate multiple concurrent links"
            )
        index[key] = rel
    return index


def _diff_relation_fields(
    a_rel: Relation, b_rel: Relation
) -> tuple[FieldDelta, ...]:
    deltas: list[FieldDelta] = []
    for name in _RELATION_FIELDS:
        a_value = getattr(a_rel, name)
        b_value = getattr(b_rel, name)
        delta_type = _classify_delta(a_value, b_value)
        if delta_type is None:
            continue
        deltas.append(
            FieldDelta(
                field_name=name,
                period_a_value=a_value,
                period_b_value=b_value,
                delta_type=delta_type,
            )
        )
    return tuple(deltas)


def _build_relationship_deltas(
    a_relations: list[Relation], b_relations: list[Relation]
) -> tuple[RelationshipDelta, ...]:
    a_by_pair = _index_relations_by_pair(a_relations, "period_a")
    b_by_pair = _index_relations_by_pair(b_relations, "period_b")

    matched_pairs = sorted(a_by_pair.keys() & b_by_pair.keys())
    added_pairs = sorted(b_by_pair.keys() - a_by_pair.keys())
    deleted_pairs = sorted(a_by_pair.keys() - b_by_pair.keys())

    deltas: list[RelationshipDelta] = []

    for key in matched_pairs:
        field_deltas = _diff_relation_fields(a_by_pair[key], b_by_pair[key])
        deltas.append(
            RelationshipDelta(
                predecessor_unique_id=key[0],
                successor_unique_id=key[1],
                presence=RelationshipPresence.MATCHED,
                field_deltas=field_deltas,
            )
        )
    for key in added_pairs:
        deltas.append(
            RelationshipDelta(
                predecessor_unique_id=key[0],
                successor_unique_id=key[1],
                presence=RelationshipPresence.ADDED_IN_B,
                field_deltas=(),
            )
        )
    for key in deleted_pairs:
        deltas.append(
            RelationshipDelta(
                predecessor_unique_id=key[0],
                successor_unique_id=key[1],
                presence=RelationshipPresence.DELETED_FROM_A,
                field_deltas=(),
            )
        )

    return tuple(deltas)


def compare_schedules(
    period_a: Schedule,
    period_b: Schedule,
    options: ComparatorOptions | None = None,
) -> ComparatorResult:
    """Compare two schedules by UniqueID and return a frozen result.

    AC #1 invariant: for every matched / added / deleted UniqueID a
    corresponding :class:`TaskDelta` is emitted. Relationship deltas
    are populated in Block 4; in Block 3 the field is always an
    empty tuple.

    Args:
        period_a: Period A schedule (earlier revision).
        period_b: Period B schedule (later revision).
        options: Optional :class:`ComparatorOptions`; the default is
            canonical per the M9 AC #1 shape.

    Returns:
        :class:`ComparatorResult` — frozen Pydantic v2 model.

    Raises:
        ComparatorError: on duplicate UniqueIDs within a schedule
            (i.e. a caller that bypassed the M2 G10 validator).
    """
    opts = options or ComparatorOptions()

    a_by_uid = _index_tasks_by_uid(period_a, "period_a")
    b_by_uid = _index_tasks_by_uid(period_b, "period_b")

    matched_uids = sorted(a_by_uid.keys() & b_by_uid.keys())
    added_uids = frozenset(b_by_uid.keys() - a_by_uid.keys())
    deleted_uids = frozenset(a_by_uid.keys() - b_by_uid.keys())

    task_deltas: list[TaskDelta] = []

    for uid in matched_uids:
        delta = _build_matched_delta(
            uid,
            a_by_uid[uid],
            b_by_uid[uid],
            period_a.status_date,
            period_b.status_date,
        )
        if not opts.include_unchanged_matched_tasks and not delta.field_deltas:
            # Skip quiet matches; downstream consumers opted out.
            continue
        task_deltas.append(delta)

    for uid in sorted(added_uids):
        task_deltas.append(_build_added_delta(uid, b_by_uid[uid]))

    for uid in sorted(deleted_uids):
        task_deltas.append(_build_deleted_delta(uid, a_by_uid[uid]))

    relationship_deltas = _build_relationship_deltas(
        period_a.relations, period_b.relations
    )

    return ComparatorResult(
        period_a_status_date=period_a.status_date,
        period_b_status_date=period_b.status_date,
        task_deltas=tuple(task_deltas),
        relationship_deltas=relationship_deltas,
        added_task_uids=added_uids,
        deleted_task_uids=deleted_uids,
        matched_task_count=len(matched_uids),
    )


__all__ = [
    "ComparatorError",
    "ComparatorOptions",
    "compare_schedules",
]
