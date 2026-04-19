"""Shared metric primitives — :class:`Severity`, :class:`MetricResult`,
:class:`Offender`, :class:`ThresholdConfig`, and :class:`BaseMetric`.

All four DCMA metrics in M5 scope (Logic, Leads, Lags, Relationship
Types) emit :class:`MetricResult`. The class is frozen
(:meth:`dataclasses.dataclass(frozen=True)`) so a result can be
shared across the narrative layer, the export modules, and the
M11 manipulation engine without risk of mutation
(``forensic-manipulation-patterns §1`` indicators-not-verdicts; M5
locked-design constraint "metrics do NOT mutate Schedule or
CPMResult, results are immutable").

:class:`Offender` is the per-task / per-relation drill-down record
that BUILD-PLAN §6 AC bar #3 requires: every percentage must trace
back to the UniqueID(s) that produced it.

:class:`BaseMetric` codifies the metric contract — every metric
exposes a ``metric_id``, a ``run(schedule, options)`` callable, and
the threshold/source citation pair the narrative layer renders.

Authority:

* Indicator-not-verdict framing — ``dcma-14-point-assessment §6
  Rule 1``.
* Threshold-citation requirement — BUILD-PLAN §5 M5 AC5 ("every
  metric module has docstring citing dcma-14-point-assessment skill
  section AND DeltekDECMMetricsJan2022.xlsx sheet/row"); M5 CM5
  ("every metric cites its DeltekDECM source row in the
  MetricResult").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from app.metrics.options import MetricOptions
from app.models.schedule import Schedule


class Severity(StrEnum):
    """Three-state severity ordering used by every metric.

    The values match the BUILD-PLAN §5 M5 deliverable ("Severity
    enum (PASS/WARN/FAIL)") and are stringly-typed so they survive
    JSON/JSONLines export without bespoke encoders.
    """

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class Offender:
    """A single drill-down record contributing to a metric finding.

    Per BUILD-PLAN §6 AC bar #3 ("results cite the exact UniqueID(s)
    and task name(s)"), every metric that flags failures must list
    the offenders. ``unique_id`` is always populated; the relation-
    valued metrics (Leads, Lags, Relationship Types) populate
    ``successor_unique_id``, ``relation_type``, and the value field
    so the offender row is interpretable without joining back to the
    schedule.

    ``value`` carries the metric-specific number (lag minutes,
    relation-type label, etc.) as a string so the dataclass stays
    schema-stable across all four M5 metrics.
    """

    unique_id: int
    """``Task.unique_id`` (or relation predecessor UID for
    relation-valued metrics)."""

    name: str = ""
    """Task name for the unique_id above; empty when the offender
    is a relation pair where neither task is the focus."""

    successor_unique_id: int | None = None
    """For relation-valued metrics, the successor side of the link.
    ``None`` for task-valued metrics (e.g. Missing Logic)."""

    successor_name: str = ""
    """Successor task name for relation-valued metrics."""

    relation_type: str = ""
    """``RelationType`` as a string label (``"FS"``, ``"SS"``,
    ``"FF"``, ``"SF"``). Empty for task-valued metrics."""

    value: str = ""
    """Metric-specific numeric/categorical value, stringified.

    Examples:

    * Logic: ``"missing_predecessor"`` or ``"missing_successor"``.
    * Leads: ``"-2400 min"`` (the lag value).
    * Lags: ``"4800 min"``.
    * Relationship Types: ``"SS"`` / ``"FF"`` / ``"SF"``.
    """


@dataclass(frozen=True, slots=True)
class ThresholdConfig:
    """Records the threshold the metric ran against and its source.

    Carried on every :class:`MetricResult` so the narrative and
    export layers can render a defensible citation: "metric X passed
    against the protocol DCMA 5% threshold (DeltekDECM row Y,
    skill §Z)" or "metric X failed against the contract-acceptance
    7% threshold overriding the DCMA default."

    Authority for the source-citation requirement:
    ``dcma-14-point-assessment §6 Rule 1`` (indicators not verdicts);
    M5 CM5 (every metric result carries DeltekDECM row + skill section).
    """

    value: float
    """Numeric threshold expressed as a percent in [0, 100]."""

    direction: str
    """Either ``"<="`` (lower-is-better metric — Logic, Leads, Lags)
    or ``">="`` (higher-is-better metric — Relationship Types FS share)."""

    source_skill_section: str
    """Authoritative skill citation, e.g.
    ``"dcma-14-point-assessment §4.1"``."""

    source_decm_row: str
    """Source row label in
    ``docs/sources/DeltekDECMMetricsJan2022.xlsx`` — e.g.
    ``"06A204b (Guideline 6 row 32) — Logic / Missing Logic"``."""

    is_overridden: bool = False
    """``True`` when the operator supplied a non-default override on
    :class:`~app.metrics.options.MetricOptions`."""


@dataclass(frozen=True, slots=True)
class MetricResult:
    """The single output type for every M5 DCMA metric.

    Frozen so the comparator (M9), the narrative layer (M12), and
    the export modules (M13) can pass the same instance through
    multiple consumers without collision. The metric module is the
    sole producer; downstream code is read-only.

    Attributes:
        metric_id: stable identifier (``"DCMA-1"`` … ``"DCMA-4"``).
        metric_name: human-readable name.
        severity: :class:`Severity`.
        computed_value: the numerator-as-percent the metric
            actually computed. ``None`` when the metric could not
            compute a value (e.g. Relationship Types on a schedule
            with zero relations).
        threshold: :class:`ThresholdConfig`.
        numerator: the numerator of the X/Y ratio this metric
            computes. For lower-is-better metrics this is typically
            the count of offenders; for higher-is-better metrics this
            is typically the count of passing items. Downstream
            consumers should rely on ``computed_value`` and
            ``threshold.direction`` rather than interpreting this
            field's semantics.
        denominator: count of items in the population (incomplete
            tasks, total relations, etc.).
        offenders: drill-down list per BUILD-PLAN §6 AC bar #3.
        notes: free-form context (e.g. "no incomplete tasks; metric
            passes vacuously").
    """

    metric_id: str
    metric_name: str
    severity: Severity
    threshold: ThresholdConfig
    numerator: int
    denominator: int
    offenders: tuple[Offender, ...] = field(default_factory=tuple)
    computed_value: float | None = None
    notes: str = ""


class BaseMetric(ABC):
    """Contract every concrete metric implements.

    Subclasses are stateless and may be instantiated once and reused.
    The :meth:`run` method is the only entry point; it must be a pure
    function of ``(schedule, options)`` — no caching of inputs, no
    mutation of arguments, no I/O. Two calls on the same input must
    produce byte-equal results (M5 CM3).

    Class attributes the subclass overrides:

    * :attr:`metric_id` — stable identifier.
    * :attr:`metric_name` — human-readable name.
    * :attr:`source_skill_section` — skill citation.
    * :attr:`source_decm_row` — DeltekDECM row citation.
    """

    metric_id: str = ""
    metric_name: str = ""
    source_skill_section: str = ""
    source_decm_row: str = ""

    @abstractmethod
    def run(
        self,
        schedule: Schedule,
        options: MetricOptions | None = None,
    ) -> MetricResult:
        """Compute the metric for ``schedule`` and return a result.

        ``options`` may be ``None`` (the metric uses
        :class:`MetricOptions` defaults) or an instance the operator
        supplied. The metric must not mutate either argument.
        """
