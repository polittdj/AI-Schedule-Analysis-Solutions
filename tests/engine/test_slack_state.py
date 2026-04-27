"""Tests for the SlackState classifier — M11 Block 4 step 1.

Exercises :mod:`app.engine.slack_state` against the 10-row
classification table in the module docstring plus four edge cases
beyond the table (multi-edge ``min``, windowing flag pass-through,
empty-on-both RETAINED default, floating-point boundary).

Authority:

* ``app.contracts.manipulation_scoring.SlackState`` — the four-state
  vocabulary.
* ``forensic-manipulation-patterns §9`` (cross-version erosion).
* ``driving-slack-and-paths §6`` (trend label vocabulary), ``§9``
  (Period A but-for rule).

Construction note: ``ConstraintDrivenPredecessor`` carries a
validator that requires ``slack_days < -1.157e-5`` (one second of
working-days; see ``driving_path_types._ZERO_SLACK_TOLERANCE_DAYS``).
For tests that need ``slack_days ≈ 0`` (the on-primary branches of
the classification table) we use ``model_construct`` to bypass
validation, mirroring the established pattern in
``tests/test_engine_constraints.py`` and ``tests/test_engine_topology.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contracts.manipulation_scoring import SlackState
from app.engine.driving_path_types import ConstraintDrivenPredecessor
from app.engine.slack_state import SetMembership, classify_slack_state
from app.models.enums import ConstraintType, RelationType

_ANCHOR = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


def _make_pred(uid: int, ds: float) -> ConstraintDrivenPredecessor:
    """Build a :class:`ConstraintDrivenPredecessor` with ``slack_days=ds``.

    Uses ``model_construct`` to bypass the strictly-negative-slack
    validator so on-primary (``ds ≈ 0``) test cases are constructible.
    Only the fields the classifier inspects need realistic values
    (``slack_days``); the rest are populated with neutral defaults so
    the record is shape-complete.
    """
    return ConstraintDrivenPredecessor.model_construct(
        predecessor_uid=uid,
        predecessor_name=f"P{uid}",
        successor_uid=uid + 1000,
        successor_name=f"S{uid + 1000}",
        relation_type=RelationType.FS,
        lag_days=0.0,
        slack_days=float(ds),
        calendar_hours_per_day=8.0,
        predecessor_constraint_type=ConstraintType.MUST_START_ON,
        predecessor_constraint_date=_ANCHOR,
        rationale="test fixture",
    )


# ----------------------------------------------------------------------
# Row coverage — one test per row of the 10-row classification table.
# ----------------------------------------------------------------------


def test_t01_added_b_on_primary_joins_primary() -> None:
    """Row 1: ADDED + B on primary → JOINED_PRIMARY."""
    state = classify_slack_state(
        membership=SetMembership.ADDED,
        period_a_predecessors=(),
        period_b_predecessors=(_make_pred(1, 0.0),),
    )
    assert state is SlackState.JOINED_PRIMARY


def test_t02_added_b_off_primary_eroding_toward_primary() -> None:
    """Row 2: ADDED + B off primary → ERODING_TOWARD_PRIMARY."""
    state = classify_slack_state(
        membership=SetMembership.ADDED,
        period_a_predecessors=(),
        period_b_predecessors=(_make_pred(1, -2.5),),
    )
    assert state is SlackState.ERODING_TOWARD_PRIMARY


def test_t03_removed_a_on_primary_recovering() -> None:
    """Row 3: REMOVED + A on primary → RECOVERING."""
    state = classify_slack_state(
        membership=SetMembership.REMOVED,
        period_a_predecessors=(_make_pred(1, 0.0),),
        period_b_predecessors=(),
    )
    assert state is SlackState.RECOVERING


def test_t04_removed_a_off_primary_recovering() -> None:
    """Row 4: REMOVED + A off primary → RECOVERING (collapses with row 3)."""
    state = classify_slack_state(
        membership=SetMembership.REMOVED,
        period_a_predecessors=(_make_pred(1, -3.0),),
        period_b_predecessors=(),
    )
    assert state is SlackState.RECOVERING


def test_t05_retained_a_off_b_on_joins_primary() -> None:
    """Row 5: RETAINED + A off, B on → JOINED_PRIMARY."""
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(_make_pred(1, -2.0),),
        period_b_predecessors=(_make_pred(1, 0.0),),
    )
    assert state is SlackState.JOINED_PRIMARY


def test_t06_retained_both_on_primary_stable() -> None:
    """Row 6: RETAINED + A on, B on → STABLE.

    Driver in both periods — no transition has occurred in this
    comparison. The Block 4 step 2 scoring engine captures the
    "still a driver" forensic signal separately.
    """
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(_make_pred(1, 0.0),),
        period_b_predecessors=(_make_pred(1, 0.0),),
    )
    assert state is SlackState.STABLE


def test_t07_retained_a_on_b_off_recovering() -> None:
    """Row 7: RETAINED + A on, B off → RECOVERING."""
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(_make_pred(1, 0.0),),
        period_b_predecessors=(_make_pred(1, -1.5),),
    )
    assert state is SlackState.RECOVERING


def test_t08_retained_both_off_b_more_negative_eroding() -> None:
    """Row 8: RETAINED + both off + B_min_DS < A_min_DS → ERODING_TOWARD_PRIMARY."""
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(_make_pred(1, -5.0),),
        period_b_predecessors=(_make_pred(1, -8.0),),
    )
    assert state is SlackState.ERODING_TOWARD_PRIMARY


def test_t09_retained_both_off_equal_stable() -> None:
    """Row 9: RETAINED + both off + B_min_DS == A_min_DS → STABLE."""
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(_make_pred(1, -4.0),),
        period_b_predecessors=(_make_pred(1, -4.0),),
    )
    assert state is SlackState.STABLE


def test_t10_retained_both_off_b_less_negative_recovering() -> None:
    """Row 10: RETAINED + both off + B_min_DS > A_min_DS → RECOVERING."""
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(_make_pred(1, -6.0),),
        period_b_predecessors=(_make_pred(1, -2.0),),
    )
    assert state is SlackState.RECOVERING


# ----------------------------------------------------------------------
# Edge case coverage (≥4 tests beyond the 10-row table).
# ----------------------------------------------------------------------


def test_t11_multiple_predecessors_uses_min_across_edges() -> None:
    """Multi-edge: ``min()`` across edges drives A_min_DS, not first/last/sum.

    Three Period A edges with DS values (-5.0, 0.0, -3.0); A_min_DS
    must be 0.0 → A_on_primary True. Combined with a B side that is
    off-primary, this is row 7 (RECOVERING).
    """
    period_a = (
        _make_pred(1, -5.0),
        _make_pred(2, 0.0),
        _make_pred(3, -3.0),
    )
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=period_a,
        period_b_predecessors=(_make_pred(1, -1.0),),
    )
    assert state is SlackState.RECOVERING


def test_t12_windowing_incomplete_does_not_alter_classification() -> None:
    """``windowing_incomplete=True`` is forensic-visibility only.

    Per the contract docstring on
    ``ManipulationScoringResult.windowing_incomplete``, this module
    does NOT degrade severity / state. Same input shape with the flag
    flipped must yield the same SlackState.
    """
    kwargs = dict(
        membership=SetMembership.ADDED,
        period_a_predecessors=(),
        period_b_predecessors=(_make_pred(1, -1.0),),
    )
    flag_off = classify_slack_state(**kwargs, windowing_incomplete=False)
    flag_on = classify_slack_state(**kwargs, windowing_incomplete=True)
    assert flag_off is flag_on is SlackState.ERODING_TOWARD_PRIMARY


def test_t13_retained_both_empty_with_windowing_defaults_stable() -> None:
    """RETAINED with both predecessor tuples empty under
    ``windowing_incomplete=True`` falls back to STABLE without raising."""
    state = classify_slack_state(
        membership=SetMembership.RETAINED,
        period_a_predecessors=(),
        period_b_predecessors=(),
        windowing_incomplete=True,
    )
    assert state is SlackState.STABLE


def test_t14_floating_point_boundary_is_close_to_zero_is_on_primary() -> None:
    """Float boundary: ``math.isclose(1e-12, 0.0, abs_tol=1e-9)`` is True.

    A near-zero DS like 1e-12 must classify as on-primary; a value
    1.0 (well outside ``abs_tol``) must classify as off-primary. ADDED
    membership exercises the simplest single-side branch.
    """
    on_primary = classify_slack_state(
        membership=SetMembership.ADDED,
        period_a_predecessors=(),
        period_b_predecessors=(_make_pred(1, 1e-12),),
    )
    off_primary = classify_slack_state(
        membership=SetMembership.ADDED,
        period_a_predecessors=(),
        period_b_predecessors=(_make_pred(1, -1.0),),
    )
    assert on_primary is SlackState.JOINED_PRIMARY
    assert off_primary is SlackState.ERODING_TOWARD_PRIMARY
