"""Frozen Pydantic contract types for the M11 manipulation-scoring engine.

Authority: BUILD-PLAN §2.22 (AM12, 4/23/2026) subsection (c). The four
public Pydantic models and two ``StrEnum`` classes below are the
public surface of the M11 scoring domain — the
``ConstraintDrivenCrossVersionComparator`` (Block 3) emits
``ConstraintDrivenCrossVersionResult`` and the scoring engine (Block
4) emits ``ManipulationScoringResult`` / ``ManipulationScoringSummary``
for consumption by the M12 AI narrative layer and the M13 Flask UI.

Every public model is ``ConfigDict(frozen=True)``; every duration
field is denominated in **days** per BUILD-PLAN §2.19 (AM9 days-only
UX). Integer minutes are never exposed on M11 public models. Field
names, types, and ordering are frozen by AM12 subsection (c).

Authority references:

* ``forensic-manipulation-patterns §4.4`` (constraint injection).
* ``forensic-manipulation-patterns §4.5`` (constraint removal hiding
  slip).
* ``forensic-manipulation-patterns §9`` (cross-version erosion).
* ``forensic-manipulation-patterns §10`` (red-flag aggregation tiers).
* ``acumen-reference §3.3`` (tripwire-not-verdict).
* ``acumen-reference §3.6`` (weighting at scorecard assembly).
* ``driving-slack-and-paths §6`` (TotalFloat trend classification).
* ``driving-slack-and-paths §9`` (Period A slack but-for rule).
* BUILD-PLAN §2.20 (three-bucket partition, AM10) —
  ``ConstraintDrivenPredecessor`` origin.
* BUILD-PLAN §2.21 (M10.2 ``skipped_cycle_participants``, AM11).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathResult,
)


class SlackState(StrEnum):
    """Per-UID slack state transition from Period A to Period B.

    Authority: forensic-manipulation-patterns §9 (cross-version
    erosion); driving-slack-and-paths §6 (TotalFloat trend
    classification vocabulary adapted for constraint-driven slack).
    """

    JOINED_PRIMARY = "joined_primary"
    ERODING_TOWARD_PRIMARY = "eroding_toward_primary"
    STABLE = "stable"
    RECOVERING = "recovering"


class SeverityTier(StrEnum):
    """Per-UID severity tier driving the Acumen-Fuse-style weighted
    score. Weights defined in subsection (e)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConstraintDrivenCrossVersionResult(BaseModel):
    """Per-UID set algebra on constraint_driven_predecessors across
    Period A and Period B. Period A is the but-for reference per
    BUILD-PLAN §2.9 / driving-slack-and-paths §9.

    Emitted by ConstraintDrivenCrossVersionComparator. Consumed
    read-only by the M11 scoring engine.
    """

    model_config = ConfigDict(frozen=True)

    period_a_result: DrivingPathResult
    period_b_result: DrivingPathResult
    period_a_status_date_days_offset: float | None
    period_b_status_date_days_offset: float | None

    added_constraint_driven_uids: set[int] = Field(default_factory=set)
    """Successor UIDs that carry a ConstraintDrivenPredecessor in
    Period B but not in Period A. Identity: successor_uid."""

    removed_constraint_driven_uids: set[int] = Field(default_factory=set)
    """Successor UIDs that carried a ConstraintDrivenPredecessor in
    Period A but not in Period B."""

    retained_constraint_driven_uids: set[int] = Field(default_factory=set)
    """Successor UIDs present in both periods' constraint_driven_
    predecessors lists. State transition computed by the scoring
    engine per subsection (d)."""

    period_a_predecessors_by_successor: dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ] = Field(default_factory=dict)
    """Period A's ConstraintDrivenPredecessor records indexed by
    successor_uid. Preserves the full forensic trail for drill-down."""

    period_b_predecessors_by_successor: dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ] = Field(default_factory=dict)
    """Period B's records indexed by successor_uid."""

    @model_validator(mode="after")
    def _check_set_algebra_disjoint(self) -> ConstraintDrivenCrossVersionResult:
        added = self.added_constraint_driven_uids
        removed = self.removed_constraint_driven_uids
        retained = self.retained_constraint_driven_uids

        added_removed = added & removed
        added_retained = added & retained
        removed_retained = removed & retained

        if added_removed or added_retained or removed_retained:
            overlaps: list[str] = []
            if added_removed:
                overlaps.append(
                    "added_constraint_driven_uids ∩ "
                    f"removed_constraint_driven_uids = {sorted(added_removed)!r}"
                )
            if added_retained:
                overlaps.append(
                    "added_constraint_driven_uids ∩ "
                    f"retained_constraint_driven_uids = {sorted(added_retained)!r}"
                )
            if removed_retained:
                overlaps.append(
                    "removed_constraint_driven_uids ∩ "
                    f"retained_constraint_driven_uids = {sorted(removed_retained)!r}"
                )
            raise ValueError(
                "ConstraintDrivenCrossVersionResult set-algebra "
                "disjointness invariant violated. The three sets are "
                "respectively B−A, A−B, and A∩B on successor_uid "
                "populations and MUST be pairwise disjoint. Overlap(s): "
                + "; ".join(overlaps)
                + ". Authority: BUILD-PLAN §2.22 (AM12) subsection (c)."
            )
        return self


