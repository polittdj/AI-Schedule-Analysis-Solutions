"""Frozen result contract for task-specific driving-path analysis.

Milestone 10. Consumed read-only by the M11 manipulation engine, the
M12 AI narrative layer, and the M13 drill-down UI. Every model carries
``ConfigDict(frozen=True)`` and every collection field is declared as a
``tuple``/``frozenset`` so the contract is immutable end-to-end per
BUILD-PLAN §2.13 mutation-vs-wrap and §5 M10 Block 0 reconciliation.

Authority:

* SSI driving-slack definition — ``driving-slack-and-paths §2``.
* Per-link relationship-slack semantics —
  ``driving-slack-and-paths §3``.
* Backward walk from a Focus Point —
  ``driving-slack-and-paths §5``.
* Multi-branch (non-driving predecessor) termination —
  ``driving-slack-and-paths §7``.
* Period A slack but-for rule — ``driving-slack-and-paths §9``.
* UniqueID-only matching —
  BUILD-PLAN §2.7; ``mpp-parsing-com-automation §5``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import RelationType


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
    """A single node on the driving chain.

    Carries ``unique_id`` + ``name`` for forensic drill-down per
    BUILD-PLAN §6 AC bar #3 (every output record cites the UniqueID
    that drove it).
    """

    model_config = ConfigDict(frozen=True)

    unique_id: int
    """``Task.unique_id`` — the only cross-version-stable identifier
    per BUILD-PLAN §2.7."""

    name: str
    """``Task.name`` — captured for UI drill-down; CUI-bearing per
    ``cui-compliance-constraints §2d`` and never used for matching."""


class DrivingPathLink(BaseModel):
    """A single link on the driving chain.

    The chain is materialised as a parallel pair: ``chain[i]`` is the
    predecessor of ``chain[i+1]``, and ``links[i]`` records the edge
    between them. ``relationship_slack_minutes == 0`` on every driving
    link by definition — the driving-path walk only follows zero-slack
    edges per ``driving-slack-and-paths §5``.
    """

    model_config = ConfigDict(frozen=True)

    predecessor_unique_id: int
    """``Relation.predecessor_unique_id``."""

    successor_unique_id: int
    """``Relation.successor_unique_id``."""

    relation_type: RelationType
    """FS / SS / FF / SF per ``driving-slack-and-paths §3``."""

    lag_minutes: int
    """Working-minute lag on the link. May be negative (a "lead")
    per ``dcma-14-point-assessment §4.2``. A positive or negative
    lag with zero resulting relationship slack still counts as a
    driving link — the slack, not the lag, is what defines
    drivership (``driving-slack-and-paths §5``)."""

    relationship_slack_minutes: int
    """Per-link driving slack in working minutes computed via
    :func:`app.engine.relations.link_driving_slack_minutes`.
    Always ``0`` on a :class:`DrivingPathLink`; non-driving edges
    land on :class:`NonDrivingPredecessor` instead."""


class NonDrivingPredecessor(BaseModel):
    """A predecessor whose relationship slack to its successor is > 0.

    The backward walk enumerates every incoming edge on each chain
    task; edges with ``relationship_slack_minutes == 0`` drive the
    chain, edges with ``> 0`` terminate that branch and land here.
    Consumers render the secondary list alongside the chain so the
    analyst can see "this predecessor would have driven if its slack
    had eroded by N working days" — the forensic signal for
    manipulation detection (``forensic-manipulation-patterns §9``).
    """

    model_config = ConfigDict(frozen=True)

    predecessor_unique_id: int
    """``Relation.predecessor_unique_id`` of the non-driving edge."""

    predecessor_name: str
    """``Task.name`` of the predecessor."""

    successor_unique_id: int
    """``Relation.successor_unique_id`` of the non-driving edge — a
    task on the driving chain."""

    successor_name: str
    """``Task.name`` of the successor (a chain node)."""

    relation_type: RelationType
    """FS / SS / FF / SF."""

    relationship_slack_minutes: int
    """Working-minute slack on this edge. Strictly ``> 0`` for a
    non-driving predecessor; zero-slack alternates from the multi-
    driver tie-break rule also land here with slack = 0 so the UI
    can surface the parallel-driver case (BUILD-PLAN §5 M10 Block 0
    tie-break reconciliation)."""


class DrivingPathResult(BaseModel):
    """Result of :func:`app.engine.driving_path.trace_driving_path`.

    Structure invariants:

    * ``chain[-1].unique_id == focus_unique_id`` — the chain
      terminates at the Focus Point.
    * ``len(links) == max(0, len(chain) - 1)`` — the links list is
      parallel-indexed with the edges between consecutive chain
      nodes. A single-node chain (focus task with no driving
      predecessors) has ``links = ()``.
    * Chain order runs earliest-ancestor → focus, i.e. topological
      order on the driving sub-graph.

    Both invariants are validated at model construction.
    """

    model_config = ConfigDict(frozen=True)

    focus_unique_id: int
    """UniqueID of the Focus Point."""

    focus_name: str
    """``Task.name`` of the Focus Point."""

    chain: tuple[DrivingPathNode, ...]
    """Ordered driving chain, earliest-ancestor → focus. Always
    non-empty; the focus task itself is always the last element."""

    links: tuple[DrivingPathLink, ...]
    """Links between consecutive chain nodes. ``links[i]`` is the
    edge from ``chain[i]`` to ``chain[i+1]``."""

    non_driving_predecessors: tuple[NonDrivingPredecessor, ...]
    """Every incoming non-driving edge observed during the walk, for
    every chain node. Deterministic ordering: iterated in chain
    order (focus → earliest ancestor), and within each node ordered
    by ``(predecessor_unique_id, relation_type)`` ascending."""

    @model_validator(mode="after")
    def _check_structure(self) -> DrivingPathResult:
        if not self.chain:
            raise ValueError("DrivingPathResult.chain must be non-empty")
        if self.chain[-1].unique_id != self.focus_unique_id:
            raise ValueError(
                "DrivingPathResult.chain must terminate at focus_unique_id "
                f"(got chain[-1].unique_id={self.chain[-1].unique_id}, "
                f"focus_unique_id={self.focus_unique_id})"
            )
        expected_link_count = max(0, len(self.chain) - 1)
        if len(self.links) != expected_link_count:
            raise ValueError(
                "DrivingPathResult.links must be parallel-indexed with "
                f"chain edges (expected {expected_link_count}, "
                f"got {len(self.links)})"
            )
        for i, link in enumerate(self.links):
            pred = self.chain[i]
            succ = self.chain[i + 1]
            if link.predecessor_unique_id != pred.unique_id:
                raise ValueError(
                    f"links[{i}].predecessor_unique_id "
                    f"({link.predecessor_unique_id}) does not match "
                    f"chain[{i}].unique_id ({pred.unique_id})"
                )
            if link.successor_unique_id != succ.unique_id:
                raise ValueError(
                    f"links[{i}].successor_unique_id "
                    f"({link.successor_unique_id}) does not match "
                    f"chain[{i + 1}].unique_id ({succ.unique_id})"
                )
        return self


class DrivingPathCrossVersionResult(BaseModel):
    """Result of
    :func:`app.engine.driving_path.trace_driving_path_cross_version`.

    Period A is the sole but-for reference per
    ``driving-slack-and-paths §9``. The ``added_predecessor_uids`` /
    ``removed_predecessor_uids`` / ``retained_predecessor_uids``
    semantics are framed from Period A's perspective:

    * ``added`` — UniqueIDs present in Period B's driving chain but
      not in Period A's.
    * ``removed`` — UniqueIDs present in Period A's driving chain
      but not in Period B's.
    * ``retained`` — UniqueIDs present in both chains.

    The focus UID itself is excluded from all three sets
    (structurally it is always "retained" — the walk terminates at
    it by definition).

    Period B's trace is stored on ``period_b_result`` for display /
    drill-down, but Period B's slack values are **never** used to
    derive the delta semantics. Doing so would be circular per
    ``driving-slack-and-paths §9``: a task that became a driver
    *because* of the Period B change will read zero slack in Period
    B, which proves nothing about what the schedule would have done
    absent the change.
    """

    model_config = ConfigDict(frozen=True)

    focus_unique_id: int
    """UniqueID of the Focus Point, shared across both periods. The
    trace function raises :class:`DrivingPathError` when anchor
    resolution disagrees between Period A and Period B."""

    period_a_result: DrivingPathResult
    """Driving path traced against Period A slack — the but-for
    reference per ``driving-slack-and-paths §9``."""

    period_b_result: DrivingPathResult
    """Driving path traced against Period B slack — descriptive,
    for UI display only. Not used to compute deltas."""

    added_predecessor_uids: frozenset[int]
    """UIDs in ``period_b_result``'s chain but not in
    ``period_a_result``'s chain (focus UID excluded)."""

    removed_predecessor_uids: frozenset[int]
    """UIDs in ``period_a_result``'s chain but not in
    ``period_b_result``'s chain (focus UID excluded)."""

    retained_predecessor_uids: frozenset[int]
    """UIDs in both chains (focus UID excluded)."""


__all__ = [
    "DrivingPathCrossVersionResult",
    "DrivingPathLink",
    "DrivingPathNode",
    "DrivingPathResult",
    "FocusPointAnchor",
    "NonDrivingPredecessor",
]
