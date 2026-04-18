"""Unit tests for the MS Project predecessor-string parser.

Covers parser gotchas:

* P4 — empty / None predecessor → empty list (no crash, no None)
* P5 — whitespace and case normalization
* P6 — Task ID → UniqueID translation via id_map
* P7 — predecessor referencing a non-existent Task ID raises
  CorruptScheduleError (chosen behavior — strict)
"""

from __future__ import annotations

import pytest

from app.models.enums import RelationType
from app.parsers._predecessor_parser import (
    CalendarUnits,
    parse_predecessor_string,
)
from app.parsers.exceptions import CorruptScheduleError


# A baseline id_map matching the most common test scenarios. The
# audit Minor #6 hand-trace example uses Task ID 5 → UniqueID 4217 to
# exercise P6 (renumbered tasks across versions).
ID_MAP = {1: 100, 2: 200, 3: 300, 4: 400, 5: 4217, 7: 700}


class TestEmptyAndNone:
    """Parser gotcha P4 — empty input yields an empty list."""

    @pytest.mark.parametrize("raw", [None, "", "   ", "\t\n"])
    def test_empty_inputs_return_empty_list(self, raw: str | None) -> None:
        result = parse_predecessor_string(
            raw, successor_unique_id=999, id_map=ID_MAP
        )
        assert result == []


class TestSimpleTokens:
    """Single-token parses — happy path for FS, SS, FF, SF."""

    def test_bare_id_defaults_to_fs_zero_lag(self) -> None:
        rels = parse_predecessor_string(
            "1", successor_unique_id=999, id_map=ID_MAP
        )
        assert len(rels) == 1
        r = rels[0]
        assert r.predecessor_unique_id == 100
        assert r.successor_unique_id == 999
        assert r.relation_type is RelationType.FS
        assert r.lag_minutes == 0

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1FS", RelationType.FS),
            ("1SS", RelationType.SS),
            ("1FF", RelationType.FF),
            ("1SF", RelationType.SF),
        ],
    )
    def test_explicit_relation_types(self, raw: str, expected: RelationType) -> None:
        rels = parse_predecessor_string(
            raw, successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].relation_type is expected

    def test_uses_successor_unique_id(self) -> None:
        rels = parse_predecessor_string(
            "1", successor_unique_id=12345, id_map=ID_MAP
        )
        assert rels[0].successor_unique_id == 12345


class TestWhitespaceAndCase:
    """Parser gotcha P5 — whitespace and mixed case normalize."""

    @pytest.mark.parametrize(
        "raw",
        [
            "2fs+3d",
            "2 FS + 3 d",
            "  2  fs  + 3  d  ",
            "2Fs+3D",
            "2fS+3d",
        ],
    )
    def test_whitespace_and_case_normalize(self, raw: str) -> None:
        rels = parse_predecessor_string(
            raw, successor_unique_id=999, id_map=ID_MAP
        )
        assert len(rels) == 1
        r = rels[0]
        assert r.predecessor_unique_id == 200
        assert r.relation_type is RelationType.FS
        # 3 working days * 8h * 60min/h = 1440 minutes
        assert r.lag_minutes == 1440


