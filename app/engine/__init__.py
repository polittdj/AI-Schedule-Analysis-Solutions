"""CPM engine package — Milestone 4.

Pure-computation layer: forward pass, backward pass, driving slack,
and near-critical classification over ``app.models.Schedule``. No I/O,
no COM, no network (BUILD-PLAN §2 locked decisions; M4 guardrails).

Forensic authority: ``driving-slack-and-paths/SKILL.md`` (SSI driving-
slack methodology, §§2-4, §8 CPM discipline) is the governing skill.
DCMA consumer skills read slack and constraint fields emitted here
(``dcma-14-point-assessment §§4.2, 4.3, 4.5, 4.6, 4.7``) but compute
their own metrics in later milestones.

Public API — see ``app/engine/README.md`` for the mutation-vs-wrap
decision, big-O notes, and forensic-defensibility commentary.
"""

from __future__ import annotations

from app.engine.comparator import (
    ComparatorError,
    ComparatorOptions,
    compare_schedules,
)
from app.engine.cpm import CPMEngine, compute_cpm
from app.engine.delta import (
    ComparatorResult,
    DeltaType,
    FieldDelta,
    RelationshipDelta,
    RelationshipPresence,
    TaskDelta,
    TaskPresence,
)
from app.engine.duration import (
    minutes_to_working_days,
    working_days_to_minutes,
)
from app.engine.exceptions import (
    CircularDependencyError,
    ConstraintViolation,
    EngineError,
    InvalidConstraintError,
    MissingCalendarError,
)
from app.engine.options import CPMOptions
from app.engine.paths import (
    critical_path_chains,
    driving_slack_to_focus,
    near_critical_chain,
)
from app.engine.result import CPMResult, TaskCPMResult
from app.engine.windowing import is_legitimate_actual

__all__ = [
    "CPMEngine",
    "CPMOptions",
    "CPMResult",
    "CircularDependencyError",
    "ComparatorError",
    "ComparatorOptions",
    "ComparatorResult",
    "ConstraintViolation",
    "DeltaType",
    "EngineError",
    "FieldDelta",
    "InvalidConstraintError",
    "MissingCalendarError",
    "RelationshipDelta",
    "RelationshipPresence",
    "TaskCPMResult",
    "TaskDelta",
    "TaskPresence",
    "compare_schedules",
    "compute_cpm",
    "critical_path_chains",
    "driving_slack_to_focus",
    "is_legitimate_actual",
    "minutes_to_working_days",
    "near_critical_chain",
    "working_days_to_minutes",
]
