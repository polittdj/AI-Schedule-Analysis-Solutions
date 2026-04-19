"""Enumerations for the Schedule Forensics core data model.

Every enum value maps to a Microsoft Project COM property documented in
``.claude/skills/mpp-parsing-com-automation/SKILL.md`` (Appendix B "COM
Automation Type Mappings") or to a DCMA 14-Point Assessment
classification from
``.claude/skills/dcma-14-point-assessment/SKILL.md``. Integer values
mirror the COM enum where one exists so the Milestone 3 adapter can
coerce raw COM ints directly.
"""

from __future__ import annotations

from enum import IntEnum


class RelationType(IntEnum):
    """Task-dependency link type.

    Integer values follow the Microsoft Project COM ``PjTaskLinkType``
    enumeration documented in
    ``mpp-parsing-com-automation §5``: ``0=FF, 1=FS, 2=SF, 3=SS``.
    Third-party library enum orderings differ; do not port integer
    values verbatim between code paths without conversion.
    """

    FF = 0
    FS = 1
    SF = 2
    SS = 3


class ConstraintType(IntEnum):
    """Task constraint type.

    Integer values follow the Microsoft Project COM
    ``PjConstraint`` enumeration. The six constraint types exercised by
    the CPM engine (``driving-slack-and-paths §4``) are MSO, MFO, SNLT,
    FNLT, SNET, FNET; ASAP and ALAP round out the full COM enum for
    completeness (ALAP is additionally flagged as a manipulation signal
    in ``forensic-manipulation-patterns §5.3``).

    Date semantics (enforced by ``Task`` validators):

    * ``AS_SOON_AS_POSSIBLE`` and ``AS_LATE_AS_POSSIBLE`` MUST NOT carry
      a constraint date.
    * ``MUST_START_ON``, ``MUST_FINISH_ON``, ``START_NO_EARLIER_THAN``,
      ``START_NO_LATER_THAN``, ``FINISH_NO_EARLIER_THAN``,
      ``FINISH_NO_LATER_THAN`` MUST carry a constraint date.
    * The four "hard" constraints per ``dcma-14-point-assessment §4.5``
      (DCMA Metric 5, 09NOV09 revision) are MSO, MFO, SNLT, FNLT.
    """

    AS_SOON_AS_POSSIBLE = 0
    AS_LATE_AS_POSSIBLE = 1
    MUST_START_ON = 2
    MUST_FINISH_ON = 3
    START_NO_EARLIER_THAN = 4
    START_NO_LATER_THAN = 5
    FINISH_NO_EARLIER_THAN = 6
    FINISH_NO_LATER_THAN = 7


HARD_CONSTRAINTS: frozenset[ConstraintType] = frozenset(
    {
        ConstraintType.MUST_START_ON,
        ConstraintType.MUST_FINISH_ON,
        ConstraintType.START_NO_LATER_THAN,
        ConstraintType.FINISH_NO_LATER_THAN,
    }
)
"""The four 09NOV09 hard-constraint types used by DCMA Metric 5.

Cited to ``dcma-14-point-assessment §4.5`` and ``§3``. SNET, FNET,
ASAP, ALAP are deliberately excluded; ALAP has its own detection path
in Milestone 11 per ``forensic-manipulation-patterns §5.3``.
"""


DATE_BEARING_CONSTRAINTS: frozenset[ConstraintType] = frozenset(
    {
        ConstraintType.MUST_START_ON,
        ConstraintType.MUST_FINISH_ON,
        ConstraintType.START_NO_EARLIER_THAN,
        ConstraintType.START_NO_LATER_THAN,
        ConstraintType.FINISH_NO_EARLIER_THAN,
        ConstraintType.FINISH_NO_LATER_THAN,
    }
)
"""Constraint types that require a ``constraint_date``.

ASAP and ALAP are excluded; see ``Task`` validator G6/G7.
"""


class TaskType(IntEnum):
    """Task scheduling type.

    Integer values follow the Microsoft Project COM ``PjTaskFixedType``
    enumeration. ``FIXED_UNITS`` is the MSP default. ``FIXED_DURATION``
    and ``FIXED_WORK`` are the other two choices shown in the Task
    Information dialog.
    """

    FIXED_UNITS = 0
    FIXED_DURATION = 1
    FIXED_WORK = 2


class ResourceType(IntEnum):
    """Resource type.

    Integer values follow the Microsoft Project COM ``PjResourceType``
    enumeration: ``0=Work`` (people / equipment consumed by the hour),
    ``1=Material`` (consumables measured by unit), ``2=Cost``
    (budget-only resources with no effort contribution).
    """

    WORK = 0
    MATERIAL = 1
    COST = 2
