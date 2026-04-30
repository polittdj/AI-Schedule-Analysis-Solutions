"""Engine tests for the M11 manipulation scoring engine - Block 4.

Authority: BUILD-PLAN section 2.22(g) Block 4 floor - >=20 tests covering
state-machine transitions (8), scoring arithmetic (5), per-UID dedup (4),
and always-zero regression (3).

Block 4b will add 6 more tests (integration 3, schema invariants 3) to
hit the section 2.22(g) >=26 floor.

Most tests target the package-private inner helper
``_score_from_cross_version_result`` because building synthetic
CPMResults to drive the full ``score_manipulation`` facade is expensive.
End-to-end tests through the public facade are reserved for Block 4b's
integration category.
"""

from __future__ import annotations

import math
from datetime import datetime

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

# Package-private engine imports: these tests intentionally couple to
# the engine module's private constants and inner helper. Rationale:
#   * The four _SCORE_* constants and _AGGREGATE_SCORE_CLAMP_MAX are
#     the canonical numeric values that BUILD-PLAN §2.22(e) freezes;
#     asserting against the named constants (rather than re-typing
#     2/5/10/100 in the test bodies) means a future change to the
#     spec-frozen weights surfaces as an import error or a test
#     failure at exactly one site, not as silent test drift.
#   * _score_from_cross_version_result is the inner helper that
#     accepts a pre-built ConstraintDrivenCrossVersionResult and
#     returns a ManipulationScoringSummary, bypassing the full
#     score_manipulation facade. Building synthetic CPMResults to
#     drive the public facade is expensive; the inner helper keeps
#     these unit tests fast. End-to-end facade coverage is reserved
#     for Block 4b's integration category per BUILD-PLAN §2.22(k).
# Do NOT "promote" these imports to the public API surface; that is
# Block 5's responsibility per §2.22(k). Authority: PR #40 audit
# POTENTIAL_REVISION 4.
from app.engine.manipulation_scoring import (
    _AGGREGATE_SCORE_CLAMP_MAX,
    _SCORE_HIGH,
    _SCORE_LOW,
    _SCORE_MEDIUM,
    _score_from_cross_version_result,
)
from app.engine.manipulation_scoring_renderer import render_manipulation_scoring_summary
from app.models.calendar import Calendar
from app.models.enums import ConstraintType, RelationType
from app.models.schedule import Schedule
from app.models.task import Task

# Anchor datetimes for fixture construction. CDP.predecessor_constraint_date
# carries a Python datetime with no tz-aware requirement at the CDP level
# (the tz validators live on Task / Schedule, not CDP). The contracts test
# uses a naive datetime here too; mirroring keeps the two test files
# aligned.
_T0 = datetime(2026, 1, 1, 8, 0)
_T1 = datetime(2026, 1, 2, 16, 0)


# ----------------------------------------------------------------------
# Helper fixtures - mirror tests/contracts/test_manipulation_scoring.py
# patterns. Re-implemented here rather than imported so this file stays
# self-contained per the Block 4 step 2 audit guidance.
# ----------------------------------------------------------------------


def _cdp(
    pred_uid: int,
    succ_uid: int,
    *,
    slack_days: float = -1.0,
    constraint_type: ConstraintType = ConstraintType.MUST_START_ON,
    rationale: str = "negative slack held by MSO predecessor",
) -> ConstraintDrivenPredecessor:
    """Build a ConstraintDrivenPredecessor with sensible defaults.

    Defaults to MUST_START_ON (a HARD_CONSTRAINTS member) and slack -1.0
    days - well below the CDP validator floor of -1/86_400 days. Tests
    that need an off-anchor RECOVERING case override
    ``constraint_type`` to a non-hard value (e.g. SNET).
    """
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
    """Minimal DrivingPathResult containing only the focus node."""
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


def _dpr_with_skipped_participants(
    focus_uid: int,
    skipped: list[int],
) -> DrivingPathResult:
    """DrivingPathResult builder that injects skipped_cycle_participants.

    Used by tests that exercise the AM12 section 2.22(f)
    windowing_incomplete forensic-visibility flag - the flag does NOT
    alter slack-state classification or score, but the engine still
    computes it and the tests confirm scoring proceeds regardless.
    """
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
        skipped_cycle_participants=list(skipped),
    )


def _minimal_schedule(uids: list[int]) -> Schedule:
    """Schedule builder with Tasks for the supplied UIDs.

    Tasks default to AS_SOON_AS_POSSIBLE (no constraint_date required
    per Task validator G6) and zero duration. The engine only needs
    these tasks for the windowing-incomplete predecessor lookup; tests
    that don't exercise that path can pass an empty UID list.
    """
    tasks = [
        Task(
            unique_id=uid,
            task_id=uid,
            name=f"Task{uid}",
            constraint_type=ConstraintType.AS_SOON_AS_POSSIBLE,
        )
        for uid in uids
    ]
    return Schedule(
        name="test-schedule",
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        calendars=[Calendar(name="Standard")],
    )


