"""End-to-end integration test for the M9 comparator (Block 5).

Builds a paired 30-task schedule matching the integration scenario
described in the Block 5 prompt:

* 30 tasks each, 25 matched, 3 added in B, 2 deleted from A.
* 2 matched tasks exhibit legitimate actuals inside the window.
* 2 matched tasks exhibit changes outside the window (candidate
  manipulation).
* 1 relationship added, 1 deleted, 1 type-changed, 1 lag-changed.
* Both schedules carry valid status_dates, 30 days apart.
* All tasks renamed in Period B to exercise the UniqueID-only
  matching rule alongside the full pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.engine.comparator import compare_schedules
from app.engine.delta import RelationshipPresence, TaskPresence
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

STATUS_A = datetime(2026, 3, 1, 16, 0, tzinfo=UTC)
STATUS_B = datetime(2026, 3, 31, 16, 0, tzinfo=UTC)
ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _t(uid: int, name: str, **fields: object) -> Task:
    base = {"unique_id": uid, "task_id": uid, "name": name}
    base.update(fields)
    return Task(**base)  # type: ignore[arg-type]


def _build_period_a() -> Schedule:
    tasks: list[Task] = []
    # 25 matched UIDs: 1..25
    for uid in range(1, 26):
        if uid == 10:
            # Legitimate actual A: finish inside B window.
            tasks.append(
                _t(uid, f"A{uid}",
                   finish=datetime(2026, 3, 10, 16, tzinfo=UTC),
                   total_slack_minutes=480)
            )
        elif uid == 11:
            # Legitimate actual B: finish exactly at B's status_date.
            tasks.append(
                _t(uid, f"A{uid}",
                   finish=STATUS_B,
                   total_slack_minutes=0)
            )
        elif uid == 20:
            # Candidate manipulation A: finish well after B status.
            tasks.append(
                _t(uid, f"A{uid}",
                   finish=datetime(2026, 6, 15, 16, tzinfo=UTC),
                   total_slack_minutes=960)
            )
        elif uid == 21:
            # Candidate manipulation B: finish None (can't tag).
            tasks.append(
                _t(uid, f"A{uid}",
                   finish=None,
                   total_slack_minutes=240)
            )
        else:
            tasks.append(
                _t(uid, f"A{uid}",
                   finish=datetime(2026, 5, 15, 16, tzinfo=UTC))
            )

    # Deleted-from-A UIDs: 96, 97
    tasks.append(_t(96, "A96"))
    tasks.append(_t(97, "A97"))

    # Three parallel FS relations anchoring the diff vectors.
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS, lag_minutes=0),
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.FS, lag_minutes=240),
        Relation(predecessor_unique_id=4, successor_unique_id=5,
                 relation_type=RelationType.FS, lag_minutes=0),
        # Link that will be DELETED_FROM_A:
        Relation(predecessor_unique_id=6, successor_unique_id=7,
                 relation_type=RelationType.FS, lag_minutes=0),
    ]
    return Schedule(
        project_calendar_hours_per_day=8.0,
        name="period_a",
        project_start=ANCHOR,
        status_date=STATUS_A,
        tasks=tasks,
        relations=relations,
    )


def _build_period_b() -> Schedule:
    tasks: list[Task] = []
    # 25 matched UIDs: 1..25 — but with TOTALLY DIFFERENT names.
    for uid in range(1, 26):
        if uid == 10:
            # Legitimate actual A: actual_finish newly populated.
            tasks.append(
                _t(uid, f"RENAMED_{uid}",
                   finish=datetime(2026, 3, 10, 16, tzinfo=UTC),
                   total_slack_minutes=0,
                   actual_finish=datetime(2026, 3, 10, 16, tzinfo=UTC))
            )
        elif uid == 11:
            # Legitimate actual B: finish at B's status_date, slight TS edit.
            tasks.append(
                _t(uid, f"RENAMED_{uid}",
                   finish=STATUS_B,
                   total_slack_minutes=120)
            )
        elif uid == 20:
            # Candidate manipulation A: total_slack changed outside window.
            tasks.append(
                _t(uid, f"RENAMED_{uid}",
                   finish=datetime(2026, 6, 15, 16, tzinfo=UTC),
                   total_slack_minutes=-60)
            )
        elif uid == 21:
            # Candidate manipulation B: finish None (predicate False).
            tasks.append(
                _t(uid, f"RENAMED_{uid}",
                   finish=None,
                   total_slack_minutes=0)
            )
        else:
            tasks.append(
                _t(uid, f"RENAMED_{uid}",
                   finish=datetime(2026, 5, 15, 16, tzinfo=UTC))
            )

    # Added-in-B UIDs: 500, 501, 502
    tasks.append(_t(500, "RENAMED_500"))
    tasks.append(_t(501, "RENAMED_501"))
    tasks.append(_t(502, "RENAMED_502"))

    relations = [
        # 1→2 unchanged.
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS, lag_minutes=0),
        # 2→3: TYPE change FS → SS.
        Relation(predecessor_unique_id=2, successor_unique_id=3,
                 relation_type=RelationType.SS, lag_minutes=240),
        # 4→5: LAG change 0 → 3600.
        Relation(predecessor_unique_id=4, successor_unique_id=5,
                 relation_type=RelationType.FS, lag_minutes=3600),
        # 6→7 DELETED (absent here).
        # 8→9: ADDED in B.
        Relation(predecessor_unique_id=8, successor_unique_id=9,
                 relation_type=RelationType.FS, lag_minutes=0),
    ]
    return Schedule(
        project_calendar_hours_per_day=8.0,
        name="period_b",
        project_start=ANCHOR,
        status_date=STATUS_B,
        tasks=tasks,
        relations=relations,
    )


def test_integration_end_to_end_counts_and_tagging() -> None:
    a = _build_period_a()
    b = _build_period_b()

    a_snapshot = a.model_dump()
    b_snapshot = b.model_dump()

    result = compare_schedules(a, b)

    # AC #1 arithmetic: 25 matched + 3 added + 2 deleted = 30 rows.
    assert result.matched_task_count == 25
    assert len(result.added_task_uids) == 3
    assert len(result.deleted_task_uids) == 2
    assert result.added_task_uids == frozenset({500, 501, 502})
    assert result.deleted_task_uids == frozenset({96, 97})
    assert len(result.task_deltas) == 30

    presences = [d.presence for d in result.task_deltas]
    assert presences.count(TaskPresence.MATCHED) == 25
    assert presences.count(TaskPresence.ADDED_IN_B) == 3
    assert presences.count(TaskPresence.DELETED_FROM_A) == 2

    # Legitimate-actual tagging: 2 matched tasks qualify (UIDs 10, 11).
    # Every other matched task has finish beyond STATUS_B (or None for
    # UID 21), so is_legitimate_actual = False.
    legit = [d for d in result.task_deltas if d.is_legitimate_actual]
    legit_uids = {d.unique_id for d in legit}
    assert legit_uids == {10, 11}

    # Candidate-manipulation UIDs have is_legitimate_actual = False.
    candidate_uids = {d.unique_id for d in result.task_deltas
                      if not d.is_legitimate_actual
                      and d.presence is TaskPresence.MATCHED
                      and d.field_deltas}
    assert 20 in candidate_uids

    # AC #4 regression: every matched UID's names differ.
    for delta in result.task_deltas:
        if delta.presence is TaskPresence.MATCHED:
            assert delta.period_a_name.startswith("A")
            assert delta.period_b_name.startswith("RENAMED_")

    # Relationship deltas: 1 added, 1 deleted, 1 type-change,
    # 1 lag-change, 1 unchanged-matched (1→2). Total = 5 rows.
    rd_by_pair = {(rd.predecessor_unique_id, rd.successor_unique_id): rd
                  for rd in result.relationship_deltas}
    assert (8, 9) in rd_by_pair
    assert rd_by_pair[(8, 9)].presence is RelationshipPresence.ADDED_IN_B
    assert (6, 7) in rd_by_pair
    assert rd_by_pair[(6, 7)].presence is RelationshipPresence.DELETED_FROM_A
    assert (2, 3) in rd_by_pair
    type_fd = next(
        fd for fd in rd_by_pair[(2, 3)].field_deltas
        if fd.field_name == "relation_type"
    )
    assert type_fd.period_a_value is RelationType.FS
    assert type_fd.period_b_value is RelationType.SS
    lag_fd = next(
        fd for fd in rd_by_pair[(4, 5)].field_deltas
        if fd.field_name == "lag_minutes"
    )
    assert lag_fd.period_a_value == 0
    assert lag_fd.period_b_value == 3600
    # 1→2 matched with no field change.
    assert rd_by_pair[(1, 2)].presence is RelationshipPresence.MATCHED
    assert rd_by_pair[(1, 2)].field_deltas == ()

    # Status-date carry-through.
    assert result.period_a_status_date == STATUS_A
    assert result.period_b_status_date == STATUS_B

    # Mutation-invariance on both inputs (the Block 5 prompt's final
    # gate).
    assert a.model_dump() == a_snapshot
    assert b.model_dump() == b_snapshot
