"""Tests for ``app.models.relation``. Covers G3, G4, G5."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import RelationType
from app.models.relation import Relation


class TestRelationConstruction:
    def test_minimal(self) -> None:
        r = Relation(predecessor_unique_id=1, successor_unique_id=2)
        assert r.relation_type is RelationType.FS
        assert r.lag_minutes == 0

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Relation(
                predecessor_unique_id=1,
                successor_unique_id=2,
                surprise=True,  # type: ignore[call-arg]
            )

    def test_all_relation_types_accepted(self) -> None:
        for rt in (RelationType.FS, RelationType.SS, RelationType.FF, RelationType.SF):
            r = Relation(predecessor_unique_id=1, successor_unique_id=2, relation_type=rt)
            assert r.relation_type is rt


class TestG3UniqueIdPositive:
    def test_pred_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relation(predecessor_unique_id=0, successor_unique_id=2)

    def test_succ_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relation(predecessor_unique_id=1, successor_unique_id=0)

    def test_pred_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relation(predecessor_unique_id=-1, successor_unique_id=2)


class TestG4NoSelfLoop:
    """G4: predecessor_unique_id != successor_unique_id."""

    def test_self_loop_rejected(self) -> None:
        with pytest.raises(ValidationError, match="G4"):
            Relation(predecessor_unique_id=7, successor_unique_id=7)

    def test_distinct_uids_accepted(self) -> None:
        r = Relation(predecessor_unique_id=7, successor_unique_id=8)
        assert r.predecessor_unique_id != r.successor_unique_id


class TestG5LagMinutes:
    """G5: lag is in minutes; negative (leads) and positive (lags)
    are both legal at the model level."""

    @pytest.mark.parametrize("lag", [-1440, -60, 0, 60, 1440, 2400])
    def test_lag_signed_minutes(self, lag: int) -> None:
        r = Relation(predecessor_unique_id=1, successor_unique_id=2, lag_minutes=lag)
        assert r.lag_minutes == lag

    def test_lead_default_lag_relation_distinct(self) -> None:
        lead = Relation(predecessor_unique_id=1, successor_unique_id=2, lag_minutes=-480)
        lag = Relation(predecessor_unique_id=1, successor_unique_id=2, lag_minutes=480)
        assert lead.lag_minutes < 0 < lag.lag_minutes


class TestRoundTrip:
    def test_json_roundtrip(self) -> None:
        original = Relation(
            predecessor_unique_id=10,
            successor_unique_id=20,
            relation_type=RelationType.SS,
            lag_minutes=-240,
        )
        clone = Relation.model_validate_json(original.model_dump_json())
        assert clone == original
