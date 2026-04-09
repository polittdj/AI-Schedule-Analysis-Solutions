"""Work-calendar extraction helpers.

The forensic engine needs to convert working-day durations into calendar
days (for example, to compute slippage in real-world days between a
baseline finish and a current finish). That conversion depends on the
project's work calendar: which weekdays are working days, how many hours
per day, and what non-working exceptions (holidays) apply.

This module pulls that information out of an MPXJ `ProjectCalendar` and
exposes it as a plain Python `CalendarInfo` model that can be used
without a JVM attached.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Standard Microsoft Project day ordering (Sunday=1 through Saturday=7).
_DAY_NAMES = [
    "SUNDAY",
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
]


class CalendarException(BaseModel):
    """A non-working date range (holiday, shutdown, ...)."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None


class CalendarInfo(BaseModel):
    """A simplified, JVM-free snapshot of a project calendar."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    working_days: List[str] = Field(default_factory=list)  # e.g. ["MONDAY", ...]
    hours_per_day: float = 8.0
    exceptions: List[CalendarException] = Field(default_factory=list)


def _hours_for_day(jcal: Any, day_name: str) -> float:
    """Sum the working hours for a single day-of-week."""
    try:
        import jpype  # local import; tests don't need jpype loaded
    except ImportError:
        return 0.0
    try:
        DayOfWeek = jpype.JClass("java.time.DayOfWeek")
        jday = getattr(DayOfWeek, day_name)
        hours = jcal.getCalendarHours(jday)
    except Exception:
        return 0.0
    if hours is None:
        return 0.0
    total_minutes = 0
    try:
        for rng in hours:
            start = rng.getStart()
            end = rng.getEnd()
            if start is None or end is None:
                continue
            # LocalTime.toSecondOfDay() is the safest conversion.
            try:
                secs = int(end.toSecondOfDay()) - int(start.toSecondOfDay())
            except Exception:
                # Fall back to millisecond diff if it's a legacy Date range.
                secs = (int(end.getTime()) - int(start.getTime())) // 1000
            total_minutes += max(0, secs) // 60
    except Exception:
        return 0.0
    return round(total_minutes / 60.0, 4)


def _is_working_day(jcal: Any, day_name: str) -> bool:
    try:
        import jpype
        DayOfWeek = jpype.JClass("java.time.DayOfWeek")
        jday = getattr(DayOfWeek, day_name)
        return bool(jcal.isWorkingDay(jday))
    except Exception:
        return False


def extract_calendar_info(jcal: Any) -> CalendarInfo:
    """Return a `CalendarInfo` built from an MPXJ `ProjectCalendar`.

    Passing None returns an empty default calendar (Mon–Fri, 8h/day).
    """
    if jcal is None:
        return CalendarInfo(
            name=None,
            working_days=["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
            hours_per_day=8.0,
            exceptions=[],
        )

    name = None
    try:
        n = jcal.getName()
        name = str(n) if n is not None else None
    except Exception:
        name = None

    working_days: List[str] = []
    hours_samples: List[float] = []
    # Skip SUNDAY / SATURDAY from the standard sum sample — most projects
    # rely on a Mon–Fri base and we want the average of actual working days.
    for day in _DAY_NAMES:
        if _is_working_day(jcal, day):
            working_days.append(day)
            h = _hours_for_day(jcal, day)
            if h > 0:
                hours_samples.append(h)

    hours_per_day = (
        round(sum(hours_samples) / len(hours_samples), 4) if hours_samples else 8.0
    )

    exceptions: List[CalendarException] = []
    try:
        jexceptions = jcal.getCalendarExceptions()
    except Exception:
        jexceptions = None
    if jexceptions is not None:
        for exc in jexceptions:
            try:
                ex_name = exc.getName()
                from_d = exc.getFromDate()
                to_d = exc.getToDate()
            except Exception:
                continue
            exceptions.append(
                CalendarException(
                    name=str(ex_name) if ex_name is not None else None,
                    from_date=_to_py_datetime(from_d),
                    to_date=_to_py_datetime(to_d),
                )
            )

    return CalendarInfo(
        name=name,
        working_days=working_days,
        hours_per_day=hours_per_day,
        exceptions=exceptions,
    )


def _to_py_datetime(jdt: Any) -> Optional[datetime]:
    if jdt is None:
        return None
    try:
        if hasattr(jdt, "getTime") and not hasattr(jdt, "getYear"):
            ms = int(jdt.getTime())
            return datetime.fromtimestamp(ms / 1000.0)
    except Exception:
        pass
    try:
        s = str(jdt)
        if "T" in s and s.count(":") == 1:
            s = s + ":00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def working_days_between(
    start: datetime,
    end: datetime,
    calendar: CalendarInfo,
) -> int:
    """Count working days between two datetimes using a `CalendarInfo`.

    Pure Python — does not need the JVM. Used by the forensic engine to
    compute slippage in calendar-working-day units.
    """
    if start is None or end is None or end < start:
        return 0
    working_set = {d.upper() for d in calendar.working_days} or {
        "MONDAY",
        "TUESDAY",
        "WEDNESDAY",
        "THURSDAY",
        "FRIDAY",
    }
    # Python weekday(): Monday=0 ... Sunday=6
    py_to_name = {
        0: "MONDAY",
        1: "TUESDAY",
        2: "WEDNESDAY",
        3: "THURSDAY",
        4: "FRIDAY",
        5: "SATURDAY",
        6: "SUNDAY",
    }
    excluded: set[date] = set()
    for exc in calendar.exceptions:
        if exc.from_date is None:
            continue
        cur = exc.from_date.date()
        stop = (exc.to_date or exc.from_date).date()
        while cur <= stop:
            excluded.add(cur)
            cur += timedelta(days=1)

    count = 0
    cur = start.date()
    stop = end.date()
    while cur <= stop:
        if py_to_name[cur.weekday()] in working_set and cur not in excluded:
            count += 1
        cur += timedelta(days=1)
    return count