def _make_cross_version_result(
    *,
    added: tuple[int, ...] = (),
    removed: tuple[int, ...] = (),
    retained: tuple[int, ...] = (),
    period_a_predecessors_by_successor: dict[int, tuple[ConstraintDrivenPredecessor, ...]]
    | None = None,
    period_b_predecessors_by_successor: dict[int, tuple[ConstraintDrivenPredecessor, ...]]
    | None = None,
    dpr_a: DrivingPathResult | None = None,
    dpr_b: DrivingPathResult | None = None,
    period_a_status_date: datetime | None = None,
    period_b_status_date: datetime | None = None,
) -> ConstraintDrivenCrossVersionResult:
    """Convenience builder for ConstraintDrivenCrossVersionResult.

    Defaults supply empty DPRs and empty predecessor dicts; tests
    override only the fields they exercise. The three set-algebra
    arguments must be pairwise disjoint (model-validated).
    """
    return ConstraintDrivenCrossVersionResult(
        period_a_result=dpr_a if dpr_a is not None else _empty_driving_path_result(1),
        period_b_result=dpr_b if dpr_b is not None else _empty_driving_path_result(1),
        period_a_status_date=period_a_status_date,
        period_b_status_date=period_b_status_date,
        added_constraint_driven_uids=set(added),
        removed_constraint_driven_uids=set(removed),
        retained_constraint_driven_uids=set(retained),
        period_a_predecessors_by_successor=period_a_predecessors_by_successor or {},
        period_b_predecessors_by_successor=period_b_predecessors_by_successor or {},
    )


def _score(
    cv: ConstraintDrivenCrossVersionResult,
    *,
    period_a: Schedule | None = None,
    period_b: Schedule | None = None,
) -> ManipulationScoringSummary:
    """Run the inner scorer against a cross-version result.

    Builds default empty Schedules when the caller does not supply
    them. ``project_calendar_hours_per_day`` is required on every
    Schedule and is set to the conventional 8.0.
    """
    sched_a = period_a if period_a is not None else _minimal_schedule([])
    sched_b = period_b if period_b is not None else _minimal_schedule([])
    return _score_from_cross_version_result(
        cross_version_result=cv,
        period_a=sched_a,
        period_b=sched_b,
    )


# ----------------------------------------------------------------------
# Category 1 - State-machine transitions (>=8 tests)
# Authority: AM12 section 2.22(d).
# ----------------------------------------------------------------------


def test_eroding_added_bucket_scores_high() -> None:
    """ADDED + Period B off-primary -> ERODING_TOWARD_PRIMARY -> HIGH (10).

    The ADDED-bucket state-machine transition with a HIGH outcome.

    Note on the JOINED_PRIMARY branch: the AM12 ADDED-bucket has two
    classifier outcomes per ``slack_state.py`` rows 1-2 - JOINED_PRIMARY
    (B on-primary) and ERODING_TOWARD_PRIMARY (B off-primary). Both
    classify HIGH. JOINED_PRIMARY is unreachable through this engine
    because (a) the CDP validator forbids ``slack_days >= -1.157e-5``
    while ``_on_primary`` requires ``|slack_days| < 1e-9``, AND (b)
    Pydantic v2 re-validates nested CDPs when the engine constructs
    its ``ManipulationScoringResult(period_b_predecessors=...)``
    emission - so even ``model_construct``-bypassed CDPs trip the
    validator at engine emission time. The classifier's on-primary
    branches (slack_state.py rows 1, 5) are unit-tested directly at
    the classifier layer in tests/engine/test_slack_state.py per
    Block 4 step 1; the engine layer can only exercise the
    off-primary ADDED branch, which is what this test does.
    """
    succ = 42
    cv = _make_cross_version_result(
        added=(succ,),
        period_b_predecessors_by_successor={
            succ: (_cdp(100, succ, slack_days=-1.0),),
        },
    )

    summary = _score(cv)

    assert summary.uid_count_high == 1
    assert summary.uid_count_eroding_toward_primary == 1
    assert summary.total_score == _SCORE_HIGH
    assert len(summary.per_uid_results) == 1
    record = summary.per_uid_results[0]
    assert record.unique_id == succ
    assert record.severity_tier == SeverityTier.HIGH
    assert record.slack_state == SlackState.ERODING_TOWARD_PRIMARY
    assert record.score == _SCORE_HIGH


