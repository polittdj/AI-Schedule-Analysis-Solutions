"""Unit tests for the MPP parser module.

These tests intentionally do NOT require a real .mpp file or a running
JVM — they exercise the pure-Python helpers and verify the error path
when a caller asks for a file that doesn't exist.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.parser.calendar_parser import (
    CalendarException,
    CalendarInfo,
    working_days_between,
)
from app.parser.mpp_reader import duration_to_days, parse_mpp
from app.parser.schema import (
    AssignmentData,
    ProjectInfo,
    Relationship,
    ResourceData,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Schema instantiation
# --------------------------------------------------------------------------- #


class TestSchema:
    def test_project_info_minimal(self):
        info = ProjectInfo()
        assert info.name is None
        assert info.status_date is None

    def test_project_info_full(self):
        info = ProjectInfo(
            name="Bridge Replacement",
            status_date=datetime(2026, 4, 1),
            start_date=datetime(2025, 1, 1),
            finish_date=datetime(2027, 6, 30),
            current_date=datetime(2026, 4, 9),
            calendar_name="Standard",
        )
        assert info.name == "Bridge Replacement"
        assert info.calendar_name == "Standard"

    def test_task_data_defaults(self):
        task = TaskData(uid=42)
        assert task.uid == 42
        assert task.critical is False
        assert task.summary is False
        assert task.milestone is False
        assert task.predecessors == []
        assert task.successors == []

    def test_task_data_with_relations(self):
        task = TaskData(
            uid=100,
            id=5,
            name="Install girders",
            wbs="1.2.3",
            outline_level=3,
            duration=12.0,
            critical=True,
            predecessors=[98, 99],
            successors=[101],
        )
        assert task.duration == 12.0
        assert task.predecessors == [98, 99]
        assert task.critical is True

    def test_relationship_model(self):
        rel = Relationship(predecessor_uid=1, successor_uid=2, type="FS", lag_days=2.5)
        assert rel.type == "FS"
        assert rel.lag_days == 2.5

    def test_relationship_defaults(self):
        rel = Relationship(predecessor_uid=1, successor_uid=2)
        assert rel.type == "FS"
        assert rel.lag_days == 0.0

    def test_resource_data(self):
        res = ResourceData(uid=7, name="Crane Op", type="WORK", max_units=1.0)
        assert res.name == "Crane Op"
        assert res.max_units == 1.0

    def test_assignment_data(self):
        asn = AssignmentData(
            task_uid=100, resource_uid=7, work=40.0, actual_work=16.0, cost=4800.0
        )
        assert asn.task_uid == 100
        assert asn.work == 40.0

    def test_schedule_data_container(self):
        schedule = ScheduleData(
            project_info=ProjectInfo(name="Demo"),
            tasks=[TaskData(uid=1, name="A"), TaskData(uid=2, name="B")],
            resources=[ResourceData(uid=1, name="Alice")],
            assignments=[AssignmentData(task_uid=1, resource_uid=1, work=8.0)],
            relationships=[
                Relationship(predecessor_uid=1, successor_uid=2, type="FS")
            ],
        )
        assert len(schedule.tasks) == 2
        assert schedule.project_info.name == "Demo"
        assert schedule.relationships[0].predecessor_uid == 1


# --------------------------------------------------------------------------- #
# parse_mpp error path
# --------------------------------------------------------------------------- #


class TestParseMpp:
    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "nope.mpp"
        with pytest.raises(FileNotFoundError):
            parse_mpp(str(missing))

    def test_empty_path_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_mpp("")

    def test_directory_path_raises(self, tmp_path):
        # A directory is not a file — should also raise FileNotFoundError.
        with pytest.raises(FileNotFoundError):
            parse_mpp(str(tmp_path))


# --------------------------------------------------------------------------- #
# Duration conversion (hours → working days)
# --------------------------------------------------------------------------- #


class TestDurationConversion:
    def test_hours_to_days_short_code(self):
        # 16 hours / 8h per day = 2 days
        assert duration_to_days(16.0, "h") == pytest.approx(2.0)

    def test_hours_to_days_long_name(self):
        assert duration_to_days(40.0, "HOURS") == pytest.approx(5.0)

    def test_days_passthrough(self):
        assert duration_to_days(7.0, "d") == pytest.approx(7.0)
        assert duration_to_days(7.0, "DAYS") == pytest.approx(7.0)

    def test_weeks_to_days(self):
        # 2 weeks = 10 working days
        assert duration_to_days(2.0, "w") == pytest.approx(10.0)

    def test_minutes_to_days(self):
        # 480 minutes = 8 working hours = 1 day
        assert duration_to_days(480.0, "min") == pytest.approx(1.0)

    def test_none_value_returns_none(self):
        assert duration_to_days(None, "h") is None

    def test_none_unit_passthrough(self):
        assert duration_to_days(3.0, None) == pytest.approx(3.0)

    def test_unknown_unit_passthrough(self):
        assert duration_to_days(5.0, "fortnights") == pytest.approx(5.0)

    def test_elapsed_hours(self):
        assert duration_to_days(24.0, "eh") == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# Calendar helpers
# --------------------------------------------------------------------------- #


class TestCalendarHelpers:
    def test_calendar_info_defaults(self):
        cal = CalendarInfo()
        assert cal.hours_per_day == 8.0
        assert cal.working_days == []

    def test_working_days_between_std_week(self):
        cal = CalendarInfo(
            working_days=["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
        )
        # Mon 2026-04-06 → Sun 2026-04-12 = 5 working days
        start = datetime(2026, 4, 6)
        end = datetime(2026, 4, 12)
        assert working_days_between(start, end, cal) == 5

    def test_working_days_between_with_holiday(self):
        cal = CalendarInfo(
            working_days=["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
            exceptions=[
                CalendarException(
                    name="Good Friday",
                    from_date=datetime(2026, 4, 3),
                    to_date=datetime(2026, 4, 3),
                )
            ],
        )
        # Mon–Fri of the prior week, Friday is a holiday → 4 working days
        start = datetime(2026, 3, 30)
        end = datetime(2026, 4, 3)
        assert working_days_between(start, end, cal) == 4

    def test_working_days_between_reversed(self):
        cal = CalendarInfo(working_days=["MONDAY"])
        assert working_days_between(datetime(2026, 4, 10), datetime(2026, 4, 1), cal) == 0
