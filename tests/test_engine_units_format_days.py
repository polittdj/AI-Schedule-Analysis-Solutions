"""Unit tests for :func:`app.engine.units.format_days`.

The helper is the sole formatting point for user-visible durations
per BUILD-PLAN §2.19 (AM9, 4/23/2026). Authority: NASA Schedule
Management Handbook §5.5.9.1 and Papicito's forensic-tool standard
dated 4/23/2026. Format contract:

- 2-decimal precision maximum.
- Positive values round by ceiling to the next 0.01; negative values
  round by floor to the next -0.01; exactly 0.0 is preserved.
- Trailing zeros and orphan decimal points stripped.
- Leading zero omitted on fractional absolute values.
- Singular " day" only for rounded == +1.0 or -1.0.
"""

from __future__ import annotations

from app.engine.units import format_days


class TestFormatDaysZero:
    def test_exact_zero_returns_zero_days_plural(self) -> None:
        assert format_days(0.0) == "0 days"


class TestFormatDaysExactIntegers:
    def test_one_day_singular(self) -> None:
        assert format_days(1.0) == "1 day"

    def test_negative_one_day_singular(self) -> None:
        assert format_days(-1.0) == "-1 day"

    def test_two_days_plural(self) -> None:
        assert format_days(2.0) == "2 days"

    def test_negative_two_days_plural(self) -> None:
        assert format_days(-2.0) == "-2 days"

    def test_three_days_plural(self) -> None:
        assert format_days(3.0) == "3 days"

    def test_one_hundred_days_plural(self) -> None:
        assert format_days(100.0) == "100 days"

    def test_three_hundred_sixty_five_days_plural(self) -> None:
        assert format_days(365.0) == "365 days"


class TestFormatDaysHalfDay:
    def test_positive_half_day_leading_zero_omitted(self) -> None:
        assert format_days(0.5) == ".5 days"

    def test_negative_half_day_leading_zero_omitted(self) -> None:
        assert format_days(-0.5) == "-.5 days"

    def test_positive_one_and_a_half_days(self) -> None:
        assert format_days(1.5) == "1.5 days"

    def test_negative_one_and_a_half_days(self) -> None:
        assert format_days(-1.5) == "-1.5 days"


class TestFormatDaysTwoDecimals:
    def test_two_decimals_positive(self) -> None:
        assert format_days(2.25) == "2.25 days"

    def test_two_decimals_negative(self) -> None:
        assert format_days(-2.25) == "-2.25 days"

    def test_quarter_day_positive_leading_zero_omitted(self) -> None:
        assert format_days(0.25) == ".25 days"

    def test_quarter_day_negative_leading_zero_omitted(self) -> None:
        assert format_days(-0.25) == "-.25 days"


class TestFormatDaysTrailingZeroStrip:
    def test_one_trailing_zero_stripped(self) -> None:
        # 2.10 → "2.10" → ".10" strip → "2.1"
        assert format_days(2.10) == "2.1 days"

    def test_both_trailing_zeros_and_decimal_point_stripped(self) -> None:
        # 2.00 → "2.00" → strip "00" → strip "." → "2"
        assert format_days(2.00) == "2 days"


class TestFormatDaysSubPrecisionPositive:
    def test_zero_point_zero_zero_three_ceilings_up_to_one_cent(self) -> None:
        assert format_days(0.003) == ".01 days"

    def test_zero_point_zero_zero_one_ceilings_up_to_one_cent(self) -> None:
        assert format_days(0.001) == ".01 days"

    def test_zero_point_zero_zero_zero_one_ceilings_up_to_one_cent(self) -> None:
        assert format_days(0.0001) == ".01 days"


class TestFormatDaysSubPrecisionNegative:
    def test_negative_zero_point_zero_zero_three_floors_to_negative_cent(self) -> None:
        assert format_days(-0.003) == "-.01 days"

    def test_negative_zero_point_zero_zero_one_floors_to_negative_cent(self) -> None:
        assert format_days(-0.001) == "-.01 days"


class TestFormatDaysLarge:
    def test_one_thousand_days_plural(self) -> None:
        assert format_days(1000.0) == "1000 days"

    def test_ten_thousand_point_five_days(self) -> None:
        assert format_days(10000.5) == "10000.5 days"


class TestFormatDaysPrecisionFloor:
    def test_exact_positive_precision_floor(self) -> None:
        assert format_days(0.01) == ".01 days"

    def test_exact_negative_precision_floor(self) -> None:
        assert format_days(-0.01) == "-.01 days"


class TestFormatDaysCloseToOne:
    def test_zero_point_nine_nine_nine_ceilings_to_singular_one(self) -> None:
        # Ceiling to 0.01 lands at 1.00; rounded == 1.0 exactly ⇒ " day".
        assert format_days(0.999) == "1 day"


class TestFormatDaysCeilingBoundaries:
    def test_two_point_two_five_one_ceilings_positive(self) -> None:
        assert format_days(2.251) == "2.26 days"

    def test_two_point_two_five_one_negative_floors(self) -> None:
        assert format_days(-2.251) == "-2.26 days"


class TestFormatDaysDecimalSafeRounding:
    """Regression coverage for the M10.2 Block 1 decimal-safe fix.

    Authority: BUILD-PLAN §2.21 (AM11, 4/23/2026). Codex's PR #33
    P1 finding flagged that the naive ``math.ceil(days * 100) / 100``
    path in M10.1 Block 3 distorted exact-looking decimal inputs via
    IEEE-754 binary representation error — ``format_days(2.2)`` emitted
    ``"2.21 days"`` where ``"2.2 days"`` was required. The fix routes
    rounding through :class:`decimal.Decimal` with ``Decimal(str(days))``
    construction so the shortest round-tripping decimal representation
    of the input float drives the quantize step.
    """

    def test_two_point_two_positive_no_cent_inflation(self) -> None:
        assert format_days(2.2) == "2.2 days"

    def test_negative_one_point_one_no_cent_inflation(self) -> None:
        assert format_days(-1.1) == "-1.1 days"

    def test_one_point_one_positive_no_cent_inflation(self) -> None:
        assert format_days(1.1) == "1.1 days"

    def test_three_point_three_positive_no_cent_inflation(self) -> None:
        assert format_days(3.3) == "3.3 days"

    def test_negative_two_point_two_no_cent_inflation(self) -> None:
        assert format_days(-2.2) == "-2.2 days"

    def test_zero_point_seven_positive(self) -> None:
        assert format_days(0.7) == ".7 days"

    def test_negative_zero_point_seven(self) -> None:
        assert format_days(-0.7) == "-.7 days"

    def test_zero_point_one_binary_imprecise_decimal(self) -> None:
        assert format_days(0.1) == ".1 days"

    def test_zero_point_two_binary_imprecise_decimal(self) -> None:
        assert format_days(0.2) == ".2 days"

    def test_zero_point_three_binary_imprecise_decimal(self) -> None:
        assert format_days(0.3) == ".3 days"

    def test_negative_zero_point_one_binary_imprecise_decimal(self) -> None:
        assert format_days(-0.1) == "-.1 days"
