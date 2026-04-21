"""Cross-version comparator contract — Milestone 9.

Frozen Pydantic v2 models emitted by :mod:`app.engine.comparator`.
The contract is deliberately narrow: values are recorded verbatim,
the consumer derives presentation (calendar-day slip, working-day
duration-delta) at render time per BUILD-PLAN §2.16 and the M9 Block
0 reconciliation.

Authority:

* UniqueID-only matching — BUILD-PLAN §2.7;
  ``mpp-parsing-com-automation §5``;
  ``forensic-manipulation-patterns §3.1``.
* Legitimate-actual tagging — ``forensic-manipulation-patterns §3.2``
  and ``driving-slack-and-paths §10`` (Period A finish ≤ Period B
  status_date).
* Mutation-vs-wrap — BUILD-PLAN §2.13; mirrors the ``CPMResult``
  shape in :mod:`app.engine.result`.

The module exports four models and three string enums; they are the
public API M10 (driving-path) and M11 (manipulation) will consume.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class DeltaType(StrEnum):
    """Classification of a single field-level change.

    * ``VALUE_CHANGE`` — the field is present on both sides and the
      values differ.
    * ``ADDED`` — the field was ``None`` in Period A and populated in
      Period B.
    * ``REMOVED`` — the field was populated in Period A and ``None``
      in Period B.
    """

    VALUE_CHANGE = "VALUE_CHANGE"
    ADDED = "ADDED"
    REMOVED = "REMOVED"


class TaskPresence(StrEnum):
    """Cross-version presence of a task matched by UniqueID.

    ``MATCHED`` — the UniqueID appears in both Period A and Period B.
    ``ADDED_IN_B`` — present in Period B only.
    ``DELETED_FROM_A`` — present in Period A only.
    """

    MATCHED = "MATCHED"
    ADDED_IN_B = "ADDED_IN_B"
    DELETED_FROM_A = "DELETED_FROM_A"


class RelationshipPresence(StrEnum):
    """Cross-version presence of a relationship matched by
    ``(predecessor_unique_id, successor_unique_id)``.

    ``MATCHED`` — the pair appears in both Period A and Period B.
    ``ADDED_IN_B`` — present in Period B only.
    ``DELETED_FROM_A`` — present in Period A only.
    """

    MATCHED = "MATCHED"
    ADDED_IN_B = "ADDED_IN_B"
    DELETED_FROM_A = "DELETED_FROM_A"


class FieldDelta(BaseModel):
    """A single field-level change between Period A and Period B.

    Values are recorded verbatim. For datetime fields the consumer
    derives the ``timedelta`` at render time (BUILD-PLAN §5 M9 AC5);
    for duration / slack fields the values are integer minutes per
    BUILD-PLAN §2.16 and are compared to each other directly. No
    presentation-layer unit conversion is performed here.
    """

    model_config = ConfigDict(frozen=True)

    field_name: str
    """The canonical attribute name on :class:`~app.models.task.Task`
    or :class:`~app.models.relation.Relation` that changed."""

    period_a_value: Any | None
    """Raw value from Period A. ``None`` when the field was absent
    or nullable-unset on the Period A side."""

    period_b_value: Any | None
    """Raw value from Period B. ``None`` when the field was absent
    or nullable-unset on the Period B side."""

    delta_type: DeltaType
    """:class:`DeltaType` classification — ``VALUE_CHANGE``,
    ``ADDED``, or ``REMOVED``."""


class TaskDelta(BaseModel):
    """Cross-version delta for a single task.

    Matched by ``unique_id`` per BUILD-PLAN §2.7 — ``task_id`` and
    ``name`` are never consulted for matching. The regression in
    :mod:`tests.test_engine_comparator` renames every task in Period
    B and verifies the matched-delta count is unchanged.
    """

    model_config = ConfigDict(frozen=True)

    unique_id: int
    """``Task.unique_id`` — stable cross-version identifier."""

    presence: TaskPresence
    """Whether the task is matched, added in B, or deleted from A."""

    period_a_name: str | None
    """``Task.name`` in Period A (``None`` for ``ADDED_IN_B``).
    Captured for UI drill-down; never used for matching."""

    period_b_name: str | None
    """``Task.name`` in Period B (``None`` for ``DELETED_FROM_A``).
    Captured for UI drill-down; never used for matching."""

    field_deltas: tuple[FieldDelta, ...]
    """Per-field changes on matched tasks. Empty tuple for
    structurally-unchanged matches and for ``ADDED_IN_B`` /
    ``DELETED_FROM_A`` rows (a structural add / delete already
    carries all of its field values on the underlying ``Task``
    snapshot; emitting every field as a ``FieldDelta`` would double-
    record)."""

    is_legitimate_actual: bool
    """``True`` iff the skill-anchored windowing predicate fires —
    Period A finish ≤ Period B status_date per
    ``forensic-manipulation-patterns §3.2`` and
    ``driving-slack-and-paths §10``. Always ``False`` for
    ``ADDED_IN_B`` / ``DELETED_FROM_A`` rows."""


class RelationshipDelta(BaseModel):
    """Cross-version delta for a single logic link.

    Matched by the composite key
    ``(predecessor_unique_id, successor_unique_id)`` — both UniqueID
    fields per BUILD-PLAN §2.7. Matching does not consider
    ``relation_type`` or ``lag_minutes``; those are diff-ed as
    ``FieldDelta`` rows on a matched pair.

    M10 (driving-path cross-version deltas) consumes this type to
    detect added / removed driving predecessors; M11 (manipulation)
    consumes it for logic-tampering detectors per
    ``forensic-manipulation-patterns §4``.
    """

    model_config = ConfigDict(frozen=True)

    predecessor_unique_id: int
    """``Relation.predecessor_unique_id``."""

    successor_unique_id: int
    """``Relation.successor_unique_id``."""

    presence: RelationshipPresence
    """Whether the link is matched, added in B, or deleted from A."""

    field_deltas: tuple[FieldDelta, ...]
    """Per-field changes on matched links (``relation_type``,
    ``lag_minutes``). Empty tuple for presence != ``MATCHED`` and
    for structurally-unchanged matches."""


class ComparatorResult(BaseModel):
    """Aggregate output of
    :func:`app.engine.comparator.compare_schedules`.

    Mirrors the frozen-contract posture of
    :class:`app.engine.result.CPMResult`: the comparator is a
    producer, downstream consumers are read-only. The AC #1
    invariant (50 tasks A, 50 tasks B, 40 matched, 5 added, 5
    deleted ⇒ 50 task-deltas total) is enforced by the comparator;
    ``len(task_deltas) ==
    matched_task_count + len(added_task_uids) +
    len(deleted_task_uids)``.
    """

    model_config = ConfigDict(frozen=True)

    period_a_status_date: datetime | None
    """Copy of ``Schedule.status_date`` from Period A, for
    downstream consumers that render the window."""

    period_b_status_date: datetime | None
    """Copy of ``Schedule.status_date`` from Period B."""

    task_deltas: tuple[TaskDelta, ...]
    """All task-level deltas — matched + added + deleted."""

    relationship_deltas: tuple[RelationshipDelta, ...]
    """All relationship-level deltas — matched + added + deleted."""

    added_task_uids: frozenset[int]
    """UniqueIDs present in Period B but not Period A."""

    deleted_task_uids: frozenset[int]
    """UniqueIDs present in Period A but not Period B."""

    matched_task_count: int
    """Count of UniqueIDs present in both schedules (structural
    intersection of A ∩ B). Reported independently of
    :attr:`~app.engine.comparator.ComparatorOptions.include_unchanged_matched_tasks`:
    when that option is ``False``, quiet matches (zero
    ``field_deltas``) are dropped from ``task_deltas`` for UI
    ergonomics, but ``matched_task_count`` still reports the full
    intersection size. Pre-computed for O(1) access."""


__all__ = [
    "ComparatorResult",
    "DeltaType",
    "FieldDelta",
    "RelationshipDelta",
    "RelationshipPresence",
    "TaskDelta",
    "TaskPresence",
]
