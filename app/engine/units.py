"""Units conversion helper for the forensic output contract.

Block 7 (2026-04-22) establishes a units convention for the driving-
path public contracts: public Pydantic models carry durations in
**days** (float), while the CPM engine continues to carry minutes
internally to preserve multi-calendar precision. Conversion happens
at the contract boundary.

This module is the **sole** path for minute → day conversion on the
public contract. Inline arithmetic such as ``minutes / 480`` is
prohibited — it silently hard-codes an 8-hour working day and breaks
multi-calendar schedules (``mpp-parsing-com-automation §3.5`` Gotcha
5). Existing :func:`app.engine.duration.minutes_to_working_days` is
retained for metric code that needs the ``int | None`` input shape;
driving-path contracts accept ``float`` and require ``None`` filtering
upstream so the audit-trail invariant (``days * hours_per_day * 60 ==
minutes``) holds exactly.

Every public contract model that carries a days-denominated duration
also carries the ``calendar_hours_per_day`` factor used to compute it
(BUILD-PLAN §2.18 companion note). An attorney or senior reviewer can
reconstruct minutes from ``days * hours_per_day * 60`` without
re-running the engine.
"""

from __future__ import annotations

import math


def minutes_to_days(minutes: float, hours_per_day: float) -> float:
    """Convert a duration in minutes to days using a calendar factor.

    The conversion is ``minutes / (hours_per_day * 60)``. Every
    minute-to-day conversion on the driving-path public contract MUST
    go through this function — it is the forensic audit-trail point
    documented at BUILD-PLAN §2.18.

    Args:
        minutes: Duration in minutes. May be negative (leads on
            relationships produce negative slack / lag values per
            ``driving-slack-and-paths §3``).
        hours_per_day: Calendar hours-per-day factor. Must be
            strictly positive. Sourced from
            :attr:`app.models.task.Task.calendar_hours_per_day` when
            non-``None``, otherwise
            :attr:`app.models.schedule.Schedule.project_calendar_hours_per_day`
            (the M1.1 patch session denormalised these fields so this
            helper need not walk calendars).

    Returns:
        Duration in days as a ``float``. A full 8-hour day at
        ``hours_per_day=8.0`` returns ``1.0`` exactly; fractional
        inputs round per IEEE-754.

    Raises:
        ValueError: ``hours_per_day <= 0``. A zero or negative value
            would produce a division-by-zero or a sign-flipped
            result; either is a correctness bug, not a data
            anomaly.
    """
    if hours_per_day <= 0:
        raise ValueError(
            f"hours_per_day must be strictly positive (got {hours_per_day!r}); "
            "a non-positive calendar factor breaks the "
            "days * hours_per_day * 60 == minutes audit trail"
        )
    return minutes / (hours_per_day * 60.0)


def format_days(days: float) -> str:
    """Format a days-denominated duration for user-visible output.

    This helper is the **sole** formatting point for user-visible
    durations — Pydantic contract string fields, renderer output,
    README examples, Word/Excel/HTML report bodies, and CLI output
    all route through here per BUILD-PLAN §2.19 (AM9, 4/23/2026).
    Authority: NASA Schedule Management Handbook §5.5.9.1 ("task
    durations should generally be assigned in workdays"); Papicito's
    forensic-tool standard dated 4/23/2026.

    Format rules (verbatim from BUILD-PLAN §2.19):

    - Maximum 2-decimal precision.
    - Positive values round by ceiling to the next 0.01; negative
      values round by floor to the next -0.01; exactly ``0.0`` is
      preserved without rounding.
    - Trailing zeros and any orphan decimal point are stripped.
    - Leading zero omitted on fractional absolute values (``0.5``
      renders as ``.5``, ``-0.5`` renders as ``-.5``).
    - Singular suffix ``" day"`` only when the rounded value equals
      ``+1.0`` or ``-1.0`` exactly; ``" days"`` everywhere else,
      including ``".5 days"`` and ``"0 days"``.

    Example inputs and outputs:

    =========  ============
    Input      Output
    =========  ============
    ``0.0``    ``"0 days"``
    ``1.0``    ``"1 day"``
    ``-1.0``   ``"-1 day"``
    ``3.0``    ``"3 days"``
    ``0.5``    ``".5 days"``
    ``-0.5``   ``"-.5 days"``
    ``2.25``   ``"2.25 days"``
    ``0.003``  ``".01 days"``
    ``-0.003`` ``"-.01 days"``
    ``100.0``  ``"100 days"``
    =========  ============

    Args:
        days: Duration in days as a ``float``. May be negative,
            zero, or positive.

    Returns:
        The formatted user-visible string with the appropriate
        singular / plural unit suffix.
    """
    if days == 0.0:
        return "0 days"

    if days > 0.0:
        rounded = math.ceil(days * 100.0) / 100.0
    else:
        rounded = math.floor(days * 100.0) / 100.0

    text = f"{rounded:.2f}".rstrip("0").rstrip(".")

    if text.startswith("0."):
        text = text[1:]
    elif text.startswith("-0."):
        text = "-" + text[2:]

    if text == "" or text == "-":
        return "0 days"

    suffix = " day" if rounded == 1.0 or rounded == -1.0 else " days"
    return text + suffix


__all__ = ["format_days", "minutes_to_days"]
