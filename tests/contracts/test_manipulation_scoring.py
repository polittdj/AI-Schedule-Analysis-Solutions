"""Frozen-contract tests for the M11 manipulation-scoring types.

Authority: BUILD-PLAN §2.22 (AM12, 4/23/2026) subsection (g). Four
categories at a ≥18-test floor: contract shape validation (A1-A5),
field presence (B1-B4), M10.1 / M10.2 integration (C1-C3), and
validator-raise cases (D1-D6).

No engine / comparator / scoring logic is exercised here — Block 2
covers contracts only. Engine coverage arrives in Blocks 3-4.
"""

from __future__ import annotations

from datetime import datetime
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from app.contracts.manipulation_scoring import (
    ConstraintDrivenCrossVersionResult,
    ManipulationScoringResult,
    ManipulationScoringSummary,
    SeverityTier,
    SlackState,
)
from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathNode,
    DrivingPathResult,
)
from app.models.enums import ConstraintType, RelationType

_T0 = datetime(2026, 1, 1, 8, 0)
_T1 = datetime(2026, 1, 2, 16, 0)


def _cdp(
    pred_uid: int,
    succ_uid: int,
    *,
    slack_days: float = -1.0,
    constraint_type: ConstraintType = ConstraintType.MUST_START_ON,
    rationale: str = "negative slack held by MSO predecessor",
) -> ConstraintDrivenPredecessor:
    return ConstraintDrivenPredecessor(
        predecessor_uid=pred_uid,
        predecessor_name=f"P{pred_uid}",
        successor_uid=succ_uid,
        successor_name=f"S{succ_uid}",
        relation_type=RelationType.FS,
        lag_days=0.0,
        slack_days=slack_days,
        calendar_hours_per_day=8.0,
        predecessor_constraint_type=constraint_type,
        predecessor_constraint_date=_T0,
        rationale=rationale,
    )


def _empty_driving_path_result(focus_uid: int = 1) -> DrivingPathResult:
    focus_node = DrivingPathNode(
        unique_id=focus_uid,
        name=f"Focus{focus_uid}",
        early_start=_T0,
        early_finish=_T1,
        late_start=_T0,
        late_finish=_T1,
        total_float_days=0.0,
        calendar_hours_per_day=8.0,
    )
    return DrivingPathResult(
        focus_point_uid=focus_uid,
        focus_point_name=f"Focus{focus_uid}",
        nodes={focus_uid: focus_node},
        edges=[],
        non_driving_predecessors=[],
        constraint_driven_predecessors=[],
        skipped_cycle_participants=[],
    )


def _canonical_result() -> ManipulationScoringResult:
    return ManipulationScoringResult(
        unique_id=42,
        name="Task 42",
        score=10,
        severity_tier=SeverityTier.HIGH,
        slack_state=SlackState.JOINED_PRIMARY,
        period_a_predecessors=(),
        period_b_predecessors=(_cdp(100, 42),),
        skipped_cycle_participants_reference=(),
        rationale="joined the primary constraint-driven regime",
    )


def _canonical_cross_version() -> ConstraintDrivenCrossVersionResult:
    return ConstraintDrivenCrossVersionResult(
        period_a_result=_empty_driving_path_result(1),
        period_b_result=_empty_driving_path_result(1),
    )


# ----------------------------------------------------------------------
# Category A — Contract shape validation
# ----------------------------------------------------------------------


def test_all_four_models_frozen() -> None:
    """A1: Attempting mutation on any public model raises ValidationError.

    Pydantic v2 ``ConfigDict(frozen=True)`` rejects attribute
    assignment. The ``StrEnum`` members are strings and are not
    considered a public Pydantic model; frozen-ness is checked on the
    three BaseModel subclasses.
    """
    cv = _canonical_cross_version()
    with pytest.raises(ValidationError):
        cv.period_working_days_elapsed = 1.0  # type: ignore[misc]

    result = _canonical_result()
    with pytest.raises(ValidationError):
        result.score = 5  # type: ignore[misc]

    summary = ManipulationScoringSummary(
        total_score=0,
        uid_count_high=0,
        uid_count_medium=0,
        uid_count_low=0,
        uid_count_joined_primary=0,
        uid_count_eroding_toward_primary=0,
        uid_count_stable=0,
        uid_count_recovering=0,
    )
    with pytest.raises(ValidationError):
        summary.total_score = 50  # type: ignore[misc]


