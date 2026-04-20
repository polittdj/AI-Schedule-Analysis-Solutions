"""NASA SMH overlay — frozen contract and rule orchestrator.

The overlay layers NASA Schedule Management Handbook expectations on
top of the frozen DCMA :class:`~app.metrics.base.MetricResult`
contract without mutating upstream metric output. Every rule takes
the original ``MetricResult``, the source :class:`~app.models.
schedule.Schedule`, and :class:`~app.metrics.options.MetricOptions`
read-only, and returns a new :class:`OverlayResult` that carries
adjusted numerator / denominator / ratio / severity alongside
informational notes the downstream consumer (M11 manipulation
engine) will read.

Architectural position. The overlay sits above the metrics layer and
reads its outputs; it does not sit inside the engine (which is
pure-CPM, :mod:`app.engine`) and is not itself a DCMA metric (which
would live in :mod:`app.metrics`). See BUILD-PLAN §5 M8 AM5 for the
package-placement rationale.

Non-mutation invariant. :attr:`OverlayResult.original_result` is the
exact ``MetricResult`` the upstream metric produced. The overlay
never rebinds it, never rewrites its ``offenders`` tuple, and never
alters its ``computed_value``. Adjusted fields live on
``OverlayResult``. Mutation-invariance is asserted in the overlay
tests via a deterministic snapshot helper.

Authority:

* Schedule margin is not float — ``nasa-schedule-management §3``;
  High-Float denominator exclusion — ``§6`` and
  ``dcma-14-point-assessment §4.6 / §8``.
* Governance-milestone constraints — ``nasa-schedule-management §6``
  and ``nasa-program-project-governance §§4, 5``.
* Rolling-wave 6–12 month window — ``nasa-schedule-management §4``;
  interaction with DCMA Metric 8 — ``dcma-14-point-assessment §4.8``.
* Indicator-not-verdict framing — ``dcma-14-point-assessment §6
  Rule 1`` and BUILD-PLAN §6 AC bar #3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.metrics.base import MetricResult, Severity
from app.metrics.options import MetricOptions
from app.models.schedule import Schedule
from app.models.task import Task
from app.overlay.exceptions import MissingMetricResultError


class OverlayNoteKind(StrEnum):
    """Structured label for each informational note kind the overlay
    emits. Stringly-typed so the note survives JSON / JSONLines
    export without bespoke encoders; the M11 manipulation engine
    routes on the exact values below.

    Values:

    * ``GOVERNANCE_MILESTONE_TRIAGE`` — a task whose name matches a
      NASA governance-milestone pattern (KDP, SRR, MDR, PDR, CDR,
      SIR, ORR, MCR, FRR) carries a hard-constraint (MSO / MFO /
      SNLT / FNLT). The constraint is governance-driven and the
      downstream manipulation engine should not raise it as a
      constraint-injection finding.
    * ``ROLLING_WAVE_NEAR_TERM_WARNING`` — a task flagged
      ``is_rolling_wave = True`` whose forecast window is inside the
      SMH 6–12-month near-term boundary. SMH §4 expects near-term
      work to be planned to discrete detail, so a near-term
      rolling-wave tag is a BoE / decomposition concern rather than
      an exemption.
    * ``ROLLING_WAVE_OUT_OF_WINDOW`` — an ``is_rolling_wave = True``
      task whose forecast window is outside the SMH 12-month
      rolling-wave band (informational; commonly benign for far-out
      planning packages that should be refined as they approach).
    """

    GOVERNANCE_MILESTONE_TRIAGE = "GOVERNANCE_MILESTONE_TRIAGE"
    ROLLING_WAVE_NEAR_TERM_WARNING = "ROLLING_WAVE_NEAR_TERM_WARNING"
    ROLLING_WAVE_OUT_OF_WINDOW = "ROLLING_WAVE_OUT_OF_WINDOW"


@dataclass(frozen=True, slots=True)
class OverlayNote:
    """A single informational note emitted by an overlay rule.

    Consumer-agnostic structure: the note carries enough context for
    a drill-down UI to render the row without joining back to the
    schedule, and for the M11 manipulation engine to route on the
    note kind without re-deriving it. The ``detail`` string is
    free-form and is the only field the narrative layer should
    render verbatim.
    """

    note_kind: OverlayNoteKind
    """Structured label — ``OverlayNoteKind`` value."""

    unique_id: int
    """``Task.unique_id`` — the task the note is about."""

    task_name: str
    """Task name, captured for drill-down rendering."""

    detail: str
    """Free-form detail string, e.g. ``"MFO constraint on governance
    milestone CDR"`` or ``"rolling-wave tag on a forecast 4 months
    out (SMH §4 near-term window)"``."""


