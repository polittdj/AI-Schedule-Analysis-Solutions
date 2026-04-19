"""Metric configuration knobs.

:class:`MetricOptions` is the single dataclass that exposes every
per-metric override available in M5. Defaults track the
``dcma-14-point-assessment`` skill (§§4.1–4.4) and the threshold
values published in ``docs/sources/DeltekDECMMetricsJan2022.xlsx``.

Forensic rationale (BUILD-PLAN §5 M5 locked-design constraint
"thresholds are CONFIGURABLE per client-specific acceptance"): a
contractor whose programme acceptance criteria require a 7% logic
ceiling instead of the protocol default 5% must be able to pin that
threshold without forking the metric module. The override is recorded
on the resulting :class:`~app.metrics.base.MetricResult` so the
narrative layer can cite "passed against client-specified 7%
threshold" rather than misrepresent it as protocol compliance.

LOE detection: the M5 default policy is to honour
:attr:`~app.models.task.Task.is_loe` exactly. ``loe_name_patterns``
is a deferred, opt-in fallback that lets sites running schedules
where LOE is encoded only in the task name (not via a custom field)
flag those tasks at metric time without touching the parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.metrics.exceptions import InvalidThresholdError


@dataclass(frozen=True, slots=True)
class MetricOptions:
    """Overrides for the four DCMA metrics in M5 scope.

    Authority:

    * Logic threshold ≤5% — ``dcma-14-point-assessment §4.1``,
      DeltekDECM ``Logic / Missing Logic`` row.
    * Leads threshold 0% — ``dcma-14-point-assessment §4.2``,
      DeltekDECM ``Leads`` row.
    * Lags threshold ≤5% — ``dcma-14-point-assessment §4.3``,
      DeltekDECM ``Lags`` row.
    * FS-share threshold ≥90% — ``dcma-14-point-assessment §4.4``,
      DeltekDECM ``Relationship Types`` row.

    Threshold semantics:

    * Pct fields are expressed as a fraction in [0, 100]. The
      ``__post_init__`` validator enforces the range and raises
      :class:`~app.metrics.exceptions.InvalidThresholdError` on a
      bad value.
    * A higher-is-better metric (``fs_threshold_pct`` for Metric 4)
      passes when the computed value is **>=** the threshold.
    * A lower-is-better metric (Metrics 1, 2, 3) passes when the
      computed value is **<=** the threshold.
    """

    logic_threshold_pct: float = 5.0
    """Metric 1 (Missing Logic) — % of incomplete tasks allowed to
    have a missing predecessor or successor before the metric flags
    FAIL. Default 5.0 per ``dcma-14-point-assessment §4.1``."""

    leads_threshold_pct: float = 0.0
    """Metric 2 (Leads) — % of relations allowed to carry negative
    lag. Default 0.0 per ``dcma-14-point-assessment §4.2`` (zero
    tolerance)."""

    lags_threshold_pct: float = 5.0
    """Metric 3 (Lags) — % of non-lead relations allowed to carry
    positive lag. Default 5.0 per ``dcma-14-point-assessment §4.3``.
    The denominator excludes leads (negative-lag relations) so M2
    and M3 do not double-count the same offender."""

    fs_threshold_pct: float = 90.0
    """Metric 4 (Relationship Types) — minimum % of relations that
    must be Finish-to-Start. Default 90.0 per
    ``dcma-14-point-assessment §4.4``."""

    hard_constraints_threshold_pct: float = 5.0
    """Metric 5 (Hard Constraints) — % of tasks allowed to carry a
    09NOV09 hard constraint (MSO, MFO, SNLT, FNLT) before the metric
    flags FAIL. Default 5.0 per ``dcma-14-point-assessment §4.5``.
    SNET, FNET, ASAP, and ALAP are not counted (ALAP has its own
    detection path in M11 per ``forensic-manipulation-patterns
    §5.3``)."""

    high_float_threshold_pct: float = 5.0
    """Metric 6 (High Float) — % of incomplete tasks allowed to
    carry ``total_slack`` strictly greater than
    :attr:`high_float_threshold_working_days`. Default 5.0 per
    ``dcma-14-point-assessment §4.6``."""

    high_float_threshold_working_days: float = 44.0
    """Metric 6 (High Float) — working-day ceiling above which a
    task's ``total_slack`` is counted in the numerator. Default 44.0
    per ``dcma-14-point-assessment §4.6``. Comparison is strict
    (``>``) — a task with ``total_slack = 44.0 WD`` does not flag;
    ``44.01 WD`` does (BUILD-PLAN §5 M6 AC 2)."""

    negative_float_threshold_pct: float = 0.0
    """Metric 7 (Negative Float) — % of tasks allowed to carry
    ``total_slack < 0`` before the metric flags FAIL. Default 0.0
    per ``dcma-14-point-assessment §4.7`` — any negative float flags
    (BUILD-PLAN §5 M6 AC 3)."""

    high_duration_threshold_pct: float = 5.0
    """Metric 8 (High Duration) — % of incomplete tasks allowed to
    carry remaining duration strictly greater than
    :attr:`high_duration_threshold_working_days`. Default 5.0 per
    ``dcma-14-point-assessment §4.8``."""

    high_duration_threshold_working_days: float = 44.0
    """Metric 8 (High Duration) — working-day ceiling above which a
    task's remaining duration is counted in the numerator. Default
    44.0 per ``dcma-14-point-assessment §4.8``. Tasks tagged
    ``is_rolling_wave=True`` are exempt from the numerator per
    BUILD-PLAN §5 M6 AC 4."""

    exclude_loe: bool = True
    """Excludes tasks marked as Level-of-Effort
    (``Task.is_loe == True``) from the Metric 1 denominator per
    ``dcma-14-point-assessment §3``."""

    exclude_summary: bool = True
    """Excludes summary tasks (``Task.is_summary == True``) from the
    Metric 1 denominator per ``dcma-14-point-assessment §3``."""

    exclude_completed: bool = True
    """Excludes 100%-complete tasks from the Metric 1 denominator —
    they cannot be retroactively re-logiced
    (``dcma-14-point-assessment §3``)."""

    exclude_milestones_from_logic: bool = True
    """Excludes project start and finish milestones from the
    "Missing Logic" check. Per ``dcma-14-point-assessment §4.1``
    these milestones legitimately have only a successor (start) or
    only a predecessor (finish). The detector identifies them
    structurally — see ``app.metrics.logic._project_endpoints``."""

    loe_name_patterns: tuple[str, ...] = field(default_factory=tuple)
    """Optional fallback list of case-insensitive substrings that
    flag a task as LOE based on name when ``Task.is_loe`` is not
    set by the parser. Empty by default; opt-in only. Patterns are
    compared with ``in`` against the lower-cased task name."""

    def __post_init__(self) -> None:
        for name, value in (
            ("logic_threshold_pct", self.logic_threshold_pct),
            ("leads_threshold_pct", self.leads_threshold_pct),
            ("lags_threshold_pct", self.lags_threshold_pct),
            ("fs_threshold_pct", self.fs_threshold_pct),
            ("hard_constraints_threshold_pct", self.hard_constraints_threshold_pct),
            ("high_float_threshold_pct", self.high_float_threshold_pct),
            ("negative_float_threshold_pct", self.negative_float_threshold_pct),
            ("high_duration_threshold_pct", self.high_duration_threshold_pct),
        ):
            if not isinstance(value, int | float):
                raise InvalidThresholdError("M5", name, value)
            if value < 0.0 or value > 100.0:
                raise InvalidThresholdError("M5", name, value)
        for name, value in (
            (
                "high_float_threshold_working_days",
                self.high_float_threshold_working_days,
            ),
            (
                "high_duration_threshold_working_days",
                self.high_duration_threshold_working_days,
            ),
        ):
            if not isinstance(value, int | float):
                raise InvalidThresholdError("M6", name, value)
            if value < 0.0:
                raise InvalidThresholdError("M6", name, value)
