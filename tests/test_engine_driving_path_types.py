"""Frozen-contract tests for the Milestone 10 driving-path types.

Reshaped in Block 7 (2026-04-22) for the adjacency-map contract per
BUILD-PLAN AM8 and the three-session audit findings (F1, F3). The
chain + parallel-links contract is gone; tests here cover the new
``nodes`` / ``edges`` / ``non_driving_predecessors`` shape and the
validator-enforced mutually-exclusive slack regimes.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.engine.driving_path_types import (
    DrivingPathCrossVersionResult,
    DrivingPathEdge,
    DrivingPathNode,
    DrivingPathResult,
    FocusPointAnchor,
    NonDrivingPredecessor,
)
from app.models.enums import RelationType

_T0 = datetime(2026, 1, 1, 8, 0)
_T1 = datetime(2026, 1, 2, 16, 0)


def _node(uid: int, name: str) -> DrivingPathNode:
    return DrivingPathNode(
        unique_id=uid,
        name=name,
        early_start=_T0,
        early_finish=_T1,
        late_start=_T0,
        late_finish=_T1,
        total_float_days=0.0,
        calendar_hours_per_day=8.0,
    )


def _edge(pred: int, succ: int, slack_days: float = 0.0) -> DrivingPathEdge:
    return DrivingPathEdge(
        predecessor_uid=pred,
        predecessor_name=f"T{pred}",
        successor_uid=succ,
        successor_name=f"T{succ}",
        relation_type=RelationType.FS,
        lag_days=0.0,
        relationship_slack_days=slack_days,
        calendar_hours_per_day=8.0,
    )


def _ndp(
    pred: int, succ: int, slack_days: float = 1.0
) -> NonDrivingPredecessor:
    return NonDrivingPredecessor(
        predecessor_uid=pred,
        predecessor_name=f"T{pred}",
        successor_uid=succ,
        successor_name=f"T{succ}",
        relation_type=RelationType.FS,
        lag_days=0.0,
        slack_days=slack_days,
        calendar_hours_per_day=8.0,
    )


# ----------------------------------------------------------------------
# FocusPointAnchor enum
# ----------------------------------------------------------------------


def test_focus_point_anchor_has_exactly_two_values() -> None:
    assert {a.value for a in FocusPointAnchor} == {"project_finish", "project_start"}
    assert len(list(FocusPointAnchor)) == 2


def test_focus_point_anchor_is_str_enum() -> None:
    assert FocusPointAnchor.PROJECT_FINISH == "project_finish"
    assert FocusPointAnchor.PROJECT_START == "project_start"


# ----------------------------------------------------------------------
# Frozen-ness
# ----------------------------------------------------------------------


def test_driving_path_node_is_frozen() -> None:
    node = _node(1, "A")
    with pytest.raises(ValidationError):
        node.unique_id = 2  # type: ignore[misc]


def test_driving_path_edge_is_frozen() -> None:
    edge = _edge(1, 2)
    with pytest.raises(ValidationError):
        edge.lag_days = 99.0  # type: ignore[misc]


def test_non_driving_predecessor_is_frozen() -> None:
    ndp = _ndp(7, 2, slack_days=2.0)
    with pytest.raises(ValidationError):
        ndp.slack_days = 0.5  # type: ignore[misc]


def test_driving_path_result_is_frozen() -> None:
    result = DrivingPathResult(
        focus_point_uid=2,
        focus_point_name="Focus",
        nodes={2: _node(2, "Focus"), 1: _node(1, "A")},
        edges=[_edge(1, 2)],
        non_driving_predecessors=[],
    )
    with pytest.raises(ValidationError):
        result.focus_point_name = "different"  # type: ignore[misc]


def test_driving_path_cross_version_result_is_frozen() -> None:
    base = DrivingPathResult(
        focus_point_uid=2,
        focus_point_name="Focus",
        nodes={2: _node(2, "Focus"), 1: _node(1, "A")},
        edges=[_edge(1, 2)],
        non_driving_predecessors=[],
    )
    cv = DrivingPathCrossVersionResult(
        period_a_result=base,
        period_b_result=base,
        added_predecessor_uids=set(),
        removed_predecessor_uids=set(),
        retained_predecessor_uids={1},
        added_edges=[],
        removed_edges=[],
        retained_edges=[_edge(1, 2)],
    )
    with pytest.raises(ValidationError):
        cv.added_predecessor_uids = {99}  # type: ignore[misc]


# ----------------------------------------------------------------------
# Calendar audit-trail fields
# ----------------------------------------------------------------------


def test_node_rejects_zero_hours_per_day() -> None:
    with pytest.raises(ValidationError):
        DrivingPathNode(
            unique_id=1,
            name="A",
            early_start=_T0,
            early_finish=_T1,
            late_start=_T0,
            late_finish=_T1,
            total_float_days=0.0,
            calendar_hours_per_day=0.0,
        )


def test_edge_rejects_zero_hours_per_day() -> None:
    with pytest.raises(ValidationError):
        DrivingPathEdge(
            predecessor_uid=1,
            predecessor_name="A",
            successor_uid=2,
            successor_name="B",
            relation_type=RelationType.FS,
            lag_days=0.0,
            relationship_slack_days=0.0,
            calendar_hours_per_day=0.0,
        )


def test_non_driving_predecessor_rejects_zero_hours_per_day() -> None:
    with pytest.raises(ValidationError):
        NonDrivingPredecessor(
            predecessor_uid=1,
            predecessor_name="A",
            successor_uid=2,
            successor_name="B",
            relation_type=RelationType.FS,
            lag_days=0.0,
            slack_days=1.0,
            calendar_hours_per_day=0.0,
        )


# ----------------------------------------------------------------------
# Adjacency-map minimal result
# ----------------------------------------------------------------------


def test_minimal_result_with_single_focus_node() -> None:
    # Focus point with no driving predecessors — valid single-node
    # sub-graph, zero edges.
    result = DrivingPathResult(
        focus_point_uid=42,
        focus_point_name="Alone",
        nodes={42: _node(42, "Alone")},
        edges=[],
        non_driving_predecessors=[],
    )
    assert result.nodes.keys() == {42}
    assert result.edges == []


def test_three_node_linear_chain_as_adjacency_map() -> None:
    # Y → X → Focus linear chain, expressed as an adjacency map.
    result = DrivingPathResult(
        focus_point_uid=3,
        focus_point_name="Focus",
        nodes={
            1: _node(1, "Y"),
            2: _node(2, "X"),
            3: _node(3, "Focus"),
        },
        edges=[_edge(1, 2), _edge(2, 3)],
        non_driving_predecessors=[],
    )
    assert len(result.nodes) == 3
    assert len(result.edges) == 2


# ----------------------------------------------------------------------
# Validator: slack regimes on Edge and NonDrivingPredecessor
#
# These four tests address F4 — the Block 7 audit found that no test
# exercised the mutually-exclusive slack regime. See
# ``tests/test_engine_driving_path_true_multi_branch.py`` for the
# multi-branch scenario coverage (also F4).
# ----------------------------------------------------------------------


def test_driving_path_edge_rejects_positive_slack() -> None:
    with pytest.raises(
        ValidationError, match="must be ~0"
    ):
        _edge(1, 2, slack_days=0.1)


def test_driving_path_edge_accepts_sub_second_tolerance() -> None:
    # One second in days is ~1.157e-5. The validator accepts values
    # up to that magnitude so a non-8h/day calendar conversion can
    # round without triggering a false negative.
    edge = _edge(1, 2, slack_days=1.0 / 86_400.0)
    assert edge.relationship_slack_days == pytest.approx(1.0 / 86_400.0)


def test_driving_path_edge_rejects_just_over_tolerance() -> None:
    # Slightly over one second — should reject.
    with pytest.raises(ValidationError, match="must be ~0"):
        _edge(1, 2, slack_days=1.0 / 86_400.0 * 2.0)


def test_non_driving_predecessor_rejects_zero_slack() -> None:
    with pytest.raises(ValidationError, match="strictly.*positive"):
        _ndp(1, 2, slack_days=0.0)


def test_non_driving_predecessor_rejects_negative_slack() -> None:
    with pytest.raises(ValidationError, match="strictly.*positive"):
        _ndp(1, 2, slack_days=-0.5)


def test_non_driving_predecessor_rejects_sub_second_slack() -> None:
    # Slack that would round to zero under the Edge tolerance must
    # also be rejected here — the two regimes are mutually exclusive
    # and together cover the real line.
    with pytest.raises(ValidationError, match="strictly.*positive"):
        _ndp(1, 2, slack_days=1.0 / 86_400.0 / 2.0)


def test_validator_error_messages_cite_skill_sections() -> None:
    # Per Block 7 §3.4 the validator error messages must cite §4 and
    # §5 verbatim so future debuggers see the authority inline.
    with pytest.raises(ValidationError) as exc_info:
        _edge(1, 2, slack_days=1.0)
    message = str(exc_info.value)
    assert "No path is dropped" in message
    assert "walks recursively" in message

    with pytest.raises(ValidationError) as exc_info:
        _ndp(1, 2, slack_days=0.0)
    message = str(exc_info.value)
    assert "No path is dropped" in message
    assert "walks recursively" in message
