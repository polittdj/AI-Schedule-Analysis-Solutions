"""Unit tests for the pure COM helper functions.

Pure functions only — no COM, no win32com import. Covers:

* parser gotcha P8 (naive COM datetime → tz-aware UTC)
* gotcha P9 hand-off (constraint date null-out happens upstream of
  the constraint mapping)
* the Gotcha 6 status-date sentinel matrix
* duration / slack / lag minute coercion (Gotcha 5)
* the COM ``PjTaskLinkType`` and ``PjConstraint`` enum mappings
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models.enums import ConstraintType, RelationType, ResourceType
from app.parsers._com_helpers import (
    cast_minutes,
    coerce_datetime_to_utc,
    map_constraint_type,
    map_relation_type,
    map_resource_type,
    safe_get,
)


class TestCoerceDatetimeToUtc:
    """Date boundary contract — naive COM datetimes become UTC-aware."""

    def test_none_returns_none(self) -> None:
        assert coerce_datetime_to_utc(None) is None

    def test_naive_datetime_becomes_utc_aware(self) -> None:
        """P8: naive COM datetime must come back tz-aware UTC."""
        result = coerce_datetime_to_utc(datetime(2025, 1, 1, 8, 0, 0))
        assert result is not None
        assert result.tzinfo is UTC
        assert result == datetime(2025, 1, 1, 8, 0, 0, tzinfo=UTC)

    def test_aware_datetime_passes_through_as_utc(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        result = coerce_datetime_to_utc(datetime(2025, 1, 1, 13, 0, 0, tzinfo=eastern))
        assert result == datetime(2025, 1, 1, 18, 0, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        "sentinel",
        [
            datetime(1899, 12, 30),
            datetime(1984, 1, 1),
        ],
    )
    def test_sentinel_dates_become_none(self, sentinel: datetime) -> None:
        """Gotcha 6: OLE-zero and MSP-epoch sentinels normalize to None."""
        assert coerce_datetime_to_utc(sentinel) is None

    def test_sentinel_with_tzinfo_still_recognized(self) -> None:
        """Sentinels carrying a tz still indicate "unset"."""
        sentinel = datetime(1899, 12, 30, tzinfo=UTC)
        assert coerce_datetime_to_utc(sentinel) is None

    @pytest.mark.parametrize("text", ["NA", "na", " na ", " NA  ", ""])
    def test_string_sentinels_become_none(self, text: str) -> None:
        """Gotcha 6: ``'NA'`` and empty strings normalize to None."""
        assert coerce_datetime_to_utc(text) is None

    def test_unrecognized_string_returns_none(self) -> None:
        """Defense in depth: unparseable strings do not crash."""
        assert coerce_datetime_to_utc("not a date") is None

    def test_non_datetime_object_returns_none(self) -> None:
        assert coerce_datetime_to_utc(12345) is None
        assert coerce_datetime_to_utc(object()) is None


class TestCastMinutes:
    """Duration / slack / lag minute coercion (Gotcha 5)."""

    def test_none_returns_zero(self) -> None:
        assert cast_minutes(None) == 0

    def test_int_passes_through(self) -> None:
        assert cast_minutes(2400) == 2400

    def test_float_rounds_to_nearest(self) -> None:
        """COM may return 1/10-minute precision; we round."""
        assert cast_minutes(2400.4) == 2400
        assert cast_minutes(2400.6) == 2401

    def test_negative_clamped_by_default(self) -> None:
        """Duration fields cannot be negative (model G2)."""
        assert cast_minutes(-5) == 0

    def test_negative_allowed_for_slack(self) -> None:
        """Slack can be negative — DCMA Metric 7."""
        assert cast_minutes(-480, allow_negative=True) == -480

    def test_negative_lead_lag_allowed(self) -> None:
        """Leads (negative lag) preserved when explicitly allowed."""
        assert cast_minutes(-1440.0, allow_negative=True) == -1440

    def test_unparseable_returns_zero(self) -> None:
        assert cast_minutes("not a number") == 0
        assert cast_minutes(object()) == 0


class TestMapConstraintType:
    """``Task.ConstraintType`` (PjConstraint) translation."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0, ConstraintType.AS_SOON_AS_POSSIBLE),
            (1, ConstraintType.AS_LATE_AS_POSSIBLE),
            (2, ConstraintType.MUST_START_ON),
            (3, ConstraintType.MUST_FINISH_ON),
            (4, ConstraintType.START_NO_EARLIER_THAN),
            (5, ConstraintType.START_NO_LATER_THAN),
            (6, ConstraintType.FINISH_NO_EARLIER_THAN),
            (7, ConstraintType.FINISH_NO_LATER_THAN),
        ],
    )
    def test_known_ints(self, raw: int, expected: ConstraintType) -> None:
        assert map_constraint_type(raw) is expected

    def test_none_defaults_to_asap(self) -> None:
        assert map_constraint_type(None) is ConstraintType.AS_SOON_AS_POSSIBLE

    def test_unknown_int_defaults_to_asap(self) -> None:
        assert map_constraint_type(99) is ConstraintType.AS_SOON_AS_POSSIBLE

    def test_unparseable_defaults_to_asap(self) -> None:
        assert map_constraint_type("garbage") is ConstraintType.AS_SOON_AS_POSSIBLE

    def test_float_int_coerced(self) -> None:
        """COM may surface integers as floats over IDispatch."""
        assert map_constraint_type(2.0) is ConstraintType.MUST_START_ON


