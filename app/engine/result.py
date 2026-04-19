"""CPM engine output wrapper.

The engine returns a :class:`CPMResult` rather than mutating
``Schedule`` in place. Rationale (mutation-vs-wrap decision, per
BUILD-PLAN §5 M4 AC10 and M7 AC1 non-mutation invariant):

* The comparator (M9) runs CPM on two schedule versions — mutating
  either in place would double-book the input objects.
* DCMA CPT (M7) runs a ``+600-day probe`` via
  ``Schedule.model_copy(update=...)`` and then re-runs CPM; a wrapper
  result is the natural output shape for those repeated invocations.
* Pydantic models are frozen-by-convention downstream; a wrapper
  preserves that without forcing ``model_config`` plumbing.

The result is a plain :mod:`dataclasses` object — no Pydantic
validation is needed because every datetime comes from engine
computation (already tz-aware) and every integer comes from working-
minute arithmetic (already a Python ``int``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.engine.exceptions import ConstraintViolation


@dataclass(frozen=True, slots=True)
class TaskCPMResult:
    """CPM output for a single task.

    All datetime fields are tz-aware (G1). ``total_slack_minutes`` and
    ``free_slack_minutes`` can be negative (BUILD-PLAN §5 M4 E21;
    ``dcma-14-point-assessment §4.7`` negative-float metric). A
    ``None`` date field means the task was excluded from the pass —
    e.g. it participates in a cycle and the engine is in lenient mode.
    """

    unique_id: int
    early_start: datetime | None = None
    early_finish: datetime | None = None
    late_start: datetime | None = None
    late_finish: datetime | None = None
    total_slack_minutes: int = 0
    free_slack_minutes: int = 0
    on_critical_path: bool = False
    on_near_critical: bool = False
    skipped_due_to_cycle: bool = False


@dataclass(frozen=True, slots=True)
class CPMResult:
    """Full CPM output for a :class:`~app.models.schedule.Schedule`.

    Attributes:
        tasks: per-task CPM values keyed by ``unique_id``.
        project_start: earliest ES across non-skipped tasks.
        project_finish: latest EF across non-skipped tasks.
        cycles_detected: UIDs that participate in a cycle.
        critical_path_uids: UIDs with ``total_slack_minutes <= 0``.
        near_critical_uids: UIDs with TS in ``(0, threshold]`` working
            minutes. Empty when every task is critical or beyond the
            threshold.
        violations: soft-constraint breaches accumulated during the
            forward and backward passes.
        options_used: the :class:`~app.engine.options.CPMOptions` the
            engine actually ran with — handy for cross-checking.
    """

    tasks: dict[int, TaskCPMResult]
    project_start: datetime | None = None
    project_finish: datetime | None = None
    cycles_detected: frozenset[int] = field(default_factory=frozenset)
    critical_path_uids: frozenset[int] = field(default_factory=frozenset)
    near_critical_uids: frozenset[int] = field(default_factory=frozenset)
    violations: tuple[ConstraintViolation, ...] = field(default_factory=tuple)
