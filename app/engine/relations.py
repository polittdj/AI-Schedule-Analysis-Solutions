"""Per-relation-type driving-slack and pass-propagation formulas.

Anchored to ``driving-slack-and-paths §3``:

* FS  (Finish-to-Start): DS = ES(succ) - EF(pred) - lag
* SS  (Start-to-Start):  DS = ES(succ) - ES(pred) - lag
* FF  (Finish-to-Finish): DS = EF(succ) - EF(pred) - lag
* SF  (Start-to-Finish): DS = EF(succ) - ES(pred) - lag

The same four formulas drive the forward pass and the backward pass
once rearranged:

Forward pass — given predecessor ES/EF, what is the earliest
successor can begin and finish across this link? The link contributes
a lower bound on either ``ES(succ)`` or ``EF(succ)``:

* FS: ``ES(succ) >= EF(pred) + lag``
* SS: ``ES(succ) >= ES(pred) + lag``
* FF: ``EF(succ) >= EF(pred) + lag``
* SF: ``EF(succ) >= ES(pred) + lag``

The missing boundary (ES for FF/SF, EF for FS/SS) is derived from the
successor's own duration in the caller — this module does not know
durations.

Backward pass — given successor LS/LF, what is the latest predecessor
can finish or start without delaying the successor? The link
contributes an upper bound on either ``LS(pred)`` or ``LF(pred)``:

* FS: ``LF(pred) <= LS(succ) - lag``
* SS: ``LS(pred) <= LS(succ) - lag``
* FF: ``LF(pred) <= LF(succ) - lag``
* SF: ``LS(pred) <= LF(succ) - lag``

Lag is positive (wait), negative (lead), or zero. Calendar-aware
addition/subtraction from :mod:`app.engine.calendar_math` handles
weekends and exceptions; ``driving-slack-and-paths §8`` CPM discipline
invariant requires calendar-faithful arithmetic.
"""

from __future__ import annotations

from datetime import datetime

from app.engine.calendar_math import (
    add_working_minutes,
    snap_forward,
    subtract_working_minutes,
    working_minutes_between,
)
from app.models.calendar import Calendar
from app.models.enums import RelationType


def forward_link_bound(
    rel_type: RelationType,
    pred_es: datetime,
    pred_ef: datetime,
    lag_minutes: int,
    cal: Calendar,
) -> tuple[str, datetime]:
    """Return the bound a relation imposes on the successor.

    Returns a tuple ``(field, bound)``:

    * ``field == "ES"``: bound is a lower bound on the successor's
      early start (FS, SS).
    * ``field == "EF"``: bound is a lower bound on the successor's
      early finish (FF, SF).

    The bound already includes ``lag_minutes``. The caller applies
    ``max()`` across all predecessor links (BUILD-PLAN §5 M4 E15).
    """
    if rel_type == RelationType.FS:
        return "ES", add_working_minutes(pred_ef, lag_minutes, cal)
    if rel_type == RelationType.SS:
        return "ES", add_working_minutes(pred_es, lag_minutes, cal)
    if rel_type == RelationType.FF:
        return "EF", add_working_minutes(pred_ef, lag_minutes, cal)
    if rel_type == RelationType.SF:
        return "EF", add_working_minutes(pred_es, lag_minutes, cal)
    raise ValueError(f"unknown RelationType: {rel_type!r}")


def backward_link_bound(
    rel_type: RelationType,
    succ_ls: datetime,
    succ_lf: datetime,
    lag_minutes: int,
    cal: Calendar,
) -> tuple[str, datetime]:
    """Return the bound a relation imposes on the predecessor.

    Returns ``(field, bound)``:

    * ``field == "LF"``: bound is an upper bound on the predecessor's
      late finish (FS, FF).
    * ``field == "LS"``: bound is an upper bound on the predecessor's
      late start (SS, SF).

    The caller applies ``min()`` across all successor links
    (BUILD-PLAN §5 M4 E16).
    """
    if rel_type == RelationType.FS:
        return "LF", subtract_working_minutes(succ_ls, lag_minutes, cal)
    if rel_type == RelationType.SS:
        return "LS", subtract_working_minutes(succ_ls, lag_minutes, cal)
    if rel_type == RelationType.FF:
        return "LF", subtract_working_minutes(succ_lf, lag_minutes, cal)
    if rel_type == RelationType.SF:
        return "LS", subtract_working_minutes(succ_lf, lag_minutes, cal)
    raise ValueError(f"unknown RelationType: {rel_type!r}")


def link_driving_slack_minutes(
    rel_type: RelationType,
    pred_es: datetime,
    pred_ef: datetime,
    succ_es: datetime,
    succ_ef: datetime,
    lag_minutes: int,
    cal: Calendar,
) -> int:
    """Working-minute driving slack across a single link.

    Positive → predecessor has that many working minutes of
    flexibility before driving the successor. Zero → predecessor is
    driving. Negative → the link is already violated (the forward pass
    ought to have pushed the successor further, so negative DS means
    the predecessor-successor pair is in conflict — typically with a
    constraint on the successor).

    The formulas are taken verbatim from ``driving-slack-and-paths
    §3``; the subtraction is performed in working minutes so that the
    result is calendar-faithful (SSI worked example §2.4 is in
    working-day counts).
    """
    # The formula shapes:
    #   FS: DS = ES(succ) - EF(pred) - lag
    #   SS: DS = ES(succ) - ES(pred) - lag
    #   FF: DS = EF(succ) - EF(pred) - lag
    #   SF: DS = EF(succ) - ES(pred) - lag
    if rel_type == RelationType.FS:
        left, right = succ_es, pred_ef
    elif rel_type == RelationType.SS:
        left, right = succ_es, pred_es
    elif rel_type == RelationType.FF:
        left, right = succ_ef, pred_ef
    elif rel_type == RelationType.SF:
        left, right = succ_ef, pred_es
    else:
        raise ValueError(f"unknown RelationType: {rel_type!r}")

    # Snap both operands forward so the working-minute distance ignores
    # whichever trailing non-working tail an end-of-window date may
    # have (e.g. EF that lands at Fri 16:00 vs Mon 08:00).
    left_c = snap_forward(left, cal)
    right_c = snap_forward(right, cal)
    gap_min = working_minutes_between(right_c, left_c, cal)
    return gap_min - lag_minutes
