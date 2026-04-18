"""Tests for ``app.models.calendar``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.calendar import Calendar, CalendarException, WorkingTime


def _dt(year: int, month: int, day: int, hour: int = 8) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


class TestWorkingTime:
    def test_valid_window(self) -> None:
        w = WorkingTime(from_minute=8 * 60, to_minute=17 * 60)
        assert w.from_minute == 480
        assert w.to_minute == 1020

    def test_to_must_exceed_from(self) -> None:
        with pytest.raises(ValidationError):
            WorkingTime(from_minute=10 * 60, to_minute=10 * 60)

    def test_to_less_than_from_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkingTime(from_minute=15 * 60, to_minute=8 * 60)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkingTime(from_minute=-1, to_minute=60)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            WorkingTime(from_minute=0, to_minute=60, extra="x")  # type: ignore[call-arg]


class TestCalendarException:
    def test_construct_holiday(self) -> None:
        e = CalendarException(
            name="July 4",
            start=_dt(2026, 7, 4, 0),
            finish=_dt(2026, 7, 4, 23),
            is_working=False,
        )
        assert e.name == "July 4"
        assert e.is_working is False
        assert e.working_times == []

    def test_g1_naive_start_rejected(self) -> None:
        """G1: tz-naive datetime rejected."""
        with pytest.raises(ValidationError):
            CalendarException(
                name="Bad",
                start=datetime(2026, 7, 4, 0),  # naive
                finish=_dt(2026, 7, 4, 23),
            )

    def test_g1_naive_finish_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CalendarException(
                name="Bad",
                start=_dt(2026, 7, 4, 0),
                finish=datetime(2026, 7, 4, 23),  # naive
            )

    def test_finish_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CalendarException(
                start=_dt(2026, 7, 5, 0),
                finish=_dt(2026, 7, 4, 0),
            )

    def test_working_override_carries_times(self) -> None:
        e = CalendarException(
            name="Saturday make-up",
            start=_dt(2026, 7, 11, 0),
            finish=_dt(2026, 7, 11, 23),
            is_working=True,
            working_times=[WorkingTime(from_minute=8 * 60, to_minute=12 * 60)],
        )
        assert e.is_working
        assert len(e.working_times) == 1


class TestCalendar:
    def test_defaults(self) -> None:
        c = Calendar(name="Standard")
        assert c.hours_per_day == 8.0
        assert c.working_days_per_week == 5
        assert c.minutes_per_week == 2400
        assert c.exceptions == []

    def test_invalid_hours_per_day_zero(self) -> None:
        with pytest.raises(ValidationError):
            Calendar(name="X", hours_per_day=0)

    def test_invalid_hours_per_day_over_24(self) -> None:
        with pytest.raises(ValidationError):
            Calendar(name="X", hours_per_day=25)

    def test_invalid_working_days_per_week(self) -> None:
        with pytest.raises(ValidationError):
            Calendar(name="X", working_days_per_week=8)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Calendar(name="X", surprise=True)  # type: ignore[call-arg]

    def test_named_tz_accepted(self) -> None:
        """A non-UTC named timezone is still tz-aware and is accepted."""
        tz = timezone(timedelta(hours=-5), name="EST")
        e = CalendarException(
            start=datetime(2026, 7, 4, 0, tzinfo=tz),
            finish=datetime(2026, 7, 4, 23, tzinfo=tz),
        )
        assert e.start.tzinfo is not None
