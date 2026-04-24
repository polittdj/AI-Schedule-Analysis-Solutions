"""Cross-milestone frozen contract types.

Home for Pydantic contract surfaces that span more than one
milestone's implementation layer. Introduced by BUILD-PLAN §2.22
(AM12, 4/23/2026) subsection (b) as a stable import surface for
downstream consumers (M12 AI narrative, M13 UI, export modules) so
they need not reach into ``app/engine/`` internals.

Phase 1 convention — types only. This package carries Pydantic
models and ``StrEnum`` classes; helper functions, builders, and
anything that isn't a pure contract shape live in ``app/engine/``.
"""

from app.contracts.manipulation_scoring import (
    ConstraintDrivenCrossVersionResult,
    ManipulationScoringResult,
    ManipulationScoringSummary,
    SeverityTier,
    SlackState,
)

__all__ = (
    "ConstraintDrivenCrossVersionResult",
    "ManipulationScoringResult",
    "ManipulationScoringSummary",
    "SlackState",
    "SeverityTier",
)
