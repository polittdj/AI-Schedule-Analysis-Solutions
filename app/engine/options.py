"""CPM engine configuration.

:class:`CPMOptions` is the single knob set exposed to M4's callers.
Defaults track the ``driving-slack-and-paths`` skill and BUILD-PLAN
locked decisions:

* ``near_critical_threshold_days`` — 10 working days, per
  ``driving-slack-and-paths §4`` (near-critical band labeled as the
  standard forensic bucket; customizable for operator-picked bands).
* ``project_finish_override`` — ``None`` means back-pass from the
  maximum early finish; an override supports the +600-day probe
  pattern used by DCMA CPT (BUILD-PLAN §5 M7 AC1) and the but-for
  analysis Period A anchor (``driving-slack-and-paths §9``).
* ``strict_cycles`` — when ``True``, cycles raise
  :class:`~app.engine.exceptions.CircularDependencyError` (forensic
  review mode); when ``False``, cycles are collected on the result
  and the non-cyclic subgraph still receives float (BUILD-PLAN §5 M4
  AC5).

The class is a plain dataclass — it is not a Pydantic model because it
holds no schedule data and has no cross-field validation beyond simple
positive-number checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CPMOptions:
    """Options for :class:`~app.engine.cpm.CPMEngine`.

    Authority:

    * Near-critical threshold — ``driving-slack-and-paths §4``.
    * Finish override — BUILD-PLAN §5 M4 E18.
    * Cycle mode — BUILD-PLAN §5 M4 AC5 (lenient) and M4 E1 (strict).
    """

    near_critical_threshold_days: float = 10.0
    project_finish_override: datetime | None = None
    strict_cycles: bool = False

    def __post_init__(self) -> None:
        if self.near_critical_threshold_days < 0:
            raise ValueError(
                "near_critical_threshold_days must be >= 0 "
                "(driving-slack-and-paths §4)"
            )
        if self.project_finish_override is not None:
            if self.project_finish_override.tzinfo is None:
                raise ValueError(
                    "project_finish_override must be tz-aware "
                    "(mpp-parsing-com-automation §3.10 / model G1)"
                )
