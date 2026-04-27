"""SlackState classifier — Period A vs Period B per-UID transition rules.

Maps the tuple ``(set_membership, period_a_predecessors,
period_b_predecessors)`` to a value of
:class:`app.contracts.manipulation_scoring.SlackState`. The set-algebra
buckets are emitted by the Block 3 cross-version comparator
(``ConstraintDrivenCrossVersionResult``); this module is the pure-
function classifier consumed by the Block 4 step 2 manipulation
scoring engine.

Authority:

* ``forensic-manipulation-patterns §9`` (cross-version erosion
  detection).
* ``forensic-manipulation-patterns §4.4`` (constraint injection)
  and ``§4.5`` (constraint removal hiding slip) — the manipulation
  patterns this classification is downstream of.
* ``driving-slack-and-paths §6`` (cross-version trend label
  vocabulary), ``§1`` (DS vs TS vs FS), ``§9`` (Period A but-for
  rule).

This module is the **first canonicalization** of the SlackState
transition rules. Both authority skills explicitly defer the
cross-version erosion detection algorithm to "Session 18 cross-skill
reconciliation". Lessons Learned §11 #3 uses the five-label
vocabulary (CRITICAL / SEVERE EROSION / ERODING / STABLE / IMPROVING)
which is **not** the AM12-adapted four-state vocabulary used by the
contract; this module implements the AM12 four-state vocabulary
(``JOINED_PRIMARY`` / ``ERODING_TOWARD_PRIMARY`` / ``STABLE`` /
``RECOVERING``).

Classification table (10 rows; the function MUST produce these
outputs for these inputs):

    ADDED set (B present, not A present):
      1. B_on_primary=True                         → JOINED_PRIMARY
      2. B_on_primary=False                        → ERODING_TOWARD_PRIMARY

    REMOVED set (A present, not B present):
      3. A_on_primary=True                         → RECOVERING
      4. A_on_primary=False                        → RECOVERING
         (Both rows collapse to RECOVERING — the UID has fully
         exited the constraint-driven bucket.)

    RETAINED set (A present and B present):
      5. A_on=False, B_on=True                     → JOINED_PRIMARY
      6. A_on=True,  B_on=True                     → STABLE
      7. A_on=True,  B_on=False                    → RECOVERING
      8. A_on=False, B_on=False, B_min_DS < A_min  → ERODING_TOWARD_PRIMARY
      9. A_on=False, B_on=False, B_min_DS == A_min → STABLE
     10. A_on=False, B_on=False, B_min_DS > A_min  → RECOVERING

    Row 6 ("on primary in both") is conceptually still a driver,
    but no transition has occurred in this comparison — STABLE is
    correct here. The forensic signal that a Period A driver
    remains a driver in Period B is captured at scoring time
    (Block 4 step 2), not in this classifier.

Floating-point equality policy: ``ConstraintDrivenPredecessor.slack_days``
is a ``float`` denominated in working days
(see :mod:`app.engine.driving_path_types`). On-primary and
A_min == B_min comparisons therefore use
``math.isclose(value, 0.0, abs_tol=1e-9)`` — exact equality on a
days-denominated float would be brittle to non-8h/day calendar
conversions. Note that the CDP type validator separately requires
``slack_days < -1.157e-5``; in practice the on-primary branches are
unreachable for valid CDP records but are encoded for completeness
of the classification table.

``windowing_incomplete`` behavior: per
:class:`app.contracts.manipulation_scoring.ManipulationScoringResult`
the flag is forensic-visibility only — "the scoring record is
retained rather than dropped; severity tier may be degraded by
downstream consumers but is NOT degraded by the scoring engine
itself." This module follows the same rule: classify with whatever
data is available; never raise; never skip. When predecessor data
is missing on a side that would otherwise drive classification,
fall back to a defensible default (``RECOVERING`` for REMOVED,
``STABLE`` for the empty RETAINED edge case).
"""

from __future__ import annotations

import math
from enum import StrEnum

from app.contracts.manipulation_scoring import SlackState
from app.engine.driving_path_types import ConstraintDrivenPredecessor


class SetMembership(StrEnum):
    """Internal helper enum for the classifier's set-algebra input.

    Mirrors the three set-algebra fields on
    :class:`~app.contracts.manipulation_scoring.ConstraintDrivenCrossVersionResult`
    (``added_constraint_driven_uids`` / ``removed_constraint_driven_uids``
    / ``retained_constraint_driven_uids``). Internal to this module —
    not exported on the public manipulation-scoring contract surface.
    """

    ADDED = "added"
    REMOVED = "removed"
    RETAINED = "retained"


