"""Integration tests for :class:`MPProjectParser`.

These tests exercise the parser end-to-end with synthetic COM-shaped
fixtures (``tests/fixtures``). They run on Linux CI because the
parser accepts injected ``dispatch`` / ``co_initialize`` /
``co_uninitialize`` callables. A separate test class verifies the
real-win32com import path gracefully raises COMUnavailableError
when pywin32 is absent (P1).

Parser gotcha coverage map
==========================

* P1  — COM unavailable path (``win32com`` absent)     → TestComUnavailable
* P2  — file not found                                  → TestFileOpenErrors
* P3  — corrupt file / mid-parse COM error              → TestCorruptSchedule
* P8  — naive COM datetime → tz-aware UTC               → TestTaskDates
* P9  — ASAP/ALAP with a stray constraint date          → TestConstraintNullOut
* P10 — summary tasks parsed, flag preserved            → TestTaskFlags
* P11 — milestone tasks parsed (zero duration legal)    → TestTaskFlags
* P12 — deleted / null tasks skipped                    → TestNullTasks
* P13 — inactive tasks parsed, flag preserved           → TestTaskFlags
* P14 — Quit called on error (no orphaned process)      → TestCleanup
* P15 — indexed iteration on large schedules            → TestLargeSchedule
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.enums import ConstraintType, RelationType
from app.parsers.com_parser import MPProjectParser, parse_mpp
from app.parsers.exceptions import (
    COMUnavailableError,
    CorruptScheduleError,
    MPOpenError,
)
from tests.fixtures import (
    FakeAssignment,
    FakeCalendar,
    FakeMSProjectApp,
    FakeProject,
    FakeResource,
    FakeTask,
    make_minimal_project,
)


def _dispatch_factory(app: FakeMSProjectApp):
    """Return a ``dispatch`` callable that always hands back ``app``."""

    def dispatch(prog_id: str) -> FakeMSProjectApp:
        assert prog_id == "MSProject.Application"
        return app

    return dispatch


def _parser_with(app: FakeMSProjectApp) -> MPProjectParser:
    """Construct a parser wired to ``app`` with no-op CoInit / CoUninit."""
    return MPProjectParser(
        dispatch=_dispatch_factory(app),
        co_initialize=lambda: None,
        co_uninitialize=lambda: None,
    )


# ---------------------------------------------------------------------------
# P1 — COM unavailable
# ---------------------------------------------------------------------------


class TestComUnavailable:
    def test_dispatch_raising_comunavailable_surfaces(self, tmp_path) -> None:
        """Parser gotcha P1: win32com missing → COMUnavailableError."""
        def dispatch(prog_id: str) -> Any:
            raise COMUnavailableError("win32com not installed")

        parser = MPProjectParser(
            dispatch=dispatch,
            co_initialize=lambda: None,
            co_uninitialize=lambda: None,
        )
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"stub")
        with pytest.raises(COMUnavailableError):
            parser.parse(mpp)

    def test_generic_dispatch_error_becomes_comunavailable(self, tmp_path) -> None:
        """Any Dispatch failure is surfaced as COMUnavailableError."""
        def dispatch(prog_id: str) -> Any:
            raise RuntimeError("OLE error 0x80040154 — class not registered")

        parser = MPProjectParser(
            dispatch=dispatch,
            co_initialize=lambda: None,
            co_uninitialize=lambda: None,
        )
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"stub")
        with pytest.raises(COMUnavailableError):
            parser.parse(mpp)


# ---------------------------------------------------------------------------
# P2 — file not found / unable to open
# ---------------------------------------------------------------------------


class TestFileOpenErrors:
    def test_missing_file_raises_mpopenerror(self) -> None:
        """Parser gotcha P2: missing file → MPOpenError (not IOError)."""
        app = FakeMSProjectApp(
            file_open_should_raise=FileNotFoundError("file not found"),
        )
        with _parser_with(app) as parser, pytest.raises(MPOpenError) as exc:
            parser.parse("/nonexistent/never-existed.mpp")
        assert "never-existed.mpp" in str(exc.value)

    def test_permission_denied_raises_mpopenerror(self, tmp_path) -> None:
        """A locked/unreadable file also routes through MPOpenError."""
        mpp = tmp_path / "locked.mpp"
        mpp.write_bytes(b"")
        app = FakeMSProjectApp(
            file_open_should_raise=PermissionError("file is locked"),
        )
        with _parser_with(app) as parser, pytest.raises(MPOpenError):
            parser.parse(mpp)


# ---------------------------------------------------------------------------
# P3 — corrupt schedule / mid-parse COM error
# ---------------------------------------------------------------------------


class TestCorruptSchedule:
    def test_no_active_project_after_open(self, tmp_path) -> None:
        """Gotcha P3: FileOpen succeeded but ActiveProject is None."""
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")

        app = FakeMSProjectApp()
        # Force ActiveProject to remain None after FileOpen.
        app.FileOpen = lambda path, ReadOnly=False: None  # type: ignore[method-assign]
        with _parser_with(app) as parser, pytest.raises(CorruptScheduleError):
            parser.parse(mpp)

    def test_bad_unique_id_becomes_corrupt(self, tmp_path) -> None:
        """A task whose UniqueID is non-integer fails int() conversion;
        the parser must wrap that in CorruptScheduleError rather than
        leaking a ``ValueError`` / ``TypeError``.
        """
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        bad = FakeTask(unique_id="not-a-number", task_id=1, name="T")  # type: ignore[arg-type]
        project = FakeProject(tasks=[bad])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser, pytest.raises(CorruptScheduleError):
            parser.parse(mpp)

    def test_duplicate_unique_ids_becomes_corrupt(self, tmp_path) -> None:
        """Model G10 rejects duplicate UniqueIDs; parser surfaces as
        CorruptScheduleError.
        """
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        a = FakeTask(unique_id=1, task_id=1, name="A")
        b = FakeTask(unique_id=1, task_id=2, name="B")
        project = FakeProject(tasks=[a, b])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser, pytest.raises(CorruptScheduleError):
            parser.parse(mpp)


# ---------------------------------------------------------------------------
# Gotcha-2 ordering — Visible/DisplayAlerts set BEFORE FileOpen
# ---------------------------------------------------------------------------


class TestHeadlessOrdering:
    def test_visible_and_displayalerts_precede_fileopen(self, tmp_path) -> None:
        """Skill §3.2 Gotcha 2: headless flags set before FileOpen."""
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        app = FakeMSProjectApp(make_minimal_project())
        with _parser_with(app) as parser:
            parser.parse(mpp)

        # Both writes land before the FileOpen entry in the call log.
        fileopen_idx = next(
            i for i, s in enumerate(app.call_log) if s.startswith("FileOpen:")
        )
        visible_idx = next(
            i for i, s in enumerate(app.call_log) if s == "set:Visible=False"
        )
        alerts_idx = next(
            i
            for i, s in enumerate(app.call_log)
            if s == "set:DisplayAlerts=False"
        )
        assert visible_idx < fileopen_idx
        assert alerts_idx < fileopen_idx

    def test_readonly_true_on_fileopen(self, tmp_path) -> None:
        """Gotcha 9 — FileOpen ReadOnly=True."""
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        app = FakeMSProjectApp(make_minimal_project())
        with _parser_with(app) as parser:
            parser.parse(mpp)

        assert any(
            "ReadOnly=True" in s for s in app.call_log if s.startswith("FileOpen")
        )

    def test_fileclose_save_zero(self, tmp_path) -> None:
        """Gotcha 9 — FileClose with Save=0 so source is never mutated."""
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        app = FakeMSProjectApp(make_minimal_project())
        with _parser_with(app) as parser:
            parser.parse(mpp)

        assert "FileClose:Save=0" in app.call_log


# ---------------------------------------------------------------------------
# P8 — task dates arrive tz-aware UTC
# ---------------------------------------------------------------------------


class TestTaskDates:
    def test_naive_datetime_becomes_utc_aware(self) -> None:
        """P8: COM returns naive; model sees UTC-aware."""
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="T",
            start=datetime(2025, 1, 1, 8, 0, 0),
            finish=datetime(2025, 1, 8, 17, 0, 0),
        )
        project = FakeProject(tasks=[t])

        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)

        task = schedule.tasks[0]
        assert task.start is not None
        assert task.start.tzinfo is UTC
        assert task.start == datetime(2025, 1, 1, 8, 0, 0, tzinfo=UTC)
        assert task.finish.tzinfo is UTC

    def test_status_date_sentinel_becomes_none(self) -> None:
        """Gotcha 6: OLE-zero normalizes to None."""
        project = make_minimal_project(status_date=datetime(1899, 12, 30))
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.status_date is None

    def test_status_date_na_string_becomes_none(self) -> None:
        project = make_minimal_project(status_date="NA")
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.status_date is None

    def test_status_date_set_is_preserved(self) -> None:
        project = make_minimal_project(status_date=datetime(2025, 3, 1))
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.status_date == datetime(2025, 3, 1, tzinfo=UTC)


def _parse_with(parser: MPProjectParser, project: FakeProject):
    """Drive ``parser.parse`` using the fixture ``project`` directly.

    Wraps a temp-file dance so tests don't need to create empty files
    on disk. The dispatch-injected FakeMSProjectApp serves the
    fixture project on FileOpen.
    """
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mpp", delete=False) as tf:
        path = tf.name
    try:
        return parser.parse(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# P9 — ASAP/ALAP null out constraint_date
# ---------------------------------------------------------------------------


class TestConstraintNullOut:
    def test_asap_with_stray_constraint_date_nulled(self) -> None:
        """Gotcha P9: COM may return constraint_date on ASAP rows."""
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="T",
            constraint_type=0,  # ASAP
            constraint_date=datetime(2025, 1, 1),  # bogus — COM noise
        )
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        task = schedule.tasks[0]
        assert task.constraint_type is ConstraintType.AS_SOON_AS_POSSIBLE
        assert task.constraint_date is None

    def test_alap_with_stray_constraint_date_nulled(self) -> None:
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="T",
            constraint_type=1,  # ALAP
            constraint_date=datetime(2025, 1, 1),
        )
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].constraint_type is ConstraintType.AS_LATE_AS_POSSIBLE
        assert schedule.tasks[0].constraint_date is None

    def test_mso_preserves_constraint_date(self) -> None:
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="T",
            constraint_type=2,  # MSO
            constraint_date=datetime(2025, 3, 15),
        )
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        task = schedule.tasks[0]
        assert task.constraint_type is ConstraintType.MUST_START_ON
        assert task.constraint_date == datetime(2025, 3, 15, tzinfo=UTC)

    def test_mso_missing_date_falls_back_to_asap(self) -> None:
        """Date-bearing constraint without a date would fail G7;
        parser degrades to ASAP rather than hard-failing the parse.
        """
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="T",
            constraint_type=2,  # MSO
            constraint_date=None,
        )
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].constraint_type is ConstraintType.AS_SOON_AS_POSSIBLE


# ---------------------------------------------------------------------------
# P10 / P11 / P13 — task flags (summary, milestone, inactive)
# ---------------------------------------------------------------------------


class TestTaskFlags:
    def test_summary_task_parsed_and_flagged(self, tmp_path) -> None:
        """P10: summary tasks still parse; M4 filters them."""
        summary = FakeTask(
            unique_id=1,
            task_id=1,
            name="Summary",
            summary=True,
            outline_level=1,
        )
        child = FakeTask(
            unique_id=2, task_id=2, name="Child", summary=False, outline_level=2
        )
        project = FakeProject(tasks=[summary, child])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.tasks) == 2
        parsed_summary = next(t for t in schedule.tasks if t.unique_id == 1)
        assert parsed_summary.is_summary is True
        parsed_child = next(t for t in schedule.tasks if t.unique_id == 2)
        assert parsed_child.is_summary is False

    def test_milestone_zero_duration_legal(self, tmp_path) -> None:
        """P11: zero-duration milestone tasks are valid."""
        m = FakeTask(
            unique_id=1,
            task_id=1,
            name="M",
            milestone=True,
            duration=0,
        )
        project = FakeProject(tasks=[m])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].is_milestone is True
        assert schedule.tasks[0].duration_minutes == 0

    def test_critical_flag_preserved(self, tmp_path) -> None:
        t = FakeTask(unique_id=1, task_id=1, name="Crit", critical=True)
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].is_critical_from_msp is True

    def test_inactive_task_still_parsed(self, tmp_path) -> None:
        """P13: inactive tasks parse; flag preserved for M4 filter."""
        t = FakeTask(unique_id=1, task_id=1, name="Inactive", active=False)
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.tasks) == 1
        # The model doesn't currently carry is_active; verify the
        # task was still parsed rather than dropped.
        assert schedule.tasks[0].unique_id == 1


# ---------------------------------------------------------------------------
# P12 — null / deleted tasks
# ---------------------------------------------------------------------------


class TestNullTasks:
    def test_none_row_skipped(self, tmp_path) -> None:
        """Gotcha 4 / P12: None entries in Tasks collection skip cleanly.

        Following tasks are not lost.
        """
        good1 = FakeTask(unique_id=1, task_id=1, name="A")
        good2 = FakeTask(unique_id=2, task_id=2, name="B")
        # The MS Project COM Tasks collection may contain None entries.
        project = FakeProject(tasks=[good1, None, good2])  # type: ignore[list-item]
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert [t.unique_id for t in schedule.tasks] == [1, 2]

    def test_null_unique_id_skipped(self, tmp_path) -> None:
        """P12: a row with null UniqueID is a deleted ghost — skip."""
        ghost = FakeTask(
            unique_id=None,  # type: ignore[arg-type]
            task_id=99,
            name=None,
        )
        good = FakeTask(unique_id=1, task_id=1, name="Real")
        project = FakeProject(tasks=[ghost, good])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert [t.unique_id for t in schedule.tasks] == [1]

    def test_null_name_and_duration_skipped(self, tmp_path) -> None:
        """P12 heuristic: UniqueID present but Name and Duration both
        null → ghost row, skip.
        """
        ghost = FakeTask(
            unique_id=1,
            task_id=1,
            name=None,
            duration=None,  # type: ignore[arg-type]
        )
        good = FakeTask(unique_id=2, task_id=2, name="Real")
        project = FakeProject(tasks=[ghost, good])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert [t.unique_id for t in schedule.tasks] == [2]


# ---------------------------------------------------------------------------
# Relations — predecessor-string parsing with Task ID → UniqueID translation
# ---------------------------------------------------------------------------


class TestRelations:
    def test_simple_predecessor(self, tmp_path) -> None:
        t1 = FakeTask(unique_id=100, task_id=1, name="A")
        t2 = FakeTask(unique_id=200, task_id=2, name="B", predecessors="1FS")
        project = FakeProject(tasks=[t1, t2])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.relations) == 1
        r = schedule.relations[0]
        assert r.predecessor_unique_id == 100
        assert r.successor_unique_id == 200
        assert r.relation_type is RelationType.FS

    def test_task_id_translated_to_unique_id(self, tmp_path) -> None:
        """P6: Task IDs in predecessor string → UniqueIDs via id_map.

        Task ID 1 maps to UniqueID 4217 below — simulating a task
        that was renumbered across versions.
        """
        t1 = FakeTask(unique_id=4217, task_id=1, name="A")
        t2 = FakeTask(unique_id=200, task_id=2, name="B", predecessors="1FS+2d")
        project = FakeProject(tasks=[t1, t2])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        r = schedule.relations[0]
        assert r.predecessor_unique_id == 4217
        # 2 working days * 8h * 60min = 960 minutes
        assert r.lag_minutes == 960

    def test_unknown_task_id_in_predecessor_raises(self, tmp_path) -> None:
        """P7: predecessor referencing non-existent Task ID → corrupt."""
        t1 = FakeTask(unique_id=1, task_id=1, name="A", predecessors="99FS")
        project = FakeProject(tasks=[t1])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser, pytest.raises(CorruptScheduleError):
            _parse_with(parser, project)

    def test_empty_predecessor_is_ok(self, tmp_path) -> None:
        """P4: empty predecessor string yields no relations."""
        t1 = FakeTask(unique_id=1, task_id=1, name="A", predecessors="")
        project = FakeProject(tasks=[t1])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.relations == []

    def test_multiple_predecessors(self, tmp_path) -> None:
        t1 = FakeTask(unique_id=100, task_id=1, name="A")
        t2 = FakeTask(unique_id=200, task_id=2, name="B")
        t3 = FakeTask(
            unique_id=300, task_id=3, name="C", predecessors="1FS,2SS+1d"
        )
        project = FakeProject(tasks=[t1, t2, t3])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.relations) == 2


# ---------------------------------------------------------------------------
# Resources + calendars
# ---------------------------------------------------------------------------


class TestResourcesAndCalendars:
    def test_resources_parsed(self, tmp_path) -> None:
        r = FakeResource(unique_id=1, resource_id=1, name="Alice")
        project = FakeProject(
            tasks=[FakeTask(unique_id=1, task_id=1, name="T")],
            resources=[r],
        )
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.resources) == 1
        assert schedule.resources[0].unique_id == 1

    def test_assignments_parsed(self, tmp_path) -> None:
        a = FakeAssignment(resource_unique_id=1, task_unique_id=1, units=0.5, work=480)
        t = FakeTask(unique_id=1, task_id=1, name="T", assignments=[a])
        r = FakeResource(unique_id=1, resource_id=1, name="Alice")
        project = FakeProject(tasks=[t], resources=[r])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.assignments) == 1
        assert schedule.assignments[0].units == 0.5
        assert schedule.assignments[0].work_minutes == 480
        # resource_count derived from len(Task.Assignments)
        assert schedule.tasks[0].resource_count == 1

    def test_default_calendar_captured(self, tmp_path) -> None:
        project = make_minimal_project()
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.default_calendar_name == "Standard"
        assert len(schedule.calendars) >= 1
        assert schedule.calendars[0].hours_per_day == 8.0

    def test_nonstandard_calendar_factors(self, tmp_path) -> None:
        """A 10h day / 4d week project propagates into the calendar."""
        project = make_minimal_project()
        project.HoursPerDay = 10.0
        project.MinutesPerWeek = 4 * 10 * 60
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.calendars[0].hours_per_day == 10.0
        assert schedule.calendars[0].working_days_per_week == 4


# ---------------------------------------------------------------------------
# M1.1 — calendar hours-per-day propagation (Schedule + Task denormalized)
# ---------------------------------------------------------------------------


class TestCalendarHoursPerDayPropagation:
    def test_parser_populates_project_calendar_hours_per_day(self) -> None:
        """Project HoursPerDay=8.0 → Schedule.project_calendar_hours_per_day."""
        project = make_minimal_project()
        assert project.HoursPerDay == 8.0
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.project_calendar_hours_per_day == 8.0

    def test_parser_populates_project_calendar_hours_per_day_10h(self) -> None:
        """Project HoursPerDay=10.0 propagates to the Schedule field."""
        project = make_minimal_project()
        project.HoursPerDay = 10.0
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.project_calendar_hours_per_day == 10.0

    def test_parser_task_without_task_calendar_has_none(self) -> None:
        """A task with no task-specific calendar has calendar_hours_per_day=None."""
        project = make_minimal_project()
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert all(t.calendar_hours_per_day is None for t in schedule.tasks)

    def test_parser_task_with_task_calendar_populates_hours(self) -> None:
        """Task with a 24h/day elapsed-time calendar → 24.0."""
        elapsed = FakeCalendar(name="Elapsed", hours_per_day=24.0)
        standard = FakeCalendar(name="Standard", hours_per_day=8.0)
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="elapsed-task",
            calendar_name="Elapsed",
        )
        project = FakeProject(
            tasks=[t],
            calendars=[standard, elapsed],
        )
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].calendar_hours_per_day == 24.0

    def test_parser_task_calendar_com_object_resolves(self) -> None:
        """COM surface of Calendar is an object with a Name property."""
        elapsed = FakeCalendar(name="Elapsed", hours_per_day=24.0)
        standard = FakeCalendar(name="Standard", hours_per_day=8.0)
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="elapsed-task",
            calendar=elapsed,
        )
        project = FakeProject(
            tasks=[t],
            calendars=[standard, elapsed],
        )
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].calendar_hours_per_day == 24.0

    def test_parser_task_with_unresolvable_calendar_name_falls_back_to_none(
        self, caplog
    ) -> None:
        """Unresolvable task calendar name → None + warning log."""
        standard = FakeCalendar(name="Standard", hours_per_day=8.0)
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="orphan-calendar",
            calendar_name="NotInProject",
        )
        project = FakeProject(tasks=[t], calendars=[standard])
        app = FakeMSProjectApp(project)
        with caplog.at_level("WARNING", logger="app.parsers.com_parser"):
            with _parser_with(app) as parser:
                schedule = _parse_with(parser, project)
        assert schedule.tasks[0].calendar_hours_per_day is None
        assert any(
            "NotInProject" in rec.getMessage() for rec in caplog.records
        )


# ---------------------------------------------------------------------------
# P14 — cleanup on error (Quit called even if parse raises)
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_quit_called_on_successful_parse(self, tmp_path) -> None:
        app = FakeMSProjectApp(make_minimal_project())
        with _parser_with(app) as parser:
            _parse_with(parser, app._project)
        assert app.quit_called is True

    def test_quit_called_on_mpopen_failure(self, tmp_path) -> None:
        """P14: FileOpen failure must still Quit the app."""
        app = FakeMSProjectApp(
            file_open_should_raise=FileNotFoundError("missing"),
        )
        with _parser_with(app) as parser:
            with pytest.raises(MPOpenError):
                parser.parse("/does-not-exist.mpp")
        assert app.quit_called is True

    def test_quit_called_on_corrupt_parse(self, tmp_path) -> None:
        """P14: mid-parse failure must still Quit the app."""
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        bad = FakeTask(unique_id="bogus", task_id=1, name="T")  # type: ignore[arg-type]
        project = FakeProject(tasks=[bad])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            with pytest.raises(CorruptScheduleError):
                parser.parse(mpp)
        assert app.quit_called is True

    def test_co_uninitialize_called_after_close(self, tmp_path) -> None:
        """CoUninitialize must fire on close() even on failure."""
        counter = {"called": 0}

        def counting_uninit() -> None:
            counter["called"] += 1

        app = FakeMSProjectApp(make_minimal_project())
        parser = MPProjectParser(
            dispatch=_dispatch_factory(app),
            co_initialize=lambda: None,
            co_uninitialize=counting_uninit,
        )
        with parser:
            _parse_with(parser, app._project)
        assert counter["called"] == 1

    def test_close_is_idempotent(self, tmp_path) -> None:
        """Double-close must not raise."""
        app = FakeMSProjectApp(make_minimal_project())
        parser = MPProjectParser(
            dispatch=_dispatch_factory(app),
            co_initialize=lambda: None,
            co_uninitialize=lambda: None,
        )
        with parser:
            _parse_with(parser, app._project)
        parser.close()  # second close — no-op
        assert app.quit_called is True


# ---------------------------------------------------------------------------
# P15 — large schedule performance (indexed iteration)
# ---------------------------------------------------------------------------


class TestLargeSchedule:
    def test_ten_thousand_tasks_parses(self, tmp_path) -> None:
        """P15: parser iterates by index; 10k tasks parse under a
        reasonable ceiling (generous in mock — target is <5min on
        real COM for the same size; unmockable in CI).
        """
        tasks = [
            FakeTask(
                unique_id=i,
                task_id=i,
                name=f"T{i}",
                duration=480,
                remaining_duration=480,
            )
            for i in range(1, 10_001)
        ]
        project = FakeProject(tasks=tasks)
        app = FakeMSProjectApp(project)
        import time

        started = time.monotonic()
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        elapsed = time.monotonic() - started
        assert len(schedule.tasks) == 10_000
        # Mocked fixture is in-process; 30s is a loose upper bound.
        assert elapsed < 30.0

    def test_indexed_iteration_when_count_available(self, tmp_path) -> None:
        """Parser uses ``Count`` + ``Item(i)`` when available (real COM path)."""

        class IndexedTasks:
            def __init__(self, items: list[FakeTask]) -> None:
                self._items = items
                self.Count = len(items)

            def Item(self, i: int) -> FakeTask:
                return self._items[i - 1]

        tasks = [FakeTask(unique_id=i, task_id=i, name=f"T{i}") for i in (1, 2, 3)]
        project = FakeProject(tasks=tasks)
        project.Tasks = IndexedTasks(tasks)  # type: ignore[assignment]

        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert [t.unique_id for t in schedule.tasks] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Module-level convenience / top-level parse_mpp
# ---------------------------------------------------------------------------


class TestParseMppConvenience:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Linux-only COMUnavailableError path; Windows path tested separately",
    )
    def test_parse_mpp_on_linux_raises_comunavailable(self, tmp_path) -> None:
        """parse_mpp uses the default Dispatch which requires win32com.

        On Linux CI, win32com is unavailable → COMUnavailableError.
        """
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"stub")
        with pytest.raises(COMUnavailableError):
            parse_mpp(mpp)


# ---------------------------------------------------------------------------
# Silence unused-import warnings for references kept for future use.
# ---------------------------------------------------------------------------


_UNUSED = (ConstraintType, MagicMock)


# ---------------------------------------------------------------------------
# Extra coverage — rare branches that are safely testable on Linux
# ---------------------------------------------------------------------------


class TestRareBranches:
    def test_project_with_no_tasks_collection(self, tmp_path) -> None:
        """Defensive: project.Tasks is None → empty schedule."""
        project = FakeProject()
        project.Tasks = None  # type: ignore[assignment]
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks == []

    def test_project_with_no_calendars_synthesizes_default(self, tmp_path) -> None:
        """Defensive: project.Calendars is None → synthesized default."""
        project = make_minimal_project()
        project.Calendars = None  # type: ignore[assignment]
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.calendars) >= 1
        assert schedule.calendars[0].name == "Standard"

    def test_project_with_empty_calendars_synthesizes_default(self, tmp_path) -> None:
        """Defensive: project.Calendars is an empty iterable → default."""
        project = make_minimal_project()
        project.Calendars = []  # type: ignore[assignment]
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert len(schedule.calendars) >= 1

    def test_invalid_task_type_defaults_to_fixed_units(self, tmp_path) -> None:
        """A garbage Task.Type falls back to FIXED_UNITS (model default)."""
        t = FakeTask(unique_id=1, task_id=1, name="T")
        t.Type = "garbage"  # type: ignore[attr-defined]
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        # FIXED_UNITS is the MSP default; we do not crash on bad input.
        assert schedule.tasks[0].task_type.value == 0

    def test_task_with_no_assignments_collection(self, tmp_path) -> None:
        t = FakeTask(unique_id=1, task_id=1, name="T")
        t.Assignments = None  # type: ignore[attr-defined]
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.tasks[0].resource_count == 0

    def test_assignment_with_null_resource_uid_skipped(self, tmp_path) -> None:
        """Unassigned placeholders (ResourceUniqueID null) are skipped."""
        t = FakeTask(
            unique_id=1,
            task_id=1,
            name="T",
            assignments=[FakeAssignment(resource_unique_id=0, task_unique_id=1)],
        )
        project = FakeProject(tasks=[t])
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        # Assignment with resource_uid == 0 is treated as a placeholder
        # and does NOT land in schedule.assignments.
        assert schedule.assignments == []

    def test_resource_with_null_unique_id_skipped(self, tmp_path) -> None:
        r = FakeResource(unique_id=0, resource_id=1, name="ghost")
        r.UniqueID = None  # type: ignore[attr-defined]
        project = make_minimal_project()
        project.Resources = [r]  # type: ignore[assignment]
        app = FakeMSProjectApp(project)
        with _parser_with(app) as parser:
            schedule = _parse_with(parser, project)
        assert schedule.resources == []