def test_eroding_at_exactly_tolerance_classifies_as_stable_via_classifier() -> None:
    """RETAINED + |A_min - B_min| within 1e-9 -> STABLE (LOW, 2).

    Both slacks are well below the CDP validator floor of -1.157e-5,
    so normal validated construction works. The on-primary band is
    1e-9 absolute - here A and B differ by 1e-10 (inside the band).
    """
    succ = 7
    pred_a = _cdp(50, succ, slack_days=-1.0)
    pred_b = _cdp(50, succ, slack_days=-1.0 + 1e-10)
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (pred_a,)},
        period_b_predecessors_by_successor={succ: (pred_b,)},
    )

    summary = _score(cv)

    assert summary.uid_count_low == 1
    assert summary.uid_count_stable == 1
    assert summary.total_score == _SCORE_LOW
    assert math.isclose(pred_a.slack_days - pred_b.slack_days, -1e-10, abs_tol=1e-9)


def test_eroding_strictly_beyond_tolerance_classifies_as_eroding() -> None:
    """RETAINED + B more negative beyond tolerance -> ERODING -> HIGH (10)."""
    succ = 11
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (_cdp(60, succ, slack_days=-1.0),)},
        period_b_predecessors_by_successor={succ: (_cdp(60, succ, slack_days=-2.0),)},
    )

    summary = _score(cv)

    assert summary.uid_count_high == 1
    assert summary.uid_count_eroding_toward_primary == 1
    assert summary.total_score == _SCORE_HIGH
    record = summary.per_uid_results[0]
    assert record.slack_state == SlackState.ERODING_TOWARD_PRIMARY
    assert record.severity_tier == SeverityTier.HIGH


def test_stable_zero_delta_classifies_stable() -> None:
    """RETAINED + A_min == B_min exactly -> STABLE -> LOW (2)."""
    succ = 13
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (_cdp(70, succ, slack_days=-2.0),)},
        period_b_predecessors_by_successor={succ: (_cdp(70, succ, slack_days=-2.0),)},
    )

    summary = _score(cv)

    assert summary.uid_count_low == 1
    assert summary.uid_count_stable == 1
    assert summary.total_score == _SCORE_LOW


def test_stable_within_tolerance_classifies_stable() -> None:
    """RETAINED + A,B differ by < 1e-9 -> STABLE -> LOW (2)."""
    succ = 14
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (_cdp(80, succ, slack_days=-1.0),)},
        period_b_predecessors_by_successor={succ: (_cdp(80, succ, slack_days=-1.0 + 5e-10),)},
    )

    summary = _score(cv)

    assert summary.uid_count_low == 1
    assert summary.uid_count_stable == 1
    assert summary.total_score == _SCORE_LOW


def test_recovering_removed_bucket_no_hard_constraint_anchor() -> None:
    """REMOVED + no Period A hard-constraint anchor -> RECOVERING -> LOW (2).

    Uses START_NO_EARLIER_THAN (SNET), which is in DATE_BEARING_CONSTRAINTS
    but NOT in HARD_CONSTRAINTS. Constraint date is supplied per the
    Task G7 rule (irrelevant to CDP construction here, but consistent).
    """
    succ = 22
    cv = _make_cross_version_result(
        removed=(succ,),
        period_a_predecessors_by_successor={
            succ: (
                _cdp(
                    90,
                    succ,
                    slack_days=-1.0,
                    constraint_type=ConstraintType.START_NO_EARLIER_THAN,
                ),
            ),
        },
    )

    summary = _score(cv)

    assert summary.uid_count_low == 1
    assert summary.uid_count_recovering == 1
    assert summary.total_score == _SCORE_LOW
    record = summary.per_uid_results[0]
    assert record.slack_state == SlackState.RECOVERING
    assert record.severity_tier == SeverityTier.LOW


def test_recovering_with_hard_constraint_period_a_anchor_scores_medium() -> None:
    """REMOVED + Period A MSO anchor -> RECOVERING + hard anchor -> MEDIUM (5)."""
    succ = 23
    cv = _make_cross_version_result(
        removed=(succ,),
        period_a_predecessors_by_successor={
            succ: (
                _cdp(
                    91,
                    succ,
                    slack_days=-1.0,
                    constraint_type=ConstraintType.MUST_START_ON,
                ),
            ),
        },
    )

    summary = _score(cv)

    assert summary.uid_count_medium == 1
    assert summary.uid_count_recovering == 1
    assert summary.total_score == _SCORE_MEDIUM
    record = summary.per_uid_results[0]
    assert record.severity_tier == SeverityTier.MEDIUM
    assert record.slack_state == SlackState.RECOVERING
    assert record.score == _SCORE_MEDIUM


