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
    bearing constraint is inconsistent with the rest of the network.
    BUILD-PLAN §5 M4 E8 / E11 call for the violation to surface on the
    task, not as a crash.

    Attributes:
        unique_id: ``Task.unique_id`` of the offending task.
        kind: Human-readable classification (e.g. ``"FNLT_BREACHED"``).
        detail: Additional context (dates, offending predecessor UIDs).
    """

    unique_id: int
    kind: str
    detail: str = field(default="")
