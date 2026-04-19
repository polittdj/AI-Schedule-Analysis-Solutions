"""Synthetic :class:`Schedule` builders for CPM engine tests.

Every builder is hand-crafted from synthetic numbers
(``cui-compliance-constraints §2e`` fixture-data quarantine) and
returns a fully-validated :class:`~app.models.schedule.Schedule`.

Builders:

* :func:`small_fs_chain` — 3-task Finish-to-Start chain. Smoke test.
* :func:`medium_mixed_relations` — 10 tasks with SS, FF, SF mixed in.
* :func:`complex_with_exceptions` — 50-ish tasks spanning 8 weeks
  with a Christmas exception and an interim MFO-constrained milestone.

All builders use ``2026-04-20`` (Monday) as their anchor start so
that the default 5-day Mon-Fri calendar produces predictable output.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.calendar import Calendar, CalendarException
from app.models.enums import ConstraintType, RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)  # Monday 08:00 UTC


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def small_fs_chain() -> Schedule:
    """Three-task FS chain: A → B → C, each 1 working day (480 min)."""
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    return Schedule(
        name="small_fs_chain",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def medium_mixed_relations() -> Schedule:
    """10-task network exercising FS, SS, FF, and SF links."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 11)
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=1, successor_unique_id=3,
                 relation_type=RelationType.SS),
        Relation(predecessor_unique_id=2, successor_unique_id=4,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=3, successor_unique_id=4,
                 relation_type=RelationType.FF),
        Relation(predecessor_unique_id=4, successor_unique_id=5,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=4, successor_unique_id=6,
                 relation_type=RelationType.SS, lag_minutes=120),
        Relation(predecessor_unique_id=5, successor_unique_id=7,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=6, successor_unique_id=7,
                 relation_type=RelationType.FF),
        Relation(predecessor_unique_id=7, successor_unique_id=8,
                 relation_type=RelationType.FS),
        Relation(predecessor_unique_id=8, successor_unique_id=9,
                 relation_type=RelationType.SF),
        Relation(predecessor_unique_id=9, successor_unique_id=10,
                 relation_type=RelationType.FS),
    ]
    return Schedule(
        name="medium_mixed_relations",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def complex_with_exceptions() -> Schedule:
    """50-task network with calendar exception and an MFO milestone.

    Topology: 5 parallel chains of 10 tasks each, then a final
    ``Finish`` milestone. Christmas 2026-12-25 is non-working; task
    30 (mid-chain) carries an MFO constraint mid-schedule.
    """
    tasks: list[Task] = []
    relations: list[Relation] = []

    next_uid = 1
    chain_tails: list[int] = []
    for chain in range(5):
        prev: int | None = None
        for step in range(10):
            uid = next_uid
            is_mfo = uid == 30
            tasks.append(
                Task(
                    unique_id=uid,
                    task_id=uid,
                    name=f"C{chain}S{step}",
                    duration_minutes=480,
                    constraint_type=(
                        ConstraintType.MUST_FINISH_ON
                        if is_mfo else ConstraintType.AS_SOON_AS_POSSIBLE
                    ),
                    constraint_date=(
                        datetime(2026, 6, 19, 16, 0, tzinfo=UTC)
                        if is_mfo else None
                    ),
                )
            )
            if prev is not None:
                relations.append(
                    Relation(
                        predecessor_unique_id=prev,
                        successor_unique_id=uid,
                        relation_type=RelationType.FS,
                    )
                )
            prev = uid
            next_uid += 1
        chain_tails.append(prev)  # type: ignore[arg-type]

    finish_uid = next_uid
    tasks.append(
        Task(
            unique_id=finish_uid, task_id=finish_uid, name="Finish",
            duration_minutes=0, is_milestone=True,
        )
    )
    for tail in chain_tails:
        relations.append(
            Relation(
                predecessor_unique_id=tail,
                successor_unique_id=finish_uid,
                relation_type=RelationType.FS,
            )
        )

    cal = Calendar(
        name="Standard",
        exceptions=[
            CalendarException(
                name="Christmas",
                start=datetime(2026, 12, 25, tzinfo=UTC),
                finish=datetime(2026, 12, 25, tzinfo=UTC),
                is_working=False,
            )
        ],
    )

    return Schedule(
        name="complex_with_exceptions",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[cal],
    )


__all__ = [
    "ANCHOR",
    "complex_with_exceptions",
    "medium_mixed_relations",
    "small_fs_chain",
]