def test_recovering_retained_b_greater_than_a_classifies_recovering() -> None:
    """RETAINED + B less negative than A beyond tolerance -> RECOVERING.

    No hard-constraint anchor in Period A here (SNET only) -> tier LOW (2).
    """
    succ = 24
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={
            succ: (
                _cdp(
                    92,
                    succ,
                    slack_days=-2.0,
                    constraint_type=ConstraintType.START_NO_EARLIER_THAN,
                ),
            ),
        },
        period_b_predecessors_by_successor={
            succ: (
                _cdp(
                    92,
                    succ,
                    slack_days=-0.5,
                    constraint_type=ConstraintType.START_NO_EARLIER_THAN,
                ),
            ),
        },
    )

    summary = _score(cv)

    assert summary.uid_count_low == 1
    assert summary.uid_count_recovering == 1
    assert summary.total_score == _SCORE_LOW
    record = summary.per_uid_results[0]
    assert record.slack_state == SlackState.RECOVERING
    assert record.severity_tier == SeverityTier.LOW


# ----------------------------------------------------------------------
# Category 2 - Scoring arithmetic (>=5 tests)
# Authority: AM12 section 2.22(e) - per-UID weights and aggregate clamp.
# ----------------------------------------------------------------------


def test_high_severity_scores_ten() -> None:
    """Single HIGH UID (ERODING) -> total_score == 10, count_high == 1."""
    succ = 100
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (_cdp(200, succ, slack_days=-1.0),)},
        period_b_predecessors_by_successor={succ: (_cdp(200, succ, slack_days=-3.0),)},
    )

    summary = _score(cv)

    assert summary.total_score == _SCORE_HIGH
    assert summary.uid_count_high == 1
    assert summary.uid_count_medium == 0
    assert summary.uid_count_low == 0


def test_medium_severity_scores_five() -> None:
    """Single MEDIUM UID (RECOVERING + MFO anchor) -> total_score == 5."""
    succ = 101
    cv = _make_cross_version_result(
        removed=(succ,),
        period_a_predecessors_by_successor={
            succ: (
                _cdp(
                    201,
                    succ,
                    constraint_type=ConstraintType.MUST_FINISH_ON,
                ),
            ),
        },
    )

    summary = _score(cv)

    assert summary.total_score == _SCORE_MEDIUM
    assert summary.uid_count_medium == 1
    assert summary.uid_count_high == 0
    assert summary.uid_count_low == 0


def test_low_severity_scores_two() -> None:
    """Single LOW UID (STABLE retained) -> total_score == 2."""
    succ = 102
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (_cdp(202, succ, slack_days=-1.5),)},
        period_b_predecessors_by_successor={succ: (_cdp(202, succ, slack_days=-1.5),)},
    )

    summary = _score(cv)

    assert summary.total_score == _SCORE_LOW
    assert summary.uid_count_low == 1
    assert summary.uid_count_high == 0
    assert summary.uid_count_medium == 0


def test_three_high_uids_sum_to_thirty() -> None:
    """Three HIGH UIDs -> total_score == 30 (no clamp triggered)."""
    succs = (300, 301, 302)
    period_a = {uid: (_cdp(uid + 1000, uid, slack_days=-1.0),) for uid in succs}
    period_b = {uid: (_cdp(uid + 1000, uid, slack_days=-3.0),) for uid in succs}
    cv = _make_cross_version_result(
        retained=succs,
        period_a_predecessors_by_successor=period_a,
        period_b_predecessors_by_successor=period_b,
    )

    summary = _score(cv)

    assert summary.total_score == 30
    assert summary.uid_count_high == 3
    assert len(summary.per_uid_results) == 3


def test_fifteen_high_uids_clamp_to_one_hundred_exactly() -> None:
    """Fifteen HIGH UIDs -> total clamped to 100; per-UID list unscaled."""
    succs = tuple(range(400, 415))
    period_a = {uid: (_cdp(uid + 1000, uid, slack_days=-1.0),) for uid in succs}
    period_b = {uid: (_cdp(uid + 1000, uid, slack_days=-3.0),) for uid in succs}
    cv = _make_cross_version_result(
        retained=succs,
        period_a_predecessors_by_successor=period_a,
        period_b_predecessors_by_successor=period_b,
    )

    summary = _score(cv)

    assert summary.total_score == _AGGREGATE_SCORE_CLAMP_MAX
    assert summary.uid_count_high == 15
    assert len(summary.per_uid_results) == 15
    assert all(r.score == _SCORE_HIGH for r in summary.per_uid_results)


# ----------------------------------------------------------------------
# Category 3 - Per-UID dedup (>=4 tests)
# Authority: AM12 section 2.22(e) - one record per successor_uid.
# ----------------------------------------------------------------------


def test_one_uid_two_predecessors_yields_one_record() -> None:
    """RETAINED UID with two CDPs in Period B -> exactly one record."""
    succ = 500
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={
            succ: (_cdp(600, succ, slack_days=-1.0),),
        },
        period_b_predecessors_by_successor={
            succ: (
                _cdp(600, succ, slack_days=-2.0),
                _cdp(601, succ, slack_days=-2.5),
            ),
        },
    )

    summary = _score(cv)

    assert len(summary.per_uid_results) == 1
    record = summary.per_uid_results[0]
    assert record.unique_id == succ
    assert len(record.period_b_predecessors) == 2


