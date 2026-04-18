"""Tests for ``app.models.enums``.

The integer values of every enum must match the Microsoft Project COM
enum so the Milestone 3 adapter can cast raw COM values directly.
"""

from __future__ import annotations

import pytest

from app.models.enums import (
    DATE_BEARING_CONSTRAINTS,
    HARD_CONSTRAINTS,
    ConstraintType,
    RelationType,
    ResourceType,
    TaskType,
)


class TestRelationType:
    def test_com_enum_integers(self) -> None:
        """COM ``PjTaskLinkType``: 0=FF, 1=FS, 2=SF, 3=SS."""
        assert RelationType.FF.value == 0
        assert RelationType.FS.value == 1
        assert RelationType.SF.value == 2
        assert RelationType.SS.value == 3

    def test_four_members(self) -> None:
        assert len(RelationType) == 4

    def test_cast_from_int(self) -> None:
        assert RelationType(1) is RelationType.FS


class TestConstraintType:
    @pytest.mark.parametrize(
        ("member", "value"),
        [
            (ConstraintType.AS_SOON_AS_POSSIBLE, 0),
            (ConstraintType.AS_LATE_AS_POSSIBLE, 1),
            (ConstraintType.MUST_START_ON, 2),
            (ConstraintType.MUST_FINISH_ON, 3),
            (ConstraintType.START_NO_EARLIER_THAN, 4),
            (ConstraintType.START_NO_LATER_THAN, 5),
            (ConstraintType.FINISH_NO_EARLIER_THAN, 6),
            (ConstraintType.FINISH_NO_LATER_THAN, 7),
        ],
    )
    def test_com_enum_integers(self, member: ConstraintType, value: int) -> None:
        assert member.value == value

    def test_eight_members(self) -> None:
        assert len(ConstraintType) == 8

    def test_hard_constraints_are_09nov09_four(self) -> None:
        """DCMA Metric 5 (09NOV09) hard constraints: MSO, MFO, SNLT, FNLT."""
        assert HARD_CONSTRAINTS == frozenset(
            {
                ConstraintType.MUST_START_ON,
                ConstraintType.MUST_FINISH_ON,
                ConstraintType.START_NO_LATER_THAN,
                ConstraintType.FINISH_NO_LATER_THAN,
            }
        )

    def test_asap_alap_not_hard(self) -> None:
        assert ConstraintType.AS_SOON_AS_POSSIBLE not in HARD_CONSTRAINTS
        assert ConstraintType.AS_LATE_AS_POSSIBLE not in HARD_CONSTRAINTS

    def test_snet_fnet_not_hard(self) -> None:
        """SNET/FNET are date-bearing but not in the 09NOV09 hard list."""
        assert ConstraintType.START_NO_EARLIER_THAN not in HARD_CONSTRAINTS
        assert ConstraintType.FINISH_NO_EARLIER_THAN not in HARD_CONSTRAINTS

    def test_date_bearing_excludes_asap_alap(self) -> None:
        assert ConstraintType.AS_SOON_AS_POSSIBLE not in DATE_BEARING_CONSTRAINTS
        assert ConstraintType.AS_LATE_AS_POSSIBLE not in DATE_BEARING_CONSTRAINTS

    def test_date_bearing_includes_all_dated_six(self) -> None:
        assert DATE_BEARING_CONSTRAINTS == frozenset(
            {
                ConstraintType.MUST_START_ON,
                ConstraintType.MUST_FINISH_ON,
                ConstraintType.START_NO_EARLIER_THAN,
                ConstraintType.START_NO_LATER_THAN,
                ConstraintType.FINISH_NO_EARLIER_THAN,
                ConstraintType.FINISH_NO_LATER_THAN,
            }
        )

    def test_hard_is_subset_of_date_bearing(self) -> None:
        assert HARD_CONSTRAINTS <= DATE_BEARING_CONSTRAINTS


class TestTaskType:
    def test_com_enum_integers(self) -> None:
        assert TaskType.FIXED_UNITS.value == 0
        assert TaskType.FIXED_DURATION.value == 1
        assert TaskType.FIXED_WORK.value == 2


class TestResourceType:
    def test_com_enum_integers(self) -> None:
        assert ResourceType.WORK.value == 0
        assert ResourceType.MATERIAL.value == 1
        assert ResourceType.COST.value == 2
