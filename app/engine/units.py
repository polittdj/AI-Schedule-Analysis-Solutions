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


__all__ = ["minutes_to_days"]
