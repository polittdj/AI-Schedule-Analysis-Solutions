"""M11 manipulation scoring engine - Block 4.

Authority: BUILD-PLAN sections 2.22 (AM12, 4/23/2026) subsections (d),
(e), (f); 2.23 (AM13, 4/24/2026).

This module consumes a frozen
:class:`~app.contracts.manipulation_scoring.ConstraintDrivenCrossVersionResult`
emitted by the Block 3 comparator
(:func:`app.engine.constraint_driven_cross_version.compare_constraint_driven_cross_version`)
and produces a frozen
:class:`~app.contracts.manipulation_scoring.ManipulationScoringSummary`.
The summary is the M11 public emission consumed by the M12 AI narrative
layer and the M13 Flask UI.

The Block 3 comparator already applies the AM12 subsection (f)
status-date filter to its predecessor edges. Block 4 does NOT
re-filter; it consumes the pre-filtered per-successor predecessor
dicts as-is and only sets ``windowing_incomplete`` as a forensic-
visibility flag.

Public surface (frozen by AM12 subsection (h)): exactly
:func:`score_manipulation`.

STATE MACHINE - per AM12 section 2.22(d)
==================================
Each successor_uid in the comparator's three sets gets exactly one
SlackState. The four states are mutually exclusive and exhaustive.
Tolerance band: +/- 1/86,400 days (encoded in app/engine/slack_state.py
as _ON_PRIMARY_ABS_TOL=1e-9 - engine delegates classification to
classify_slack_state).

- JOINED_PRIMARY        - UID in added_constraint_driven_uids.
- ERODING_TOWARD_PRIMARY - UID in retained, B_min_DS strictly less
                           than A_min_DS outside tolerance band.
- STABLE                 - UID in retained, B_min_DS ~ A_min_DS
                           within tolerance band.
- RECOVERING             - UID in removed, OR retained with
                           B_min_DS strictly greater than A_min_DS
                           outside tolerance band.

SEVERITY TIER ASSIGNMENT - per AM12 section 2.22(e)
=============================================
Encoded behavior. If this table and the implementation diverge,
treat the table as authoritative and patch the implementation.

tier   | conditions
-------|------------------------------------------------------------
HIGH   | slack_state == JOINED_PRIMARY
       | OR slack_state == ERODING_TOWARD_PRIMARY
MEDIUM | slack_state == RECOVERING AND any contributing Period A
       | predecessor's predecessor_constraint_type is in
       | HARD_CONSTRAINTS (MSO, MFO, SNLT, FNLT)
LOW    | slack_state == STABLE
       | OR slack_state == RECOVERING with no hard-constraint
       |    Period A anchor

PER-UID DEDUPLICATION - per AM12 section 2.22(e)
==========================================
A single successor_uid produces exactly one ManipulationScoringResult
regardless of how many ConstraintDrivenPredecessor edges it carries.
Score is a single tier value (10/5/2), never a sum.

AGGREGATE CLAMP - per AM12 section 2.22(e)
====================================
total_score = min(sum(per_uid_scores), 100). Clamping happens
IN THIS ENGINE before constructing ManipulationScoringSummary.
The Field(ge=0, le=100) on the summary is a safety-net validator,
not the clamp mechanism.

STATUS-DATE FILTER - per AM12 section 2.22(f)
=======================================
The comparator (Block 3) reuses
app.engine.windowing.is_legitimate_actual to filter
ConstraintDrivenPredecessor edges. The
ConstraintDrivenCrossVersionResult consumed here ALREADY has
filtered predecessors by-successor dicts. Block 4 does NOT
re-filter.

windowing_incomplete is set True on a per-UID record when ANY of:
- The cross-version result's period_b_status_date is None.
- For any contributing predecessor in either period, the
  predecessor task can't be looked up in its Schedule.
- For any contributing predecessor in either period, the
  predecessor_uid is in
  period_a_result.skipped_cycle_participants OR
  period_b_result.skipped_cycle_participants.
"""

