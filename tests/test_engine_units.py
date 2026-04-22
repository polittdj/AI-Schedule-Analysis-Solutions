"""Unit tests for :mod:`app.engine.units`.

Block 7 audit trail: the conversion helper is the sole minute→day
path for driving-path public contracts (BUILD-PLAN §2.18). 100%
coverage is a hard gate.
"""

from __future__ import annotations

import pytest

from app.engine.units import minutes_to_days


class TestMinutesToDays:
    def test_eight_hour_day_480_minutes_is_one_day(self) -> None:
        assert minutes_to_days(480.0, 8.0) == 1.0

    def test_ten_hour_day_600_minutes_is_one_day(self) -> None:
        assert minutes_to_days(600.0, 10.0) == 1.0

    def test_twenty_four_hour_day_1440_minutes_is_one_day(self) -> None:
        assert minutes_to_days(1440.0, 24.0) == 1.0

    def test_fractional_half_day_on_8h_calendar(self) -> None:
        assert minutes_to_days(240.0, 8.0) == 0.5

    def test_negative_minutes_returns_negative_days(self) -> None:
        # Leads on relationships produce negative slack / lag values
        # per driving-slack-and-paths §3. The helper must not clamp.
        assert minutes_to_days(-240.0, 8.0) == -0.5

    def test_zero_minutes_returns_zero_days(self) -> None:
        assert minutes_to_days(0.0, 8.0) == 0.0

    def test_zero_hours_per_day_raises(self) -> None:
        with pytest.raises(ValueError, match="hours_per_day must be strictly positive"):
            minutes_to_days(480.0, 0.0)

    def test_negative_hours_per_day_raises(self) -> None:
        with pytest.raises(ValueError, match="hours_per_day must be strictly positive"):
            minutes_to_days(480.0, -8.0)

    def test_error_message_mentions_audit_trail(self) -> None:
        with pytest.raises(ValueError, match="audit trail"):
            minutes_to_days(480.0, 0.0)