def test_two_predecessors_same_tier_yields_single_record() -> None:
    """Two predecessors that classify the same way -> one record, single
    tier value, score == single tier weight (not summed)."""
    succ = 501
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={
            succ: (
                _cdp(610, succ, slack_days=-1.0),
                _cdp(611, succ, slack_days=-1.0),
            ),
        },
        period_b_predecessors_by_successor={
            succ: (
                _cdp(610, succ, slack_days=-3.0),
                _cdp(611, succ, slack_days=-3.0),
            ),
        },
    )

    summary = _score(cv)

    assert len(summary.per_uid_results) == 1
    record = summary.per_uid_results[0]
    assert record.severity_tier == SeverityTier.HIGH
    assert record.score == _SCORE_HIGH
    # Score is the single-tier weight, not 2 x _SCORE_HIGH.
    assert summary.total_score == _SCORE_HIGH


def test_one_uid_with_multiple_off_primary_predecessors_records_single_high() -> None:
    """Per-UID dedup: multiple ConstraintDrivenPredecessor edges sharing
    a successor_uid collapse into a single ManipulationScoringResult via
    structural set iteration; the SlackState classifier consumes the full
    predecessor tuple and emits one state via min-slack aggregation. The
    engine performs no per-edge tier classification or "highest tier
    wins" merging — see BUILD-PLAN §2.22(d) and §2.22(e) for the
    canonical per-UID semantics. Authority: PR #40 audit POTENTIAL_REVISION 2.
    """
    succ = 502
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={
            succ: (_cdp(620, succ, slack_days=-1.0),),
        },
        period_b_predecessors_by_successor={
            succ: (
                _cdp(620, succ, slack_days=-1.0),
                _cdp(621, succ, slack_days=-5.0),
            ),
        },
    )

    summary = _score(cv)

    assert len(summary.per_uid_results) == 1
    record = summary.per_uid_results[0]
    assert record.severity_tier == SeverityTier.HIGH
    assert record.score == _SCORE_HIGH


def test_one_uid_with_three_off_primary_predecessors_records_single_high() -> None:
    """Per-UID dedup: multiple ConstraintDrivenPredecessor edges sharing
    a successor_uid collapse into a single ManipulationScoringResult via
    structural set iteration; the SlackState classifier consumes the full
    predecessor tuple and emits one state via min-slack aggregation. The
    engine performs no per-edge tier classification or "highest tier
    wins" merging — see BUILD-PLAN §2.22(d) and §2.22(e) for the
    canonical per-UID semantics. Authority: PR #40 audit POTENTIAL_REVISION 2.
    """
    succ = 503
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={
            succ: (
                _cdp(
                    630,
                    succ,
                    slack_days=-1.0,
                    constraint_type=ConstraintType.MUST_START_ON,
                ),
                _cdp(
                    631,
                    succ,
                    slack_days=-2.0,
                    constraint_type=ConstraintType.START_NO_EARLIER_THAN,
                ),
            ),
        },
        period_b_predecessors_by_successor={
            succ: (
                _cdp(630, succ, slack_days=-4.0),
                _cdp(631, succ, slack_days=-5.0),
            ),
        },
    )

    summary = _score(cv)

    assert len(summary.per_uid_results) == 1
    record = summary.per_uid_results[0]
    assert record.severity_tier == SeverityTier.HIGH
    assert record.score == _SCORE_HIGH
    assert summary.total_score == _SCORE_HIGH


# ----------------------------------------------------------------------
# Category 4 - Always-zero regression (>=3 tests)
# Authority: AM12 section 2.22(g) - clean schedule pair returns 0.
# ----------------------------------------------------------------------


def test_empty_buckets_yield_zero_total_score() -> None:
    """Always-zero floor: when both Period A and Period B have empty
    constraint-driven predecessor buckets — i.e., no CDPs at all — the
    engine yields total_score == 0 with no per-UID records. Note this
    test exercises the empty-bucket short-circuit; identical-with-content
    Period A/B is covered by
    test_identical_retained_cdps_classify_stable_and_yield_low_score.
    Authority: BUILD-PLAN §2.22(g); PR #40 audit POTENTIAL_REVISION 3.
    """
    cv = _make_cross_version_result()

    summary = _score(cv)

    assert summary.total_score == 0
    assert summary.uid_count_high == 0
    assert summary.uid_count_medium == 0
    assert summary.uid_count_low == 0
    assert summary.uid_count_joined_primary == 0
    assert summary.uid_count_eroding_toward_primary == 0
    assert summary.uid_count_stable == 0
    assert summary.uid_count_recovering == 0
    assert summary.per_uid_results == ()


