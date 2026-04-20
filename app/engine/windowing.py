"""Status-date windowing predicate — Milestone 9 Block 2.

The comparator tags a matched :class:`~app.engine.delta.TaskDelta` as
``is_legitimate_actual = True`` when the skill-anchored predicate
fires. The predicate lives here so the comparator orchestration stays
thin and the forensic rule is audit-able as a standalone function.

Authoritative predicate (verbatim from
``forensic-manipulation-patterns §3.2`` and
``driving-slack-and-paths §10``):

    For each matched UniqueID where Period A ``Finish`` ≤ Period B
    ``StatusDate``, Period-B field deltas are treated as **legitimate
    recorded actuals** and excluded from manipulation findings.

Boundary behavior:

* Either ``status_date`` is ``None``  ⇒  predicate is ``False``. The
  filter requires a Period B cutoff to classify a change as
  retrospective statusing; without it the comparator must treat every
  change as a candidate for manipulation scoring (M11 will decide).
* Period A task missing (``TaskPresence.ADDED_IN_B``)  ⇒  ``False``.
  A task that did not exist in A cannot have had its A-side finish
  compared to B's status date.
* Period B task missing (``TaskPresence.DELETED_FROM_A``)  ⇒  ``False``.
  A structural deletion is not a status update.
* Period A ``finish`` is ``None``  ⇒  ``False``. A task with no
  forecast finish in A has no date to compare against the B cutoff.
* All datetime comparisons are tz-aware. Upstream
  :class:`~app.models.task.Task` and
  :class:`~app.models.schedule.Schedule` validators (G1, G9) reject
  naive datetimes at parser boundary; the predicate relies on that
  invariant and does not re-check.

Out-of-scope for this predicate (M11 territory per Block 0 §2.4):

* Scoring the change once it is tagged as candidate manipulation.
* Distinguishing among the five manipulation pattern families.
* Aggregating across multiple revisions (§10 Tier 1/2/3 is M11).

The skill §3.2 text is labeled "(inferred — not sourced)" in the
skill itself; the predicate is encoded here as the canonical
implementation and any future refinement lives in a follow-up
amendment to `forensic-manipulation-patterns/SKILL.md`.
"""

from __future__ import annotations

from datetime import datetime

from app.models.task import Task


def is_legitimate_actual(
    period_a_task: Task | None,
    period_b_task: Task | None,
    period_a_status_date: datetime | None,
    period_b_status_date: datetime | None,
) -> bool:
    """Return ``True`` iff the skill-anchored windowing predicate
    fires for this task pair.

    Signature rationale (Block 0 §2.4): the predicate consumes both
    ``Task`` snapshots and both status dates rather than a
    :class:`~app.engine.delta.TaskDelta`. This keeps the function
    callable at comparator construction time — before ``TaskDelta``
    rows exist — and avoids a circular coupling between
    :mod:`app.engine.delta` and :mod:`app.engine.windowing`.

    Args:
        period_a_task: Period A ``Task`` snapshot, or ``None`` if the
            UniqueID was not present in Period A.
        period_b_task: Period B ``Task`` snapshot, or ``None`` if the
            UniqueID was not present in Period B.
        period_a_status_date: Period A ``Schedule.status_date``.
        period_b_status_date: Period B ``Schedule.status_date``.

    Returns:
        ``True`` iff all four arguments are non-``None``, the Period
        A task carries a non-``None`` ``finish``, and that finish is
        less than or equal to ``period_b_status_date``. ``False`` in
        every other case.

    The predicate never raises. Naive-vs-aware datetime comparison
    is impossible because the model validators enforce tz-awareness
    at the Schedule boundary; an attempt to call this function with
    a hand-built naive datetime would surface as a Python
    ``TypeError`` at the comparison site, which is the correct
    failure mode for a contract violation.
    """
    # Structural change — not a status update.
    if period_a_task is None or period_b_task is None:
        return False

    # Window requires both cutoffs.
    if period_a_status_date is None or period_b_status_date is None:
        return False

    # The A-side task must have a forecast finish to compare.
    a_finish = period_a_task.finish
    if a_finish is None:
        return False

    # The authoritative predicate: Period A finish ≤ Period B status date.
    return a_finish <= period_b_status_date