# Absolute tolerance for "on the primary path" (slack ≈ 0). 1 ns in
# working-days terms — well below the CDP validator's 1-second
# tolerance (``_ZERO_SLACK_TOLERANCE_DAYS`` in driving_path_types.py)
# but tight enough to keep day-precision arithmetic from drifting.
_ON_PRIMARY_ABS_TOL: float = 1e-9


def _min_driving_slack(
    predecessors: tuple[ConstraintDrivenPredecessor, ...],
) -> float | None:
    """Return the minimum per-edge driving slack across predecessors.

    Returns ``None`` when the tuple is empty. ``ConstraintDrivenPredecessor.
    slack_days`` is the per-edge driving slack to the project-finish
    Focus Point per ``driving-slack-and-paths §3``.
    """
    if not predecessors:
        return None
    return min(p.slack_days for p in predecessors)


def _on_primary(min_ds: float | None) -> bool:
    """Return True if ``min_ds`` is approximately zero (on primary path).

    ``slack_days`` is float, so use ``math.isclose`` rather than exact
    equality.
    """
    if min_ds is None:
        return False
    return math.isclose(min_ds, 0.0, abs_tol=_ON_PRIMARY_ABS_TOL)


def classify_slack_state(
    *,
    membership: SetMembership,
    period_a_predecessors: tuple[ConstraintDrivenPredecessor, ...],
    period_b_predecessors: tuple[ConstraintDrivenPredecessor, ...],
    windowing_incomplete: bool = False,
) -> SlackState:
    """Classify a UID's Period A → Period B SlackState transition.

    Pure function — no I/O, no global state, never raises for valid
    inputs. Always returns a :class:`SlackState`.

    Keyword-only parameters:

    :param membership: One of :class:`SetMembership` — which of the
        three set-algebra buckets this UID landed in.
    :param period_a_predecessors: Tuple of
        :class:`ConstraintDrivenPredecessor` records on this UID in
        Period A. Empty tuple when ``membership`` is ``ADDED``.
    :param period_b_predecessors: Tuple of
        :class:`ConstraintDrivenPredecessor` records on this UID in
        Period B. Empty tuple when ``membership`` is ``REMOVED``.
    :param windowing_incomplete: Forensic-visibility flag passed
        through from the Block 3 result. Does NOT alter classification
        in this module — the flag is honored by downstream severity-
        tier consumers per the contract docstring.
    :returns: The :class:`SlackState` value per the 10-row
        classification table documented at module level.
    """
    a_min_ds = _min_driving_slack(period_a_predecessors)
    b_min_ds = _min_driving_slack(period_b_predecessors)
    a_on_primary = _on_primary(a_min_ds)
    b_on_primary = _on_primary(b_min_ds)

    match membership:
        case SetMembership.ADDED:
            # Rows 1–2: only Period B predecessors meaningful.
            if b_on_primary:
                return SlackState.JOINED_PRIMARY
            return SlackState.ERODING_TOWARD_PRIMARY

        case SetMembership.REMOVED:
            # Rows 3–4 collapse: UID has fully exited the constraint-
            # driven bucket in Period B. Period A on-primary value is
            # immaterial to the outcome.
            return SlackState.RECOVERING

        case SetMembership.RETAINED:
            # Empty-on-both edge case: defensible default with no
            # classification basis is STABLE (per windowing_incomplete
            # rule — never raise, classify with what is available).
            if a_min_ds is None and b_min_ds is None:
                return SlackState.STABLE

            # Row 5: A off-primary, B on-primary.
            if not a_on_primary and b_on_primary:
                return SlackState.JOINED_PRIMARY
            # Row 6: both on-primary.
            if a_on_primary and b_on_primary:
                return SlackState.STABLE
            # Row 7: A on-primary, B off-primary.
            if a_on_primary and not b_on_primary:
                return SlackState.RECOVERING

            # Rows 8–10: both off-primary; compare magnitudes.
            # Defensive: if one side is None (windowing_incomplete
            # with partial data), fall back to STABLE rather than
            # comparing None.
            if a_min_ds is None or b_min_ds is None:
                return SlackState.STABLE
            if math.isclose(a_min_ds, b_min_ds, abs_tol=_ON_PRIMARY_ABS_TOL):
                return SlackState.STABLE  # row 9
            if b_min_ds < a_min_ds:
                return SlackState.ERODING_TOWARD_PRIMARY  # row 8
            return SlackState.RECOVERING  # row 10


__all__ = [
    "SetMembership",
    "classify_slack_state",
]