def test_identical_retained_cdps_classify_stable_and_yield_low_score() -> None:
    """Hardens the always-zero semantic boundary: identical-with-content
    Period A and Period B do NOT yield zero — they classify STABLE per
    UID and contribute LOW (score 2) per UID per §2.22(d) state-machine
    and §2.22(e) weights. This is the test the BUILD-PLAN §2.22(g) line
    "identical Period A and Period B → total_score = 0" wording could
    easily be misread as covering. Pin the non-zero LOW outcome
    explicitly so a future regression that conflates "identical
    periods" with "always-zero" surfaces here. Authority: BUILD-PLAN
    §2.22(d), §2.22(e), §2.22(g); PR #40 audit POTENTIAL_REVISION 3.
    """
    # Identical retained CDPs in both periods: same successor_uid, same
    # predecessor_uid, same slack_days (-1.0, comfortably outside the
    # _ZERO_SLACK_TOLERANCE_DAYS = 1.157e-5 boundary on the negative
    # side), same constraint_type. Mirrors the construction idiom of
    # the neighboring retained-bucket tests (e.g.
    # test_low_severity_scores_two, test_stable_zero_delta_classifies_stable).
    succ = 700
    cv = _make_cross_version_result(
        retained=(succ,),
        period_a_predecessors_by_successor={succ: (_cdp(800, succ, slack_days=-1.0),)},
        period_b_predecessors_by_successor={succ: (_cdp(800, succ, slack_days=-1.0),)},
    )

    summary = _score(cv)

    assert summary.total_score == _SCORE_LOW
    assert len(summary.per_uid_results) == 1
    assert summary.per_uid_results[0].slack_state == SlackState.STABLE
    assert summary.per_uid_results[0].severity_tier == SeverityTier.LOW
    assert summary.per_uid_results[0].score == _SCORE_LOW


def test_both_periods_no_constraint_driven_predecessors_yields_zero() -> None:
    """All three buckets empty even when status dates are populated.

    Confirms the empty-bucket short-circuit does not depend on the
    AM13 status-date / project-start fields - those carry timeline
    metadata used by downstream renderers but never gate scoring.
    """
    sd_a = datetime(2026, 1, 15, 8, 0)
    sd_b = datetime(2026, 2, 14, 8, 0)
    cv = _make_cross_version_result(
        period_a_status_date=sd_a,
        period_b_status_date=sd_b,
    )

    summary = _score(cv)

    assert summary.total_score == 0
    assert summary.per_uid_results == ()


def test_status_date_filter_drains_all_candidates_yields_zero() -> None:
    """Comparator's status-date filter drained every candidate -> 0.

    The AM12 section 2.22(f) windowing filter runs in Block 3; the
    cross-version result consumed by the engine is already filtered.
    Simulate a fully-drained comparator output by constructing a CDR
    with empty predecessor dicts despite the comparator having
    plausibly examined a non-trivial schedule pair (status dates set).
    """
    cv = _make_cross_version_result(
        period_a_status_date=datetime(2026, 1, 15, 8, 0),
        period_b_status_date=datetime(2026, 2, 14, 8, 0),
    )

    summary = _score(cv)

    assert summary.total_score == 0
    assert summary.uid_count_high == 0
    assert summary.uid_count_medium == 0
    assert summary.uid_count_low == 0
    assert summary.per_uid_results == ()


# ----------------------------------------------------------------------
# Category 5 - Integration (>=3 tests)
# Authority: AM12 section 2.22(g) - Block 4b renderer integration tests
# closing the §2.22(g) Category 5 deficit deferred by Block 4. Exercises
# render_manipulation_scoring_summary against ManipulationScoringSummary
# instances constructed via Pydantic directly (no engine round-trip).
# ----------------------------------------------------------------------