class ManipulationScoringResult(BaseModel):
    """Per-UID scoring result. One record per successor_uid that
    appears in any of the three set-algebra sets.

    Consumed by the M11 summary aggregator (subsection (e)) and the
    M13 renderer (subsection (i)).
    """

    model_config = ConfigDict(frozen=True)

    unique_id: int
    """successor_uid of the constraint-driven edge(s)."""

    name: str
    """Task.name at Period B if the UID is present in Period B;
    Period A name otherwise. Every scoring record cites a name per
    BUILD-PLAN §6 AC bar #3."""

    score: int
    """Per-UID weighted-Acumen-Fuse score — 10, 5, or 2 per
    subsection (e). Integer by contract."""

    severity_tier: SeverityTier
    """HIGH / MEDIUM / LOW. Highest-severity tier wins on
    per-UID dedup (subsection (e))."""

    slack_state: SlackState
    """Transition classification per subsection (d)."""

    period_a_predecessors: tuple[ConstraintDrivenPredecessor, ...] = ()
    """Constraint-driven edges on this successor in Period A.
    Empty if the UID first appears in Period B."""

    period_b_predecessors: tuple[ConstraintDrivenPredecessor, ...] = ()
    """Constraint-driven edges on this successor in Period B.
    Empty if the UID is only in Period A (RECOVERING full exit)."""

    skipped_cycle_participants_reference: tuple[int, ...] = ()
    """UIDs from DrivingPathResult.skipped_cycle_participants (M10.2,
    §2.21) that are implicated in this UID's constraint-driven
    cluster. Forensic visibility trail — empty when no cycle
    participant touches this UID."""

    windowing_incomplete: bool = False
    """True when status-date filtering could not fully evaluate this UID
    (missing Period B status_date, missing predecessor task in one or
    both periods, or predecessor task present in M10.2
    skipped_cycle_participants and thus carrying non-authoritative CPM
    dates). Forensic visibility flag per subsection (f). When True, the
    scoring record is retained rather than dropped; severity tier may be
    degraded by downstream consumers but is NOT degraded by the scoring
    engine itself."""

    rationale: str
    """Human-readable narrative composed from the contributing
    ConstraintDrivenPredecessor.rationale strings (M10.1) and the
    SlackState transition. Deposition-grade for M12 / M13
    consumption."""


class ManipulationScoringSummary(BaseModel):
    """Schedule-level aggregate across every per-UID scoring record.

    One instance per ConstraintDrivenCrossVersionResult. The total_score
    is bounded at 100 per the Acumen-Fuse-style clamp (subsection (e))
    — additive-before-clamp, never additive-unclamped.
    """

    model_config = ConfigDict(frozen=True)

    total_score: int = Field(ge=0, le=100)
    """Sum of per-UID scores, clamped to [0, 100]. An
    all-clean schedule pair returns 0 per the M11 always-100
    regression bar (superseded phrasing; numeric contract identical)."""

    uid_count_high: int = Field(ge=0)
    uid_count_medium: int = Field(ge=0)
    uid_count_low: int = Field(ge=0)

    uid_count_joined_primary: int = Field(ge=0)
    uid_count_eroding_toward_primary: int = Field(ge=0)
    uid_count_stable: int = Field(ge=0)
    uid_count_recovering: int = Field(ge=0)

    per_uid_results: tuple[ManipulationScoringResult, ...] = ()
    """Every per-UID record. Sorted by (severity_tier desc,
    unique_id asc) for deterministic renderer output."""


__all__ = [
    "ConstraintDrivenCrossVersionResult",
    "ManipulationScoringResult",
    "ManipulationScoringSummary",
    "SeverityTier",
    "SlackState",
]
