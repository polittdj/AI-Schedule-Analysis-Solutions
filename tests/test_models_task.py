"""Tests for ``app.models.task``.

Covers gotchas G1, G2, G3, G6, G7, G8 from Milestone 2 prompt §4.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.enums import ConstraintType, TaskType
from app.models.task import Task

UTC = timezone.utc


def _dt(d: int = 1, h: int = 8) -> datetime:
    return datetime(2026, 4, d, h, tzinfo=UTC)


def _minimal_task(**overrides) -> Task:
    base: dict = {"unique_id": 1, "task_id": 1, "name": "Task 1"}
    base.update(overrides)
    return Task(**base)


class TestTaskMinimalConstruction:
    def test_minimal(self) -> None:
        t = _minimal_task()
        assert t.unique_id == 1
        assert t.constraint_type is ConstraintType.AS_SOON_AS_POSSIBLE
        assert t.constraint_date is None
        assert t.percent_complete == 0.0
        assert t.task_type is TaskType.FIXED_UNITS
        assert t.is_milestone is False

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(surprise="x")


class TestG1NaiveDatetimeRejection:
    """G1: tz-naive datetime is rejected for every datetime field."""

    @pytest.mark.parametrize(
        "field",
        [
            "start",
            "finish",
            "early_start",
            "early_finish",
            "late_start",
            "late_finish",
            "baseline_start",
            "baseline_finish",
            "actual_start",
            "actual_finish",
            "deadline",
        ],
    )
    def test_naive_datetime_rejected_per_field(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(**{field: datetime(2026, 4, 1, 8)})  # naive

    def test_constraint_date_naive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(
                constraint_type=ConstraintType.MUST_START_ON,
                constraint_date=datetime(2026, 4, 1, 8),
            )

    def test_aware_datetime_accepted(self) -> None:
        t = _minimal_task(start=_dt(), finish=_dt(2))
        assert t.start is not None
        assert t.finish is not None


class TestG2NegativeDurationRejection:
    """G2: durations must be non-negative.

    Slack fields are signed and not covered by G2 (DCMA Metric 7
    requires negative slack representation).
    """

    @pytest.mark.parametrize(
        "field",
        [
            "duration_minutes",
            "remaining_duration_minutes",
            "actual_duration_minutes",
            "baseline_duration_minutes",
        ],
    )
    def test_negative_duration_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(**{field: -1})

    def test_negative_total_slack_allowed(self) -> None:
        """Total slack may be negative — DCMA Metric 7 depends on it."""
        t = _minimal_task(total_slack_minutes=-480)
        assert t.total_slack_minutes == -480


class TestG3UniqueId:
    def test_zero_unique_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(unique_id=0)

    def test_negative_unique_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(unique_id=-5)

    def test_positive_unique_id_accepted(self) -> None:
        assert _minimal_task(unique_id=99).unique_id == 99


class TestG6AsapAlapNoDate:
    """G6: ASAP and ALAP MUST NOT carry a constraint date."""

    def test_asap_with_date_rejected(self) -> None:
        with pytest.raises(ValidationError, match="G6"):
            _minimal_task(
                constraint_type=ConstraintType.AS_SOON_AS_POSSIBLE,
                constraint_date=_dt(),
            )

    def test_alap_with_date_rejected(self) -> None:
        with pytest.raises(ValidationError, match="G6"):
            _minimal_task(
                constraint_type=ConstraintType.AS_LATE_AS_POSSIBLE,
                constraint_date=_dt(),
            )

    def test_asap_without_date_ok(self) -> None:
        t = _minimal_task(constraint_type=ConstraintType.AS_SOON_AS_POSSIBLE)
        assert t.constraint_date is None

    def test_alap_without_date_ok(self) -> None:
        t = _minimal_task(constraint_type=ConstraintType.AS_LATE_AS_POSSIBLE)
        assert t.constraint_date is None


class TestG7HardConstraintsRequireDate:
    """G7: date-bearing constraints (MSO/MFO/SNET/SNLT/FNET/FNLT)
    require a constraint_date."""

    @pytest.mark.parametrize(
        "ct",
        [
            ConstraintType.MUST_START_ON,
            ConstraintType.MUST_FINISH_ON,
            ConstraintType.START_NO_LATER_THAN,
            ConstraintType.FINISH_NO_LATER_THAN,
            ConstraintType.START_NO_EARLIER_THAN,
            ConstraintType.FINISH_NO_EARLIER_THAN,
        ],
    )
    def test_missing_date_rejected(self, ct: ConstraintType) -> None:
        with pytest.raises(ValidationError, match="G7"):
            _minimal_task(constraint_type=ct)

    @pytest.mark.parametrize(
        "ct",
        [
            ConstraintType.MUST_START_ON,
            ConstraintType.MUST_FINISH_ON,
            ConstraintType.START_NO_LATER_THAN,
            ConstraintType.FINISH_NO_LATER_THAN,
            ConstraintType.START_NO_EARLIER_THAN,
            ConstraintType.FINISH_NO_EARLIER_THAN,
        ],
    )
    def test_with_date_accepted(self, ct: ConstraintType) -> None:
        t = _minimal_task(constraint_type=ct, constraint_date=_dt())
        assert t.constraint_date is not None


class TestG8PercentComplete:
    """G8: percent_complete must lie in [0, 100]."""

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(percent_complete=-0.1)

    def test_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_task(percent_complete=100.01)

    @pytest.mark.parametrize("v", [0.0, 0.5, 50.0, 99.9, 100.0])
    def test_in_range_accepted(self, v: float) -> None:
        t = _minimal_task(percent_complete=v)
        assert t.percent_complete == v


class TestRoundTrip:
    def test_json_roundtrip_preserves_fields(self) -> None:
        t = _minimal_task(
            unique_id=42,
            task_id=10,
            name="Pour foundation",
            wbs="1.2.3",
            duration_minutes=2400,
            total_slack_minutes=-960,
            percent_complete=37.5,
            is_critical_from_msp=True,
            is_schedule_margin=False,
            constraint_type=ConstraintType.START_NO_LATER_THAN,
            constraint_date=_dt(15, 8),
            start=_dt(1, 8),
            finish=_dt(10, 17),
        )
        payload = t.model_dump_json()
        clone = Task.model_validate_json(payload)
        assert clone == t