from __future__ import annotations

from app.contracts.manipulation_scoring import (
    ConstraintDrivenCrossVersionResult,
    ManipulationScoringResult,
    ManipulationScoringSummary,
    SeverityTier,
    SlackState,
)
from app.engine.constraint_driven_cross_version import (
    compare_constraint_driven_cross_version,
)
from app.engine.driving_path import trace_driving_path
from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathResult,
    FocusPointAnchor,
)
from app.engine.result import CPMResult
from app.engine.slack_state import SetMembership, classify_slack_state
from app.models.enums import HARD_CONSTRAINTS
from app.models.schedule import Schedule
from app.models.task import Task

# Authority: AM12 section 2.22(e). Per-UID weighted-Acumen-Fuse scores.
# Frozen integer values; not operator-tunable in M11.
_SCORE_HIGH: int = 10
_SCORE_MEDIUM: int = 5
_SCORE_LOW: int = 2

# Authority: AM12 section 2.22(e) "Aggregate score clamping" - sum of
# per-UID scores is clamped to [0, 100] before summary construction.
# Inclusive upper bound.
_AGGREGATE_SCORE_CLAMP_MAX: int = 100

# Authority: AM12 section 2.22(e) - sort summary by (severity_tier desc,
# unique_id asc). HIGH > MEDIUM > LOW. Lower integer = higher
# severity for ascending sort, equivalent to severity descending.
_SEVERITY_SORT_RANK: dict[SeverityTier, int] = {
    SeverityTier.HIGH: 0,
    SeverityTier.MEDIUM: 1,
    SeverityTier.LOW: 2,
}


def _select_membership(
    uid: int,
    cross_version_result: ConstraintDrivenCrossVersionResult,
) -> SetMembership:
    """Map a UID to its SetMembership bucket per AM12 section 2.22(d).

    The three set-algebra fields on ConstraintDrivenCrossVersionResult
    are pairwise disjoint (model-validated); exactly one of the three
    branches matches for any UID drawn from their union.
    """
    if uid in cross_version_result.added_constraint_driven_uids:
        return SetMembership.ADDED
    if uid in cross_version_result.removed_constraint_driven_uids:
        return SetMembership.REMOVED
    return SetMembership.RETAINED


def _has_hard_constraint_in_period_a(
    predecessors_a: tuple[ConstraintDrivenPredecessor, ...],
) -> bool:
    """Return True iff any Period A predecessor carries a hard constraint.

    Authority: AM12 section 2.22(e) MEDIUM tier rule. The DCMA Metric 5
    hard constraints (MSO / MFO / SNLT / FNLT) are the canonical
    AM10/AM12 anchor for the recovering-but-formerly-anchored case.
    """
    return any(p.predecessor_constraint_type in HARD_CONSTRAINTS for p in predecessors_a)


def _compute_severity_tier(
    slack_state: SlackState,
    period_a_predecessors: tuple[ConstraintDrivenPredecessor, ...],
) -> SeverityTier:
    """Apply the AM12 section 2.22(e) severity tier rules.

    HIGH: JOINED_PRIMARY or ERODING_TOWARD_PRIMARY.
    MEDIUM: RECOVERING with at least one Period A hard-constraint anchor.
    LOW: STABLE, or RECOVERING with no hard-constraint Period A anchor.
    """
    if slack_state in (SlackState.JOINED_PRIMARY, SlackState.ERODING_TOWARD_PRIMARY):
        return SeverityTier.HIGH
    if slack_state == SlackState.RECOVERING and _has_hard_constraint_in_period_a(
        period_a_predecessors
    ):
        return SeverityTier.MEDIUM
    return SeverityTier.LOW


def _compute_score(severity_tier: SeverityTier) -> int:
    """Map SeverityTier to integer per-UID score per AM12 section 2.22(e)."""
    if severity_tier == SeverityTier.HIGH:
        return _SCORE_HIGH
    if severity_tier == SeverityTier.MEDIUM:
        return _SCORE_MEDIUM
    return _SCORE_LOW