def test_render_returns_expected_dict_for_synthetic_summary() -> None:
    """Synthetic three-row summary renders to the §2.22(i) dict shape.

    Verifies the full renderer projection: total_score, severity_banner,
    uid_counts_by_severity, uid_counts_by_slack_state, and rows with the
    six prescribed columns. total_score=15 falls in the [1, 25) band so
    severity_banner == "low".
    """
    high_result = ManipulationScoringResult(
        unique_id=100,
        name="task-100",
        score=_SCORE_HIGH,
        severity_tier=SeverityTier.HIGH,
        slack_state=SlackState.JOINED_PRIMARY,
        rationale="HIGH rationale",
    )
    medium_result = ManipulationScoringResult(
        unique_id=200,
        name="task-200",
        score=_SCORE_MEDIUM,
        severity_tier=SeverityTier.MEDIUM,
        slack_state=SlackState.RECOVERING,
        rationale="MEDIUM rationale",
    )
    low_result = ManipulationScoringResult(
        unique_id=300,
        name="task-300",
        score=_SCORE_LOW,
        severity_tier=SeverityTier.LOW,
        slack_state=SlackState.ERODING_TOWARD_PRIMARY,
        rationale="LOW rationale",
    )
    summary = ManipulationScoringSummary(
        total_score=15,
        uid_count_high=1,
        uid_count_medium=1,
        uid_count_low=1,
        uid_count_joined_primary=1,
        uid_count_eroding_toward_primary=1,
        uid_count_stable=0,
        uid_count_recovering=1,
        per_uid_results=(high_result, medium_result, low_result),
    )

    rendered = render_manipulation_scoring_summary(summary)

    assert rendered == {
        "total_score": 15,
        "severity_banner": "low",
        "uid_counts_by_severity": {
            "high": 1,
            "medium": 1,
            "low": 1,
        },
        "uid_counts_by_slack_state": {
            "joined_primary": 1,
            "eroding_toward_primary": 1,
            "stable": 0,
            "recovering": 1,
        },
        "rows": [
            {
                "unique_id": 100,
                "name": "task-100",
                "score": _SCORE_HIGH,
                "severity_tier": "high",
                "slack_state": "joined_primary",
                "rationale": "HIGH rationale",
            },
            {
                "unique_id": 200,
                "name": "task-200",
                "score": _SCORE_MEDIUM,
                "severity_tier": "medium",
                "slack_state": "recovering",
                "rationale": "MEDIUM rationale",
            },
            {
                "unique_id": 300,
                "name": "task-300",
                "score": _SCORE_LOW,
                "severity_tier": "low",
                "slack_state": "eroding_toward_primary",
                "rationale": "LOW rationale",
            },
        ],
    }


def test_render_handles_empty_summary() -> None:
    """Empty summary renders with all required keys, rows=[], banner='clean'.

    Empty-safe behavior: every top-level key is present even with zero
    per-UID records and zero counts; rows is the empty list, not a
    missing key. severity_banner == "clean" is the total_score==0 band.
    """
    summary = ManipulationScoringSummary(
        total_score=0,
        uid_count_high=0,
        uid_count_medium=0,
        uid_count_low=0,
        uid_count_joined_primary=0,
        uid_count_eroding_toward_primary=0,
        uid_count_stable=0,
        uid_count_recovering=0,
        per_uid_results=(),
    )

    rendered = render_manipulation_scoring_summary(summary)

    assert rendered == {
        "total_score": 0,
        "severity_banner": "clean",
        "uid_counts_by_severity": {"high": 0, "medium": 0, "low": 0},
        "uid_counts_by_slack_state": {
            "joined_primary": 0,
            "eroding_toward_primary": 0,
            "stable": 0,
            "recovering": 0,
        },
        "rows": [],
    }


def test_render_preserves_contract_sort_order_in_rows() -> None:
    """Rows preserve summary.per_uid_results order; combined invariant check.

    Verifies two invariants in one assertion:
      (a) Renderer preserves input order (does NOT re-sort).
      (b) Input is contract-sorted to begin with, where the contract
          sort is (severity_tier desc, unique_id asc) — within HIGH
          tier, lower unique_id comes first.

    Build sequence: HIGH uid=100, HIGH uid=200, MEDIUM uid=50, LOW
    uid=10 (the contract-correct order). Rendered row unique_ids must
    appear as [100, 200, 50, 10].
    """
    high_low_uid = ManipulationScoringResult(
        unique_id=100,
        name="task-100",
        score=_SCORE_HIGH,
        severity_tier=SeverityTier.HIGH,
        slack_state=SlackState.JOINED_PRIMARY,
        rationale="r-100",
    )
    high_high_uid = ManipulationScoringResult(
        unique_id=200,
        name="task-200",
        score=_SCORE_HIGH,
        severity_tier=SeverityTier.HIGH,
        slack_state=SlackState.ERODING_TOWARD_PRIMARY,
        rationale="r-200",
    )
    medium_result = ManipulationScoringResult(
        unique_id=50,
        name="task-50",
        score=_SCORE_MEDIUM,
        severity_tier=SeverityTier.MEDIUM,
        slack_state=SlackState.RECOVERING,
        rationale="r-50",
    )
    low_result = ManipulationScoringResult(
        unique_id=10,
        name="task-10",
        score=_SCORE_LOW,
        severity_tier=SeverityTier.LOW,
        slack_state=SlackState.STABLE,
        rationale="r-10",
    )
    summary = ManipulationScoringSummary(
        total_score=27,
        uid_count_high=2,
        uid_count_medium=1,
        uid_count_low=1,
        uid_count_joined_primary=1,
        uid_count_eroding_toward_primary=1,
        uid_count_stable=1,
        uid_count_recovering=1,
        per_uid_results=(high_low_uid, high_high_uid, medium_result, low_result),
    )

    rendered = render_manipulation_scoring_summary(summary)

    rendered_uids = [row["unique_id"] for row in rendered["rows"]]
    assert rendered_uids == [100, 200, 50, 10]


