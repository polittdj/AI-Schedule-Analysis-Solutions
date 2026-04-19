"""Tests for duration conversion helpers (mpp-parsing §3.5)."""

from __future__ import annotations

import pytest

from app.engine.duration import minutes_to_working_days, working_days_to_minutes


def test_default_8h_conversion() -> None:
    assert minutes_to_working_days(2400) == 5.0
    assert working_days_to_minutes(5) == 2400


def test_none_returns_zero() -> None:
    assert minutes_to_working_days(None) == 0.0


def test_custom_hours_per_day() -> None:
    # 6-hour workday → 1 working day = 360 minutes.
    assert minutes_to_working_days(720, hours_per_day=6.0) == 2.0
    assert working_days_to_minutes(2, hours_per_day=6.0) == 720


def test_fractional_days() -> None:
    # 0.5 working day at 8h = 240 min.
    assert working_days_to_minutes(0.5) == 240
    assert minutes_to_working_days(240) == 0.5


def test_zero_hours_per_day_rejected() -> None:
    with pytest.raises(ValueError):
        minutes_to_working_days(480, hours_per_day=0)
    with pytest.raises(ValueError):
        working_days_to_minutes(1, hours_per_day=0)


def test_negative_hours_per_day_rejected() -> None:
    with pytest.raises(ValueError):
        minutes_to_working_days(480, hours_per_day=-1)
    with pytest.raises(ValueError):
        working_days_to_minutes(1, hours_per_day=-1)


def test_round_trip() -> None:
    for d in (1, 2, 5, 10, 20):
        assert minutes_to_working_days(working_days_to_minutes(d)) == d