def test_field_types_well_formed() -> None:
    """A2: Canonical construction populates fields with their declared
    python types."""
    cv = _canonical_cross_version()
    assert isinstance(cv.period_a_result, DrivingPathResult)
    assert isinstance(cv.period_b_result, DrivingPathResult)
    assert cv.period_a_status_date is None
    assert cv.period_b_status_date is None
    assert cv.period_a_project_start is None
    assert cv.period_b_project_start is None
    assert cv.period_working_days_elapsed is None
    assert isinstance(cv.added_constraint_driven_uids, set)
    assert isinstance(cv.period_a_predecessors_by_successor, dict)

    result = _canonical_result()
    assert isinstance(result.unique_id, int)
    assert isinstance(result.name, str)
    assert isinstance(result.score, int)
    assert isinstance(result.severity_tier, SeverityTier)
    assert isinstance(result.slack_state, SlackState)
    assert isinstance(result.period_a_predecessors, tuple)
    assert isinstance(result.period_b_predecessors, tuple)
    assert isinstance(result.skipped_cycle_participants_reference, tuple)
    assert isinstance(result.windowing_incomplete, bool)
    assert isinstance(result.rationale, str)

    summary = ManipulationScoringSummary(
        total_score=12,
        uid_count_high=1,
        uid_count_medium=0,
        uid_count_low=1,
        uid_count_joined_primary=1,
        uid_count_eroding_toward_primary=0,
        uid_count_stable=1,
        uid_count_recovering=0,
        per_uid_results=(result,),
    )
    assert isinstance(summary.total_score, int)
    assert isinstance(summary.per_uid_results, tuple)
    assert all(
        isinstance(r, ManipulationScoringResult) for r in summary.per_uid_results
    )


def test_slackstate_enum_completeness() -> None:
    """A3: SlackState has exactly four members with canonical values."""
    expected = {
        "JOINED_PRIMARY": "joined_primary",
        "ERODING_TOWARD_PRIMARY": "eroding_toward_primary",
        "STABLE": "stable",
        "RECOVERING": "recovering",
    }
    assert {m.name: m.value for m in SlackState} == expected
    assert len(list(SlackState)) == 4


def test_severitytier_enum_completeness() -> None:
    """A4: SeverityTier has exactly three members with canonical values."""
    expected = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    assert {m.name: m.value for m in SeverityTier} == expected
    assert len(list(SeverityTier)) == 3


def test_total_score_bounds_and_default_factory_invariants() -> None:
    """A5: total_score accepts 0 / 50 / 100; default_factory fields
    return independent empty containers on every construction."""
    for score in (0, 50, 100):
        summary = ManipulationScoringSummary(
            total_score=score,
            uid_count_high=0,
            uid_count_medium=0,
            uid_count_low=0,
            uid_count_joined_primary=0,
            uid_count_eroding_toward_primary=0,
            uid_count_stable=0,
            uid_count_recovering=0,
        )
        assert summary.total_score == score
        assert summary.per_uid_results == ()

    cv_a = _canonical_cross_version()
    cv_b = _canonical_cross_version()
    assert cv_a.added_constraint_driven_uids == set()
    assert cv_a.removed_constraint_driven_uids == set()
    assert cv_a.retained_constraint_driven_uids == set()
    assert cv_a.period_a_predecessors_by_successor == {}
    assert cv_a.period_b_predecessors_by_successor == {}
    assert (
        cv_a.added_constraint_driven_uids
        is not cv_b.added_constraint_driven_uids
    )
    assert (
        cv_a.period_a_predecessors_by_successor
        is not cv_b.period_a_predecessors_by_successor
    )


