"""Tests for working-calendar arithmetic.

Covers BUILD-PLAN §5 M4 E12 (weekend skipping) and E13 (calendar
exception skipping), plus sub-day arithmetic invariants needed by the
forward/backward pass.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.calendar_math import (
    add_working_minutes,
    is_working_minute,
    snap_backward,
    snap_forward,
    subtract_working_minutes,
    working_minutes_between,
    working_windows_for_date,
)
from app.models.calendar import Calendar, CalendarException, WorkingTime


@pytest.fixture
def standard_cal() -> Calendar:
    """Default 5-day Mon-Fri, 8h/day calendar."""
    return Calendar(name="Standard")


@pytest.fixture
def seven_day_cal() -> Calendar:
    return Calendar(name="24x7", working_days_per_week=7)


@pytest.fixture
def holiday_cal() -> Calendar:
    """Calendar with 2026-12-25 (a Friday) as a non-working holiday."""
    return Calendar(
        name="Holiday",
        exceptions=[
            CalendarException(
                name="Christmas",
                start=datetime(2026, 12, 25, tzinfo=UTC),
                finish=datetime(2026, 12, 25, tzinfo=UTC),
                is_working=False,
            )
        ],
    )


@pytest.fixture
def saturday_working_cal() -> Calendar:
    """Calendar with 2026-04-25 (Saturday) overridden to working."""
    return Calendar(
        name="SatWork",
        exceptions=[
            CalendarException(
                name="Special Saturday",
                start=datetime(2026, 4, 25, tzinfo=UTC),
                finish=datetime(2026, 4, 25, tzinfo=UTC),
                is_working=True,
                working_times=[WorkingTime(from_minute=540, to_minute=900)],
            )
        ],
    )


def _dt(y: int, m: int, d: int, h: int = 8, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def test_weekday_windows_are_08_16(standard_cal: Calendar) -> None:
    # 2026-04-20 is a Monday.
    windows = working_windows_for_date(_dt(2026, 4, 20).date(), standard_cal)
    assert windows == [(8 * 60, 16 * 60)]


def test_weekend_has_no_windows(standard_cal: Calendar) -> None:
    # 2026-04-25 is a Saturday.
    assert working_windows_for_date(_dt(2026, 4, 25).date(), standard_cal) == []
    # 2026-04-26 is a Sunday.
    assert working_windows_for_date(_dt(2026, 4, 26).date(), standard_cal) == []


def test_seven_day_week_has_weekend_windows(seven_day_cal: Calendar) -> None:
    assert working_windows_for_date(_dt(2026, 4, 25).date(), seven_day_cal) != []


def test_holiday_exception_is_nonworking(holiday_cal: Calendar) -> None:
    assert working_windows_for_date(_dt(2026, 12, 25).date(), holiday_cal) == []


def test_saturday_working_override_uses_working_times(
    saturday_working_cal: Calendar,
) -> None:
    windows = working_windows_for_date(
        _dt(2026, 4, 25).date(), saturday_working_cal
    )
    assert windows == [(540, 900)]


def test_is_working_minute_true_mid_window(standard_cal: Calendar) -> None:
    assert is_working_minute(_dt(2026, 4, 20, 10, 0), standard_cal)


def test_is_working_minute_false_end_of_window(standard_cal: Calendar) -> None:
    # Half-open: 16:00 is NOT a working minute.
    assert not is_working_minute(_dt(2026, 4, 20, 16, 0), standard_cal)


def test_is_working_minute_false_on_weekend(standard_cal: Calendar) -> None:
    assert not is_working_minute(_dt(2026, 4, 25, 10, 0), standard_cal)


def test_is_working_minute_rejects_naive() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        is_working_minute(datetime(2026, 4, 20, 10, 0), Calendar(name="X"))


def test_snap_forward_inside_window(standard_cal: Calendar) -> None:
    assert snap_forward(_dt(2026, 4, 20, 10, 0), standard_cal) == _dt(
        2026, 4, 20, 10, 0
    )


def test_snap_forward_before_window(standard_cal: Calendar) -> None:
    # 06:00 → 08:00 same day.
    assert snap_forward(_dt(2026, 4, 20, 6, 0), standard_cal) == _dt(
        2026, 4, 20, 8, 0
    )


def test_snap_forward_friday_afternoon_to_monday(standard_cal: Calendar) -> None:
    # Friday 17:00 → Monday 08:00.
    out = snap_forward(_dt(2026, 4, 24, 17, 0), standard_cal)
    assert out == _dt(2026, 4, 27, 8, 0)


def test_snap_backward_after_window(standard_cal: Calendar) -> None:
    # Friday 20:00 → Friday 16:00.
    out = snap_backward(_dt(2026, 4, 24, 20, 0), standard_cal)
    assert out == _dt(2026, 4, 24, 16, 0)


def test_snap_backward_sunday_to_friday(standard_cal: Calendar) -> None:
    # Sunday 06:00 → Friday 16:00.
    out = snap_backward(_dt(2026, 4, 26, 6, 0), standard_cal)
    assert out == _dt(2026, 4, 24, 16, 0)


def test_snap_backward_inside_window_returns_same(
    standard_cal: Calendar,
) -> None:
    out = snap_backward(_dt(2026, 4, 20, 10, 30), standard_cal)
    assert out == _dt(2026, 4, 20, 10, 30)


def test_add_working_minutes_zero_same_day(standard_cal: Calendar) -> None:
    # Inside window: zero stays put.
    out = add_working_minutes(_dt(2026, 4, 20, 10, 0), 0, standard_cal)
    assert out == _dt(2026, 4, 20, 10, 0)


def test_add_working_minutes_within_day(standard_cal: Calendar) -> None:
    out = add_working_minutes(_dt(2026, 4, 20, 8, 0), 240, standard_cal)
    assert out == _dt(2026, 4, 20, 12, 0)


def test_add_working_minutes_e12_friday_plus_day_is_monday(
    standard_cal: Calendar,
) -> None:
    """E12: 1 working day starting Friday 08:00 → Monday 08:00."""
    out = add_working_minutes(_dt(2026, 4, 24, 8, 0), 480, standard_cal)
    assert out == _dt(2026, 4, 27, 8, 0)


def test_add_working_minutes_multi_day(standard_cal: Calendar) -> None:
    # Tuesday 08:00 + 3 working days (1440 min) = Friday 08:00.
    out = add_working_minutes(_dt(2026, 4, 21, 8, 0), 3 * 480, standard_cal)
    assert out == _dt(2026, 4, 24, 8, 0)


def test_add_working_minutes_e13_skips_holiday(holiday_cal: Calendar) -> None:
    """E13: duration skips a calendar exception (Christmas Friday)."""
    # Thursday 2026-12-24 08:00 + 1 working day. Holiday = Fri 12/25.
    # So 480 min work = all Thursday. Add 0 remaining → snap to next
    # working window = Mon 12/28 08:00.
    out = add_working_minutes(_dt(2026, 12, 24, 8, 0), 480, holiday_cal)
    assert out == _dt(2026, 12, 28, 8, 0)


def test_add_working_minutes_partial_then_next_day(
    standard_cal: Calendar,
) -> None:
    # Friday 14:00 + 180 min → 120 min finish Fri 16:00, 60 more on Mon.
    out = add_working_minutes(_dt(2026, 4, 24, 14, 0), 180, standard_cal)
    assert out == _dt(2026, 4, 27, 9, 0)


def test_add_working_minutes_negative_delegates(standard_cal: Calendar) -> None:
    out = add_working_minutes(_dt(2026, 4, 20, 12, 0), -120, standard_cal)
    assert out == _dt(2026, 4, 20, 10, 0)


def test_add_working_minutes_starting_on_weekend(standard_cal: Calendar) -> None:
    # Saturday + 1 min of work = Mon 08:01.
    out = add_working_minutes(_dt(2026, 4, 25, 12, 0), 1, standard_cal)
    assert out == _dt(2026, 4, 27, 8, 1)


def test_subtract_working_minutes_within_day(standard_cal: Calendar) -> None:
    out = subtract_working_minutes(_dt(2026, 4, 20, 12, 0), 120, standard_cal)
    assert out == _dt(2026, 4, 20, 10, 0)


def test_subtract_working_minutes_zero_from_start_of_day(
    standard_cal: Calendar,
) -> None:
    # Zero minutes from Mon 08:00 → stays at Mon 08:00 (Mon 08:00 is a
    # working minute under the half-open convention; no boundary roll).
    out = subtract_working_minutes(_dt(2026, 4, 20, 8, 0), 0, standard_cal)
    assert out == _dt(2026, 4, 20, 8, 0)


def test_subtract_working_minutes_one_full_day(standard_cal: Calendar) -> None:
    # Tue 08:00 - 1 working day = Mon 08:00.
    out = subtract_working_minutes(_dt(2026, 4, 21, 8, 0), 480, standard_cal)
    assert out == _dt(2026, 4, 20, 8, 0)


def test_subtract_working_minutes_across_weekend(
    standard_cal: Calendar,
) -> None:
    # Mon 10:00 - 1 working day (480 min) = Fri 10:00.
    out = subtract_working_minutes(_dt(2026, 4, 27, 10, 0), 480, standard_cal)
    assert out == _dt(2026, 4, 24, 10, 0)


def test_subtract_working_minutes_partial_multi_day(
    standard_cal: Calendar,
) -> None:
    # Mon 10:00 - 180 min: 120 min to Mon 08:00, 60 min back into Fri
    # 16:00 → Fri 15:00.
    out = subtract_working_minutes(_dt(2026, 4, 27, 10, 0), 180, standard_cal)
    assert out == _dt(2026, 4, 24, 15, 0)


def test_subtract_working_minutes_negative_delegates(
    standard_cal: Calendar,
) -> None:
    out = subtract_working_minutes(_dt(2026, 4, 20, 10, 0), -120, standard_cal)
    assert out == _dt(2026, 4, 20, 12, 0)


def test_subtract_working_minutes_rejects_naive(standard_cal: Calendar) -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        subtract_working_minutes(datetime(2026, 4, 20, 10, 0), 0, standard_cal)


def test_add_working_minutes_rejects_naive(standard_cal: Calendar) -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        add_working_minutes(datetime(2026, 4, 20, 10, 0), 10, standard_cal)


def test_snap_forward_rejects_naive(standard_cal: Calendar) -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        snap_forward(datetime(2026, 4, 20, 10, 0), standard_cal)


def test_snap_backward_rejects_naive(standard_cal: Calendar) -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        snap_backward(datetime(2026, 4, 20, 10, 0), standard_cal)


def test_working_minutes_between_same_day(standard_cal: Calendar) -> None:
    out = working_minutes_between(
        _dt(2026, 4, 20, 8, 0), _dt(2026, 4, 20, 12, 0), standard_cal
    )
    assert out == 240


def test_working_minutes_between_across_weekend(standard_cal: Calendar) -> None:
    # Fri 08:00 to Mon 08:00 = 1 working day = 480 min.
    out = working_minutes_between(
        _dt(2026, 4, 24, 8, 0), _dt(2026, 4, 27, 8, 0), standard_cal
    )
    assert out == 480


def test_working_minutes_between_negative(standard_cal: Calendar) -> None:
    out = working_minutes_between(
        _dt(2026, 4, 20, 12, 0), _dt(2026, 4, 20, 8, 0), standard_cal
    )
    assert out == -240


def test_working_minutes_between_equal(standard_cal: Calendar) -> None:
    out = working_minutes_between(
        _dt(2026, 4, 20, 8, 0), _dt(2026, 4, 20, 8, 0), standard_cal
    )
    assert out == 0


def test_working_minutes_between_rejects_naive(standard_cal: Calendar) -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        working_minutes_between(
            datetime(2026, 4, 20, 8), _dt(2026, 4, 20, 9), standard_cal
        )


def test_working_exception_empty_times_uses_default_window() -> None:
    """Exception with is_working=True and empty working_times uses
    the calendar's default 08:00 + hours_per_day window."""
    cal = Calendar(
        name="WE",
        exceptions=[
            CalendarException(
                name="Special Sat",
                start=datetime(2026, 4, 25, tzinfo=UTC),
                finish=datetime(2026, 4, 25, tzinfo=UTC),
                is_working=True,
                working_times=[],
            )
        ],
    )
    windows = working_windows_for_date(datetime(2026, 4, 25).date(), cal)
    assert windows == [(8 * 60, 16 * 60)]


