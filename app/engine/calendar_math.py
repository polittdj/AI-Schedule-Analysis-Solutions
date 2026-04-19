"""Working-calendar arithmetic.

All CPM date math is calendar-aware. Raw clock minutes would over-
schedule weekends and holidays and undercut the MS-Project-match
requirement in ``driving-slack-and-paths §8`` (CPM discipline
invariant: forward/backward pass dates must match MSP field-for-field).
``mpp-parsing-com-automation §3.5`` (Gotcha 5) fixes durations in
**minutes**; this module provides the minutes-to-datetime translation
using an :class:`~app.models.calendar.Calendar`.

Model
=====

Working time is modeled as a sequence of daily windows. For a given
date:

* If the date falls inside a ``CalendarException`` with
  ``is_working=False``, the date has **no** working windows.
* If the date falls inside a ``CalendarException`` with
  ``is_working=True``, the date has exactly the
  ``working_times`` windows (empty list → single default window).
* Otherwise, the date is working iff its weekday is in the base
  working-day set (Mon-Fri by default; Mon-Sun if
  ``Calendar.working_days_per_week == 7``).

The default working window for a working day is
``[08:00, 08:00 + hours_per_day)`` UTC. A "working minute" is an
instant ``t`` such that some window ``[w_start, w_end)`` contains it
(half-open interval — end-of-day belongs to the next window's start).

Convention: advancing zero minutes from the end of a window snaps to
the start of the next window. E12 (BUILD-PLAN §5 M4) calls this
explicitly — a 1-working-day task starting Friday 08:00 must finish
Monday 08:00, not Friday 16:00 and not Saturday.

All inputs and outputs are tz-aware (G1, ``mpp-parsing-com-automation
§3.10``). UTC is the wire convention; non-UTC inputs are preserved
without conversion — the engine compares on wall-clock minute arithmetic
per tz, which is safe provided inputs all share one zone (the M3 parser
guarantees UTC across the pipeline per AM1).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.models.calendar import Calendar, CalendarException, WorkingTime

_MIN_PER_DAY = 24 * 60
_DEFAULT_DAY_START_MIN = 8 * 60  # 08:00


def _day_start(d: date, tzinfo) -> datetime:  # type: ignore[no-untyped-def]
    return datetime.combine(d, time(0, 0), tzinfo=tzinfo)


def _base_is_working_weekday(d: date, cal: Calendar) -> bool:
    """Return True if the weekday is in the calendar's base work set.

    Mon=0..Sun=6. Supports the two common forms (5-day Mon-Fri and
    7-day around-the-clock). Other configurations fall back to
    Mon-Fri; the ``driving-slack-and-paths §8`` multi-calendar rule
    is labeled inferred in-skill, so Phase 1 keeps the base pattern
    conservative and documented.
    """
    if cal.working_days_per_week == 7:
        return True
    return d.weekday() < 5


def _exception_for_date(d: date, cal: Calendar) -> CalendarException | None:
    """Return the first :class:`CalendarException` whose inclusive
    date range contains ``d``, or ``None``.

    Earlier exceptions in :attr:`Calendar.exceptions` win — matches the
    COM iteration order from ``mpp-parsing-com-automation §3``.
    """
    for exc in cal.exceptions:
        if exc.start.date() <= d <= exc.finish.date():
            return exc
    return None


def _default_window_for_day(cal: Calendar) -> WorkingTime:
    """The synthesized default window for a working weekday.

    Start = 08:00; length = ``hours_per_day * 60`` minutes. Synthesized
    each call rather than cached — cheap, and avoids mutable-default
    footguns if the engine is imported in a long-lived process.
    """
    end_min = _DEFAULT_DAY_START_MIN + int(round(cal.hours_per_day * 60))
    end_min = min(end_min, _MIN_PER_DAY)
    return WorkingTime(from_minute=_DEFAULT_DAY_START_MIN, to_minute=end_min)


def working_windows_for_date(d: date, cal: Calendar) -> list[tuple[int, int]]:
    """Return the list of ``(from_min, to_min)`` windows for ``d``.

    Empty list means the date is fully non-working. Windows are
    sorted by start minute and do not overlap (validated by the
    model's :class:`WorkingTime` constructor). Values are half-open
    in minutes-from-midnight.
    """
    exc = _exception_for_date(d, cal)
    if exc is not None:
        if not exc.is_working:
            return []
        if exc.working_times:
            return sorted(
                (wt.from_minute, wt.to_minute) for wt in exc.working_times
            )
        w = _default_window_for_day(cal)
        return [(w.from_minute, w.to_minute)]

    if not _base_is_working_weekday(d, cal):
        return []

    w = _default_window_for_day(cal)
    return [(w.from_minute, w.to_minute)]


def _minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def is_working_minute(dt: datetime, cal: Calendar) -> bool:
    """Return True iff ``dt`` falls inside a working window.

    End-of-window is **not** a working minute (half-open).

    Raises:
        ValueError: if ``dt`` is tz-naive.
    """
    if dt.tzinfo is None:
        raise ValueError("is_working_minute requires a tz-aware datetime (G1)")
    m = _minute_of_day(dt)
    for w_start, w_end in working_windows_for_date(dt.date(), cal):
        if w_start <= m < w_end:
            return True
    return False


def _iter_windows_forward(
    start_date: date, cal: Calendar, horizon_days: int = 365 * 20
):
    """Yield ``(date, w_start_min, w_end_min)`` triples forward.

    Bounded horizon prevents runaway iteration on pathological inputs
    (a schedule with no working days at all). Default horizon of 20
    years is generous for any realistic IMS.
    """
    d = start_date
    for _ in range(horizon_days):
        for w_start, w_end in working_windows_for_date(d, cal):
            yield d, w_start, w_end
        d += timedelta(days=1)


def _iter_windows_backward(
    start_date: date, cal: Calendar, horizon_days: int = 365 * 20
):
    """Yield ``(date, w_start_min, w_end_min)`` triples backward."""
    d = start_date
    for _ in range(horizon_days):
        windows = working_windows_for_date(d, cal)
        for w_start, w_end in reversed(windows):
            yield d, w_start, w_end
        d -= timedelta(days=1)


def snap_forward(dt: datetime, cal: Calendar) -> datetime:
    """Snap ``dt`` forward to the next working moment.

    If ``dt`` is already a working minute, it is returned unchanged.
    If ``dt`` lies at or past a window's end, the result is the start
    of the next window. This is the convention that makes
    ``add_working_minutes(EF, 0)`` equivalent to snapping the
    successor's ES forward through a day boundary (BUILD-PLAN §5 M4
    E12).
    """
    if dt.tzinfo is None:
        raise ValueError("snap_forward requires a tz-aware datetime (G1)")
    m = _minute_of_day(dt)
    for d, w_start, w_end in _iter_windows_forward(dt.date(), cal):
        if d == dt.date():
            if m < w_start:
                return dt.replace(hour=w_start // 60, minute=w_start % 60,
                                  second=0, microsecond=0)
            if w_start <= m < w_end:
                return dt.replace(second=0, microsecond=0)
            # m >= w_end → fall through to next window
            continue
        return _day_start(d, dt.tzinfo).replace(
            hour=w_start // 60, minute=w_start % 60
        )
    raise RuntimeError("snap_forward exhausted horizon; calendar has no working time")


def snap_backward(dt: datetime, cal: Calendar) -> datetime:
    """Snap ``dt`` backward to the most recent working moment.

    If ``dt`` lies inside a window it is returned unchanged. If it is
    before a window start, the result is the **end** of the previous
    window (exclusive end — one minute before ``w_end``). This mirrors
    :func:`snap_forward` for the backward pass.
    """
    if dt.tzinfo is None:
        raise ValueError("snap_backward requires a tz-aware datetime (G1)")
    m = _minute_of_day(dt)
    for d, w_start, w_end in _iter_windows_backward(dt.date(), cal):
        if d == dt.date():
            if m >= w_end:
                return dt.replace(hour=w_end // 60, minute=w_end % 60,
                                  second=0, microsecond=0)
            if w_start <= m < w_end:
                return dt.replace(second=0, microsecond=0)
            # m < w_start → fall through to earlier window
            continue
        return _day_start(d, dt.tzinfo).replace(
            hour=w_end // 60, minute=w_end % 60
        )
    raise RuntimeError("snap_backward exhausted horizon; calendar has no working time")


def add_working_minutes(start: datetime, minutes: int, cal: Calendar) -> datetime:
    """Advance ``start`` by ``minutes`` of working time.

    * Negative ``minutes`` delegates to :func:`subtract_working_minutes`.
    * Zero from a window boundary snaps forward to the next window
      start (``Fri 16:00 + 0 → Mon 08:00``).
    * Working-time-skipping across weekends and exceptions is handled
      window-by-window.

    Args:
        start: tz-aware datetime (G1).
        minutes: non-negative minutes of working time to advance.
        cal: calendar supplying working windows.
    """
    if minutes < 0:
        return subtract_working_minutes(start, -minutes, cal)
    if start.tzinfo is None:
        raise ValueError("add_working_minutes requires a tz-aware datetime (G1)")

    cur = start
    m = _minute_of_day(cur)
    remaining = minutes
    for d, w_start, w_end in _iter_windows_forward(cur.date(), cal):
        if d == cur.date() and m >= w_end:
            continue
        window_entry = max(m, w_start) if d == cur.date() else w_start
        available = w_end - window_entry
        if available > remaining:
            end_min = window_entry + remaining
            return datetime.combine(
                d, time(end_min // 60, end_min % 60), tzinfo=start.tzinfo
            )
        remaining -= available
        if remaining == 0:
            # Roll to next window start (E12 convention).
            continue
        # else: keep consuming on the next window.
    raise RuntimeError("add_working_minutes exhausted horizon")


def subtract_working_minutes(start: datetime, minutes: int, cal: Calendar) -> datetime:
    """Rewind ``start`` by ``minutes`` of working time.

    Symmetric to :func:`add_working_minutes`. Negative ``minutes`` is
    delegated forward.
    """
    if minutes < 0:
        return add_working_minutes(start, -minutes, cal)
    if start.tzinfo is None:
        raise ValueError("subtract_working_minutes requires a tz-aware datetime (G1)")

    cur = start
    m = _minute_of_day(cur)
    remaining = minutes
    for d, w_start, w_end in _iter_windows_backward(cur.date(), cal):
        if d == cur.date() and m <= w_start:
            continue
        window_exit = min(m, w_end) if d == cur.date() else w_end
        available = window_exit - w_start
        if available > remaining:
            end_min = window_exit - remaining
            return datetime.combine(
                d, time(end_min // 60, end_min % 60), tzinfo=start.tzinfo
            )
        remaining -= available
        if remaining == 0:
            continue
    raise RuntimeError("subtract_working_minutes exhausted horizon")


def working_minutes_between(a: datetime, b: datetime, cal: Calendar) -> int:
    """Return working minutes between two tz-aware instants (``b - a``).

    Positive when ``b > a`` (and they span working windows); negative
    when ``a > b``; zero when they bracket only non-working time.
    The absolute count is capped at the horizon iterator bound.
    """
    if a.tzinfo is None or b.tzinfo is None:
        raise ValueError("working_minutes_between requires tz-aware datetimes (G1)")
    if a == b:
        return 0
    if a > b:
        return -working_minutes_between(b, a, cal)

    total = 0
    m = _minute_of_day(a)
    for d, w_start, w_end in _iter_windows_forward(a.date(), cal):
        if d == a.date() and m >= w_end:
            continue
        if d > b.date():
            break
        window_entry = max(m, w_start) if d == a.date() else w_start
        if d == b.date():
            mb = _minute_of_day(b)
            window_exit = min(mb, w_end)
            if window_exit > window_entry:
                total += window_exit - window_entry
            if mb <= w_end:
                break
        else:
            total += w_end - window_entry
    return total