# ----------------------------------------------------------------------
# Category B — Field presence (ordered per AM12 subsection (c))
# ----------------------------------------------------------------------


def test_constraint_driven_cross_version_result_fields() -> None:
    """B1: Every field named in AM12 subsection (c) (as amended by
    AM13) for the comparator result exists on the model with the
    stated annotation.

    AM13 removed the two ``*_status_date_days_offset`` fields and
    replaced them with the five absolute-date / working-days-elapsed
    fields asserted here.
    """
    fields = ConstraintDrivenCrossVersionResult.model_fields
    assert set(fields.keys()) == {
        "period_a_result",
        "period_b_result",
        "period_a_status_date",
        "period_b_status_date",
        "period_a_project_start",
        "period_b_project_start",
        "period_working_days_elapsed",
        "added_constraint_driven_uids",
        "removed_constraint_driven_uids",
        "retained_constraint_driven_uids",
        "period_a_predecessors_by_successor",
        "period_b_predecessors_by_successor",
    }
    hints = get_type_hints(ConstraintDrivenCrossVersionResult)
    assert hints["period_a_result"] is DrivingPathResult
    assert hints["period_b_result"] is DrivingPathResult
    assert hints["period_a_status_date"] == (datetime | None)
    assert hints["period_b_status_date"] == (datetime | None)
    assert hints["period_a_project_start"] == (datetime | None)
    assert hints["period_b_project_start"] == (datetime | None)
    assert hints["period_working_days_elapsed"] == (float | None)
    assert hints["added_constraint_driven_uids"] == set[int]
    assert hints["removed_constraint_driven_uids"] == set[int]
    assert hints["retained_constraint_driven_uids"] == set[int]
    assert hints["period_a_predecessors_by_successor"] == dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ]
    assert hints["period_b_predecessors_by_successor"] == dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ]


def test_am13_new_fields_defaults_are_none() -> None:
    """B1b (AM13): the five new fields default to ``None`` on
    canonical construction — every new field is optional and the
    comparator populates them lazily from schedule state."""
    cv = _canonical_cross_version()
    assert cv.period_a_status_date is None
    assert cv.period_b_status_date is None
    assert cv.period_a_project_start is None
    assert cv.period_b_project_start is None
    assert cv.period_working_days_elapsed is None

    fields = ConstraintDrivenCrossVersionResult.model_fields
    assert fields["period_a_status_date"].default is None
    assert fields["period_b_status_date"].default is None
    assert fields["period_a_project_start"].default is None
    assert fields["period_b_project_start"].default is None
    assert fields["period_working_days_elapsed"].default is None


def test_am13_new_fields_round_trip_with_values() -> None:
    """B1c (AM13): construct a ConstraintDrivenCrossVersionResult with
    all five new fields populated with concrete values and assert the
    stored values round-trip unchanged."""
    dpr = _empty_driving_path_result(1)
    sd_a = datetime(2026, 1, 15, 8, 0)
    sd_b = datetime(2026, 2, 14, 8, 0)
    ps_a = datetime(2025, 12, 1, 8, 0)
    ps_b = datetime(2025, 12, 1, 8, 0)
    elapsed = 21.5

    cv = ConstraintDrivenCrossVersionResult(
        period_a_result=dpr,
        period_b_result=dpr,
        period_a_status_date=sd_a,
        period_b_status_date=sd_b,
        period_a_project_start=ps_a,
        period_b_project_start=ps_b,
        period_working_days_elapsed=elapsed,
    )
    assert cv.period_a_status_date == sd_a
    assert cv.period_b_status_date == sd_b
    assert cv.period_a_project_start == ps_a
    assert cv.period_b_project_start == ps_b
    assert cv.period_working_days_elapsed == elapsed
    assert isinstance(cv.period_a_status_date, datetime)
    assert isinstance(cv.period_working_days_elapsed, float)