def test_snap_backward_before_window_on_current_day_falls_through() -> None:
    """Line 218 — snap_backward when m < w_start on current date."""
    cal = Calendar(name="Std")
    # Tue 06:00 — before Tue's window. Should snap back to Mon 16:00.
    out = snap_backward(_dt(2026, 4, 21, 6, 0), cal)
    assert out == _dt(2026, 4, 20, 16, 0)


def test_subtract_working_minutes_current_day_before_window_falls_through() -> None:
    """Line 281 — subtract where m < w_start on current date."""
    cal = Calendar(name="Std")
    # Tue 06:00 (pre-window) - 60 min → Mon 15:00.
    out = subtract_working_minutes(_dt(2026, 4, 21, 6, 0), 60, cal)
    assert out == _dt(2026, 4, 20, 15, 0)


def test_add_working_minutes_past_window_end_skips_to_next_day() -> None:
    """Line 249 — add where m >= w_end on current date."""
    cal = Calendar(name="Std")
    # Mon 18:00 + 60 min → Tue 09:00.
    out = add_working_minutes(_dt(2026, 4, 20, 18, 0), 60, cal)
    assert out == _dt(2026, 4, 21, 9, 0)


def test_working_minutes_between_start_after_window_end() -> None:
    """Line 314-315 — a starts after the first window end."""
    cal = Calendar(name="Std")
    # a = Mon 17:00 (past window end); b = Tue 10:00.
    # Mon contributes 0 (past end), Tue contributes 120 min.
    out = working_minutes_between(
        _dt(2026, 4, 20, 17, 0), _dt(2026, 4, 21, 10, 0), cal
    )
    assert out == 120


def test_saturday_working_override_counts(saturday_working_cal: Calendar) -> None:
    # Saturday override 09:00-15:00. 09:30 is working.
    assert is_working_minute(
        _dt(2026, 4, 25, 9, 30), saturday_working_cal
    )
    assert not is_working_minute(
        _dt(2026, 4, 25, 16, 0), saturday_working_cal
    )
