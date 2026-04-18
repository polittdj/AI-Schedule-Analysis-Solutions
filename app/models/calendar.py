"""Calendar model.

Maps to MS Project's ``Calendar`` COM object and its
``WeekDays`` / ``Exceptions`` collections. The CPM engine
(Milestone 4) reads ``hours_per_day`` to convert duration minutes to
working days per ``mpp-parsing-com-automation §3.5`` (Gotcha 5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models._validators import require_tz_aware


class WorkingTime(BaseModel):
    """A single working window inside a weekday or exception day.

    Maps to one ``Calendar.WeekDays(...).WorkingTimes(i)`` record. The
    pair represents a contiguous interval of working time expressed in
    minutes-since-midnight. The CPM engine (Milestone 4) treats the
    union of all ``WorkingTime`` intervals on a given calendar day as
    that day's working capacity.
    """

    model_config = ConfigDict(extra="forbid")

    from_minute: Annotated[int, Field(ge=0, le=24 * 60)]
    """Start of the working window in minutes from midnight (0..1440).

    COM property: ``WorkingTime.From`` (a ``Date`` whose date part is
    arbitrary; only the time part is meaningful).
    """

    to_minute: Annotated[int, Field(ge=0, le=24 * 60)]
    """End of the working window in minutes from midnight (0..1440).

    COM property: ``WorkingTime.To``. Must be strictly greater than
    ``from_minute``.
    """

    @field_validator("to_minute")
    @classmethod
    def _to_after_from(cls, v: int, info) -> int:
        from_minute = info.data.get("from_minute")
        if from_minute is not None and v <= from_minute:
            raise ValueError("to_minute must be strictly greater than from_minute")
        return v


class CalendarException(BaseModel):
    """A non-default working/non-working override on a specific date.

    Maps to ``Calendar.Exceptions(i)``. Used to represent holidays,
    weekend overrides, blackout periods, and contractor stand-down
    days. The interval is a closed date range (``start`` and ``finish``
    inclusive) per the COM ``Exception.Start`` / ``Exception.Finish``
    properties.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    """COM property: ``Exception.Name``. Free-text label
    (e.g. ``"US Federal Holidays"``)."""

    start: datetime
    """Inclusive start of the exception window.

    COM property: ``Exception.Start``. tz-aware (G1).
    """

    finish: datetime
    """Inclusive end of the exception window.

    COM property: ``Exception.Finish``. tz-aware (G1).
    """

    is_working: bool = False
    """``True`` if the exception declares working time on what would
    otherwise be a non-working day; ``False`` for the more common
    non-working override (holiday).

    COM derivation: presence of ``WorkingTimes`` on the exception in
    MS Project's COM model.
    """

    working_times: list[WorkingTime] = Field(default_factory=list)
    """Working windows when ``is_working=True``. Empty otherwise.

    COM derivation: ``Exception.Shift1Start/Shift1Finish`` etc.,
    flattened to a uniform ``WorkingTime`` list.
    """

    @field_validator("start", "finish")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        return require_tz_aware(v)  # type: ignore[return-value]

    @field_validator("finish")
    @classmethod
    def _finish_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start")
        if start is not None and v < start:
            raise ValueError("finish must be on or after start")
        return v


class Calendar(BaseModel):
    """A named project calendar.

    Maps to MS Project's ``Calendar`` COM object. The ``hours_per_day``
    figure is the conversion factor used by the CPM engine and the
    DCMA metric layer to translate duration minutes (Gotcha 5,
    ``mpp-parsing-com-automation §3.5``) into the working-day units the
    presentation layer renders.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    """COM property: ``Calendar.Name``. The project default calendar
    is conventionally named ``"Standard"``."""

    hours_per_day: Annotated[float, Field(gt=0, le=24)] = 8.0
    """Working hours per day used to convert minutes → working days.

    COM derivation: project-level ``Options.HoursPerDay`` (the
    project-default conversion factor); per-calendar overrides are
    supported via per-day ``WorkingTime`` totals if needed downstream.
    """

    working_days_per_week: Annotated[int, Field(ge=1, le=7)] = 5
    """Working days per week. Project default is 5 (Mon–Fri).

    COM derivation: count of ``WeekDays`` whose ``Working == True``.
    """

    minutes_per_week: Annotated[int, Field(ge=0)] = 5 * 8 * 60
    """Working minutes per week. Used by some downstream slip
    conversions; defaults to ``working_days_per_week * hours_per_day *
    60``.

    COM derivation: project-level ``Options.MinutesPerWeek``.
    """

    exceptions: list[CalendarException] = Field(default_factory=list)
    """Calendar exceptions (holidays, blackouts, working overrides)."""
