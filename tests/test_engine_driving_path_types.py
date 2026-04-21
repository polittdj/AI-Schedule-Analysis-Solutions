"""Frozen-contract tests for the Milestone 10 driving-path types.

Validates the Pydantic v2 ``ConfigDict(frozen=True)`` posture, the
chain-link parallel-index invariant on :class:`DrivingPathResult`,
and the ``FocusPointAnchor`` enum membership.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.engine.driving_path_types import (
    DrivingPathCrossVersionResult,
    DrivingPathLink,
    DrivingPathNode,
    DrivingPathResult,
    FocusPointAnchor,
    NonDrivingPredecessor,
)
from app.models.enums import RelationType


def _node(uid: int, name: str) -> DrivingPathNode:
    return DrivingPathNode(unique_id=uid, name=name)


def _link(pred: int, succ: int) -> DrivingPathLink:
    return DrivingPathLink(
        predecessor_unique_id=pred,
        successor_unique_id=succ,
        relation_type=RelationType.FS,
        lag_minutes=0,
        relationship_slack_minutes=0,
    )


# ----------------------------------------------------------------------
# Importability and enum shape
# ----------------------------------------------------------------------


def test_focus_point_anchor_has_exactly_two_values() -> None:
    assert {a.value for a in FocusPointAnchor} == {"project_finish", "project_start"}
    assert len(list(FocusPointAnchor)) == 2


def test_focus_point_anchor_is_str_enum() -> None:
    assert FocusPointAnchor.PROJECT_FINISH == "project_finish"
    assert FocusPointAnchor.PROJECT_START == "project_start"


# ----------------------------------------------------------------------
# Frozen mutation
# ----------------------------------------------------------------------


def test_driving_path_node_is_frozen() -> None:
    node = _node(1, "A")
    with pytest.raises(ValidationError):
        node.unique_id = 2  # type: ignore[misc]


def test_driving_path_link_is_frozen() -> None:
    link = _link(1, 2)
    with pytest.raises(ValidationError):
        link.lag_minutes = 999  # type: ignore[misc]


def test_non_driving_predecessor_is_frozen() -> None:
    ndp = NonDrivingPredecessor(
        predecessor_unique_id=7,
        predecessor_name="Q",
        successor_unique_id=2,
        successor_name="X",
        relation_type=RelationType.FS,
        relationship_slack_minutes=2880,
    )
    with pytest.raises(ValidationError):
        ndp.relationship_slack_minutes = 0  # type: ignore[misc]


def test_driving_path_result_is_frozen() -> None:
    result = DrivingPathResult(
        focus_unique_id=2,
        focus_name="Focus",
        chain=(_node(1, "A"), _node(2, "Focus")),
        links=(_link(1, 2),),
        non_driving_predecessors=(),
    )
    with pytest.raises(ValidationError):
        result.focus_name = "different"  # type: ignore[misc]


def test_driving_path_cross_version_result_is_frozen() -> None:
    base = DrivingPathResult(
        focus_unique_id=2,
        focus_name="Focus",
        chain=(_node(1, "A"), _node(2, "Focus")),
        links=(_link(1, 2),),
        non_driving_predecessors=(),
    )
    cv = DrivingPathCrossVersionResult(
        focus_unique_id=2,
        period_a_result=base,
        period_b_result=base,
        added_predecessor_uids=frozenset(),
        removed_predecessor_uids=frozenset(),
        retained_predecessor_uids=frozenset({1}),
    )
    with pytest.raises(ValidationError):
        cv.focus_unique_id = 99  # type: ignore[misc]


# ----------------------------------------------------------------------
# Tuple-only collections
# ----------------------------------------------------------------------


def test_chain_rejects_list_input() -> None:
    # Pydantic v2 coerces lists to tuples for tuple[...] fields by
    # default. Asserts that the stored value is a tuple regardless
    # of the input container.
    result = DrivingPathResult(
        focus_unique_id=2,
        focus_name="Focus",
        chain=[_node(1, "A"), _node(2, "Focus")],  # type: ignore[arg-type]
        links=[_link(1, 2)],  # type: ignore[arg-type]
        non_driving_predecessors=[],  # type: ignore[arg-type]
    )
    assert isinstance(result.chain, tuple)
    assert isinstance(result.links, tuple)
    assert isinstance(result.non_driving_predecessors, tuple)


def test_frozenset_fields_are_frozensets() -> None:
    base = DrivingPathResult(
        focus_unique_id=2,
        focus_name="Focus",
        chain=(_node(2, "Focus"),),
        links=(),
        non_driving_predecessors=(),
    )
    cv = DrivingPathCrossVersionResult(
        focus_unique_id=2,
        period_a_result=base,
        period_b_result=base,
        added_predecessor_uids={1, 3},  # type: ignore[arg-type]
        removed_predecessor_uids=[],  # type: ignore[arg-type]
        retained_predecessor_uids=frozenset(),
    )
    assert isinstance(cv.added_predecessor_uids, frozenset)
    assert isinstance(cv.removed_predecessor_uids, frozenset)
    assert isinstance(cv.retained_predecessor_uids, frozenset)
    assert cv.added_predecessor_uids == frozenset({1, 3})


# ----------------------------------------------------------------------
# Structural invariants on DrivingPathResult
# ----------------------------------------------------------------------


def test_chain_must_be_non_empty() -> None:
    with pytest.raises(ValidationError, match="chain must be non-empty"):
        DrivingPathResult(
            focus_unique_id=2,
            focus_name="Focus",
            chain=(),
            links=(),
            non_driving_predecessors=(),
        )


def test_chain_must_terminate_at_focus_uid() -> None:
    with pytest.raises(ValidationError, match="terminate at focus_unique_id"):
        DrivingPathResult(
            focus_unique_id=99,
            focus_name="Focus",
            chain=(_node(1, "A"), _node(2, "B")),
            links=(_link(1, 2),),
            non_driving_predecessors=(),
        )


def test_links_parallel_index_with_chain() -> None:
    with pytest.raises(ValidationError, match="parallel-indexed"):
        DrivingPathResult(
            focus_unique_id=2,
            focus_name="Focus",
            chain=(_node(1, "A"), _node(2, "Focus")),
            links=(),
            non_driving_predecessors=(),
        )


def test_links_predecessor_uid_must_match_chain_predecessor() -> None:
    with pytest.raises(ValidationError, match="predecessor_unique_id"):
        DrivingPathResult(
            focus_unique_id=2,
            focus_name="Focus",
            chain=(_node(1, "A"), _node(2, "Focus")),
            links=(_link(99, 2),),  # wrong predecessor
            non_driving_predecessors=(),
        )


def test_links_successor_uid_must_match_chain_successor() -> None:
    with pytest.raises(ValidationError, match="successor_unique_id"):
        DrivingPathResult(
            focus_unique_id=2,
            focus_name="Focus",
            chain=(_node(1, "A"), _node(2, "Focus")),
            links=(_link(1, 99),),  # wrong successor
            non_driving_predecessors=(),
        )


def test_single_node_chain_has_empty_links() -> None:
    # Valid case: focus task with no driving predecessors.
    result = DrivingPathResult(
        focus_unique_id=42,
        focus_name="Alone",
        chain=(_node(42, "Alone"),),
        links=(),
        non_driving_predecessors=(),
    )
    assert len(result.chain) == 1
    assert result.links == ()


def test_three_tier_chain_links_validate() -> None:
    # Valid case: Y → X → Focus.
    result = DrivingPathResult(
        focus_unique_id=3,
        focus_name="Focus",
        chain=(_node(1, "Y"), _node(2, "X"), _node(3, "Focus")),
        links=(_link(1, 2), _link(2, 3)),
        non_driving_predecessors=(),
    )
    assert len(result.chain) == 3
    assert len(result.links) == 2
