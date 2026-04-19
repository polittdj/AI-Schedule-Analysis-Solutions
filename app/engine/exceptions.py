"""CPM engine exception hierarchy.

The engine raises structured errors for conditions that make a
computation unsafe to continue (cycles when ``strict_cycles=True``,
missing calendars, pathologically invalid constraints). Soft
violations — a predecessor that forces a successor past an MFO date,
for example — are reported as :class:`ConstraintViolation` records on
the ``CPMResult`` rather than raised. This split is the forensic-
defensibility line required by BUILD-PLAN §6 AC bar #3: an indicator,
not a crash, when the schedule itself is the defective artifact.

Authority:

* Cycle handling — ``driving-slack-and-paths §4`` critical-path
  discipline requires a deterministic answer; BUILD-PLAN §5 M4 AC5
  permits lenient mode so that a corrupt network still yields output
  for the non-cyclic subgraph.
* Calendar handling — ``mpp-parsing-com-automation §3.5`` (Gotcha 5)
  makes calendar-bound arithmetic a correctness invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class EngineError(Exception):
    """Base class for all CPM engine errors.

    Catching ``EngineError`` captures every engine-raised exception
    without catching unrelated ``Exception`` subclasses raised by
    Pydantic or the standard library.
    """


class CircularDependencyError(EngineError):
    """Raised when a logic cycle is detected under ``strict_cycles``.

    ``nodes`` is the set of ``Task.unique_id`` values that form one or
    more cycles. Populating as a set (not a list) avoids accidental
    duplication when two cycles share a node and preserves the test-
    assertion API from BUILD-PLAN §5 M4 E1 (``{A, B, C}`` membership).

    The engine's default behavior (``strict_cycles=False``) collects
    cycle nodes into :class:`~app.engine.result.CPMResult.cycles_detected`
    instead of raising; BUILD-PLAN §5 M4 AC5 requires the non-cyclic
    subgraph still receives float values in that mode.
    """

    def __init__(self, nodes: set[int], message: str | None = None) -> None:
        self.nodes: set[int] = set(nodes)
        if message is None:
            sorted_nodes = sorted(self.nodes)
            message = f"circular dependency detected among UniqueIDs {sorted_nodes}"
        super().__init__(message)


class MissingCalendarError(EngineError):
    """Raised when a schedule has no usable calendar for date math.

    The engine needs at least one calendar whose name matches
    ``Schedule.default_calendar_name``; absent that, forward-pass date
    arithmetic cannot respect the working-time rule from
    ``mpp-parsing-com-automation §3.5``. Empty schedules (zero tasks)
    short-circuit before this check per BUILD-PLAN §5 M4 E2.
    """

    def __init__(self, calendar_name: str) -> None:
        self.calendar_name = calendar_name
        super().__init__(
            f"no calendar named {calendar_name!r} in Schedule.calendars "
            f"(mpp-parsing-com-automation §3.5 requires a project default calendar "
            f"for working-time arithmetic)"
        )


class InvalidConstraintError(EngineError):
    """Raised when a constraint is structurally impossible to apply.

    This is distinct from a soft constraint *violation* (see
    :class:`ConstraintViolation`). ``InvalidConstraintError`` fires when
    the constraint itself is malformed — e.g. a date-bearing constraint
    arrives without a ``constraint_date`` despite the model G7
    validator. The engine defends against direct-dict injection that
    bypasses model validation per BUILD-PLAN §5 M4 E22.
    """

    def __init__(self, unique_id: int, reason: str) -> None:
        self.unique_id = unique_id
        self.reason = reason
        super().__init__(f"invalid constraint on UniqueID {unique_id}: {reason}")


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    """A soft constraint breach recorded on the CPM result.

    Emitted — not raised — when a predecessor chain forces a successor
    past a soft-backward constraint (SNLT, FNLT) or when a hard date-
    bearing constraint (MSO, MFO) overrides a predecessor-driven
    position. BUILD-PLAN §5 M4 E8 / E11 call for the violation to
    surface on the task, not as a crash.

    Structured fields (``constraint_date`` / ``computed_date``) exist
    so the M12 delay-claim exporter can render "X days late vs.
    constraint Y" directly without re-parsing the ``detail`` prose.
    ``driving-slack-and-paths §8`` (CPM discipline) requires the
    engine to report date mismatches in a form that can be audited
    field-for-field against MSP output.

    Attributes:
        unique_id: ``Task.unique_id`` of the offending task.
        kind: Classification code, e.g. ``"SNLT_BREACHED"``,
            ``"MSO_OVERRIDE_PREDECESSOR"``, ``"MFO_OVERRIDE_PREDECESSOR"``,
            ``"MFO_OVERRIDE_SUCCESSOR"``.
        constraint_date: The constraint date on the task (MSO / MFO
            lock date, SNLT / FNLT deadline). ``None`` when the
            violation kind does not carry a constraint date.
        computed_date: The date the engine computed before the
            constraint was applied — the predecessor-driven ES/EF or
            the successor-driven LS/LF that conflicted with the
            constraint. ``None`` when the violation does not refer to
            a specific computed date.
        detail: Human-readable summary retained for existing
            consumers and log lines.
    """

    unique_id: int
    kind: str
    constraint_date: datetime | None = None
    computed_date: datetime | None = None
    detail: str = field(default="")