def _compose_rationale(
    *,
    slack_state: SlackState,
    severity_tier: SeverityTier,
    period_a_predecessors: tuple[ConstraintDrivenPredecessor, ...],
    period_b_predecessors: tuple[ConstraintDrivenPredecessor, ...],
    windowing_incomplete: bool,
) -> str:
    """Compose the deterministic ASCII rationale per AM12 section 2.22(c).

    Period A and Period B predecessor rationales are sorted by
    predecessor_uid ascending and joined with ``"; "``. The literal
    string ``"none"`` stands in when a side has no predecessors.
    """
    a_sorted = sorted(period_a_predecessors, key=lambda p: p.predecessor_uid)
    b_sorted = sorted(period_b_predecessors, key=lambda p: p.predecessor_uid)
    a_text = "; ".join(p.rationale for p in a_sorted) if a_sorted else "none"
    b_text = "; ".join(p.rationale for p in b_sorted) if b_sorted else "none"
    suffix = (
        " Windowing incomplete; downstream consumers may degrade severity."
        if windowing_incomplete
        else ""
    )
    return (
        f"Slack state {slack_state.value}; severity tier {severity_tier.value}. "
        f"Period A: {a_text}. Period B: {b_text}.{suffix}"
    )


def _select_name(
    *,
    uid: int,
    period_a_result: DrivingPathResult,
    period_b_result: DrivingPathResult,
    tasks_a: dict[int, Task],
    tasks_b: dict[int, Task],
) -> str:
    """Pick the per-UID display name per AM12 section 2.22(c).

    Period B node first (current-period authority), Period A node next,
    schedule task lookup as last resort. Returns empty string only if
    the UID exists in none of the four sources - which violates the
    cross-version-result invariant and indicates upstream data
    corruption.
    """
    b_node = period_b_result.nodes.get(uid)
    if b_node is not None:
        return b_node.name
    a_node = period_a_result.nodes.get(uid)
    if a_node is not None:
        return a_node.name
    b_task = tasks_b.get(uid)
    if b_task is not None:
        return b_task.name
    a_task = tasks_a.get(uid)
    if a_task is not None:
        return a_task.name
    return ""


def _select_skipped_cycle_participants_reference(
    *,
    predecessors_a: tuple[ConstraintDrivenPredecessor, ...],
    predecessors_b: tuple[ConstraintDrivenPredecessor, ...],
    period_a_skipped: list[int],
    period_b_skipped: list[int],
) -> tuple[int, ...]:
    """Return contributing predecessor UIDs that overlap M10.2 cycle skips.

    Authority: AM12 section 2.22(c) skipped_cycle_participants_reference
    field; BUILD-PLAN section 2.21 (AM11) M10.2 skipped_cycle_participants.
    Forensic-visibility trail - empty when no cycle participant touches
    this UID.
    """
    contributing_uids = {p.predecessor_uid for p in predecessors_a} | {
        p.predecessor_uid for p in predecessors_b
    }
    skipped_union = set(period_a_skipped) | set(period_b_skipped)
    return tuple(sorted(contributing_uids & skipped_union))


def _is_windowing_incomplete(
    *,
    predecessors_a: tuple[ConstraintDrivenPredecessor, ...],
    predecessors_b: tuple[ConstraintDrivenPredecessor, ...],
    cross_version_result: ConstraintDrivenCrossVersionResult,
    tasks_a: dict[int, Task],
    tasks_b: dict[int, Task],
) -> bool:
    """Compute the per-UID windowing_incomplete flag per AM12 section 2.22(f).

    True when any of the three forensic-visibility conditions hold; see
    the module docstring "STATUS-DATE FILTER" section for the
    enumeration. The flag does not gate scoring - the record is always
    retained per the contract on ManipulationScoringResult.
    """
    if cross_version_result.period_b_status_date is None:
        return True

    skipped_union = set(cross_version_result.period_a_result.skipped_cycle_participants) | set(
        cross_version_result.period_b_result.skipped_cycle_participants
    )

    for pred in predecessors_a:
        if pred.predecessor_uid not in tasks_a:
            return True
        if pred.predecessor_uid in skipped_union:
            return True
    for pred in predecessors_b:
        if pred.predecessor_uid not in tasks_b:
            return True
        if pred.predecessor_uid in skipped_union:
            return True
    return False


