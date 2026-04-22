"""Frozen result contract for task-specific driving-path analysis.

Milestone 10, reshaped in Block 7 (2026-04-22) per BUILD-PLAN AM8 and
the three-session audit findings (F1, F3). The chain + parallel-links
contract is replaced with an adjacency map so that multi-branch
backward walks per ``driving-slack-and-paths §4`` ("No path is
dropped.") and §5 ("Walking every relationship-slack-zero link
backward … walks recursively until every driving predecessor is
exhausted.") are representable without lossy serialisation.

Every public model is ``ConfigDict(frozen=True)``; every duration
field is denominated in **days** (float) with a companion
``calendar_hours_per_day`` factor so the audit trail back to minutes
is preserved (BUILD-PLAN §2.18).

Authority:

* SSI driving-slack definition — ``driving-slack-and-paths §2``.
* Per-link relationship-slack semantics —
  ``driving-slack-and-paths §3``.
* "No path is dropped." — ``driving-slack-and-paths §4`` verbatim.
* "Walking every relationship-slack-zero link backward … walks
  recursively until every driving predecessor is exhausted." —
  ``driving-slack-and-paths §5`` verbatim.
* Period A slack but-for rule — ``driving-slack-and-paths §9``.
* UniqueID-only matching —
  BUILD-PLAN §2.7; ``mpp-parsing-com-automation §5``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import RelationType

# One-second tolerance on "zero" relationship slack in days. Minutes
# arithmetic uses integer minutes internally, so any non-zero slack
# will be at least 1 minute; the only time a days-denominated slack
# lands in a (−1/86_400, +1/86_400) band is rounding on a non-8h/day
# calendar conversion via units.minutes_to_days. One second in days
# is ``1 / 86_400`` ≈ 1.1574e-5.
_ZERO_SLACK_TOLERANCE_DAYS: float = 1.0 / 86_400.0

# §4 and §5 quotes that appear in validator error messages. The
# verbatim form is intentional — future debuggers need the authority
# inline without opening a second file.
_SKILL_S4_QUOTE = '§4: "No path is dropped."'
_SKILL_S5_QUOTE = (
    '§5: "Walking every relationship-slack-zero link backward … '
    "walks recursively until every driving predecessor is exhausted.\""
)


class FocusPointAnchor(StrEnum):
    """Predefined Focus Point anchors.

    ``PROJECT_FINISH`` — the schedule's project-finish milestone
    (the task with no outgoing relations and the latest early-finish
    date). Trace from this anchor reproduces the project critical
    path per ``driving-slack-and-paths §4``.

    ``PROJECT_START`` — the schedule's project-start milestone
    (symmetric: no incoming relations, earliest early-start date).
    Exposed for future forward-walk inversion work; M10 treats it as
    a valid resolve target without exercising a special code path.
    """

    PROJECT_FINISH = "project_finish"
    PROJECT_START = "project_start"


class DrivingPathNode(BaseModel):
    """A task in the driving-path subgraph.

    Appears exactly once per UniqueID in
    :attr:`DrivingPathResult.nodes` regardless of how many driving
    paths reach it — shared ancestors are deduplicated (``§4``). The
    model carries both UID and name per BUILD-PLAN §6 AC bar #3
    (every output record cites the UniqueID that drove it) and the
    calendar-bearing fields needed to reconstruct minute durations
    from the days-denominated contract (§0.4 of the Block 7 write-
    session prompt; BUILD-PLAN §2.18).
    """

    model_config = ConfigDict(frozen=True)

    unique_id: int
    """``Task.unique_id`` — the only cross-version-stable identifier
    per BUILD-PLAN §2.7."""

    name: str
    """``Task.name`` — captured for UI drill-down; CUI-bearing per
    ``cui-compliance-constraints §2d`` and never used for matching."""

    early_start: datetime
    """CPM-computed early start (``TaskCPMResult.early_start``)."""

    early_finish: datetime
    """CPM-computed early finish (``TaskCPMResult.early_finish``)."""

    late_start: datetime
    """CPM-computed late start (``TaskCPMResult.late_start``)."""

    late_finish: datetime
    """CPM-computed late finish (``TaskCPMResult.late_finish``)."""

    total_float_days: float
    """Total float in days (``TaskCPMResult.total_float_minutes``
    converted via :func:`app.engine.units.minutes_to_days` with
    ``calendar_hours_per_day``)."""

    calendar_hours_per_day: float = Field(gt=0)
    """Hours-per-day factor used for this node's minute→day
    conversions. Populated from
    ``Task.calendar_hours_per_day`` when non-``None`` or
    ``Schedule.project_calendar_hours_per_day`` otherwise (M1.1
    denormalised fields). The forensic audit trail: any reviewer can
    reconstruct minutes via
    ``total_float_days * calendar_hours_per_day * 60``."""


class DrivingPathEdge(BaseModel):
    """A zero-relationship-slack relationship driving its successor.

    Every such relationship found during backward walk appears
    exactly once on :attr:`DrivingPathResult.edges` — no tie-break,
    no deduplication loss, per ``driving-slack-and-paths §4``. The
    model validator enforces ``relationship_slack_days ≈ 0`` (one-
    second tolerance expressed in days). Non-driving (positive-
    slack) relationships belong on :class:`NonDrivingPredecessor`.
    """

    model_config = ConfigDict(frozen=True)

    predecessor_uid: int
    """``Relation.predecessor_unique_id``."""

    predecessor_name: str
    """``Task.name`` of the predecessor."""

    successor_uid: int
    """``Relation.successor_unique_id``."""

    successor_name: str
    """``Task.name`` of the successor."""

    relation_type: RelationType
    """FS / SS / FF / SF per ``driving-slack-and-paths §3``."""

    lag_days: float
    """Working-day lag on the link. May be negative ("lead") per
    ``dcma-14-point-assessment §4.2``. Converted from
    ``Relation.lag_minutes`` via
    :func:`app.engine.units.minutes_to_days`."""

    relationship_slack_days: float
    """Per-link driving slack in working days. Always ~0 on a
    driving edge (validator-enforced). Zero slack is the definition
    of drivership (``driving-slack-and-paths §5``); non-zero slack
    lands on :class:`NonDrivingPredecessor`."""

    calendar_hours_per_day: float = Field(gt=0)
    """Hours-per-day factor used to compute ``lag_days`` and
    ``relationship_slack_days``. Forensic audit trail per
    BUILD-PLAN §2.18."""

    @model_validator(mode="after")
    def _check_slack_is_zero(self) -> DrivingPathEdge:
        if abs(self.relationship_slack_days) > _ZERO_SLACK_TOLERANCE_DAYS:
            raise ValueError(
                "DrivingPathEdge.relationship_slack_days must be ~0 "
                f"(got {self.relationship_slack_days!r}). Non-zero "
                "slack relationships belong on NonDrivingPredecessor. "
                "Skill authority: "
                f"{_SKILL_S4_QUOTE} {_SKILL_S5_QUOTE}"
            )
        return self


class NonDrivingPredecessor(BaseModel):
    """A positive-slack relationship that terminates a backward walk.

    F3 fix (Block 7, 2026-04-22): ``slack_days`` is strictly > 0.
    The prior M10 contract admitted zero-slack alternates from the
    lowest-UID tie-break rule, which made
    :class:`NonDrivingPredecessor` and :class:`DrivingPathEdge` share
    the ``slack = 0`` regime and hid true multi-branch paths. Under
    AM8 that escape hatch is removed — slack regimes on the two
    types are mutually exclusive.
    """

    model_config = ConfigDict(frozen=True)

    predecessor_uid: int
    """``Relation.predecessor_unique_id`` of the non-driving edge."""

    predecessor_name: str
    """``Task.name`` of the predecessor."""

    successor_uid: int
    """``Relation.successor_unique_id`` of the non-driving edge — a
    task in the driving sub-graph."""

    successor_name: str
    """``Task.name`` of the successor."""

    relation_type: RelationType
    """FS / SS / FF / SF."""

    lag_days: float
    """Working-day lag on the link."""

    slack_days: float
    """Working-day driving slack on this edge. Strictly > 0 —
    enforced by ``_check_slack_is_positive``. Zero-slack edges are
    driving edges and land on :class:`DrivingPathEdge`."""

    calendar_hours_per_day: float = Field(gt=0)
    """Hours-per-day factor used to compute ``lag_days`` and
    ``slack_days``. Forensic audit trail per BUILD-PLAN §2.18."""

    @model_validator(mode="after")
    def _check_slack_is_positive(self) -> NonDrivingPredecessor:
        if self.slack_days <= _ZERO_SLACK_TOLERANCE_DAYS:
            raise ValueError(
                "NonDrivingPredecessor.slack_days must be strictly "
                f"positive (got {self.slack_days!r}). Zero or "
                "negative slack would overlap with the driving-edge "
                "regime and reintroduce the F3 escape hatch. Skill "
                f"authority: {_SKILL_S4_QUOTE} {_SKILL_S5_QUOTE}"
            )
        return self


class DrivingPathResult(BaseModel):
    """Adjacency-map representation of the driving-path subgraph.

    Replaces the M10 chain + parallel-links contract (F1) per
    BUILD-PLAN AM8. ``nodes`` is keyed by UniqueID (ancestor sharing
    is automatic); ``edges`` is a flat list of every zero-slack
    driving relationship found on the backward walk; any non-driving
    incoming relationship that terminated a branch lands on
    ``non_driving_predecessors``.

    Consumed read-only by the M11 manipulation engine, the M12 AI
    narrative layer, and the M13 drill-down UI.
    """

    model_config = ConfigDict(frozen=True)

    focus_point_uid: int
    """UniqueID of the Focus Point the walk started from."""

    focus_point_name: str
    """``Task.name`` of the Focus Point."""

    nodes: dict[int, DrivingPathNode]
    """Every task in the driving sub-graph, keyed by UniqueID. The
    Focus Point itself is always present; every transitive driving
    predecessor appears exactly once."""

    edges: list[DrivingPathEdge]
    """Every zero-relationship-slack driving relationship. Sorted by
    ``(successor_uid, predecessor_uid)`` for deterministic test
    assertions and commit diffs — semantic ordering is unordered.
    Renderers are free to reorder for display."""

    non_driving_predecessors: list[NonDrivingPredecessor]
    """Positive-slack predecessors of nodes in the sub-graph. These
    terminated the backward walk on their successor. Ordering
    mirrors ``edges``: sorted by ``(successor_uid, predecessor_uid)``
    for determinism."""


class DrivingPathCrossVersionResult(BaseModel):
    """Period A vs Period B driving-path comparison.

    Period A slack is the sole but-for reference per
    ``driving-slack-and-paths §9``. ``added`` / ``removed`` /
    ``retained`` classifications are framed from Period A's
    perspective — a UID or edge that appears in Period B but not
    Period A is "added from A's perspective." Period B's slack
    values are stored on :attr:`period_b_result` for display / drill-
    down but never used to derive the diff sets (that would be
    circular per §9).
    """

    model_config = ConfigDict(frozen=True)

    period_a_result: DrivingPathResult
    """Full Period A adjacency-map result — the but-for reference."""

    period_b_result: DrivingPathResult
    """Full Period B adjacency-map result — descriptive only."""

    added_predecessor_uids: set[int]
    """UniqueIDs in ``period_b_result.nodes`` but not in
    ``period_a_result.nodes`` (Focus Point UID excluded — it is
    structurally retained)."""

    removed_predecessor_uids: set[int]
    """UniqueIDs in ``period_a_result.nodes`` but not in
    ``period_b_result.nodes``."""

    retained_predecessor_uids: set[int]
    """UniqueIDs in both periods' ``nodes`` (Focus Point UID
    excluded)."""

    added_edges: list[DrivingPathEdge]
    """Edges in ``period_b_result.edges`` with no identity-matched
    counterpart in ``period_a_result.edges``. Edge identity is the
    tuple ``(predecessor_uid, successor_uid, relation_type)``. The
    Period B copy of the edge is carried here (Period B values for
    lag / slack / calendar)."""

    removed_edges: list[DrivingPathEdge]
    """Edges in ``period_a_result.edges`` with no identity-matched
    counterpart in ``period_b_result.edges``. The Period A copy is
    carried."""

    retained_edges: list[DrivingPathEdge]
    """Edges present in both periods by identity. The Period A copy
    is carried for forensic consistency with the Period A but-for
    rule (§9)."""


__all__ = [
    "DrivingPathCrossVersionResult",
    "DrivingPathEdge",
    "DrivingPathNode",
    "DrivingPathResult",
    "FocusPointAnchor",
    "NonDrivingPredecessor",
]