class TestLagUnits:
    """Lag unit conversion uses the project default calendar."""

    def test_minutes(self) -> None:
        rels = parse_predecessor_string(
            "1FS+30m", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == 30

    def test_hours(self) -> None:
        rels = parse_predecessor_string(
            "1FS+2h", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == 120

    def test_days_default(self) -> None:
        """Default unit is working days when no unit suffix."""
        rels = parse_predecessor_string(
            "1FS+2", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == 960  # 2 * 8 * 60

    def test_weeks(self) -> None:
        rels = parse_predecessor_string(
            "1FS+1w", successor_unique_id=999, id_map=ID_MAP
        )
        # 1 week = 5 working days * 8h * 60min = 2400
        assert rels[0].lag_minutes == 2400

    def test_elapsed_days(self) -> None:
        """Elapsed units use 24h/day, not the working calendar."""
        rels = parse_predecessor_string(
            "1FS+1ed", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == 24 * 60

    def test_elapsed_weeks(self) -> None:
        rels = parse_predecessor_string(
            "1FS+1ew", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == 7 * 24 * 60

    def test_decimal_lag(self) -> None:
        rels = parse_predecessor_string(
            "1FS+0.5d", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == 240

    def test_custom_calendar_units(self) -> None:
        """A 10h-day calendar shifts the working-day conversion."""
        rels = parse_predecessor_string(
            "1FS+1d",
            successor_unique_id=999,
            id_map=ID_MAP,
            units=CalendarUnits(hours_per_day=10.0, working_days_per_week=4),
        )
        assert rels[0].lag_minutes == 600


class TestLeads:
    """Negative lag = lead (DCMA Metric 2 forensic signal)."""

    def test_negative_lag_preserved(self) -> None:
        rels = parse_predecessor_string(
            "1FS-1d", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == -480

    def test_negative_with_whitespace(self) -> None:
        rels = parse_predecessor_string(
            "1 FS - 2 d", successor_unique_id=999, id_map=ID_MAP
        )
        assert rels[0].lag_minutes == -960


class TestMultipleTokens:
    """Comma- and semicolon-separated lists."""

    def test_comma_separated(self) -> None:
        rels = parse_predecessor_string(
            "1FS,2SS+1d,3FF-2h",
            successor_unique_id=999,
            id_map=ID_MAP,
        )
        assert len(rels) == 3
        assert [r.predecessor_unique_id for r in rels] == [100, 200, 300]
        assert [r.relation_type for r in rels] == [
            RelationType.FS,
            RelationType.SS,
            RelationType.FF,
        ]
        assert [r.lag_minutes for r in rels] == [0, 480, -120]

    def test_semicolon_separated(self) -> None:
        """European locales use ``;`` as the list separator."""
        rels = parse_predecessor_string(
            "1FS;2SS",
            successor_unique_id=999,
            id_map=ID_MAP,
        )
        assert len(rels) == 2

    def test_trailing_comma_is_tolerated(self) -> None:
        rels = parse_predecessor_string(
            "1FS,2SS,",
            successor_unique_id=999,
            id_map=ID_MAP,
        )
        assert len(rels) == 2

    def test_preserves_source_order(self) -> None:
        rels = parse_predecessor_string(
            "3FS,1FS,2FS",
            successor_unique_id=999,
            id_map=ID_MAP,
        )
        assert [r.predecessor_unique_id for r in rels] == [300, 100, 200]


class TestTaskIdToUniqueIdTranslation:
    """Parser gotcha P6 — Task ID → UniqueID via id_map.

    The Predecessors column references display Task IDs, which can
    be renumbered between schedule versions. UniqueID is the only
    safe cross-version key (BUILD-PLAN §2.7 + skill §5).
    """

    def test_renumbered_task_translates_correctly(self) -> None:
        """Task ID 5 maps to UniqueID 4217 in this fixture id_map."""
        rels = parse_predecessor_string(
            "5FS+1d", successor_unique_id=999, id_map=ID_MAP
        )
        assert len(rels) == 1
        assert rels[0].predecessor_unique_id == 4217

    def test_relation_carries_unique_id_not_task_id(self) -> None:
        rels = parse_predecessor_string(
            "5FS", successor_unique_id=999, id_map=ID_MAP
        )
        # The Relation must NOT store Task ID 5 by accident.
        assert rels[0].predecessor_unique_id != 5
        assert rels[0].predecessor_unique_id == 4217


class TestUnknownTaskId:
    """Parser gotcha P7 — chosen behavior is to raise.

    Documented in :class:`app.parsers.com_parser.MPProjectParser`.
    Rationale: silently dropping a malformed predecessor would
    corrupt the CPM result and hide a manipulation signal. The
    fail-fast posture matches "no analysis before parser
    validated" from skill §4.
    """

    def test_unknown_task_id_raises(self) -> None:
        with pytest.raises(CorruptScheduleError) as exc_info:
            parse_predecessor_string(
                "999FS",
                successor_unique_id=12,
                id_map=ID_MAP,
            )
        # Error message must mention the offending Task ID so the
        # analyst can locate the bad reference in MS Project's UI.
        assert "999" in str(exc_info.value)

    def test_partial_failure_still_raises(self) -> None:
        """One bad token aborts the whole token list."""
        with pytest.raises(CorruptScheduleError):
            parse_predecessor_string(
                "1FS,999FS,2FS",
                successor_unique_id=12,
                id_map=ID_MAP,
            )


class TestUnparseableToken:
    """Tokens that do not match the grammar raise."""

    @pytest.mark.parametrize(
        "raw",
        [
            "abc",
            "1XX",  # XX is not a valid relation type
            "1FS+",  # sign without number
            "1FS+abc",  # unit without number
        ],
    )
    def test_unparseable_token_raises(self, raw: str) -> None:
        with pytest.raises(CorruptScheduleError):
            parse_predecessor_string(
                raw, successor_unique_id=999, id_map=ID_MAP
            )
