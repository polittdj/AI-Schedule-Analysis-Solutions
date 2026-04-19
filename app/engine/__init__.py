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
decision and algorithm notes.
"""

from __future__ import annotations

from app.engine.exceptions import (
    CircularDependencyError,
    ConstraintViolation,
    EngineError,
    InvalidConstraintError,
    MissingCalendarError,
)
from app.engine.options import CPMOptions

__all__ = [
    "CPMOptions",
    "CircularDependencyError",
    "ConstraintViolation",
    "EngineError",
    "InvalidConstraintError",
    "MissingCalendarError",
]