@dataclass(frozen=True, slots=True)
class ExclusionRecord:
    """A single denominator-exclusion row.

    Emitted by rules that adjust a metric's denominator. The
    :attr:`OverlayResult.tasks_excluded_from_denominator` tuple lets
    the narrative / export layer render "7 / 10 after NASA overlay
    (3 schedule-margin tasks excluded from the denominator per SMH
    §3)" without re-deriving which tasks were dropped.
    """

    unique_id: int
    """``Task.unique_id`` — the task excluded from the denominator."""

    task_name: str
    """Task name, captured for drill-down rendering."""

    exclusion_reason: str
    """Free-form reason, e.g. ``"is_schedule_margin = True (NASA SMH
    §3)"``. The M11 consumer does not route on this string — it is a
    narrative / export payload."""


@dataclass(frozen=True, slots=True)
class OverlayResult:
    """The overlay's per-metric sibling to
    :class:`~app.metrics.base.MetricResult`.

    Carries the exact upstream ``MetricResult`` in
    :attr:`original_result` alongside the overlay's adjusted fields
    and informational notes. Every field is immutable; the dataclass
    is ``frozen=True, slots=True`` so rebinding raises
    :class:`dataclasses.FrozenInstanceError`.

    Adjusted-field semantics:

    * :attr:`adjusted_numerator` / :attr:`adjusted_denominator` —
      computed afresh by the overlay rule; ``None`` when the rule
      does not adjust that field.
    * :attr:`adjusted_ratio` — ``adjusted_numerator /
      adjusted_denominator * 100`` when both are defined and the
      denominator is positive; ``None`` otherwise.
    * :attr:`adjusted_severity` — recomputed against the same
      threshold the upstream metric used; ``None`` when the overlay
      rule is note-emission only (does not change the ratio).

    Attributes are ordered to keep the dataclass stable across M9+
    extensions — consumers should read by name.
    """

    metric_id: str
    """Upstream metric's ``metric_id`` (e.g. ``"DCMA-06"`` or
    ``"DCMA-6"`` as the upstream metric emits; the overlay echoes
    whatever the upstream produced)."""

    original_result: MetricResult
    """Exact upstream :class:`MetricResult`. The overlay never
    mutates this instance."""

    adjusted_numerator: int | None = None
    """Overlay-adjusted numerator; ``None`` when the rule is note-
    emission only."""

    adjusted_denominator: int | None = None
    """Overlay-adjusted denominator; ``None`` when the rule is
    note-emission only."""

    adjusted_ratio: float | None = None
    """Overlay-adjusted percentage
    (``adjusted_numerator / adjusted_denominator * 100``); ``None``
    when the rule is note-emission only or the adjusted denominator
    is zero."""

    adjusted_severity: Severity | None = None
    """Overlay-adjusted severity recomputed against the original
    metric's threshold; ``None`` when the rule is note-emission
    only."""

    informational_notes: tuple[OverlayNote, ...] = field(
        default_factory=tuple
    )
    """Tuple of :class:`OverlayNote` records. Empty when the rule is
    denominator-adjustment only (High-Float schedule-margin
    exclusion)."""

    tasks_excluded_from_denominator: tuple[ExclusionRecord, ...] = field(
        default_factory=tuple
    )
    """Tuple of :class:`ExclusionRecord` rows. Empty when the rule
    is note-emission only."""


# --------------------------------------------------------------------
# Helpers — DCMA §3 eligibility (mirrors app.metrics.high_float logic).
# --------------------------------------------------------------------


def _is_loe(task: Task, options: MetricOptions) -> bool:
    """Return ``True`` when ``task`` should be treated as LOE.

    Mirrors :func:`app.metrics.high_float._is_loe`: honour the
    :attr:`Task.is_loe` flag and fall back to the opt-in
    :attr:`MetricOptions.loe_name_patterns` list. The overlay must
    apply the same eligibility filters the upstream metric did so
    the denominator-exclusion accounting lines up exactly.
    """
    if task.is_loe:
        return True
    if not options.loe_name_patterns:
        return False
    name_lc = task.name.lower()
    return any(pat.lower() in name_lc for pat in options.loe_name_patterns)


def _is_dcma_eligible(task: Task, options: MetricOptions) -> bool:
    """Return ``True`` iff ``task`` is in the DCMA §3 eligible set for
    Metric 6 (High Float).

    The DCMA §3 exclusions (summary, LOE, 100%-complete) match
    :func:`app.metrics.high_float._is_excluded` exactly. The High-
    Float metric additionally drops tasks the CPM engine skipped
    due to cycle; the overlay cannot re-derive that set without the
    :class:`~app.engine.result.CPMResult`, so it applies the §3
    filters only. In practice, schedule-margin tasks are never part
    of CPM cycles (they are carefully placed reserve activities per
    SMH §3), so the approximation is exact for every realistic
    schedule; a cycle-skipped margin task would surface as a
    narrative-layer annotation.
    """
    if options.exclude_summary and task.is_summary:
        return False
    if options.exclude_loe and _is_loe(task, options):
        return False
    if options.exclude_completed and task.percent_complete >= 100.0:
        return False
    return True


