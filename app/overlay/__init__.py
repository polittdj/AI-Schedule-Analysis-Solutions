"""NASA Schedule Management Handbook overlay package — Milestone 8.

The overlay layers NASA SMH expectations on top of the frozen DCMA
:class:`~app.metrics.base.MetricResult` contract. It does not
mutate upstream metric output; it reads ``MetricResult``,
:class:`~app.models.schedule.Schedule`, and
:class:`~app.metrics.options.MetricOptions` read-only and emits a
sibling :class:`~app.overlay.nasa_overlay.OverlayResult` carrying
adjusted denominators, informational notes, and exclusion records.

Package layout (see :doc:`README`):

* :mod:`app.overlay.nasa_overlay` — frozen contract
  (:class:`OverlayResult`, :class:`OverlayNote`,
  :class:`OverlayNoteKind`, :class:`ExclusionRecord`) and the three
  M8 rule functions.
* :mod:`app.overlay.nasa_milestones` — externalized governance-
  milestone name-pattern taxonomy.
* :mod:`app.overlay.exceptions` — :class:`OverlayError` hierarchy.

Authority — ``nasa-schedule-management §§3, 4, 6``;
``nasa-program-project-governance §§4, 5``;
``dcma-14-point-assessment §§4.5, 4.6, 4.8, 8``; BUILD-PLAN §5 M8.
"""

from __future__ import annotations

from app.overlay.exceptions import MissingMetricResultError, OverlayError
from app.overlay.nasa_milestones import (
    GOVERNANCE_PATTERNS,
    is_governance_milestone,
    match_governance_pattern,
)
from app.overlay.nasa_overlay import (
    ExclusionRecord,
    OverlayNote,
    OverlayNoteKind,
    OverlayResult,
    apply_governance_milestone_triage,
    apply_rolling_wave_window_check,
    apply_schedule_margin_exclusion,
)

__all__ = [
    "ExclusionRecord",
    "GOVERNANCE_PATTERNS",
    "MissingMetricResultError",
    "OverlayError",
    "OverlayNote",
    "OverlayNoteKind",
    "OverlayResult",
    "apply_governance_milestone_triage",
    "apply_rolling_wave_window_check",
    "apply_schedule_margin_exclusion",
    "is_governance_milestone",
    "match_governance_pattern",
]
