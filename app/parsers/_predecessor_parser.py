"""Parse MS Project predecessor strings into :class:`Relation` records.

The MS Project ``Predecessors`` column displays predecessors in the
format ``"2FS+3d, 4SS-1d, 7"`` — a comma- or semicolon-separated list
of tokens, each token being:

    <task_id> [ <relation_type> ] [ <sign> <lag_number> [ <unit> ] ]

* ``task_id`` is the **display Task ID**, not the UniqueID. The
  Predecessors column is a Task-ID-keyed string by MS Project's
  design; this parser must translate every referenced Task ID to a
  UniqueID before constructing the :class:`Relation`. The
  ``mpp-parsing-com-automation §5`` "Predecessors-column trap" note
  is the source of this requirement and parser gotcha P6.
* ``relation_type`` is one of ``FS``, ``SS``, ``FF``, ``SF`` (case
  insensitive). Default is ``FS`` (Finish-to-Start) when absent —
  matches MS Project's column display convention.
* ``sign`` is ``+`` or ``-``. ``-`` is a "lead" (Gotcha 5; DCMA
  Metric 2 forensic signal).
* ``lag_number`` is the lag magnitude (integer or decimal).
* ``unit`` (optional, default ``"d"``) is one of:

  * ``m`` — minutes
  * ``h`` — hours
  * ``d`` — working days
  * ``w`` — working weeks
  * ``mo`` — working months (treated as 20 working days)
  * ``em``, ``eh``, ``ed``, ``ew``, ``emo`` — *elapsed* units
    (calendar units, 24 h/day, 7 d/week)

  Working units use the project default calendar's ``hours_per_day``
  and ``working_days_per_week`` because that is what MS Project does
  when it renders the column.

The parser is pure: no I/O, no COM, no win32com. It is unit-tested
on Linux CI per AC A2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.models.enums import RelationType
from app.models.relation import Relation
from app.parsers.exceptions import CorruptScheduleError

# ---------------------------------------------------------------------------
# Regex anatomy
# ---------------------------------------------------------------------------

# Splits a predecessor string into individual tokens. MS Project
# accepts both comma and semicolon as separators (the latter on
# locales whose decimal separator is the comma).
_TOKEN_SPLIT: Final[re.Pattern[str]] = re.compile(r"[,;]")

# Captures the three logical groups of one token. Whitespace is
# tolerated between every group to absorb the casual hand-typed
# values an analyst may paste back into the predecessors column.
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    ^\s*
    (?P<task_id>\d+)\s*
    (?P<rel>FS|SS|FF|SF)?\s*
    (?:
        (?P<sign>[+-])\s*
        (?P<num>\d+(?:\.\d+)?)\s*
        (?P<unit>emo|em|eh|ed|ew|mo|m|h|d|w)?
    )?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# COM relation enum cited in ``mpp-parsing-com-automation §5``:
# ``0=FF, 1=FS, 2=SF, 3=SS``. The string mnemonic to enum mapping
# below preserves that contract.
_RELATION_BY_MNEMONIC: Final[dict[str, RelationType]] = {
    "FF": RelationType.FF,
    "FS": RelationType.FS,
    "SF": RelationType.SF,
    "SS": RelationType.SS,
}


@dataclass(frozen=True, slots=True)
class CalendarUnits:
    """Calendar conversion factors used to translate lag units → minutes.

    Sourced from the project default calendar (M2 ``Calendar``
    model). The defaults match MS Project's "Standard" calendar
    (8h day, 5d week) so a parser caller that has no calendar yet
    still produces correct lags for the common case.
    """

    hours_per_day: float = 8.0
    working_days_per_week: int = 5

    @property
    def minutes_per_working_day(self) -> float:
        return self.hours_per_day * 60.0

    @property
    def minutes_per_working_week(self) -> float:
        return self.minutes_per_working_day * self.working_days_per_week


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------


def _lag_to_minutes(value: float, unit: str | None, units: CalendarUnits) -> int:
    """Convert a (number, unit) lag into integer minutes.

    Working units use the project default calendar. Elapsed units
    use 24 h/day and 7 d/week per the MS Project convention. The
    result is rounded to the nearest minute, matching
    :func:`app.parsers._com_helpers.cast_minutes`.
    """
    u = (unit or "d").lower()
    if u == "m":
        minutes = value
    elif u == "h":
        minutes = value * 60.0
    elif u == "d":
        minutes = value * units.minutes_per_working_day
    elif u == "w":
        minutes = value * units.minutes_per_working_week
    elif u == "mo":
        minutes = value * units.minutes_per_working_day * 20.0
    elif u == "em":
        minutes = value
    elif u == "eh":
        minutes = value * 60.0
    elif u == "ed":
        minutes = value * 24.0 * 60.0
    elif u == "ew":
        minutes = value * 7.0 * 24.0 * 60.0
    elif u == "emo":
        minutes = value * 30.0 * 24.0 * 60.0
    else:
        # Defensive — the regex restricts the alternation, but a
        # future edit could widen it; default to working days.
        minutes = value * units.minutes_per_working_day
    return int(round(minutes))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_predecessor_string(
    raw: str | None,
    *,
    successor_unique_id: int,
    id_map: dict[int, int],
    units: CalendarUnits | None = None,
) -> list[Relation]:
    """Parse a predecessor string into :class:`Relation` records.

    Parameters
    ----------
    raw
        The raw column value. May be ``None``, empty, or whitespace
        — all return an empty list (parser gotcha P4).
    successor_unique_id
        The UniqueID of the task that owns the predecessor string.
        Becomes ``Relation.successor_unique_id`` on every returned
        record.
    id_map
        A first-pass-built mapping of ``Task.ID`` → ``Task.UniqueID``.
        Each token's parsed Task ID is translated through this map
        to satisfy the BUILD-PLAN §2.7 "UniqueID only" rule. Missing
        entries raise :class:`CorruptScheduleError` (parser gotcha
        P7 chosen behavior — strict / fail-fast; documented in
        :mod:`app.parsers.com_parser`).
    units
        Calendar conversion factors. Defaults to MS Project's
        Standard calendar (8 h day, 5 d week).

    Returns
    -------
    list[Relation]
        One :class:`Relation` per token, in source order.

    Raises
    ------
    CorruptScheduleError
        If a token cannot be parsed (gotcha P5 hand-off) or if a
        token references a Task ID not present in ``id_map`` (gotcha
        P7).
    """
    if raw is None:
        return []
    if isinstance(raw, str) and raw.strip() == "":
        return []

    units = units or CalendarUnits()
    relations: list[Relation] = []

    for token in _TOKEN_SPLIT.split(raw):
        cleaned = token.strip()
        if not cleaned:
            continue

        match = _TOKEN_PATTERN.match(cleaned)
        if match is None:
            raise CorruptScheduleError(
                f"unparseable predecessor token: {cleaned!r}"
            )

        task_id = int(match.group("task_id"))
        if task_id not in id_map:
            raise CorruptScheduleError(
                "predecessor references Task ID "
                f"{task_id} with no matching task in this schedule"
            )

        rel_mnemonic = (match.group("rel") or "FS").upper()
        relation_type = _RELATION_BY_MNEMONIC[rel_mnemonic]

        sign = match.group("sign")
        num = match.group("num")
        unit = match.group("unit")
        if num is None:
            lag_minutes = 0
        else:
            magnitude = _lag_to_minutes(float(num), unit, units)
            lag_minutes = -magnitude if sign == "-" else magnitude

        relations.append(
            Relation(
                predecessor_unique_id=id_map[task_id],
                successor_unique_id=successor_unique_id,
                relation_type=relation_type,
                lag_minutes=lag_minutes,
            )
        )

    return relations
