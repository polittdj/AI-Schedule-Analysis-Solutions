"""Constraint-type handlers applied in the forward and backward passes.

All eight :class:`~app.models.enums.ConstraintType` values are honored.
Semantics follow ``driving-slack-and-paths §4`` for MSO/MFO/SNLT/FNLT/
SNET/FNET and MS Project's default-scheduling semantics for ASAP/ALAP:

=====  ==================  ==============================================
Type    Role                Forward/backward effect
=====  ==================  ==============================================
ASAP    Default forward     No constraint; forward pass pushes ES as
                            early as predecessors allow.
ALAP    Default backward    No constraint on forward pass; backward pass
                            pulls LS/LF as late as successors allow
                            (this is MSP's "schedule from project finish"
                            bias; BUILD-PLAN §5 M4 E9).
MSO     Hard start          Forward: ES = constraint_date (snapped
                            forward). Backward: LS = constraint_date.
MFO     Hard finish         Forward: EF = constraint_date (snapped
                            backward). Backward: LF = constraint_date.
SNET    Soft forward        Forward: ES = max(ES, constraint_date).
                            No backward effect.
SNLT    Soft backward       Backward: LS = min(LS, constraint_date).
                            Forward breach → :class:`ConstraintViolation`.
FNET    Soft forward        Forward: EF = max(EF, constraint_date).
                            No backward effect.
FNLT    Soft backward       Backward: LF = min(LF, constraint_date).
                            Forward breach → :class:`ConstraintViolation`.
=====  ==================  ==============================================

Forward breaches (e.g. predecessor forces successor past an FNLT date)
surface as :class:`ConstraintViolation` records on
:class:`~app.engine.result.CPMResult` — **not** as exceptions
(BUILD-PLAN §5 M4 E8/E11).

Malformed inputs — a date-bearing constraint without a date, which
the :class:`~app.models.task.Task` validator G7 forbids — raise
:class:`InvalidConstraintError` when the engine is fed a dict-injected
task bypassing Pydantic (BUILD-PLAN §5 M4 E22).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.engine.calendar_math import snap_backward, snap_forward
from app.engine.exceptions import ConstraintViolation, InvalidConstraintError
from app.models.calendar import Calendar
from app.models.enums import ConstraintType
from app.models.task import Task


@dataclass(slots=True)
class ForwardConstraintOutcome:
    """Result of applying a constraint during the forward pass."""

    early_start: datetime
    early_finish: datetime
    violation: ConstraintViolation | None = None


@dataclass(slots=True)
class BackwardConstraintOutcome:
    """Result of applying a constraint during the backward pass."""

    late_start: datetime
    late_finish: datetime
    violation: ConstraintViolation | None = None


def _require_date(task: Task) -> datetime:
    """Return ``task.constraint_date`` or raise if missing."""
    if task.constraint_date is None:
        raise InvalidConstraintError(
            task.unique_id,
            f"{task.constraint_type.name} requires a constraint_date (G7)",
        )
    return task.constraint_date


def apply_forward_constraint(
    task: Task,
    es_from_predecessors: datetime,
    ef_from_predecessors: datetime,
    cal: Calendar,
) -> ForwardConstraintOutcome:
    """Apply the task's constraint to its computed ES/EF.

    The caller has already folded in every predecessor's bound using
    :func:`~app.engine.relations.forward_link_bound` and, where a
    relation did not constrain ES directly (FF, SF), derived ES from
    EF via the task's duration. This function then narrows or locks
    those values per the constraint type.

    Args:
        task: task carrying the constraint.
        es_from_predecessors: ES as implied by incoming links and the
            task's own duration. Must be tz-aware.
        ef_from_predecessors: EF as implied by incoming links and the
            task's own duration.
        cal: calendar for snapping.

    Returns:
        :class:`ForwardConstraintOutcome` with possibly adjusted ES/EF
        and a :class:`ConstraintViolation` if an SNLT/FNLT date was
        breached in the forward pass.
    """
    ct = task.constraint_type
    es = es_from_predecessors
    ef = ef_from_predecessors
    violation: ConstraintViolation | None = None

    if ct == ConstraintType.AS_SOON_AS_POSSIBLE:
        pass
    elif ct == ConstraintType.AS_LATE_AS_POSSIBLE:
        # ALAP has no forward-pass effect — its bias is applied in the
        # backward pass per MSP semantics (E9).
        pass
    elif ct == ConstraintType.MUST_START_ON:
        d = snap_forward(_require_date(task), cal)
        es = d
        # EF is re-derived from the new ES by the caller using
        # duration; we return ES locked and leave EF placeholder to
        # the caller's subsequent duration add.
        ef = d
    elif ct == ConstraintType.MUST_FINISH_ON:
        d = snap_backward(_require_date(task), cal)
        ef = d
        # ES re-derived by the caller subtracting duration.
        es = d
    elif ct == ConstraintType.START_NO_EARLIER_THAN:
        d = snap_forward(_require_date(task), cal)
        if d > es:
            es = d
    elif ct == ConstraintType.FINISH_NO_EARLIER_THAN:
        d = snap_forward(_require_date(task), cal)
        if d > ef:
            ef = d
    elif ct == ConstraintType.START_NO_LATER_THAN:
        d = snap_backward(_require_date(task), cal)
        if es > d:
            violation = ConstraintViolation(
                unique_id=task.unique_id,
                kind="SNLT_BREACHED",
                constraint_date=d,
                computed_date=es,
                detail=(
                    f"forward pass forced start to {es.isoformat()} past "
                    f"SNLT {d.isoformat()}"
                ),
            )
    elif ct == ConstraintType.FINISH_NO_LATER_THAN:
        d = snap_backward(_require_date(task), cal)
        if ef > d:
            violation = ConstraintViolation(
                unique_id=task.unique_id,
                kind="FNLT_BREACHED",
                constraint_date=d,
                computed_date=ef,
                detail=(
                    f"forward pass forced finish to {ef.isoformat()} past "
                    f"FNLT {d.isoformat()}"
                ),
            )
    else:
        raise InvalidConstraintError(task.unique_id, f"unknown constraint {ct!r}")

    return ForwardConstraintOutcome(early_start=es, early_finish=ef, violation=violation)


def apply_backward_constraint(
    task: Task,
    ls_from_successors: datetime,
    lf_from_successors: datetime,
    cal: Calendar,
) -> BackwardConstraintOutcome:
    """Apply the task's constraint to its computed LS/LF.

    Symmetric to :func:`apply_forward_constraint` for the backward pass.

    Returns:
        :class:`BackwardConstraintOutcome`; SNET/FNET breaches are
        recorded as soft violations (the forward pass has already
        respected them; a backward-pass breach would be uncommon but
        still emitted rather than raised).
    """
    ct = task.constraint_type
    ls = ls_from_successors
    lf = lf_from_successors
    violation: ConstraintViolation | None = None

    if ct == ConstraintType.AS_SOON_AS_POSSIBLE:
        pass
    elif ct == ConstraintType.AS_LATE_AS_POSSIBLE:
        pass
    elif ct == ConstraintType.MUST_START_ON:
        d = snap_forward(_require_date(task), cal)
        ls = d
        lf = d
    elif ct == ConstraintType.MUST_FINISH_ON:
        d = snap_backward(_require_date(task), cal)
        lf = d
        ls = d
    elif ct == ConstraintType.START_NO_LATER_THAN:
        d = snap_backward(_require_date(task), cal)
        if d < ls:
            ls = d
    elif ct == ConstraintType.FINISH_NO_LATER_THAN:
        d = snap_backward(_require_date(task), cal)
        if d < lf:
            lf = d
    elif ct == ConstraintType.START_NO_EARLIER_THAN:
        d = snap_forward(_require_date(task), cal)
        if ls < d:
            violation = ConstraintViolation(
                unique_id=task.unique_id,
                kind="SNET_BREACHED_BACKWARD",
                constraint_date=d,
                computed_date=ls,
                detail=(
                    f"backward pass late start {ls.isoformat()} earlier than "
                    f"SNET {d.isoformat()}"
                ),
            )
    elif ct == ConstraintType.FINISH_NO_EARLIER_THAN:
        d = snap_forward(_require_date(task), cal)
        if lf < d:
            violation = ConstraintViolation(
                unique_id=task.unique_id,
                kind="FNET_BREACHED_BACKWARD",
                constraint_date=d,
                computed_date=lf,
                detail=(
                    f"backward pass late finish {lf.isoformat()} earlier than "
                    f"FNET {d.isoformat()}"
                ),
            )
    else:
        raise InvalidConstraintError(task.unique_id, f"unknown constraint {ct!r}")

    return BackwardConstraintOutcome(late_start=ls, late_finish=lf, violation=violation)