# ----------------------------------------------------------------------
# Category 6 - Schema invariant (>=3 tests)
# Authority: AM12 section 2.22(g) - Block 4b renderer schema invariants
# closing the §2.22(g) Category 6 deficit deferred by Block 4. Pinned
# top-level keys, banner-band boundaries, and the StrEnum value-string
# convention are renderer-version-drift detectors.
# ----------------------------------------------------------------------


def test_render_dict_contains_required_top_level_keys() -> None:
    """Rendered dict carries every §2.22(i) prescribed top-level key.

    Forward-compatibility headroom via subset comparison: future
    additive keys are permitted, but the five required keys must all
    be present on every render call regardless of summary content.
    """
    summary = ManipulationScoringSummary(
        total_score=0,
        uid_count_high=0,
        uid_count_medium=0,
        uid_count_low=0,
        uid_count_joined_primary=0,
        uid_count_eroding_toward_primary=0,
        uid_count_stable=0,
        uid_count_recovering=0,
        per_uid_results=(),
    )
    required = {
        "total_score",
        "severity_banner",
        "uid_counts_by_severity",
        "uid_counts_by_slack_state",
        "rows",
    }

    rendered = render_manipulation_scoring_summary(summary)

    assert set(rendered.keys()) >= required


def test_render_severity_banner_thresholds() -> None:
    """Banner-band boundaries match the §2.22(i) build-chat banner table.

    Boundary cases pinned in both directions: the upper-edge of each
    band and the lower-edge of the next band must classify correctly.
    Bands: clean=0, low=[1,25), moderate=[25,50), high=[50,75),
    critical=[75,100].
    """
    cases: list[tuple[int, str]] = [
        (0, "clean"),
        (1, "low"),
        (24, "low"),
        (25, "moderate"),
        (49, "moderate"),
        (50, "high"),
        (74, "high"),
        (75, "critical"),
        (100, "critical"),
    ]
    for total_score, expected_banner in cases:
        summary = ManipulationScoringSummary(
            total_score=total_score,
            uid_count_high=0,
            uid_count_medium=0,
            uid_count_low=0,
            uid_count_joined_primary=0,
            uid_count_eroding_toward_primary=0,
            uid_count_stable=0,
            uid_count_recovering=0,
            per_uid_results=(),
        )
        rendered = render_manipulation_scoring_summary(summary)
        assert rendered["severity_banner"] == expected_banner, (
            f"total_score={total_score} produced banner "
            f"{rendered['severity_banner']!r}, expected {expected_banner!r}"
        )


def test_render_strenum_fields_are_value_strings_not_enum_objects() -> None:
    """severity_tier and slack_state on rows are .value strings, not enum members.

    StrEnum convention: rendered dict carries no enum instances; only
    the lowercase string identity from SeverityTier.value /
    SlackState.value is exposed to downstream consumers.

    Discrimination matters because StrEnum is a str subclass — both
    isinstance(SeverityTier.HIGH, str) and SeverityTier.HIGH == "high"
    evaluate True. To actually catch a regression where the renderer
    drops .value and emits the enum member directly, this test uses
    type(x) is str (strict identity, False for enum members) AND
    not isinstance(x, SeverityTier/SlackState) as discriminating
    predicates. Authority: Block 4b post-audit revision per audit
    verdict 2026-04-30T19:08:51Z.
    """
    result = ManipulationScoringResult(
        unique_id=42,
        name="task-42",
        score=_SCORE_HIGH,
        severity_tier=SeverityTier.HIGH,
        slack_state=SlackState.JOINED_PRIMARY,
        rationale="r-42",
    )
    summary = ManipulationScoringSummary(
        total_score=10,
        uid_count_high=1,
        uid_count_medium=0,
        uid_count_low=0,
        uid_count_joined_primary=1,
        uid_count_eroding_toward_primary=0,
        uid_count_stable=0,
        uid_count_recovering=0,
        per_uid_results=(result,),
    )

    rendered = render_manipulation_scoring_summary(summary)
    row = rendered["rows"][0]

    # type(x) is str — strict identity check; would fail if x were a
    # SeverityTier/SlackState member (StrEnum is a str subclass so
    # isinstance(x, str) passes for both members and plain str).
    assert type(row["severity_tier"]) is str
    assert not isinstance(row["severity_tier"], SeverityTier)
    assert row["severity_tier"] == "high"
    assert type(row["slack_state"]) is str
    assert not isinstance(row["slack_state"], SlackState)
    assert row["slack_state"] == "joined_primary"