def test_manipulation_scoring_result_fields_includes_windowing_incomplete() -> None:
    """B2: Every field named in AM12 subsection (c) for the per-UID
    result exists, INCLUDING windowing_incomplete: bool = False."""
    fields = ManipulationScoringResult.model_fields
    assert set(fields.keys()) == {
        "unique_id",
        "name",
        "score",
        "severity_tier",
        "slack_state",
        "period_a_predecessors",
        "period_b_predecessors",
        "skipped_cycle_participants_reference",
        "windowing_incomplete",
        "rationale",
    }
    hints = get_type_hints(ManipulationScoringResult)
    assert hints["unique_id"] is int
    assert hints["name"] is str
    assert hints["score"] is int
    assert hints["severity_tier"] is SeverityTier
    assert hints["slack_state"] is SlackState
    assert hints["period_a_predecessors"] == tuple[
        ConstraintDrivenPredecessor, ...
    ]
    assert hints["period_b_predecessors"] == tuple[
        ConstraintDrivenPredecessor, ...
    ]
    assert hints["skipped_cycle_participants_reference"] == tuple[int, ...]
    assert hints["windowing_incomplete"] is bool
    assert hints["rationale"] is str

    windowing_default = fields["windowing_incomplete"].default
    assert windowing_default is False


def test_manipulation_scoring_summary_fields() -> None:
    """B3: Every field named in AM12 subsection (c) for the aggregate
    summary exists with the stated annotation."""
    fields = ManipulationScoringSummary.model_fields
    assert set(fields.keys()) == {
        "total_score",
        "uid_count_high",
        "uid_count_medium",
        "uid_count_low",
        "uid_count_joined_primary",
        "uid_count_eroding_toward_primary",
        "uid_count_stable",
        "uid_count_recovering",
        "per_uid_results",
    }
    hints = get_type_hints(ManipulationScoringSummary)
    assert hints["total_score"] is int
    assert hints["uid_count_high"] is int
    assert hints["uid_count_medium"] is int
    assert hints["uid_count_low"] is int
    assert hints["uid_count_joined_primary"] is int
    assert hints["uid_count_eroding_toward_primary"] is int
    assert hints["uid_count_stable"] is int
    assert hints["uid_count_recovering"] is int
    assert hints["per_uid_results"] == tuple[ManipulationScoringResult, ...]


def test_manipulation_scoring_result_field_ordering_matches_am12() -> None:
    """B4: Field iteration order on ManipulationScoringResult matches
    AM12 subsection (c) verbatim — renderer determinism depends on it."""
    expected_order = (
        "unique_id",
        "name",
        "score",
        "severity_tier",
        "slack_state",
        "period_a_predecessors",
        "period_b_predecessors",
        "skipped_cycle_participants_reference",
        "windowing_incomplete",
        "rationale",
    )
    assert tuple(ManipulationScoringResult.model_fields.keys()) == expected_order


# ----------------------------------------------------------------------
# Category C — Integration with M10.1 / M10.2
# ----------------------------------------------------------------------


def test_constraint_driven_predecessor_imports_no_circular() -> None:
    """C1: ConstraintDrivenPredecessor imports cleanly from
    ``app.engine.driving_path_types`` (no circular import) and is the
    same type referenced by the per-UID result's predecessor tuples."""
    from app.engine.driving_path_types import (  # noqa: F401 — re-import
        ConstraintDrivenPredecessor as CDPReimport,
    )

    assert CDPReimport is ConstraintDrivenPredecessor

    hints = get_type_hints(ManipulationScoringResult)
    assert hints["period_a_predecessors"] == tuple[ConstraintDrivenPredecessor, ...]
    assert hints["period_b_predecessors"] == tuple[ConstraintDrivenPredecessor, ...]

    hints_cv = get_type_hints(ConstraintDrivenCrossVersionResult)
    assert hints_cv["period_a_predecessors_by_successor"] == dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ]
    assert hints_cv["period_b_predecessors_by_successor"] == dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ]