def _score_uid(
    *,
    uid: int,
    cross_version_result: ConstraintDrivenCrossVersionResult,
    tasks_a: dict[int, Task],
    tasks_b: dict[int, Task],
) -> ManipulationScoringResult:
    """Compose a ManipulationScoringResult for a single UID per AM12 section 2.22(d)(e)(f).

    Per-UID worker. Looks up the contributing predecessor tuples,
    delegates classification to :func:`classify_slack_state`, applies
    the severity tier rules, and assembles the frozen record.
    """
    membership = _select_membership(uid, cross_version_result)
    predecessors_a = cross_version_result.period_a_predecessors_by_successor.get(uid, ())
    predecessors_b = cross_version_result.period_b_predecessors_by_successor.get(uid, ())

    windowing_incomplete = _is_windowing_incomplete(
        predecessors_a=predecessors_a,
        predecessors_b=predecessors_b,
        cross_version_result=cross_version_result,
        tasks_a=tasks_a,
        tasks_b=tasks_b,
    )

    slack_state = classify_slack_state(
        membership=membership,
        period_a_predecessors=predecessors_a,
        period_b_predecessors=predecessors_b,
        windowing_incomplete=windowing_incomplete,
    )

    severity_tier = _compute_severity_tier(slack_state, predecessors_a)
    score = _compute_score(severity_tier)

    name = _select_name(
        uid=uid,
        period_a_result=cross_version_result.period_a_result,
        period_b_result=cross_version_result.period_b_result,
        tasks_a=tasks_a,
        tasks_b=tasks_b,
    )

    rationale = _compose_rationale(
        slack_state=slack_state,
        severity_tier=severity_tier,
        period_a_predecessors=predecessors_a,
        period_b_predecessors=predecessors_b,
        windowing_incomplete=windowing_incomplete,
    )

    skipped_reference = _select_skipped_cycle_participants_reference(
        predecessors_a=predecessors_a,
        predecessors_b=predecessors_b,
        period_a_skipped=cross_version_result.period_a_result.skipped_cycle_participants,
        period_b_skipped=cross_version_result.period_b_result.skipped_cycle_participants,
    )

    return ManipulationScoringResult(
        unique_id=uid,
        name=name,
        score=score,
        severity_tier=severity_tier,
        slack_state=slack_state,
        period_a_predecessors=predecessors_a,
        period_b_predecessors=predecessors_b,
        skipped_cycle_participants_reference=skipped_reference,
        windowing_incomplete=windowing_incomplete,
        rationale=rationale,
    )


