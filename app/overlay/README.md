# NASA SMH Overlay — Milestone 8

Layers NASA Schedule Management Handbook (SMH) expectations on top
of the frozen DCMA 14-Point metric results produced by
`app/metrics/`. The overlay is a governance-triage layer: it reads
`MetricResult`, `Schedule`, and `MetricOptions` read-only and emits
a sibling `OverlayResult` carrying adjusted denominators,
informational notes, and exclusion records. The underlying
`MetricResult` is never mutated.

## Architectural position

`app/engine/` is the pure-CPM layer (forward/backward pass,
calendar math, constraint application, topology, duration helpers).
`app/metrics/` is the frozen-contract DCMA 14-Point layer
(BUILD-PLAN §2.14). `app/overlay/` sits above `app/metrics/` and
reads its outputs; it is neither pure CPM nor a new DCMA metric.
See BUILD-PLAN §5 M8 AM5 for the package-placement rationale.

## Public API

* `OverlayResult` — frozen dataclass mirroring `MetricResult`.
  Carries the original result, adjusted numerator / denominator /
  ratio / severity, a tuple of `OverlayNote`s, and a tuple of
  `ExclusionRecord`s.
* `OverlayNote` — one row of informational text tagged with an
  `OverlayNoteKind`; consumed by the M11 manipulation engine.
* `OverlayNoteKind` — `StrEnum` of note kinds
  (`GOVERNANCE_MILESTONE_TRIAGE`, `ROLLING_WAVE_NEAR_TERM_WARNING`,
  `ROLLING_WAVE_OUT_OF_WINDOW`).
* `ExclusionRecord` — one row identifying a task excluded from a
  metric's denominator.
* `GOVERNANCE_PATTERNS`, `is_governance_milestone`,
  `match_governance_pattern` — externalized governance-milestone
  name taxonomy in `app/overlay/nasa_milestones.py`.
* `OverlayError`, `MissingMetricResultError` — exception hierarchy.

Rule functions (one per M8 overlay rule):

* `apply_schedule_margin_exclusion(original_result, schedule,
  options=None)` — DCMA Metric 6 (High Float) overlay. Recomputes
  denominator and numerator excluding `Task.is_schedule_margin`
  tasks; returns an `OverlayResult` carrying
  `ExclusionRecord`s per excluded task. **Denominator-adjustment
  rule**; no notes emitted.
* `apply_governance_milestone_triage(original_result, schedule,
  options=None)` — DCMA Metric 5 (Hard Constraints) overlay. Emits
  one `GOVERNANCE_MILESTONE_TRIAGE` note per offender whose task
  name matches the NASA governance-milestone taxonomy. **Note-
  emission rule**; adjusted fields all `None`.
* `apply_rolling_wave_window_check(original_result, schedule,
  options=None)` — DCMA Metric 8 (High Duration) overlay. Emits
  `ROLLING_WAVE_NEAR_TERM_WARNING` or `ROLLING_WAVE_OUT_OF_WINDOW`
  per rolling-wave task whose forecast window is outside the SMH
  6–12 month band. **Note-emission rule**; adjusted fields all
  `None`.

## Rule / metric / skill-section map

| Rule                                   | DCMA metric | SMH section | Authority                                      |
|----------------------------------------|-------------|-------------|------------------------------------------------|
| `apply_schedule_margin_exclusion`      | Metric 6    | SMH §3, §6  | `dcma-14-point-assessment §4.6`, `§8`          |
| `apply_governance_milestone_triage`    | Metric 5    | SMH §6      | `nasa-program-project-governance §§4, 5`; DCMA `§4.5` |
| `apply_rolling_wave_window_check`      | Metric 8    | SMH §4      | `dcma-14-point-assessment §4.8`, `§8`          |

## Threshold reads

Every rule reads thresholds from the `MetricOptions` instance the
caller supplies (no hardcoded 5% / 44 WD / 6-month constants
outside the module-private helper bands). The schedule-margin
exclusion rule recomputes severity against
`options.high_float_threshold_pct`; the governance-triage rule is
note-emission only and does not consume a threshold; the rolling-
wave rule hard-codes the SMH 6/12-month calendar-day windows per
`nasa-schedule-management §4` (183 / 365 days), noted in its
docstring for a future narrative-layer adjustment.

## Non-mutation invariant

`OverlayResult.original_result` is the exact `MetricResult` the
upstream metric produced. The overlay never rebinds it, never
rewrites its `offenders` tuple, and never alters its
`computed_value`. Tests assert byte-equality of the original result
before and after every overlay call via a deterministic snapshot
helper.

## M11 consumer contract (emit-side)

M8 is strictly emit-side for governance-triage notes. M11's
manipulation engine is the downstream consumer: M11 reads the
`informational_notes` tuple, routes on the `OverlayNoteKind` value
and `unique_id`, and suppresses the relevant manipulation finding
(e.g. constraint-injection raises for governance-milestone tasks).
M8 does not stub M11 logic and does not assert M11 behaviour.

## Authority

* `nasa-schedule-management §3` — schedule margin as a deliberate
  PM-owned reserve distinct from CPM total float; High-Float
  denominator exclusion.
* `nasa-schedule-management §4` — rolling-wave 6–12 month near-term
  window; duration cap; LOE / long-lead exceptions.
* `nasa-schedule-management §6` — NASA overlay rule placement on
  the DCMA 14-Point protocol.
* `nasa-program-project-governance §4` — KDP taxonomy (programs:
  Roman-numeral KDP-0 through KDP-VII; projects: letter KDP-A
  through KDP-F).
* `nasa-program-project-governance §5` — Life-Cycle Review set
  (MCR, SRR, MDR/SDR, PDR, CDR, SIR, ORR, FRR/MRR, PLAR, CERR,
  PFAR, PIR, DR) and SRB scope.
* `dcma-14-point-assessment §4.5` — DCMA Metric 5 (Hard Constraints,
  09NOV09 four-constraint list MSO/MFO/SNLT/FNLT).
* `dcma-14-point-assessment §4.6` — DCMA Metric 6 (High Float, 44
  WD ceiling, ≤ 5% threshold).
* `dcma-14-point-assessment §4.8` — DCMA Metric 8 (High Duration,
  rolling-wave exemption).
* `dcma-14-point-assessment §8` — NASA overlay on the DCMA
  protocol.
* BUILD-PLAN §5 Milestone 8 — milestone specification and
  acceptance criteria.
