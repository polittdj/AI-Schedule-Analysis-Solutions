"""Tests for ``app.models.schedule``. Covers G1, G9, G10, G11, G12."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.calendar import Calendar
from app.models.enums import RelationType, ResourceType
from app.models.relation import Relation
from app.models.resource import Resource, ResourceAssignment
from app.models.schedule import Schedule
from app.models.task import Task

UTC = timezone.utc


def _dt(d: int = 1, h: int = 8) -> datetime:
    return datetime(2026, 4, d, h, tzinfo=UTC)


def _task(uid: int, tid: int | None = None, name: str | None = None) -> Task:
    return Task(unique_id=uid, task_id=tid if tid is not None else uid, name=name or f"T{uid}")


class TestG12EmptySchedule:
    def test_empty_schedule_is_valid(self) -> None:
        s = Schedule()
        assert s.tasks == []
        assert s.relations == []
        assert s.status_date is None


class TestG9StatusDate:
    def test_tz_aware_accepted(self) -> None:
        s = Schedule(status_date=_dt(15, 17))
        assert s.status_date is not None
        assert s.status_date.tzinfo is not None

    def test_naive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Schedule(status_date=datetime(2026, 4, 15, 17))

    def test_project_start_naive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Schedule(project_start=datetime(2026, 4, 1, 8))

    def test_project_finish_naive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Schedule(project_finish=datetime(2026, 4, 30, 17))


class TestG10UniqueIdCollisionDetection:
    def test_duplicate_unique_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="G10"):
            Schedule(
                tasks=[
                    _task(1),
                    _task(uid=1, tid=2, name="dup"),
                ],
            )

    def test_all_unique_ok(self) -> None:
        s = Schedule(tasks=[_task(1), _task(2), _task(3)])
        assert len(s.tasks) == 3


class TestG11RelationTaskExistence:
    def test_dangling_predecessor_rejected(self) -> None:
        with pytest.raises(ValidationError, match="G11"):
            Schedule(
                tasks=[_task(1), _task(2)],
                relations=[Relation(predecessor_unique_id=99, successor_unique_id=2)],
            )

    def test_dangling_successor_rejected(self) -> None:
        with pytest.raises(ValidationError, match="G11"):
            Schedule(
                tasks=[_task(1), _task(2)],
                relations=[Relation(predecessor_unique_id=1, successor_unique_id=99)],
            )

    def test_valid_relation_accepted(self) -> None:
        s = Schedule(
            tasks=[_task(1), _task(2), _task(3)],
            relations=[
                Relation(predecessor_unique_id=1, successor_unique_id=2),
                Relation(
                    predecessor_unique_id=2,
                    successor_unique_id=3,
                    relation_type=RelationType.SS,
                    lag_minutes=480,
                ),
            ],
        )
        assert len(s.relations) == 2


class TestResourceAssignmentsHygiene:
    def test_assignment_task_must_exist(self) -> None:
        with pytest.raises(ValidationError):
            Schedule(
                tasks=[_task(1)],
                resources=[Resource(unique_id=10, resource_id=1, name="R")],
                assignments=[
                    ResourceAssignment(resource_unique_id=10, task_unique_id=99)
                ],
            )

    def test_assignment_resource_must_exist_when_resources_populated(self) -> None:
        with pytest.raises(ValidationError):
            Schedule(
                tasks=[_task(1)],
                resources=[Resource(unique_id=10, resource_id=1, name="R")],
                assignments=[
                    ResourceAssignment(resource_unique_id=99, task_unique_id=1)
                ],
            )

    def test_assignment_resource_skipped_when_resources_empty(self) -> None:
        """If no resources are defined, assignment resource-UIDs aren't
        cross-checked — lets the M3 parser populate assignments before
        resources without crashing during incremental construction."""
        s = Schedule(
            tasks=[_task(1)],
            assignments=[ResourceAssignment(resource_unique_id=10, task_unique_id=1)],
        )
        assert len(s.assignments) == 1


class TestRoundTrip:
    def test_small_schedule_json_roundtrip(self) -> None:
        original = Schedule(
            name="test.mpp",
            status_date=_dt(15, 17),
            project_start=_dt(1, 8),
            project_finish=_dt(30, 17),
            tasks=[
                _task(1),
                Task(unique_id=2, task_id=2, name="T2", duration_minutes=2400),
                Task(unique_id=3, task_id=3, name="T3", percent_complete=50.0),
            ],
            relations=[
                Relation(predecessor_unique_id=1, successor_unique_id=2),
                Relation(
                    predecessor_unique_id=2,
                    successor_unique_id=3,
                    relation_type=RelationType.FS,
                    lag_minutes=-240,
                ),
            ],
            resources=[
                Resource(
                    unique_id=100,
                    resource_id=1,
                    name="R",
                    resource_type=ResourceType.WORK,
                )
            ],
            assignments=[
                ResourceAssignment(
                    resource_unique_id=100, task_unique_id=2, units=0.5, work_minutes=1200
                )
            ],
            calendars=[Calendar(name="Standard")],
        )
        clone = Schedule.model_validate_json(original.model_dump_json())
        assert clone == original

    def test_top_level_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Schedule(surprise="x")  # type: ignore[call-arg]