class TestMapRelationType:
    """``TaskDependency.Type`` (PjTaskLinkType) translation.

    The COM enum is ``0=FF, 1=FS, 2=SF, 3=SS`` per
    ``mpp-parsing-com-automation §5``. This is the source of truth;
    MPXJ's enum is deliberately not consulted (per BUILD-PLAN §2.3
    and the §2 lock that MPXJ is removed from Phase 1).
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0, RelationType.FF),
            (1, RelationType.FS),
            (2, RelationType.SF),
            (3, RelationType.SS),
        ],
    )
    def test_known_ints(self, raw: int, expected: RelationType) -> None:
        assert map_relation_type(raw) is expected

    def test_none_defaults_to_fs(self) -> None:
        assert map_relation_type(None) is RelationType.FS

    def test_unknown_int_defaults_to_fs(self) -> None:
        assert map_relation_type(42) is RelationType.FS

    def test_unparseable_defaults_to_fs(self) -> None:
        assert map_relation_type("nope") is RelationType.FS


class TestMapResourceType:
    """``Resource.Type`` (PjResourceType) translation."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0, ResourceType.WORK),
            (1, ResourceType.MATERIAL),
            (2, ResourceType.COST),
        ],
    )
    def test_known_ints(self, raw: int, expected: ResourceType) -> None:
        assert map_resource_type(raw) is expected

    def test_none_defaults_to_work(self) -> None:
        assert map_resource_type(None) is ResourceType.WORK

    def test_unknown_defaults_to_work(self) -> None:
        assert map_resource_type(99) is ResourceType.WORK


class TestSafeGet:
    """``getattr`` wrapper that swallows COM/AttributeError."""

    def test_returns_attribute_when_present(self) -> None:
        class Box:
            x = 5

        assert safe_get(Box(), "x") == 5

    def test_returns_default_when_attribute_absent(self) -> None:
        assert safe_get(object(), "missing", default="d") == "d"

    def test_returns_default_when_property_raises(self) -> None:
        class Naughty:
            @property
            def x(self) -> int:
                raise RuntimeError("simulated COM failure")

        assert safe_get(Naughty(), "x", default=0) == 0

    def test_default_is_none_by_default(self) -> None:
        assert safe_get(object(), "missing") is None


class TestMapResourceTypeEdgeCases:
    """Exercise the defensive branches of map_resource_type."""

    def test_unparseable_defaults_to_work(self) -> None:
        assert map_resource_type("garbage") is ResourceType.WORK
        assert map_resource_type(object()) is ResourceType.WORK