def _score_from_cross_version_result(
    *,
    cross_version_result: ConstraintDrivenCrossVersionResult,
    period_a: Schedule,
    period_b: Schedule,
) -> ManipulationScoringSummary:
    """Score a pre-built ConstraintDrivenCrossVersionResult.

    Package-private inner core for score_manipulation. Tests target
    this helper because building synthetic CPMResults to drive the
    full facade is expensive. Authority: AM12 section 2.22(d)(e)(f).
    """
    tasks_a: dict[int, Task] = {t.unique_id: t for t in period_a.tasks}
    tasks_b: dict[int, Task] = {t.unique_id: t for t in period_b.tasks}

    all_uids: set[int] = (
        cross_version_result.added_constraint_driven_uids
        | cross_version_result.removed_constraint_driven_uids
        | cross_version_result.retained_constraint_driven_uids
    )

    if not all_uids:
        return ManipulationScoringSummary(
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

    per_uid_records: list[ManipulationScoringResult] = [
        _score_uid(
            uid=uid,
            cross_version_result=cross_version_result,
            tasks_a=tasks_a,
            tasks_b=tasks_b,
        )
        for uid in sorted(all_uids)
    ]

    uid_count_high = sum(1 for r in per_uid_records if r.severity_tier == SeverityTier.HIGH)
    uid_count_medium = sum(1 for r in per_uid_records if r.severity_tier == SeverityTier.MEDIUM)
    uid_count_low = sum(1 for r in per_uid_records if r.severity_tier == SeverityTier.LOW)

    uid_count_joined_primary = sum(
        1 for r in per_uid_records if r.slack_state == SlackState.JOINED_PRIMARY
    )
    uid_count_eroding_toward_primary = sum(
        1 for r in per_uid_records if r.slack_state == SlackState.ERODING_TOWARD_PRIMARY
    )
    uid_count_stable = sum(1 for r in per_uid_records if r.slack_state == SlackState.STABLE)
    uid_count_recovering = sum(1 for r in per_uid_records if r.slack_state == SlackState.RECOVERING)

    # Lower bound is explicit per docstring's [0, 100] contract. Currently
    # safe because _compute_score returns only 2/5/10, but a future change
    # introducing a negative or float score would silently produce a
    # negative total_score absent this max(0, ...). Cheap defensive parity
    # with the upper-bound clamp; do not remove without revisiting the
    # docstring's [0, 100] guarantee.
    total_score = max(0, min(sum(r.score for r in per_uid_records), _AGGREGATE_SCORE_CLAMP_MAX))

    sorted_records = tuple(
        sorted(
            per_uid_records,
            key=lambda r: (_SEVERITY_SORT_RANK[r.severity_tier], r.unique_id),
        )
    )

    return ManipulationScoringSummary(
        total_score=total_score,
        uid_count_high=uid_count_high,
        uid_count_medium=uid_count_medium,
        uid_count_low=uid_count_low,
        uid_count_joined_primary=uid_count_joined_primary,
        uid_count_eroding_toward_primary=uid_count_eroding_toward_primary,
        uid_count_stable=uid_count_stable,
        uid_count_recovering=uid_count_recovering,
        per_uid_results=sorted_records,
    )


def score_manipulation(
    period_a: Schedule,
    period_b: Schedule,
    period_a_cpm_result: CPMResult,
    period_b_cpm_result: CPMResult,
    focus_spec: FocusPointAnchor,
) -> ManipulationScoringSummary:
    """Score manipulation across two schedule snapshots.

    Authority: BUILD-PLAN section 2.22(h) - frozen public signature.
    Builds DrivingPathResults via :func:`trace_driving_path` for both
    periods, runs the Block 3
    :func:`compare_constraint_driven_cross_version` comparator over
    them, then delegates to the package-private inner helper that
    consumes the cross-version result.

    The Block 3 comparator already applies the AM12 section 2.22(f)
    status-date filter; the inner helper only sets
    ``windowing_incomplete`` as a forensic-visibility flag and never
    re-filters predecessor edges.
    """
    period_a_dpr = trace_driving_path(period_a, focus_spec, period_a_cpm_result)
    period_b_dpr = trace_driving_path(period_b, focus_spec, period_b_cpm_result)

    # FocusPointAnchor is a StrEnum - it carries no integer UID itself.
    # The resolved Focus Point UID lives on the DrivingPathResult after
    # trace_driving_path runs resolve_focus_point. Pass it through to the
    # comparator for traceability; the comparator only consults focus_uid
    # on its lazy DPR-construction path, which is unused here.
    focus_uid = period_a_dpr.focus_point_uid

    cross_version_result = compare_constraint_driven_cross_version(
        schedule_a=period_a,
        schedule_b=period_b,
        dpr_a=period_a_dpr,
        dpr_b=period_b_dpr,
        focus_uid=focus_uid,
    )

    return _score_from_cross_version_result(
        cross_version_result=cross_version_result,
        period_a=period_a,
        period_b=period_b,
    )


__all__ = [
    "score_manipulation",
]
