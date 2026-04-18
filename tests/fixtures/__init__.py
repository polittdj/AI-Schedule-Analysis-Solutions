"""Synthetic COM-shaped fixture factories for the parser tests.

The Milestone 3 parser is tested without real ``.mpp`` files
(``cui-compliance-constraints §2e``) by constructing in-memory
objects that quack like the MS Project COM surface. This package
holds the factories that build those doubles.

No real schedule data lives here. Every fixture is hand-built from
synthetic numbers per
``cui-compliance-constraints §2e`` "Fixture-data quarantine."
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class _ComObject:
    """A bag of COM-style attributes.

    ``win32com.client.Dispatch`` returns objects that expose COM
    properties as Python attributes; this minimal stand-in
    accomplishes the same. Uses ``__slots__`` per attribute name is
    not feasible (we want arbitrary properties), so we use a plain
    ``__dict__``.
    """

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeTask(_ComObject):
    """Stand-in for an MS Project ``Task`` COM object.

    All COM properties referenced by the parser are exposed as
    attributes. Defaults mirror MS Project's defaults for a freshly-
    inserted task (FixedUnits, ASAP, no constraint date, not a
    summary, not a milestone, active).
    """

    def __init__(
        self,
        *,
        unique_id: int | None,
        task_id: int = 1,
        name: str | None = "Task",
        wbs: str = "1",
        outline_level: int = 1,
        start: datetime | None = None,
        finish: datetime | None = None,
        early_start: datetime | None = None,
        early_finish: datetime | None = None,
        late_start: datetime | None = None,
        late_finish: datetime | None = None,
        baseline_start: datetime | None = None,
        baseline_finish: datetime | None = None,
        actual_start: datetime | None = None,
        actual_finish: datetime | None = None,
        deadline: datetime | None = None,
        duration: int = 0,
        remaining_duration: int = 0,
        actual_duration: int = 0,
        baseline_duration: int = 0,
        total_slack: int = 0,
        free_slack: int = 0,
        constraint_type: int = 0,
        constraint_date: datetime | None = None,
        percent_complete: float = 0.0,
        task_type: int = 0,
        milestone: bool = False,
        summary: bool = False,
        critical: bool = False,
        active: bool = True,
        predecessors: str = "",
        assignments: list["FakeAssignment"] | None = None,
    ) -> None:
        super().__init__(
            UniqueID=unique_id,
            ID=task_id,
            Name=name,
            WBS=wbs,
            OutlineLevel=outline_level,
            Start=start,
            Finish=finish,
            EarlyStart=early_start,
            EarlyFinish=early_finish,
            LateStart=late_start,
            LateFinish=late_finish,
            BaselineStart=baseline_start,
            BaselineFinish=baseline_finish,
            ActualStart=actual_start,
            ActualFinish=actual_finish,
            Deadline=deadline,
            Duration=duration,
            RemainingDuration=remaining_duration,
            ActualDuration=actual_duration,
            BaselineDuration=baseline_duration,
            TotalSlack=total_slack,
            FreeSlack=free_slack,
            ConstraintType=constraint_type,
            ConstraintDate=constraint_date,
            PercentComplete=percent_complete,
            Type=task_type,
            Milestone=milestone,
            Summary=summary,
            Critical=critical,
            Active=active,
            Predecessors=predecessors,
            Assignments=assignments or [],
        )


class FakeAssignment(_ComObject):
    """Stand-in for an MS Project ``Assignment`` COM object."""

    def __init__(
        self,
        *,
        resource_unique_id: int,
        task_unique_id: int,
        units: float = 1.0,
        work: int = 0,
    ) -> None:
        super().__init__(
            ResourceUniqueID=resource_unique_id,
            TaskUniqueID=task_unique_id,
            Units=units,
            Work=work,
        )


class FakeResource(_ComObject):
    """Stand-in for an MS Project ``Resource`` COM object."""

    def __init__(
        self,
        *,
        unique_id: int,
        resource_id: int = 1,
        name: str = "Resource",
        resource_type: int = 0,
        initials: str = "",
        group: str = "",
        max_units: float = 1.0,
    ) -> None:
        super().__init__(
            UniqueID=unique_id,
            ID=resource_id,
            Name=name,
            Type=resource_type,
            Initials=initials,
            Group=group,
            MaxUnits=max_units,
        )


class FakeCalendar(_ComObject):
    """Stand-in for an MS Project ``Calendar`` COM object."""

    def __init__(
        self,
        *,
        name: str = "Standard",
    ) -> None:
        super().__init__(Name=name)


class FakeProject(_ComObject):
    """Stand-in for an MS Project ``Project`` COM object."""

    def __init__(
        self,
        *,
        name: str = "Synthetic",
        status_date: Any = None,
        project_start: datetime | None = None,
        project_finish: datetime | None = None,
        tasks: list[FakeTask] | None = None,
        resources: list[FakeResource] | None = None,
        calendars: list[FakeCalendar] | None = None,
        hours_per_day: float = 8.0,
        minutes_per_week: int = 5 * 8 * 60,
        default_calendar_name: str = "Standard",
    ) -> None:
        super().__init__(
            Name=name,
            StatusDate=status_date,
            ProjectStart=project_start,
            ProjectFinish=project_finish,
            Tasks=tasks or [],
            Resources=resources or [],
            Calendars=calendars
            or [FakeCalendar(name=default_calendar_name)],
            HoursPerDay=hours_per_day,
            MinutesPerWeek=minutes_per_week,
            DefaultCalendarName=default_calendar_name,
        )


class FakeMSProjectApp:
    """Stand-in for the ``MSProject.Application`` COM object.

    Records call order so tests can assert that ``Visible = False``
    and ``DisplayAlerts = False`` were set **before** ``FileOpen``
    (parser gotcha P-equiv-2 / skill §3.2 Gotcha 2).
    """

    def __init__(
        self,
        project: FakeProject | None = None,
        *,
        file_open_should_raise: BaseException | None = None,
    ) -> None:
        self._project = project or FakeProject()
        self._file_open_should_raise = file_open_should_raise
        self.call_log: list[str] = []
        self.Visible: bool = True
        self.DisplayAlerts: bool = True
        self.ActiveProject: FakeProject | None = None
        self._closed: bool = False
        self._quit: bool = False

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("Visible", "DisplayAlerts"):
            # Track the order of these two writes via the call log.
            super().__setattr__(name, value)
            log = self.__dict__.setdefault("call_log", [])
            log.append(f"set:{name}={value}")
            return
        super().__setattr__(name, value)

    def FileOpen(self, path: str, ReadOnly: bool = False) -> None:
        self.call_log.append(f"FileOpen:{path}:ReadOnly={ReadOnly}")
        if self._file_open_should_raise is not None:
            raise self._file_open_should_raise
        self.ActiveProject = self._project

    def FileClose(self, Save: int = 0) -> None:
        self.call_log.append(f"FileClose:Save={Save}")
        self._closed = True

    def Quit(self) -> None:
        self.call_log.append("Quit")
        self._quit = True

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def quit_called(self) -> bool:
        return self._quit


def make_minimal_project(
    *,
    status_date: datetime | None = None,
) -> FakeProject:
    """Build a 2-task synthetic project covering the happy path."""
    t1 = FakeTask(
        unique_id=10,
        task_id=1,
        name="Start",
        start=datetime(2025, 1, 1, 8, 0, 0),
        finish=datetime(2025, 1, 8, 17, 0, 0),
        duration=2400,
        remaining_duration=0,
        actual_duration=2400,
        percent_complete=100.0,
    )
    t2 = FakeTask(
        unique_id=20,
        task_id=2,
        name="Next",
        start=datetime(2025, 1, 9, 8, 0, 0),
        finish=datetime(2025, 1, 16, 17, 0, 0),
        duration=2400,
        remaining_duration=2400,
        predecessors="1",
    )
    return FakeProject(
        name="Synthetic",
        status_date=status_date,
        project_start=datetime(2025, 1, 1, 8, 0, 0),
        project_finish=datetime(2025, 1, 16, 17, 0, 0),
        tasks=[t1, t2],
    )


__all__ = [
    "FakeAssignment",
    "FakeCalendar",
    "FakeMSProjectApp",
    "FakeProject",
    "FakeResource",
    "FakeTask",
    "make_minimal_project",
]