def test_driving_path_result_reference_resolves() -> None:
    """C2: DrivingPathResult imports cleanly and is the same type
    referenced on the comparator result's period fields."""
    from app.engine.driving_path_types import (  # noqa: F401 — re-import
        DrivingPathResult as DPRReimport,
    )

    assert DPRReimport is DrivingPathResult

    hints = get_type_hints(ConstraintDrivenCrossVersionResult)
    assert hints["period_a_result"] is DrivingPathResult
    assert hints["period_b_result"] is DrivingPathResult

    cv = _canonical_cross_version()
    assert isinstance(cv.period_a_result, DrivingPathResult)
    assert isinstance(cv.period_b_result, DrivingPathResult)


def test_skipped_cycle_participants_reference_accepts_tuple() -> None:
    """C3: skipped_cycle_participants_reference on
    ManipulationScoringResult preserves a tuple[int, ...] input verbatim
    (no coercion to list)."""
    participants = (1, 2, 3)
    result = ManipulationScoringResult(
        unique_id=7,
        name="T7",
        score=5,
        severity_tier=SeverityTier.MEDIUM,
        slack_state=SlackState.RECOVERING,
        period_a_predecessors=(_cdp(9, 7),),
        period_b_predecessors=(),
        skipped_cycle_participants_reference=participants,
        rationale="constraint removed; MSO predecessor present in period A",
    )
    assert result.skipped_cycle_participants_reference == participants
    assert isinstance(result.skipped_cycle_participants_reference, tuple)
    assert not isinstance(result.skipped_cycle_participants_reference, list)


# ----------------------------------------------------------------------
# Category D — Validator-raise cases
# ----------------------------------------------------------------------


def _summary_kwargs(**overrides: int) -> dict[str, int]:
    base: dict[str, int] = {
        "total_score": 0,
        "uid_count_high": 0,
        "uid_count_medium": 0,
        "uid_count_low": 0,
        "uid_count_joined_primary": 0,
        "uid_count_eroding_toward_primary": 0,
        "uid_count_stable": 0,
        "uid_count_recovering": 0,
    }
    base.update(overrides)
    return base


def test_total_score_negative_raises() -> None:
    """D1: total_score=-1 fails the Field(ge=0) bound."""
    with pytest.raises(ValidationError):
        ManipulationScoringSummary(**_summary_kwargs(total_score=-1))


def test_total_score_over_100_raises() -> None:
    """D2: total_score=101 fails the Field(le=100) bound — the
    Acumen-Fuse clamp safety net."""
    with pytest.raises(ValidationError):
        ManipulationScoringSummary(**_summary_kwargs(total_score=101))


def test_uid_count_high_negative_raises() -> None:
    """D3: uid_count_high=-1 fails Field(ge=0)."""
    with pytest.raises(ValidationError):
        ManipulationScoringSummary(**_summary_kwargs(uid_count_high=-1))


def test_uid_count_medium_negative_raises() -> None:
    """D4: uid_count_medium=-1 fails Field(ge=0)."""
    with pytest.raises(ValidationError):
        ManipulationScoringSummary(**_summary_kwargs(uid_count_medium=-1))


def test_uid_count_low_negative_raises() -> None:
    """D5: uid_count_low=-1 fails Field(ge=0).

    Completeness spot-check for the slack-state counts: a negative
    uid_count_stable also raises (same Field(ge=0) constraint family)."""
    with pytest.raises(ValidationError):
        ManipulationScoringSummary(**_summary_kwargs(uid_count_low=-1))
    with pytest.raises(ValidationError):
        ManipulationScoringSummary(**_summary_kwargs(uid_count_stable=-1))


def test_set_algebra_overlap_raises() -> None:
    """D6: ConstraintDrivenCrossVersionResult with overlapping
    added / retained sets (UID 2 in both) raises ValidationError on
    the set-algebra disjointness invariant. The error message names
    the overlapping UID(s)."""
    dpr = _empty_driving_path_result(1)
    with pytest.raises(ValidationError) as exc_info:
        ConstraintDrivenCrossVersionResult(
            period_a_result=dpr,
            period_b_result=dpr,
            added_constraint_driven_uids={1, 2},
            retained_constraint_driven_uids={2, 3},
        )
    assert "2" in str(exc_info.value)