# --------------------------------------------------------------------
# Rule 1 — High-Float denominator exclusion (Milestone 8 Block 3).
# --------------------------------------------------------------------


def apply_schedule_margin_exclusion(
    original_result: MetricResult,
    schedule: Schedule,
    options: MetricOptions | None = None,
) -> OverlayResult:
    """Apply the NASA SMH schedule-margin exclusion to a DCMA Metric 6
    (High Float) :class:`~app.metrics.base.MetricResult`.

    NASA schedule margin is a deliberate, PM-owned reserve activity
    distinct from CPM total float (``nasa-schedule-management §3``).
    Counting it as high-float inflates Metric 6 and produces a
    false manipulation flag. This rule recomputes the denominator
    excluding every :attr:`Task.is_schedule_margin` task in the
    DCMA §3 eligible set, recomputes the numerator excluding every
    schedule-margin task that was in the original offender list,
    and emits an :class:`ExclusionRecord` per excluded task.

    The overlay reads ``original_result`` read-only and never
    mutates it. Adjusted fields live on the returned
    :class:`OverlayResult`; :attr:`OverlayResult.original_result`
    carries the exact upstream instance.

    Args:
        original_result: the DCMA Metric 6 ``MetricResult`` this
            overlay adjusts. Must not be ``None``.
        schedule: the source ``Schedule``. Read-only.
        options: ``MetricOptions``; defaults to a fresh
            :class:`MetricOptions()` when ``None``. Threshold is
            read from ``options.high_float_threshold_pct`` — not
            hardcoded — so a client-specified override flows through.

    Returns:
        A frozen :class:`OverlayResult` with the schedule-margin
        exclusion applied. ``informational_notes`` is empty for
        this rule; it is a denominator correction, not a note
        emission.

    Raises:
        :class:`MissingMetricResultError` when ``original_result``
        is ``None``.
    """
    if original_result is None:
        raise MissingMetricResultError(
            "apply_schedule_margin_exclusion", "DCMA-6"
        )

    opts = options if options is not None else MetricOptions()

    # DCMA §3 eligible set recomputed on the schedule so the
    # exclusion accounting lines up with Metric 6's own denominator.
    # The overlay does not re-run CPM; see _is_dcma_eligible for the
    # cycle-skip approximation note.
    eligible = [t for t in schedule.tasks if _is_dcma_eligible(t, opts)]
    margin_in_eligible = [t for t in eligible if t.is_schedule_margin]

    # Numerator adjustment — only the schedule-margin tasks the
    # upstream metric actually flagged (i.e. whose UniqueIDs appear
    # in offenders) come off the numerator.
    offender_uids = {o.unique_id for o in original_result.offenders}
    margin_offenders = [
        t for t in margin_in_eligible if t.unique_id in offender_uids
    ]

    adjusted_denominator = original_result.denominator - len(margin_in_eligible)
    adjusted_numerator = original_result.numerator - len(margin_offenders)

    if adjusted_denominator > 0:
        adjusted_ratio = (adjusted_numerator / adjusted_denominator) * 100.0
        # Threshold recomputation against the same MetricOptions the
        # upstream metric used — no hardcoded 4% / 5% here.
        adjusted_severity: Severity | None = (
            Severity.PASS
            if adjusted_ratio <= opts.high_float_threshold_pct
            else Severity.FAIL
        )
    else:
        # Zero-denominator case after exclusion — no eligible task
        # remains to fail against; ratio and severity are None so
        # the narrative layer can phrase it explicitly.
        adjusted_ratio = None
        adjusted_severity = None

    exclusions = tuple(
        ExclusionRecord(
            unique_id=t.unique_id,
            task_name=t.name,
            exclusion_reason=(
                "is_schedule_margin = True — NASA SMH §3 "
                "(schedule margin is not CPM total float)"
            ),
        )
        for t in margin_in_eligible
    )

    return OverlayResult(
        metric_id=original_result.metric_id,
        original_result=original_result,
        adjusted_numerator=adjusted_numerator,
        adjusted_denominator=adjusted_denominator,
        adjusted_ratio=adjusted_ratio,
        adjusted_severity=adjusted_severity,
        informational_notes=(),
        tasks_excluded_from_denominator=exclusions,
    )
