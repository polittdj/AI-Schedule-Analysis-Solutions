"""Duration-unit conversion helpers.

``mpp-parsing-com-automation §3.5`` (Gotcha 5) fixes durations, lags,
and slacks in **minutes** inside the data model. The presentation
layer (Milestone 13) renders working days; DCMA metrics consume both
forms. This module provides the conversion in both directions so
callers never roll their own arithmetic.

Consumers:

* :class:`~app.engine.result.TaskCPMResult` emits minutes; DCMA
  Metrics 6 (High Float) and 8 (High Duration) want working days.
* :class:`~app.engine.options.CPMOptions.near_critical_threshold_days`
  is expressed in working days for operator ergonomics; the CPM
  engine converts to minutes internally.

The conversion uses the project default calendar's
:attr:`Calendar.hours_per_day`, as required by §3.5 — a hard-coded
``480`` would desync any non-8h/day calendar.
"""

from __future__ import annotations


def minutes_to_working_days(minutes: int | None, hours_per_day: float = 8.0) -> float:
    """Convert minutes to working days.

    Returns ``0.0`` when ``minutes`` is ``None``; otherwise
    ``minutes / (hours_per_day * 60)``. Mirrors the canonical
    ``mpp-parsing-com-automation §3.5`` snippet.
    """
    if minutes is None:
        return 0.0
    if hours_per_day <= 0:
        raise ValueError("hours_per_day must be positive")
    return minutes / (hours_per_day * 60.0)


def working_days_to_minutes(days: float, hours_per_day: float = 8.0) -> int:
    """Convert working days to minutes, rounded to the nearest minute.

    Accepts fractional days so a threshold like ``0.5`` resolves to
    ``240`` minutes on an 8h/day calendar.
    """
    if hours_per_day <= 0:
        raise ValueError("hours_per_day must be positive")
    return int(round(days * hours_per_day * 60.0))
