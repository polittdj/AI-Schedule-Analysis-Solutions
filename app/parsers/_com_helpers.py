"""Pure helpers for the COM parser.

Every helper is a pure function: no COM, no pywintypes, no I/O. The
helpers are unit-testable on Linux CI and re-used by
:mod:`app.parsers.com_parser` to coerce raw COM values into the
units, types, and enums the Pydantic data model expects.

Conversions implemented here:

* ``coerce_datetime_to_utc`` — attaches UTC ``tzinfo`` to a naive
  ``datetime`` returned by COM, normalizing the locale-formatted
  values from ``mpp-parsing-com-automation §3.10`` (Gotcha 10).
  Status-date sentinels (Gotcha 6) are returned as ``None``.
* ``cast_minutes`` — coerces a COM ``Duration``/``TotalSlack``/``Lag``
  value (returned as float-ish minutes per Gotcha 5,
  ``mpp-parsing-com-automation §3.5``) to ``int``.
* ``map_constraint_type`` — translates the COM ``PjConstraint`` int
  to :class:`app.models.ConstraintType`.
* ``map_relation_type`` — translates the COM ``PjTaskLinkType`` int
  (``0=FF, 1=FS, 2=SF, 3=SS`` per
  ``mpp-parsing-com-automation §5``) to
  :class:`app.models.RelationType`.
* ``map_resource_type`` — translates the COM ``PjResourceType`` int
  to :class:`app.models.ResourceType`.
* ``safe_get`` — wraps ``getattr`` so a missing COM property
  (older MS Project vintages) returns the default rather than
  raising ``AttributeError``.

Per audit H7 / AC A7 the parser is the *only* package that imports
``win32com``; this module does not. It receives the values that
``com_parser.py`` already pulled across the COM boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.enums import ConstraintType, RelationType, ResourceType

# ---------------------------------------------------------------------------
# Date conversion
# ---------------------------------------------------------------------------

# OLE zero (1899-12-30) and the MS Project epoch (1984-01-01) are the
# two sentinel datetimes COM may return when a date field is unset.
# See ``mpp-parsing-com-automation §3.6`` Gotcha 6.
_STATUS_DATE_SENTINELS: frozenset[datetime] = frozenset(
    {
        datetime(1899, 12, 30),
        datetime(1984, 1, 1),
    }
)


def coerce_datetime_to_utc(value: Any) -> datetime | None:
    """Coerce a COM date value to a tz-aware UTC ``datetime``.

    Implements both Gotcha 6 (status-date sentinel handling) and the
    audit Minor #3 boundary contract: COM returns naive local
    datetimes, but the Pydantic model requires tz-aware values (G1).
    The parser attaches UTC at this boundary so every model
    instance carries a tz-aware date thereafter.

    Skill cross-reference (amendment AM1 in this PR):
    ``mpp-parsing-com-automation §3.10`` — "M3 COM adapter attaches
    UTC at the parser boundary; models carry tz-aware datetimes
    thereafter."

    Returns ``None`` for any of:

    * actual ``None``
    * empty string or the literal ``"NA"`` (case-insensitive,
      whitespace-stripped) per Gotcha 6
    * ``datetime(1899, 12, 30)`` (OLE zero) per Gotcha 6
    * ``datetime(1984, 1, 1)`` (MS Project epoch) per Gotcha 6
    * any value that is not a string or ``datetime``
    """
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().upper() in ("", "NA"):
            return None
        return None
    if not isinstance(value, datetime):
        return None
    naive = value.replace(tzinfo=None)
    if naive in _STATUS_DATE_SENTINELS:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# ---------------------------------------------------------------------------
# Numeric casts
# ---------------------------------------------------------------------------


def cast_minutes(value: Any, *, allow_negative: bool = False) -> int:
    """Cast a COM minutes value to ``int``.

    COM returns ``Duration``, ``RemainingDuration``, ``ActualDuration``,
    ``BaselineDuration``, ``TotalSlack``, ``FreeSlack``, and
    relationship ``Lag`` as float-ish minutes per
    ``mpp-parsing-com-automation §3.5`` (Gotcha 5). The Pydantic
    model stores them as ``int``; we round to nearest minute to drop
    the 1/10-minute COM precision the model does not represent.

    ``allow_negative=False`` (the default) clamps negatives to zero
    so the model's ``Field(ge=0)`` validator on duration fields does
    not reject a noisy COM value. Slack and lag set
    ``allow_negative=True`` because a negative value is forensically
    meaningful (DCMA Metric 7, lead lags).

    ``None`` returns ``0`` — older MS Project vintages may not expose
    every property and we do not want a missing field to fail-fast
    the whole parse. The chosen behavior is documented in
    :class:`app.parsers.com_parser.MPProjectParser` as well.
    """
    if value is None:
        return 0
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return 0
    minutes = int(round(as_float))
    if not allow_negative and minutes < 0:
        return 0
    return minutes


# ---------------------------------------------------------------------------
# Enum mappings
# ---------------------------------------------------------------------------

# COM property: ``Task.ConstraintType`` (PjConstraint enum).
# Documented in the Pydantic model at ``app/models/enums.py::ConstraintType``;
# the integer-to-enum mapping mirrors the COM enum so this dict is just
# explicit fail-fast coverage for unknown ints.
_CONSTRAINT_BY_INT: dict[int, ConstraintType] = {ct.value: ct for ct in ConstraintType}

# COM property: ``TaskDependency.Type`` (PjTaskLinkType enum).
# ``0=FF, 1=FS, 2=SF, 3=SS`` per ``mpp-parsing-com-automation §5``.
_RELATION_BY_INT: dict[int, RelationType] = {rt.value: rt for rt in RelationType}

# COM property: ``Resource.Type`` (PjResourceType enum).
_RESOURCE_TYPE_BY_INT: dict[int, ResourceType] = {rt.value: rt for rt in ResourceType}


def map_constraint_type(raw: Any) -> ConstraintType:
    """Translate a COM ``PjConstraint`` int to :class:`ConstraintType`.

    Defaults to ``AS_SOON_AS_POSSIBLE`` when ``raw`` is ``None`` or
    not coercible to an integer present in the COM enum, matching
    MS Project's own default for newly-created tasks.
    """
    if raw is None:
        return ConstraintType.AS_SOON_AS_POSSIBLE
    try:
        as_int = int(raw)
    except (TypeError, ValueError):
        return ConstraintType.AS_SOON_AS_POSSIBLE
    return _CONSTRAINT_BY_INT.get(as_int, ConstraintType.AS_SOON_AS_POSSIBLE)


def map_relation_type(raw: Any) -> RelationType:
    """Translate a COM ``PjTaskLinkType`` int to :class:`RelationType`.

    Defaults to ``FS`` (Finish-to-Start, COM int 1) when ``raw`` is
    ``None`` or not coercible to a known enum value, matching the MS
    Project default.
    """
    if raw is None:
        return RelationType.FS
    try:
        as_int = int(raw)
    except (TypeError, ValueError):
        return RelationType.FS
    return _RELATION_BY_INT.get(as_int, RelationType.FS)


def map_resource_type(raw: Any) -> ResourceType:
    """Translate a COM ``PjResourceType`` int to :class:`ResourceType`.

    Defaults to ``WORK`` (COM int 0) for unknown / missing values,
    matching the MS Project default.
    """
    if raw is None:
        return ResourceType.WORK
    try:
        as_int = int(raw)
    except (TypeError, ValueError):
        return ResourceType.WORK
    return _RESOURCE_TYPE_BY_INT.get(as_int, ResourceType.WORK)


# ---------------------------------------------------------------------------
# Defensive COM property access
# ---------------------------------------------------------------------------


def safe_get(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``obj.name``; return ``default`` if access raises.

    ``win32com`` proxies surface a missing property as
    ``AttributeError`` *or* a ``com_error`` depending on the COM
    server's vintage. The parser tolerates either by trapping
    ``Exception`` here — the caller already knows what default to
    substitute and what subsequent validation will catch. Using
    ``Exception`` (not ``BaseException``) preserves
    ``KeyboardInterrupt`` and ``SystemExit`` semantics.
    """
    try:
        return getattr(obj, name)
    except Exception:
        return default
