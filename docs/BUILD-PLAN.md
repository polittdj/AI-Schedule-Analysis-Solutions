# Phase 1 Master Build Plan — AI Schedule Analysis Solutions

> **Status:** Canonical specification for Phase 1 of the ScheduleForensics
> LLC flagship web application. Every milestone build session reads this
> document as ground truth. Written 2026-04-17. Scope frozen by user
> decision; see §2 for locked decisions.

---

## 1. Purpose and Scope

### 1.1 Project identity

Repository: `polittdj/AI-Schedule-Analysis-Solutions`. Brand:
ScheduleForensics LLC. Product: a local Flask web application for
forensic CPM schedule analysis of Microsoft Project `.mpp` files on a
NASA/DoD senior analyst workstation. The tool parses `.mpp` files
locally, runs deterministic forensic analysis (DCMA 14-Point,
manipulation detection, critical path, driving path, cross-version
comparison), and generates AI-assisted narrative via a dual-mode AI
backend (Ollama default, Claude API opt-in for unclassified work only).
Domain knowledge is encoded in the eight SKILL.md files under
`.claude/skills/`; build sessions read them as authoritative reference
before coding.

### 1.2 Phase 1 mission statement

Phase 1 delivers a forensic-analysis tool that (a) parses `.mpp` via
`win32com` COM automation, (b) computes all fourteen DCMA 14-Point
metrics with per-task drill-down and NASA SMH overlay, (c) detects
manipulation across two status-date-differentiated versions matched by
UniqueID, (d) traces task-specific driving paths via the SSI
methodology, and (e) renders a drill-down UI where every result cites
the exact task IDs and names. On-host only; zero schedule-data egress.

### 1.3 In-scope items (9)

A. **COM automation parser** (`win32com` primary; MPXJ/JPype removed).
   Handles the ten Appendix D gotchas from
   `mpp-parsing-com-automation §3`; yields `ScheduleData` keyed by
   UniqueID with durations in minutes (converted to working days at
   presentation per §2.6).

B. **All 14 DCMA 14-Point metrics** per `dcma-14-point-assessment §4`.
   Every result lists flagged UniqueIDs + task names, not an aggregate
   percentage alone.

C. **NASA SMH overlay** per `nasa-schedule-management §6`. High-Float
   denominator excludes schedule-margin tasks; governance-milestone
   constraints trigger triage messaging before hard-constraint flags.

D. **Manipulation scoring engine rewrite.** Fixes the always-100 bug,
   normalizes per-pattern contributions, routes the CPM cascade
   correctly, deduplicates findings by UniqueID.

E. **Task-specific driving path analysis** per `driving-slack-and-paths
   §5`. SSI focus-point methodology; back-trace along zero-slack edges
   from an operator-nominated UniqueID.

F. **Transparency / drill-down for every metric.** Every conclusion
   cites the tasks that drove it. Cross-cutting constraint on every
   milestone, not a separate one.

G. **Status-date-aware windowing.** Changes between Period A and
   Period B status dates are legitimate actuals, not manipulation
   (`forensic-manipulation-patterns §3.2`; `driving-slack-and-paths
   §10`).

H. **Ollama-default AI backend with Claude API toggle.** Ollama
   `schedule-analyst` on `http://localhost:11434` by default; Claude
   API only when the analyst toggles a project to unclassified.
   Persistent banner while Claude is active.

I. **500 MB file upload limit.** Flask `MAX_CONTENT_LENGTH`, nginx
   `client_max_body_size`, client-side JS/HTML validation,
   `RequestEntityTooLarge` handler. Already implemented on the archive
   branch; Phase 1 ratifies and ships a regression test.

### 1.4 Deferred to Phase 2 (3 items)

J. **Multi-version trend analysis across up to 10 revisions with
   One-Pager forensic reports.** Phase 1 supports exactly two versions;
   scaling requires trend math and UI changes that would force scope
   creep on every Phase 1 milestone.

K. **RAG upgrade (Option 2) for Ollama.** ChromaDB +
   sentence-transformers retrieval. Phase 1 AI consumes only
   pre-computed metrics.

L. **Ollama model improvement suite.** Custom Modelfile iteration,
   structured KB seeding, feedback loop. Phase 1 uses the existing
   model as-is.

### 1.5 Deferred to Phase 3 (1 item)

M. **Earned value metrics (SPI / BEI / CEI / SPI(t)).** Explicitly
   out-of-scope per user handoff "NO EVA in this build." BEI appears
   in DCMA 14-Point as Metric 14 and is built in Phase 1 as a DCMA
   check; full EVA integration (cost loading, CPR reconciliation,
   variance analysis) is Phase 3. See `acumen-reference §6.3` for the
   cost-CSV vocabulary that Phase 3 will consume.

---

## 2. Locked Architectural Decisions

The eleven decisions below are **frozen** by user judgement. No
milestone may propose or silently introduce an alternative.

2.1 **Backend: Flask on Python 3.13, localhost:5000.** Single-worker
dev server; multi-worker deployment is out of scope.

2.2 **AI backend: Ollama default, Claude API opt-in.** Ollama
`schedule-analyst` on `http://localhost:11434`; Claude API
(`claude-sonnet-4-6`) only for unclassified projects
(`cui-compliance-constraints §§2b, 2f`).

2.3 **Parser: `win32com` COM automation only.** MPXJ/JPype removed
from Phase 1 per `mpp-parsing-com-automation §1`.

2.4 **Frontend: vanilla JavaScript.** No React/Vue/build step.
Tabulator.js for tables; Chart.js via CDN for charts; SheetJS via CDN
for Excel.

2.5 **Export stack: `python-docx` (DOCX), `openpyxl` (XLSX),
`reportlab` (PDF).**

2.6 **Duration storage: minutes internally, working days at
presentation.** COM returns `Duration`/`RemainingDuration`/slack/`Lag`
in integer minutes (`mpp-parsing-com-automation §3.5`); conversion
uses the project default calendar's hours-per-day. Calendar-day
conversion for date slips happens at presentation only.

2.7 **Cross-version task matching: UniqueID only.** Never `ID`, never
name (`mpp-parsing-com-automation §5`). Non-negotiable across every
comparator and manipulation probe.

2.8 **Windowing: status-date-aware.** A task whose Period A finish is
≤ Period B status date is legitimate actual
(`forensic-manipulation-patterns §3.2`; `driving-slack-and-paths §10`).

2.9 **Driving path: Period A slack rule for but-for analysis** per
`driving-slack-and-paths §9`. Period B slack is circular by
construction.

2.10 **CUI: zero cloud egress for schedule data.** Schedule files and
derivatives never commit to git and never go to any remote service
(`cui-compliance-constraints §§2a, 2c, 5`); `.gitignore` enforces the
git-commit rule.

2.11 **File upload limit: 500 MB.** Flask `MAX_CONTENT_LENGTH`, nginx
`client_max_body_size`, client-side validation,
`RequestEntityTooLarge` handler. Ratified with regression test
(Milestone 1).

(Decision 2.12 consolidated with 2.6.)

2.13 **Mutation-vs-wrap.** The CPM engine returns a
:class:`~app.engine.result.CPMResult` wrapper rather than mutating
``Schedule``. Every downstream consumer (DCMA metrics, comparator,
driving path, manipulation engine, narrative layer) reads both
``Schedule`` and ``CPMResult`` **read-only**. Where a milestone needs
a variant schedule — the Metric 12 CPT +600-WD probe, the M9
cross-version comparator — it produces the variant via
``Schedule.model_copy(update=...)`` / ``Task.model_copy(update=...)``
and runs CPM against the copy. Tests assert byte-equality of the
inputs before and after any metric invocation (M6 `_utils.py`
snapshot helper; M7 mutation-invariance assertions).

2.14 **Metric result contract.**
:class:`~app.metrics.base.MetricResult`,
:class:`~app.metrics.base.Offender`,
:class:`~app.metrics.base.ThresholdConfig`,
:class:`~app.metrics.base.Severity`, and
:class:`~app.metrics.options.MetricOptions` are
``@dataclass(frozen=True, slots=True)`` and are **frozen** as a
public contract from M5 forward. Extensions land additively — new
sibling classes in ``app.metrics.base`` or new threshold fields on
``MetricOptions`` — never as mutations of existing fields. M6 (five
metrics) and M7 (five metrics + baseline plumbing) both ship under
this rule; M11 (manipulation) consumes ``MetricResult`` without
re-deriving any field.

2.15 **Indicator-only metrics.** DCMA Metric 10 (Resources) has no
published pass/fail threshold under the 09NOV09 protocol
(``dcma-14-point-assessment §4.10``,
``DeltekDECMMetricsJan2022.xlsx`` sheet *Metrics*). It emits
``Severity.WARN`` regardless of ratio, and its
:class:`ThresholdConfig` carries ``direction="indicator-only"`` as a
sentinel so the threshold carrier remains schema-stable. Other
indicator-only cases — baseline-required metrics (11, 13, 14) on a
schedule with no baseline coverage, BEI on a zero-denominator
window, and CPT's "structural-pass-fail" variant — use the same
convention: the metric returns a valid :class:`MetricResult` with
``Severity.WARN`` and an explanatory ``notes`` string rather than
raising. Raise is reserved for structural prerequisite failures
(missing :class:`CPMResult` on a CPM-consuming metric).

2.16 **Minutes → working days via engine helper.** The single source
of truth for the unit conversion is
:func:`app.engine.duration.minutes_to_working_days` (and its
inverse :func:`working_days_to_minutes`). Every metric that
presents a working-day value (Metrics 6, 7, 8 for slack / duration;
Metric 13 for CPLI baseline length) routes through the helper using
the project default calendar's ``hours_per_day``. No metric rolls
its own ``minutes / 480`` arithmetic; a non-8h/day calendar scales
correctly end-to-end.

2.17 **CPMResult consumption is read-only in the metrics layer.** A
metric that needs CPM output (Metrics 6, 7, 12, 13) accepts a
:class:`~app.engine.result.CPMResult` argument and reads
``cpm_result.tasks[unique_id]`` without mutation. The metric never
recomputes forward or backward pass. A missing ``CPMResult`` on a
CPM-consuming metric raises
:class:`~app.metrics.exceptions.MissingCPMResultError`, mirroring
the ``MissingCPMResultError`` hierarchy that M5 introduced as a
forward-looking API for M6 / M7. The engine is the single producer
of ``CPMResult``; the metrics layer is the sole consumer in
Phase 1.

2.18 **Driving path: no path is dropped on multi-branch backward
walk.** (**AM8, 2026-04-22 M10 Block 7 remediation.**) The backward
walk from a Focus Point along zero-relationship-slack edges
enumerates **every** zero-slack incoming relationship at every node
in the driving sub-graph — none is dropped. Authority is verbatim
from ``driving-slack-and-paths``:

* §4: "No path is dropped."
* §5: "Walking every relationship-slack-zero link backward … walks
  recursively until every driving predecessor is exhausted."

The "lowest-UID tie-break" rule documented in the original AM7 M10
Block 0 reconciliation (§5 M10) is **withdrawn**. Tie-break is no
longer a concept in this codebase: every zero-slack edge is a
driving edge and appears on ``DrivingPathResult.edges``. The prior
chain-based contract (``chain`` + parallel ``links`` parallel list)
is superseded by an adjacency-map contract (``nodes: dict[int,
DrivingPathNode]``, ``edges: list[DrivingPathEdge]``,
``non_driving_predecessors: list[NonDrivingPredecessor]``) so the
full sub-graph is representable without lossy serialisation. See
branch ``claude/milestone-10-block-7-remediation-2026-04-22`` and
the §5 M10 AM8 block below for implementation scope.

(Sub-item lettering note: AM8 registers a new forensic non-
negotiable "(e) No path is dropped on multi-branch backward walk."
as a companion to the four non-negotiables listed in the M10 Block
7 write-session prompt §0.3 (UniqueID-only matching, Period A slack
exclusivity, non-mutation of Schedule/CPMResult, UniqueID+name on
every node). The original prompt referenced §2.15 for this addition
in error; §2.15 is the indicator-only-metrics decision. The new
non-negotiable lives here at §2.18.)

### 2.19 User-visible durations convention (AM9, 4/23/2026)

All user-visible durations — Pydantic contract field names, renderer
output strings, README examples, Word/Excel/HTML report bodies, and
CLI output — are denominated in DAYS. Minutes and hours are internal
CPM currency (§2.16) and never appear in user-facing output.

Format helper: app.engine.units.format_days(days: float) -> str is the
sole formatting point. Format rules:

- 2-decimal precision maximum.
- Ceiling rounding at 0.01 for positive values; floor rounding at -0.01
  for negative values; exactly 0.0 preserved.
- Trailing zeros stripped: 2.0 → "2 days", 2.10 → "2.1 days".
- Leading zero omitted on fractional absolute values: 0.5 → ".5 days",
  -0.5 → "-.5 days".
- Singular / plural: "day" only for exactly +1 or exactly -1 (post-
  rounding); "days" everywhere else including ".5 days" and "0 days".

Enforcement: a schema invariant test scans every public Pydantic model
in app.engine and asserts no field name matches /_(minutes|hours|seconds)$/.
New public models that carry a duration MUST use the *_days convention.

Authority: NASA Schedule Management Handbook §5.5.9.1 ("task durations
should generally be assigned in workdays"); Papicito's forensic-tool
standard dated 4/23/2026.

### 2.20 Three-bucket partition for driving-path predecessors (AM10, 4/23/2026)

The driving-path backward walk classifies every incoming relationship
on a node in the driving sub-graph into exactly one of three buckets,
keyed on per-relationship driving slack (driving-slack-and-paths §3):

1. DrivingPathEdge — relationship_slack_days within ±(1/86,400) of
   zero. §5 verbatim: "Walking every relationship-slack-zero link
   backward … walks recursively until every driving predecessor is
   exhausted." §4 verbatim: "No path is dropped."

2. NonDrivingPredecessor — slack_days strictly greater than
   +(1/86,400). Positive-flexibility also-ran predecessors; terminate
   the backward walk on their successor.

3. ConstraintDrivenPredecessor — slack_days strictly less than
   -(1/86,400). Negative relationship slack indicates the predecessor's
   CPM dates are held by a hard constraint (MSO / MFO / SNLT / FNLT)
   or by negative-float propagation from a missed deadline.

DCMA-EA Metric #7 (Edwards 2016, pp. 9-10) verbatim: "Negative float
occurs when the project schedule is forecasting a missed deadline, or
when a hard constraint is holding a task further to the left than it
would otherwise be."

NASA Schedule Management Handbook on hard constraints, verbatim:
"Improper use can cause negative float to be calculated throughout
the schedule."

The three buckets are mutually exclusive and exhaustive over the
reals. Pydantic validators enforce the partition structurally —
no escape hatches. ConstraintDrivenPredecessor carries the
predecessor task's constraint_type, constraint_date (if date-bearing),
and a narrative rationale string for deposition-grade reports.

Resolves: PR #31 Codex review P1 (ValidationError crash on constrained
schedules). Authority references: driving-slack-and-paths §3, §4, §5;
dcma-14-point-assessment §4.7; NASA Schedule Management Handbook
§5.5.9.1 and hard-constraint sections; BUILD-PLAN §2.16, §2.18.

### 2.21 M10.2 remediation — Codex PR #33 post-merge findings (AM11, 4/23/2026)

After M10.1 merged to main via squash commit c496f5a, GitHub's Codex
automated reviewer posted two additional findings on PR #33 that the
in-flight audit missed. Both are real production bugs — neither is
style or nit — and both require remediation in M10.2. This amendment
records the findings and their remediation scope so that M10.2 Block 1
and later blocks execute against a documented, bounded target rather
than a drifting bug list.

**Finding #1 — format_days decimal rounding error (severity 1).**

The format_days helper in app/engine/units.py (M10.1 Block 3,
commit 5623f35) implements 2-decimal precision by routing positive
values through math.ceil(days * 100) / 100 and negative values through
math.floor(days * 100) / 100. The intent is ceiling-round at 0.01
for positive and floor-round at -0.01 for negative, preserving the
AM9 rounding contract (§2.19).

The defect is that IEEE-754 binary floating point cannot represent
many exact-looking decimal values precisely. 2.2 stored as a Python
float is actually 2.2000000000000002; multiplying by 100 yields
220.00000000000003, not 220.0. math.ceil then bumps that to 221,
and format_days emits "2.21 days" where the analyst expects
"2.2 days". The same class of error fires for 1.1, 3.3, 4.4, and
essentially any realistic fractional-day duration that happens to
fall on one of the non-representable binary-float boundaries.

This is a systematic numeric distortion present in every forensic
report the tool produces. A deposition-grade schedule-analysis
artifact cannot ship with this defect — adversarial counsel will
locate it immediately and every rounded duration in every table
becomes impeachable.

Remediation: replace math.ceil and math.floor operating on binary
floats with Python's decimal.Decimal using ROUND_CEILING and
ROUND_FLOOR quantization at the 0.01 step. decimal.Decimal performs
base-10 arithmetic internally and does not accumulate the binary
representation error. The public format_days signature and
contract (AM9 rules from §2.19) stay identical; only the internal
rounding mechanism changes.

**Finding #2 — skipped_cycle_participants incomplete capture (severity 2).**

The skipped_cycle_participants list on DrivingPathResult (M10.1
Block 2, commit 666226b, added per PR #31 Codex P2) is intended to
preserve forensic visibility into every predecessor UID that the
backward walk dropped because of a cycle in the logic network.
Without this list the tracer silently loses evidence — a
manipulation pattern per forensic-manipulation-patterns §3 that the
tool must surface, not hide.

The defect is that the current implementation only records UIDs at
one of two points where cycle filtering occurs. It captures UIDs
that the walk enqueued and then rejected at the visit-level
CPM-row check. It does NOT capture UIDs filtered earlier, inside
_link_slack_minutes, which returns None for any edge where either
the predecessor or the successor task is marked
skipped_due_to_cycle. When _link_slack_minutes returns None the
tracer drops the edge silently and the predecessor UID on the far
side of that edge is never enqueued, so the visit-level recorder
never sees it. Cycle participants that terminate a driving branch
at the edge level are therefore absent from
skipped_cycle_participants and the forensic-visibility contract is
incomplete.

This gap was observed during M10.1 Block 5 test authoring: the
test author had to surgically override a TaskCPMResult to exercise
the skip-recording branch at all (documented in the Block 5
session summary). Codex's PR #33 comment confirmed independently
that the edge-drop recording path does not exist.

Remediation: record the predecessor UID at the edge-drop level
inside _link_slack_minutes (or at its call site in the tracer)
when the None return is caused by cycle participation, not just at
the visit level. The recording must dedupe against the visit-level
recording so a single cycle participant that is reachable via
multiple dropped edges, or via both filter points, appears exactly
once in skipped_cycle_participants.

**Scope cap.**

M10.2 remediates only the two Codex PR #33 findings enumerated
above, plus the regression tests required to prevent recurrence.
No new features. No scope expansion. No opportunistic refactors.
All other M10.1 work — the three-bucket partition (§2.20), the
days-only UX enforcement (§2.19), the schema invariant test, the
renderer, and the public API surface — stays as-is and is not
re-opened by this amendment.

Authority references: app/engine/units.py format_days
implementation (M10.1 Block 3, commit 5623f35);
app/engine/driving_path.py skip-recording logic (M10.1 Block 2,
commit 666226b); PR #33 Codex review comments (two findings dated
4/23/2026); BUILD-PLAN §2.19 (days-only UX convention, AM9).

### 2.22 M11 manipulation-scoring engine — scope, contracts, state machine (AM12, 4/23/2026)

**(a) Scope statement.**

M11 is the manipulation-scoring engine. It detects eroding
constraint-driven slack across two UniqueID-matched schedule versions
and produces weighted Acumen-Fuse-style manipulation scores per
UniqueID, aggregated into a schedule-level summary. M11 is a NEW
forensic domain separate from M9's cross-version comparator
(`app/engine/comparator.py`, `ComparatorResult`) and from M10's
task-specific driving-path cross-version trace
(`app/engine/driving_path.py::trace_driving_path_cross_version`,
`DrivingPathCrossVersionResult`). Neither of those two surfaces is
modified by M11; M11 introduces its own comparator that operates on
the `constraint_driven_predecessors` set emitted by the M10.1
three-bucket partition (§2.20) and on the
`skipped_cycle_participants` forensic trail emitted by M10.2 (§2.21).
The authority layer is `forensic-manipulation-patterns §9`
(cross-version erosion), `forensic-manipulation-patterns §10` (red-
flag aggregation tiers), `acumen-reference §3.3` / `§3.6` (tripwire
threshold scales and weighting), `driving-slack-and-paths §6`
(TotalFloat trend classification vocabulary), and BUILD-PLAN §2.20
(three-bucket partition) and §2.8 / §2.9 (status-date windowing and
Period A but-for rule).

**(b) New modules to be created.**

Paths only — implementation is deferred to M11 Block 2+ and is
explicitly forbidden by this amendment. Block 1 (this amendment) adds
no `.py` files.

- `app/contracts/manipulation_scoring.py` — frozen Pydantic v2
  contract types for the M11 scoring surface. New package
  `app/contracts/` introduced by this amendment as the home for
  cross-milestone frozen contracts; M10.1's `ConstraintDrivenPredecessor`
  and related types remain at `app/engine/driving_path_types.py` and
  are imported by `app/contracts/manipulation_scoring.py` rather than
  relocated (M11 is additive; §2.20 contract paths are not re-opened).
- `app/engine/constraint_driven_cross_version.py` — dedicated
  `ConstraintDrivenCrossVersionComparator` class. This class is NEW
  and does NOT extend or subclass M9's `ComparatorResult` or M10's
  `DrivingPathCrossVersionResult`. It consumes two
  `DrivingPathResult` instances (one per period) and emits a
  `ConstraintDrivenCrossVersionResult` carrying per-UID set algebra
  on each period's `constraint_driven_predecessors` list.
- `app/engine/manipulation_scoring.py` — scoring engine that consumes
  a `ConstraintDrivenCrossVersionResult` plus both periods' CPM
  outputs and emits a `ManipulationScoringResult` per UID plus a
  `ManipulationScoringSummary` aggregate.
- `tests/engine/test_constraint_driven_cross_version.py` — unit tests
  for the comparator. NEW tests subdirectory `tests/engine/`
  introduced by this amendment; pre-existing tests remain at
  `tests/test_engine_*.py` flat-layout and are not relocated.
- `tests/engine/test_manipulation_scoring.py` — unit tests for the
  scoring engine.
- `tests/contracts/test_manipulation_scoring.py` — frozen-contract
  shape validation tests; parallel new subdirectory `tests/contracts/`.

Path convention note. The existing codebase places engine contract
types in `app/engine/<name>_types.py` (see `driving_path_types.py`,
`result.py`) and tests flat under `tests/test_engine_*.py`. AM12
introduces `app/contracts/` and `tests/engine/` / `tests/contracts/`
subdirectories as new conventions scoped to M11 only. Rationale:
manipulation scoring is a cross-layer domain (consumes engine
outputs, emits renderer-ready scoring artifacts, will be imported by
the M12 AI narrative layer and the M13 UI); a dedicated
`app/contracts/` package gives M12 and M13 a stable import surface
without forcing them to reach into `app/engine/` internals. Audit
this convention choice before M11 Block 2 begins implementation.
Retrofit of M10.1 types into `app/contracts/` is explicitly OUT of
scope for M11 (§2.20 is frozen; see subsection (j) below).

**(c) Contract shapes.**

All three contracts are frozen Pydantic v2 models
(`model_config = ConfigDict(frozen=True)`). Duration fields are
denominated in days per §2.19 (AM9 days-only UX); integer minutes
are never exposed on M11 public models. The specs below are
authoritative for Block 2 implementation; field names, types, and
ordering are frozen by this amendment.

```python
# app/contracts/manipulation_scoring.py

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field

from app.engine.driving_path_types import (
    ConstraintDrivenPredecessor,
    DrivingPathResult,
)


class SlackState(StrEnum):
    """Per-UID slack state transition from Period A to Period B.

    Authority: forensic-manipulation-patterns §9 (cross-version
    erosion); driving-slack-and-paths §6 (TotalFloat trend
    classification vocabulary adapted for constraint-driven slack).
    """

    JOINED_PRIMARY = "joined_primary"
    ERODING_TOWARD_PRIMARY = "eroding_toward_primary"
    STABLE = "stable"
    RECOVERING = "recovering"


class SeverityTier(StrEnum):
    """Per-UID severity tier driving the Acumen-Fuse-style weighted
    score. Weights defined in subsection (e)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConstraintDrivenCrossVersionResult(BaseModel):
    """Per-UID set algebra on constraint_driven_predecessors across
    Period A and Period B. Period A is the but-for reference per
    BUILD-PLAN §2.9 / driving-slack-and-paths §9.

    Emitted by ConstraintDrivenCrossVersionComparator. Consumed
    read-only by the M11 scoring engine.
    """

    model_config = ConfigDict(frozen=True)

    period_a_result: DrivingPathResult
    period_b_result: DrivingPathResult

    period_a_status_date: datetime | None
    """Absolute status_date carried forward from Schedule A. This is the
    "ProjectPreviousTimeNow" in Acumen Fuse's comparative-metric model.
    None when Schedule A.status_date is None. Consumers reference this
    value directly when constructing comparative predicates over the
    (period_a_status_date, period_b_status_date] window."""

    period_b_status_date: datetime | None
    """Absolute status_date carried forward from Schedule B. This is the
    "ProjectTimeNow" in Acumen Fuse's comparative-metric model. None
    when Schedule B.status_date is None."""

    period_a_project_start: datetime | None
    """Absolute project_start carried forward from Schedule A. Provided
    so downstream consumers can reason about per-period timelines
    without re-accessing the Schedule object. None when Schedule
    A.project_start is None."""

    period_b_project_start: datetime | None
    """Absolute project_start carried forward from Schedule B. None when
    Schedule B.project_start is None."""

    period_working_days_elapsed: float | None
    """Pre-computed working days between period_a_status_date and
    period_b_status_date, using PERIOD B's calendar. Computed once at
    result construction time to spare downstream consumers repeated
    calendar arithmetic. None when either status_date is None, or
    when Period B's calendar is missing or unresolvable. Rationale
    for using Period B's calendar: comparative forensic metrics
    reason about the CURRENT period's working-time frame; Period A's
    calendar may be stale if calendars changed between snapshots."""

    added_constraint_driven_uids: set[int] = Field(default_factory=set)
    """Successor UIDs that carry a ConstraintDrivenPredecessor in
    Period B but not in Period A. Identity: successor_uid."""

    removed_constraint_driven_uids: set[int] = Field(default_factory=set)
    """Successor UIDs that carried a ConstraintDrivenPredecessor in
    Period A but not in Period B."""

    retained_constraint_driven_uids: set[int] = Field(default_factory=set)
    """Successor UIDs present in both periods' constraint_driven_
    predecessors lists. State transition computed by the scoring
    engine per subsection (d)."""

    period_a_predecessors_by_successor: dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ] = Field(default_factory=dict)
    """Period A's ConstraintDrivenPredecessor records indexed by
    successor_uid. Preserves the full forensic trail for drill-down."""

    period_b_predecessors_by_successor: dict[
        int, tuple[ConstraintDrivenPredecessor, ...]
    ] = Field(default_factory=dict)
    """Period B's records indexed by successor_uid."""


class ManipulationScoringResult(BaseModel):
    """Per-UID scoring result. One record per successor_uid that
    appears in any of the three set-algebra sets.

    Consumed by the M11 summary aggregator (subsection (e)) and the
    M13 renderer (subsection (i)).
    """

    model_config = ConfigDict(frozen=True)

    unique_id: int
    """successor_uid of the constraint-driven edge(s)."""

    name: str
    """Task.name at Period B if the UID is present in Period B;
    Period A name otherwise. Every scoring record cites a name per
    BUILD-PLAN §6 AC bar #3."""

    score: int
    """Per-UID weighted-Acumen-Fuse score — 10, 5, or 2 per
    subsection (e). Integer by contract."""

    severity_tier: SeverityTier
    """HIGH / MEDIUM / LOW. Highest-severity tier wins on
    per-UID dedup (subsection (e))."""

    slack_state: SlackState
    """Transition classification per subsection (d)."""

    period_a_predecessors: tuple[ConstraintDrivenPredecessor, ...] = ()
    """Constraint-driven edges on this successor in Period A.
    Empty if the UID first appears in Period B."""

    period_b_predecessors: tuple[ConstraintDrivenPredecessor, ...] = ()
    """Constraint-driven edges on this successor in Period B.
    Empty if the UID is only in Period A (RECOVERING full exit)."""

    skipped_cycle_participants_reference: tuple[int, ...] = ()
    """UIDs from DrivingPathResult.skipped_cycle_participants (M10.2,
    §2.21) that are implicated in this UID's constraint-driven
    cluster. Forensic visibility trail — empty when no cycle
    participant touches this UID."""

    windowing_incomplete: bool = False
    """True when status-date filtering could not fully evaluate this UID
    (missing Period B status_date, missing predecessor task in one or
    both periods, or predecessor task present in M10.2
    skipped_cycle_participants and thus carrying non-authoritative CPM
    dates). Forensic visibility flag per subsection (f). When True, the
    scoring record is retained rather than dropped; severity tier may be
    degraded by downstream consumers but is NOT degraded by the scoring
    engine itself."""

    rationale: str
    """Human-readable narrative composed from the contributing
    ConstraintDrivenPredecessor.rationale strings (M10.1) and the
    SlackState transition. Deposition-grade for M12 / M13
    consumption."""


class ManipulationScoringSummary(BaseModel):
    """Schedule-level aggregate across every per-UID scoring record.

    One instance per ConstraintDrivenCrossVersionResult. The total_score
    is bounded at 100 per the Acumen-Fuse-style clamp (subsection (e))
    — additive-before-clamp, never additive-unclamped.
    """

    model_config = ConfigDict(frozen=True)

    total_score: int = Field(ge=0, le=100)
    """Sum of per-UID scores, clamped to [0, 100]. An
    all-clean schedule pair returns 0 per the M11 always-100
    regression bar (superseded phrasing; numeric contract identical)."""

    uid_count_high: int = Field(ge=0)
    uid_count_medium: int = Field(ge=0)
    uid_count_low: int = Field(ge=0)

    uid_count_joined_primary: int = Field(ge=0)
    uid_count_eroding_toward_primary: int = Field(ge=0)
    uid_count_stable: int = Field(ge=0)
    uid_count_recovering: int = Field(ge=0)

    per_uid_results: tuple[ManipulationScoringResult, ...] = ()
    """Every per-UID record. Sorted by (severity_tier desc,
    unique_id asc) for deterministic renderer output."""
```

Set-algebra disjointness invariant. The three set fields
added_constraint_driven_uids, removed_constraint_driven_uids, and
retained_constraint_driven_uids are pairwise disjoint by construction
(they are respectively B−A, A−B, and A∩B on the successor_uid
populations of the two periods' constraint_driven_predecessors lists).
A @model_validator(mode="after") on ConstraintDrivenCrossVersionResult
enforces this invariant and raises ValidationError on any overlap;
Block 3 implements the validator, and the comparator test floor in
subsection (g) covers the raise path.

Authority for the five status-date / project-start / working-days
fields (added by AM13):

Acumen Fuse exposes two named dynamic variables in every comparative
metric expression: ProjectTimeNow (the current schedule's status_date)
and ProjectPreviousTimeNow (the prior snapshot's status_date). All
comparative metrics in the NASA Quick Library
(NASA_Metrics_Complete_20260423.aft, 941 formula definitions, 389 of
which reference these variables) are written as predicates over the
(ProjectPreviousTimeNow, ProjectTimeNow] window. SSI's Baseline
Execution Performance tool uses the same absolute-date pattern
organized as weekly or monthly calendar buckets. Per the tool
fidelity promise (build-chat session 2026-04-24), our
ConstraintDrivenCrossVersionResult mirrors this model: both status
dates are first-class datetime fields, both project_starts are
first-class datetime fields, and period_working_days_elapsed is a
pre-computed convenience derived from the two status dates using
Period B's calendar. This contract shape lets downstream consumers
(Block 4 and beyond) reproduce any Acumen Fuse comparative metric
without re-touching the Schedule objects.

Note: period_working_days_elapsed is a tool-side convenience and
does not appear on Acumen Fuse's variable surface. Acumen computes
equivalent values on demand per metric via its Phase Analyzer. We
precompute once because the M11 scoring engine (Block 4) consumes
this value in multiple scoring sub-rules and recomputing per rule
would duplicate calendar arithmetic. The choice to anchor on Period
B's calendar (not Period A's, not a shared calendar) is documented
above and tested in Block 3's test floor per subsection (g).

**(d) State machine.**

Each `successor_uid` that appears in the comparator's three sets
(`added`, `removed`, `retained`) is assigned exactly one
`SlackState` by the scoring engine. The four states are mutually
exclusive and exhaustive over the set-algebra output. State is
derived from two inputs: (1) set-algebra membership on
`constraint_driven_predecessors`; (2) per-edge `slack_days`
magnitude comparison between Period A and Period B for retained
successors. No other input (total float, free slack, project
finish slip) participates in state derivation; those are for
downstream renderer context only.

The transition rules are:

- **JOINED_PRIMARY** — The successor_uid is in
  `added_constraint_driven_uids`. In Period A it had no
  ConstraintDrivenPredecessor (its incoming edges were all on
  DrivingPathEdge or NonDrivingPredecessor). In Period B it has at
  least one ConstraintDrivenPredecessor. Interpretation: a
  previously-flexible task newly joined the primary constraint-
  driven regime — a hard constraint has been injected upstream or
  negative float has propagated into its chain between the two
  status dates. Authority: `forensic-manipulation-patterns §4.4`
  (constraint injection).

- **ERODING_TOWARD_PRIMARY** — The successor_uid is in
  `retained_constraint_driven_uids` AND the minimum (most negative)
  `slack_days` across its Period B ConstraintDrivenPredecessor
  records is STRICTLY less than (more negative than) the minimum
  across its Period A records, outside the zero-slack tolerance
  band of ±1/86,400 days. Interpretation: a task already in the
  constraint-driven regime is drifting deeper into negative slack
  — the constraint is pulling harder without being removed.
  Authority: `forensic-manipulation-patterns §9`.

- **STABLE** — The successor_uid is in
  `retained_constraint_driven_uids` AND the minimum `slack_days`
  between the two periods differs by less than the zero-slack
  tolerance band of ±1/86,400 days. Interpretation: the
  constraint-driven state is unchanged across the window — not
  improving, not worsening. This is the background "already hot"
  population; it scores LOW per subsection (e), not zero, because
  a persistent constraint-driven state is itself a forensic
  signal.

- **RECOVERING** — The successor_uid is in
  `removed_constraint_driven_uids`, OR it is in
  `retained_constraint_driven_uids` AND the minimum `slack_days`
  in Period B is STRICTLY greater (less negative) than in Period A
  outside the tolerance band. Interpretation: the constraint is
  being released — either a hard constraint removed, negative float
  propagation broken, or the driving relationship replaced with a
  flexible one. Still a forensic signal (constraint removal hiding
  slip per `forensic-manipulation-patterns §4.5`), but scored LOW
  because the Period B state is healthier than Period A.

State-derivation implementation is Block 2 scope. This amendment
specifies only the decision logic. The Pydantic contract on
`ManipulationScoringResult.slack_state` is the public surface; the
scoring engine is the sole producer.

**(e) Scoring weights — weighted-Acumen-Fuse logic.**

Per-UID contribution weights are:

| Severity tier | Points |
|---------------|-------:|
| HIGH          |     10 |
| MEDIUM        |      5 |
| LOW           |      2 |

Tier assignment is determined by `SlackState` AND by the forensic
severity of the constraint type(s) involved:

- **HIGH** — `slack_state == JOINED_PRIMARY` OR
  `slack_state == ERODING_TOWARD_PRIMARY`. A newly-joined or
  deepening constraint-driven regime between two status dates is the
  strongest manipulation signal short of a rebaseline without
  governance authority (`nasa-schedule-management §7.3.4`).
- **MEDIUM** — `slack_state == RECOVERING` AND any contributing
  Period A ConstraintDrivenPredecessor carries
  `predecessor_constraint_type` ∈ {MSO, MFO, SNLT, FNLT} (the four
  09NOV09 hard constraints per `dcma-14-point-assessment §4.5`).
  Constraint-removal hiding slip per
  `forensic-manipulation-patterns §4.5` is a MEDIUM signal — it
  warrants investigation but is lower-severity than active erosion.
- **LOW** — `slack_state == STABLE`, OR `slack_state == RECOVERING`
  with no hard-constraint predecessor in Period A. A persistent-but-
  unchanged constraint-driven state is noted for context; pure
  negative-float-propagation recovery without a hard-constraint
  Period A anchor is a LOW signal.

**Per-UID deduplication.** A single successor_uid is represented by
exactly one `ManipulationScoringResult` record regardless of how
many ConstraintDrivenPredecessor edges it carries or how many
detectors it trips. When multiple detectors classify the same UID,
the HIGHEST tier wins; the per-UID score is the single tier's point
value, never the sum. Authority: `acumen-reference §3.3` (tripwire
= single-activity Boolean, not an accumulator); BUILD-PLAN §2.21
(M11 "per-UID dedup" contract carried forward from the archived
always-100 bug fix).

**Aggregate score clamping.** The caller computes sum(per_uid_scores)
and clamps it to [0, 100] BEFORE constructing ManipulationScoringSummary.
The Pydantic Field(ge=0, le=100) bound on total_score is a
safety-net validator, not the clamp mechanism itself; constructing
the summary with an un-clamped sum greater than 100 raises
ValidationError by contract. Individual UID scores are NEVER scaled
or normalized before the clamp. A schedule pair with 15 HIGH signals
(15 × 10 = 150) reports total_score = 100, and the per_uid_results
tuple carries all 15 un-scaled HIGH records for drill-down. This
mirrors the Acumen Fuse tripwire-and-scorecard pattern
(`acumen-reference §3.6` — weighting applied at scorecard assembly,
not at per-activity tripwire evaluation). No unnormalized-additive
logic; the always-100 bug regression bar from the original §5 M11
scope carries forward.

**Authority.** `acumen-reference §3.3` (tripwire threshold = flag
not verdict; [RW p.20] indicators-not-verdicts posture);
`acumen-reference §3.6` (metric weighting applies at scorecard
assembly); BUILD-PLAN §6 (forensic-defensibility — every score
cites contributing UIDs). HIGH/MEDIUM/LOW weight values are a
tool-side decision informed by `acumen-reference §3.6` (metric
weighting applied at scorecard assembly).
`forensic-manipulation-patterns §10` supplies the aggregation
protocol (three evidence-source tiers: DCMA threshold breach /
cross-version trend / EVMS probe) but does NOT supply severity
weights; §13 of that skill explicitly disclaims quantitative
severity formulas. The three severity tiers at the M11 scoring
layer are a forensic-defensibility convention, not a skill-derived
formula.

**(f) Status-date filtering — legitimate-progress exclusion.**

Before any set-algebra or state-derivation runs, the comparator
applies the standing status-date filter from BUILD-PLAN §2.8
(status-date-aware windowing), §5 M9 AC#2, and
`forensic-manipulation-patterns §3.2`:

> A ConstraintDrivenPredecessor edge whose PREDECESSOR TASK carries
> a Period A `finish` date on or before the Period B `status_date`
> is excluded from manipulation detection. The predecessor's work is
> a legitimate recorded actual per
> `forensic-manipulation-patterns §3.2` and
> `driving-slack-and-paths §10`; its constraint posture is historical,
> not prospective manipulation.

Concretely: for each ConstraintDrivenPredecessor in the two periods'
lists, look up the predecessor task by `predecessor_uid` in the
corresponding Schedule, read its `finish` date, compare to the
Period B `status_date`, and drop the edge from consideration when
`predecessor.finish <= period_b.status_date`. Both a missing Period
B status_date and a predecessor task missing in one or both periods
route to "retain the edge, flag on the scoring record via
`ManipulationScoringResult.windowing_incomplete = True`" rather than
silent drop — forensic visibility always wins when data is
incomplete. This is a standing project decision; the same predicate
is codified at `app/engine/windowing.py::is_legitimate_actual` and
the M11 comparator MUST reuse that helper rather than reimplement it
(Block 2 implementation constraint). Note (AM13):
is_legitimate_actual continues to take absolute datetimes (no change
to the helper), but Block 3's filter logic now has direct access to
period_a_status_date and period_b_status_date on the result object
and does not need to look them up from the period_a_result /
period_b_result DrivingPathResult fields or from the Schedule
objects.

Filter exception: if the predecessor task itself appears in the M10.2
`skipped_cycle_participants` list on either period's
DrivingPathResult, the edge is NOT dropped — cycle participation
overrides legitimate-actual exclusion because cycle-skipped
predecessors have non-authoritative CPM dates by construction
(`app/engine/driving_path.py` cycle-skip semantics per §2.21). The
scoring record's `skipped_cycle_participants_reference` tuple
carries these UIDs so the renderer can annotate the finding.

**(g) Test coverage targets.**

Minimum per-file test counts and required categories. Block 2
Shipping Below These Counts = blocker. Categories are non-exhaustive
(Block 2 may add tests); they are floor requirements, not ceilings.

| File                                                      | Min tests | Required categories                                                                                                                                     |
|-----------------------------------------------------------|----------:|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `tests/contracts/test_manipulation_scoring.py`            |        18 | Contract shape validation (5): frozen-config on all four public models; field-type correctness; SlackState / SeverityTier enum completeness; Field(ge=0, le=100) bounds on total_score; default_factory invariants on set / dict / tuple fields. Field presence (4): every field named in subsection (c) exists with the stated type. Integration (3): ConstraintDrivenPredecessor imported from driving_path_types (no circular import); DrivingPathResult reference resolves; skipped_cycle_participants_reference accepts tuple[int, ...]. Validator-raise cases (6): total_score = -1 raises; total_score = 101 raises; uid_count_* negative raises; set algebra with overlapping adds/removes raises (mutual exclusion). |
| `tests/engine/test_constraint_driven_cross_version.py`    |        24 | Set algebra correctness (6): empty both periods; add-only; remove-only; retain-only; mixed; UID in neither period. Status-date filter (4): predecessor finish < status date excluded; = status date excluded; > status date included; missing status date retained. Skipped-cycle override (3): predecessor in skipped_cycle_participants of period A only retained; period B only retained; both periods retained. Integration with M10.1 (3): ConstraintDrivenPredecessor with MSO / MFO / SNLT / FNLT all sort into added / removed / retained correctly; rationale string preserved verbatim on pass-through; predecessor_constraint_date None passes through. Integration with M10.2 (2): skipped_cycle_participants reference correctly forwarded to per-UID output. Edge cases (4): successor UID appears in period A retained bucket AND period B retained bucket with different constraint types; multiple predecessors on same successor; predecessor task deleted between periods (structural ADDED_IN_B/DELETED_FROM_A from M9 comparator territory — verify M11 does not touch that path). Field presence (AM13 addition, Category B): B-new: Assert that ConstraintDrivenCrossVersionResult carries all five new datetime/float fields from AM13 with their correct type annotations: period_a_status_date: datetime \| None, period_b_status_date: datetime \| None, period_a_project_start: datetime \| None, period_b_project_start: datetime \| None, period_working_days_elapsed: float \| None. Assert field ordering matches the AM12(c)-as-amended-by-AM13 specification. Validator-raise / edge-case (AM13 additions, Category D, 2 new scenarios): D-new-1: period_working_days_elapsed is None when period_b_status_date is None. D-new-2: period_working_days_elapsed is None when Period B's calendar is missing or unresolvable (per Block 3 implementation's chosen failure mode). |
| `tests/engine/test_manipulation_scoring.py`               |        26 | State-machine transitions (8): one per (SlackState × tolerance-band-edge case) matrix — JOINED_PRIMARY; ERODING_TOWARD_PRIMARY at exactly tolerance; ERODING_TOWARD_PRIMARY strictly beyond tolerance; STABLE at zero delta; STABLE within tolerance; RECOVERING at tolerance edge (removed bucket); RECOVERING with hard-constraint Period A anchor; RECOVERING without hard-constraint anchor. Scoring arithmetic (5): HIGH = 10; MEDIUM = 5; LOW = 2; three HIGH UIDs sum to 30; fifteen HIGH UIDs clamp to 100 exactly. Per-UID dedup (4): one UID with two predecessors scores once at highest tier; two detectors both classify as MEDIUM -> single MEDIUM record; HIGH + LOW -> single HIGH record; three-tier overlap -> single HIGH record. Always-zero regression (3): identical Period A and Period B -> total_score = 0; both periods with no constraint_driven_predecessors -> 0; status-date filter drains all candidates -> 0. Integration (3): skipped_cycle_participants reference appears on per-UID result; rationale string composed from M10.1 rationale fields; summary sort order (severity desc, uid asc) verified. Schema invariant (3): total_score bounded to 100; no *_minutes or *_hours fields on any public model (§2.19 invariant holds); ManipulationScoringResult.name non-empty. |

The AM11 test-convention note (flat `tests/test_engine_*.py`) is
superseded by this amendment for M11 tests only; pre-existing tests
remain at their original flat layout.

**(h) Public API surface.**

After M11 Block 2 lands, the following symbols are added to the
tool's public API. Every other M11-introduced symbol is package-
private (prefix `_`) and unsupported for downstream import.

Re-exported from `app/__init__.py` (top-level):

- `ConstraintDrivenCrossVersionResult`
- `ManipulationScoringResult`
- `ManipulationScoringSummary`
- `SlackState`
- `SeverityTier`
- `score_manipulation(period_a, period_b, period_a_cpm_result,
  period_b_cpm_result, focus_spec) -> ManipulationScoringSummary`

Re-exported from `app/engine/__init__.py`:

- `ConstraintDrivenCrossVersionComparator`
- `compare_constraint_driven_cross_version(period_a, period_b,
  focus_spec, period_a_cpm_result, period_b_cpm_result) ->
  ConstraintDrivenCrossVersionResult`

Re-exported from `app/contracts/__init__.py` (new package):

- All four Pydantic contract classes and the two StrEnums from
  `app/contracts/manipulation_scoring.py`.

Not re-exported: any helper function inside
`app/engine/manipulation_scoring.py` whose identifier begins with
`_`; the `ConstraintDrivenPredecessor` / `DrivingPathResult` types
themselves (they remain exported from `app/engine/` per §2.20 and
are not duplicated at the M11 facade). The M11 facade re-exports
ConstraintDrivenPredecessor by attribute access on
ConstraintDrivenCrossVersionResult.period_a_predecessors_by_successor
values only — never as a top-level symbol on the M11 facade.

Canonical entry point rule. score_manipulation is exported ONLY from
app/__init__.py as the top-level facade. Callers that need to bypass
the facade import directly from app.engine.manipulation_scoring;
there is no engine-level re-export and no compatibility alias.

**(i) Renderer scope.**

This amendment fixes only the high-level shape of the renderer
output; detailed UI / report layout is deferred to a later M11 block
and to M13 (Web UI). In M11 the renderer produces:

- A machine-readable `ManipulationScoringSummary` for the M12 AI
  narrative layer and the M13 Flask UI. No HTML / DOCX / XLSX is
  emitted by M11 itself.
- A Jinja2-ready dict projection produced by a pure helper
  (`render_manipulation_scoring_summary(summary) -> dict`) that the
  M13 templates consume. The dict contains: top-line
  `total_score` with severity banner; per-tier UID counts; per-slack-
  state UID counts; a flat list of per-UID rows sorted by
  `(severity_tier desc, unique_id asc)` with columns `unique_id`,
  `name`, `score`, `severity_tier`, `slack_state`, and a rendered
  rationale string.
- No PDF output is produced directly by M11; PDF export lives in
  the M13/export modules and consumes the same dict projection.

Detailed column ordering, CSS classes, drill-down affordances, and
AI-narrative prompt templates are out of scope for this amendment
and are fixed in the M11 renderer block (M11 Block 4 or later) and
in M13.

**(j) Out of scope for M11.**

M11 does NOT:

- Modify M9's `ComparatorResult`, `TaskDelta`, `RelationshipDelta`,
  or any symbol exported from `app/engine/comparator.py` or
  `app/engine/delta.py`. M9's surface is frozen from M9 forward.
- Modify M10's `DrivingPathCrossVersionResult`,
  `DrivingPathResult`, `DrivingPathEdge`, `NonDrivingPredecessor`,
  `ConstraintDrivenPredecessor`, or `trace_driving_path*` functions.
  §2.20 (AM10) is frozen; the M11 comparator is a new class that
  consumes M10 output read-only.
- Rewrite or relocate the five sub-pattern detectors originally
  scoped in §5 M11 (logic, duration, date, float, critical-path).
  The original M11 scope's detector families are superseded by the
  AM12 constraint-driven-erosion focus; other detector families
  (logic, duration, date, float, critical-path manipulation proper)
  are deferred to a later milestone and NOT built in M11 under this
  amendment. The always-100 bug regression bar from §5 M11 is
  preserved by the AM12 always-zero / clamp-at-100 contract
  (subsection (e)).
- Produce PDF, DOCX, or XLSX reports directly. Export lives in
  M13 / export modules.
- Address relationship-slack field availability on the `Relation`
  model. The M10 Block 0 §2.2 decision stands:
  relationship_slack_minutes is NOT a field on `Relation` and is
  computed at query time via `link_driving_slack_minutes`. Any
  material reopening of that decision is deferred to a future
  milestone — M11 does not touch `app/engine/relations.py` or
  `app/models/relation.py`.
- Introduce multi-version (>2) analysis. Phase 1 supports exactly
  two schedule versions per §1.4; M11 consumes exactly one Period A
  and one Period B `DrivingPathResult`.
- Introduce EVA-layer scoring or cost-side signals. EVA is Phase 3
  per §1.5; the DECM manipulation probes in
  `forensic-manipulation-patterns §10.3` (Tier 3 EVMS probes) are
  noted as authoritative vocabulary but not implemented as
  detectors in M11.
- Re-derive any DCMA 14-Point metric. M11 consumes M5–M7
  `MetricResult`s read-only if it needs them at all (and the
  amendment does NOT require any such consumption; the comparator
  operates purely on `DrivingPathResult` inputs).

**(k) Estimated block count.**

M11 is estimated at **6 to 8 blocks total**, inclusive of this
amendment block (Block 1).
AM13 does NOT introduce a new block. The six-block M11 plan
(Blocks 2, 3, 4, 4b, 5, 6) remains intact. AM13 amends the
contract consumed by Blocks 3+.
Expected decomposition:

- **Block 1** (this amendment). Scope / contracts / state machine
  / weights specified. Amendment-only; no implementation code. PR
  opens as DRAFT per CLAUDE.md §7.
- **Block 2.** Create `app/contracts/manipulation_scoring.py` with
  the four public Pydantic models and two StrEnums from subsection
  (c). Create `app/contracts/__init__.py`. Write
  `tests/contracts/test_manipulation_scoring.py` to the
  subsection (g) floor (≥ 18 tests). No engine code yet.
- **Block 3.** Implement
  `app/engine/constraint_driven_cross_version.py` —
  `ConstraintDrivenCrossVersionComparator` and
  `compare_constraint_driven_cross_version`. Wire the status-date
  filter from subsection (f). Write
  `tests/engine/test_constraint_driven_cross_version.py` to the ≥
  22-test floor. Scope extension (AM13): Block 3 additionally
  modifies app/contracts/manipulation_scoring.py to replace the two
  float offset fields on ConstraintDrivenCrossVersionResult with the
  five AM13 datetime/float fields, and correspondingly updates
  tests/contracts/test_manipulation_scoring.py for the new field
  set. This scope extension is explicit: Block 3 is no longer a
  pure engine-file-plus-tests write; it is a contract-modification
  plus engine-file-plus-tests write. All other AM13 constraints on
  Block 3 (file path, class name, function name, public-API
  non-touch, etc.) remain as in AM12.
- **Block 4.** Implement `app/engine/manipulation_scoring.py` —
  state-machine derivation per subsection (d), scoring arithmetic
  per subsection (e), summary aggregation with clamp (caller-side
  per revised subsection (e)). Write engine portion of
  `tests/engine/test_manipulation_scoring.py` to a ≥ 20-test floor
  covering state-machine transitions (8), scoring arithmetic (5),
  per-UID dedup (4), always-zero regression (3).
- **Block 4b.** Implement the dict projection helper
  `render_manipulation_scoring_summary(summary) -> dict` per
  subsection (i). Add the remaining ≥ 6 tests to
  `tests/engine/test_manipulation_scoring.py` covering integration
  (3: skipped_cycle_participants reference propagation, rationale
  composition, summary sort order) and schema invariants (3:
  total_score bound, no minutes/hours fields, name non-empty).
  Combined with Block 4 this meets the ≥ 26-test floor from
  subsection (g).
- **Block 5.** Public-API wiring: update `app/__init__.py`,
  `app/engine/__init__.py`, `app/contracts/__init__.py` per
  subsection (h). Integration test combining M10.1 / M10.2 output
  with M11 scoring end-to-end.
- **Block 6 (pure contingency).** Codex / audit remediation cycle if
  PR-round findings surface. Modeled on the M10.1 / M10.2 two-pass
  pattern (see §2.21 AM11). No planned deliverable — this block is
  reserved for remediation only.

Per CLAUDE.md §4, M11 is flagged as potentially multi-session; AM12
is the first session in that decomposition and produces amendment
text only.

**Authority references (full AM12 amendment).**

`forensic-manipulation-patterns §3.2` (status-date windowing filter);
§4.4 (constraint injection); §4.5 (constraint removal hiding slip);
§9 (cross-version erosion detection); §10 (red-flag aggregation
tiers). `acumen-reference §3.3` (tripwire-not-verdict);
§3.6 (weighting at scorecard assembly);
§5.2 (PreviousActualStart/Finish as cross-version primitive analog).
`driving-slack-and-paths §6` (TotalFloat trend classification
vocabulary); §9 (Period A slack but-for rule); §10 (status-date
filter predicate). BUILD-PLAN §2.7 (UniqueID-only matching);
§2.8 (status-date-aware windowing); §2.9 (Period A slack rule);
§2.13 (mutation-vs-wrap invariant); §2.19 (days-only UX
convention); §2.20 (three-bucket partition, AM10); §2.21 (M10.2
format_days + skipped_cycle_participants, AM11); §6 (forensic-
defensibility criteria). M10.1 implementation:
`app/engine/driving_path_types.py::ConstraintDrivenPredecessor`,
lines 238–329; `app/engine/driving_path.py::
trace_driving_path_cross_version`, lines 460–573 (with the inline
comment at line 516 confirming constraint-driven cross-version
diff is M11 scope). M10.2 implementation:
`DrivingPathResult.skipped_cycle_participants`,
`driving_path_types.py` line 382.

Inferred-source disclosure. Three of the predicates cited above
carry an "inferred — not sourced in SSI or current Lessons Learned
revision" note in their source skills:
driving-slack-and-paths §9 (SKILL.md line 156),
driving-slack-and-paths §10 (SKILL.md line 166), and
forensic-manipulation-patterns §3.2 (§14 inference table of that
skill). AM12 adopts these predicates as operational specifications
for M11 on the authority of the tool's internal cross-skill
reconciliation pass. Any downstream milestone that surfaces a
sourced contradiction must flag it for M11 re-scoring review.

## 2.23 Amendment AM13 — M11 comparative-metric anchor correction (doc-only)

  Date: 2026-04-24
  Type: BUILD-PLAN.md-only amendment (no code, no tests modified in
    this amendment; code and test modifications land in Block 3 per
    §2.22(k) scope extension)
  Preceded by: AM12 (PR #35, commit 03af553)
  Changes:
    Replaces ConstraintDrivenCrossVersionResult.period_a_status_date
    _days_offset and period_b_status_date_days_offset with five new
    fields: period_a_status_date, period_b_status_date,
    period_a_project_start, period_b_project_start,
    period_working_days_elapsed. Updates §2.22 subsections (c), (f),
    (g), and (k) accordingly.
  Motivation:
    M11 comparative-metric output must be reproducible against
    Acumen Fuse and SSI when the same files and metrics are fed into
    either reference tool. Acumen Fuse writes every comparative
    metric as a predicate over (ProjectPreviousTimeNow,
    ProjectTimeNow] with both status dates exposed as named
    variables. Our float-offset contract from AM12 would have
    forced downstream consumers to reconstruct absolute dates for
    parity, which is both error-prone and opaque. Replacing the two
    offsets with five absolute-context fields eliminates this gap.
  Authority:
    - NASA_Metrics_Complete_20260423.aft (Acumen Fuse NASA Quick
      Library export; 5585 Name elements; 941 Formula elements; 389
      formulas reference ProjectTimeNow / ProjectPreviousTimeNow /
      _PeriodStart / _PeriodEnd / BaselineStart / BaselineFinish)
    - Deltek Acumen 8.8 Metric Developer's Guide, Phase Analyzer
      Formulas and Settings (Period Start and Period End Dynamic
      Formula Fields)
    - ssitools.com/helpandsuport/ssianalysishelp/baseline_execution
      _performance.htm (SSI absolute-calendar-bucket pattern)
    - Build-chat session 2026-04-24 (Option C selected; Path 2
      confirmed; Sub-decision Option X confirmed; tool-fidelity
      promise recorded)

---

## 3. Starting State

### 3.1 Greenfield wipe

Phase 1 Milestone 1 begins with a greenfield wipe of existing
application code.

**Preserved (must not be deleted or modified at wipe):**

- `.claude/skills/` — all 8 skill directories, `SKILL.md` files, and
  `.claude/skills/README.md`.
- `.claude/CLAUDE.md` — rewritten later in Milestone 1 (§8), not
  deleted.
- `docs/` — all 22 tagged sources + 2 untagged supplementaries +
  `docs/sources/README.md` + this `docs/BUILD-PLAN.md`.
- `.github/` — workflows and issue templates if any.
- `README.md` at repo root.
- `.gitignore`.
- `LICENSE` if present.
- `archive/` — including the prior-build tree under
  `archive/prior-build-2026-04-16/`. Do not touch.

**Wiped at Milestone 1 start:**

- Any application-code directories at repo root (`app/`, `engine/`,
  `parsers/`, `templates/`, `static/`, or any other name — none are
  present at the head of `main` as of 2026-04-17, so the wipe is a
  no-op today but remains the formal step of record).
- Any `requirements.txt` at repo root (Phase 1 writes a fresh one in
  Milestone 1).
- Any `CLAUDE.md` at repo root (Phase 1 rewrites per §8).

### 3.2 Skills and docs as the immutable knowledge base

The eight skills and tagged-source manifest are the authoritative
domain reference. Phase 1 milestones reference skill sections; they do
not rewrite them. Skill updates happen outside Phase 1.

---

## 4. Milestone Overview

Phase 1 decomposes into **14 milestones**. Dependency principles:
parser before any consumer of parsed data; core data model before
metrics; base DCMA metrics before NASA overlay; driving path after
CPM; manipulation scoring after parser + comparator + driving path;
transparency/drill-down and windowing are cross-cutting constraints;
AI backend late; 500 MB limit ratified in Milestone 1.

| # | Name | Depends on | Skills referenced | Sessions |
|---|------|-----------|-------------------|---------:|
| 1 | Greenfield wipe, scaffolding, 500 MB ratification, CLAUDE.md | — | cui-compliance-constraints | 1 |
| 2 | Core Pydantic data model | 1 | mpp-parsing-com-automation, driving-slack-and-paths | 1 |
| 3 | COM automation parser | 1, 2 | mpp-parsing-com-automation, cui-compliance-constraints | 1 |
| 4 | CPM engine (forward/backward, 4 rel types, 6 constraints, DS) | 2, 3 | driving-slack-and-paths, mpp-parsing-com-automation | 1 |
| 5 | DCMA metrics 1–4 (Logic, Leads, Lags, Relationship Types) | 3, 4 | dcma-14-point-assessment, acumen-reference | 1 |
| 6 | DCMA metrics 5–8, 10 (Hard Constraints, High Float, Negative Float, High Duration, Resources) | 3, 4, 5 | dcma-14-point-assessment, acumen-reference | 1 |
| 7 | DCMA metrics 9, 11–14 (Invalid Dates, Missed Tasks, CPT, CPLI, BEI) | 3, 4, 5 | dcma-14-point-assessment, acumen-reference | 1 |
| 8 | NASA SMH overlay on DCMA | 5, 6, 7 | nasa-schedule-management, nasa-program-project-governance, dcma-14-point-assessment | 1 |
| 9 | Status-date windowing + cross-version comparator | 2, 3 | forensic-manipulation-patterns, driving-slack-and-paths, nasa-schedule-management | 1 |
| 10 | Task-specific driving path analysis | 4, 9 | driving-slack-and-paths | 1 |
| 11 | Manipulation scoring engine | 3, 4, 9, 10 | forensic-manipulation-patterns, dcma-14-point-assessment, acumen-reference | 1–2 |
| 12 | AI backend (Ollama default, Claude API toggle) | 5–8, 11 | cui-compliance-constraints | 1 |
| 13 | Web UI + transparency/drill-down integration | 5–11, 12 | cui-compliance-constraints, all metric skills | 1–2 |
| 14 | Integration tests, regression tests, CI | 1–13 | cui-compliance-constraints | 1 |

Milestones 11 and 13 may require two sessions; any milestone that
exceeds two is a decomposition candidate at plan-review time.

**M11 scope amendment.** The M11 row above is reframed by §2.22
(AM12, 4/23/2026). The amendment narrows M11 to the constraint-
driven cross-version erosion domain built atop the M10.1 three-
bucket partition (§2.20) and the M10.2 `skipped_cycle_participants`
forensic trail (§2.21); the original §5 M11 scope's five sub-
pattern detector families (logic, duration, date, float, critical-
path) are superseded by AM12 and deferred out of M11. The "1–2"
session estimate is superseded by AM12 subsection (k) — 6 to 8
blocks total including the amendment. See §2.22 for the full
restatement of M11 scope, contracts, state machine, and scoring.

---

## 5. Milestone Detail

Each milestone carries eight fields per §5 of the session prompt:
name, dependencies, deliverables, acceptance criteria, test strategy,
file-by-file scope, skills referenced, estimated session count.

### Milestone 1 — Greenfield wipe, scaffolding, 500 MB ratification, CLAUDE.md

**Dependencies.** None.

**Deliverables.** Fresh `app/` skeleton (blueprint-based);
`requirements.txt` pinned for Python 3.13; rewritten
`.claude/CLAUDE.md` (§8); `.gitignore` enforcing CUI rule 2c;
`pytest` config; 500 MB upload limit wired through Flask, nginx stub,
HTML/JS client check, and `RequestEntityTooLarge` handler; regression
test asserting 501 MB upload → 413.

**Acceptance criteria.**

1. `git ls-files` shows no `.mpp`, `.mpx`, `.xer`, `.pmxml`, `.xlsx` (CUI
   extensions), no `analysis_*.pkl`, no `UPLOAD_FOLDER/*`, confirming
   `.gitignore` enforcement of `cui-compliance-constraints §2c`.
2. `python -m app.main` boots Flask on `http://localhost:5000` in under
   3 seconds with no imports of Java, MPXJ, or `requests` at import
   time (`cui-compliance-constraints §2a` enforcement sweep).
3. POSTing a 501 MB file to `/upload` returns HTTP 413 with body
   "File exceeds 500 MB limit."; POSTing a 499 MB file returns HTTP 200
   with the analysis route response.
4. `.claude/CLAUDE.md` contains all eight fields from §8 below, with
   correct branch-naming convention and pointers to
   `docs/BUILD-PLAN.md` and `.claude/skills/`.
5. `pytest` discovers and runs at least one test (the 500 MB regression
   test).

**Test strategy.** pytest fixture uploads a file path with
`MAX_CONTENT_LENGTH + 1` bytes of null-padding against the Flask test
client. Regression test lives in `tests/test_upload_limit.py`. No MPP
data involved.

**File-by-file scope.**

- `app/__init__.py` — Flask app factory; registers blueprints.
- `app/config.py` — `MAX_CONTENT_LENGTH = 500 * 1024 * 1024`; reads
  `SCHEDULEFORENSICS_CLASSIFICATION` env var for CUI mode.
- `app/main.py` — entry point (`python -m app.main`).
- `app/web/__init__.py` — Flask blueprint module marker.
- `app/web/routes.py` — minimal `/` route returning upload form.
- `app/web/templates/base.html` — layout skeleton; CUI-banner
  placeholder (populated by Milestone 12).
- `app/web/templates/index.html` — upload form with client-side size
  check.
- `app/web/static/css/style.css` — empty placeholder.
- `requirements.txt` — Flask, pydantic (v2), pytest, python-docx,
  openpyxl, reportlab; no `mpxj`, no `jpype1`, no `requests` except
  the Anthropic SDK (added Milestone 12).
- `.gitignore` — updated per `cui-compliance-constraints §2c`
  enumeration (schedule extensions + `UPLOAD_FOLDER/` + `analysis_*.pkl`
  + export output dir).
- `.claude/CLAUDE.md` — rewritten per §8.
- `pytest.ini` — minimal config; `testpaths = tests`.
- `tests/__init__.py`.
- `tests/test_upload_limit.py` — 500 MB regression test.
- `nginx.conf.example` — documentation-only stub documenting the
  `client_max_body_size 500M;` directive; not auto-deployed.

**Skills referenced.** `cui-compliance-constraints` (§2a, §2c, §2h for
session-end wipe semantics that the upload route stubs).

**Estimated sessions.** 1.

### Milestone 2 — Core Pydantic data model

**Dependencies.** Milestone 1.

**Deliverables.** Pydantic v2 models. (**AM2, landed 2026-04-18 in
M3 PR:** the as-implemented package name is `app/models/` and the
class names are `Schedule`, `Task`, `Relation`, `Calendar`,
`Resource`, `ResourceAssignment`, `CalendarException`,
`WorkingTime`, plus the enums `ConstraintType`, `RelationType`,
`ResourceType`, `TaskType` and the frozenset constants
`HARD_CONSTRAINTS` / `DATE_BEARING_CONSTRAINTS`. The names
`ScheduleData`/`TaskData`/`Relationship`/`CalendarData`/`ProjectData`
in the original §5 M2 scope are superseded; downstream milestones
read `app.models`.) All use `ConfigDict(extra="forbid")` and
`model_dump(mode="json")`. Durations in minutes; working-day
conversion is provided by the engine layer (see AC2 amendment
below). `Task` fields cover `unique_id`, `task_id`, `name`, `wbs`,
all date fields (start, finish, baseline, actual, early, late),
duration and slack in minutes, `percent_complete`, `is_milestone`,
`is_summary`, `is_critical_from_msp`, `is_loe`, `is_rolling_wave`,
`is_schedule_margin`, `resource_count`, `constraint_type` /
`constraint_date`. Relations are stored on `Schedule.relations`,
not on per-task `predecessors` / `successors` lists.

**Acceptance criteria.**

1. `from app.schema import ScheduleData` imports cleanly with no JVM,
   COM, or network side effects.
2. (**AM3, 2026-04-18 in M3 PR:** minutes → working-days conversion
   is routed to `app/engine/duration.py` — the engine layer — rather
   than to a method on `Task`. Rationale: the CPM engine and the
   DCMA metric layer are the only callers of the conversion; placing
   it on the model would force every unit test of the model to pass
   an `hours_per_day` that models do not otherwise carry. The helper
   will be built in M4 or M5 when the first consumer lands. M2 AC2
   is thereby satisfied by the model carrying `duration_minutes` as
   an integer in minutes per Gotcha 5; the helper's unit test is
   deferred to its birth milestone.)
3. Round-trip JSON: `ScheduleData(…).model_dump(mode="json")` → JSON
   string → `ScheduleData.model_validate_json(...)` yields an equal
   model (pytest parametrized over a synthetic 10-task schedule).
4. `Constraint.type` is an `Enum` including `ASAP`, `ALAP`, `MSO`,
   `MFO`, `SNET`, `SNLT`, `FNET`, `FNLT`, matching COM enum integers
   per `mpp-parsing-com-automation §5` and
   `forensic-manipulation-patterns §4.4`.
5. `Relationship.type` is an `Enum` `FF=0, FS=1, SF=2, SS=3` per the
   COM enum from `mpp-parsing-com-automation §5` — never MPXJ's enum.
6. No model carries a mutable default; all default factories use
   Pydantic `Field(default_factory=...)`.

**Test strategy.** `tests/test_schema.py`: enum correctness,
round-trip serialization, extra-field rejection
(`ConfigDict(extra="forbid")`), working-day conversion arithmetic for
durations and slacks. All synthetic data, per
`cui-compliance-constraints §2e`.

**File-by-file scope.**

- `app/schema/__init__.py` — re-exports.
- `app/schema/enums.py` — `ConstraintType`, `RelationshipType`,
  `TaskFlag`.
- `app/schema/task.py` — `TaskData`.
- `app/schema/relationship.py` — `Relationship`.
- `app/schema/calendar.py` — `CalendarData` with `hours_per_day`,
  `working_days_per_week`, `exceptions`.
- `app/schema/project.py` — `ProjectData` with `status_date`,
  `start`, `finish`, `default_calendar`.
- `app/schema/schedule.py` — `ScheduleData` aggregating the above.
- `app/schema/analysis.py` — `AnalysisResult` envelope consumed by
  later milestones.
- `tests/test_schema.py` — unit tests.

**Skills referenced.** `mpp-parsing-com-automation` (§3.5 units, §5
UniqueID rule, §3.6 status-date sentinels), `driving-slack-and-paths`
(§2 slack vocabulary for naming consistency).

**Estimated sessions.** 1.

### Milestone 3 — COM automation parser

**Dependencies.** Milestones 1, 2.

**Deliverables.** `app/parser/com_reader.py` implementing
`parse_mpp(path: str) -> ScheduleData` via `win32com`. All ten
Appendix D gotchas from `mpp-parsing-com-automation §3` addressed.
Minutes for durations/slack; ISO-normalized `datetime` for dates;
`None` for status-date sentinels. Relationships via
`task.TaskDependencies` keyed by `dep.From.UniqueID` and
`task.UniqueID`. Orphan-sweep, `Quit()`, `CoUninitialize()` in
`finally`. Lazy `win32com` import on first call.

**Acceptance criteria.**

1. On a Windows host with MS Project installed, parsing a synthetic
   10-task `.mpp` returns a `ScheduleData` with 10 tasks, all UniqueIDs
   distinct, all durations in minutes matching what MS Project's UI
   shows in the Duration column converted via
   `minutes / (hours_per_day * 60)`.
2. A task row with a blank name (null in `Tasks` collection) is skipped
   via `if task is None: continue`, per Gotcha 4. Following tasks are
   not lost.
3. `app.DisplayAlerts = False` and `app.Visible = False` are set
   **before** `app.FileOpen`, per Gotcha 2 — test by dispatching a mock
   that records call order.
4. `project.StatusDate` returned as `"NA"`, `datetime(1899, 12, 30)`,
   or `datetime(1984, 1, 1)` is normalized to `None` per Gotcha 6.
5. The parser opens with `ReadOnly=True` and closes with `Save=0`
   (Gotchas 7, 9). The `.mpp` file's `LastSavedDate` is unchanged
   across a parse.
6. Relationship type mapping matches the COM enum (`0=FF, 1=FS, 2=SF,
   3=SS`) per `mpp-parsing-com-automation §5` — never MPXJ's.
7. Validation harness `scripts/validate_against_msp.py` exists and
   documents the §4 field-by-field comparison workflow (local-only; not
   in CI because real `.mpp` files are CUI).
8. Parser emits structured log events with task counts, parse
   duration, file path, and UUID — **never** task names, WBS labels,
   or resource names (`cui-compliance-constraints §2d`).

**Test strategy.** Unit tests monkey-patch `win32com.client.Dispatch`
with a `FakeMSProject` object exposing the COM surface. Integration
tests skipped on non-Windows CI via `pytest.mark.skipif`. Synthetic
`FakeMSProject` has configurable tasks, relationships, and status-date
sentinels to exercise every Gotcha path. No real `.mpp` fixtures.

**File-by-file scope.**

- `app/parser/__init__.py` — re-exports `parse_mpp`.
- `app/parser/com_reader.py` — COM automation implementation.
- `app/parser/status_date.py` — sentinel handler from Gotcha 6.
- `app/parser/duration.py` — minutes → working days converter.
- `app/parser/relationships.py` — `TaskDependencies` enumerator.
- `app/parser/zombie_cleanup.py` — `taskkill /F /IM MSPROJECT.EXE`
  wrapper (Gotcha 8).
- `scripts/validate_against_msp.py` — local-only MSP-UI diff harness.
- `tests/test_parser_gotchas.py` — one test per Gotcha (1–10).
- `tests/test_parser_status_date.py` — sentinel handling matrix.
- `tests/fakes/fake_msproject.py` — synthetic COM double.

**Skills referenced.** `mpp-parsing-com-automation` (§§1, 2, 3, 4, 5,
6), `cui-compliance-constraints` (§2a, §2d, §2e).

**Estimated sessions.** 1.

### Milestone 4 — CPM engine

**Dependencies.** Milestones 2, 3.

**Deliverables.** `app/engine/cpm.py` with forward/backward pass,
total float, free float, and driving slack to a nominated Focus Point.
All four relationship types (FS/SS/FF/SF) with lead/lag; all six
constraint types (SNET/SNLT/FNET/FNLT/MSO/MFO) per
`driving-slack-and-paths §4`. DS formulas from §3:

- FS: `DS = ES(succ) − EF(pred) − lag`
- SS: `DS = ES(succ) − ES(pred) − lag`
- FF: `DS = EF(succ) − EF(pred) − lag`
- SF: `DS = EF(succ) − ES(pred) − lag`

Cycles are lenient — stuck UIDs in `CPMResult.cycles_detected`;
non-cyclic subgraph gets best-effort numbers. Immutable inputs —
`model_copy(update=...)` instead of mutation.

**Acceptance criteria.**

1. On a synthetic 20-task schedule with a known critical path, the
   engine's critical-path output matches MS Project's own `Critical`
   flag task-for-task (`driving-slack-and-paths §4` MSP-validation
   requirement). If they disagree, the test fails.
2. Driving slack per relationship type returns the SSI worked-example
   values from `driving-slack-and-paths §2.4`: Pred 2 (FS → Pred 3,
   lag 0) DS = 2; Pred 1 (SS → Pred 2, lag 0) DS = 4.
3. All six constraint types are exercised by at least one unit test
   each; a task with an MSO constraint has `ES = MSO_date` regardless
   of predecessor finishes.
4. Leads (negative lag) produce the correct sign in DS formulas; a
   lost-sign defect fails the dedicated regression test.
5. A schedule with a self-referential cycle does not crash; the cycle
   UIDs are listed in `cycles_detected` and non-cyclic tasks receive
   float values.
6. No mutation of input `ScheduleData` — `model_copy` is used for the
   +600-day probe needed by DCMA CPT (Milestone 7).

**Test strategy.** Unit tests per relationship type, per constraint
type, per lead/lag sign, per cycle case. Parametrized SSI worked
example verifies DS values slide-for-slide. Synthetic data only.

**File-by-file scope.**

- `app/engine/__init__.py`.
- `app/engine/cpm.py` — forward/backward pass and DS calculator.
- `app/engine/driving_slack.py` — per-relationship formulas.
- `app/engine/constraints.py` — constraint application logic.
- `app/engine/result.py` — `CPMResult` Pydantic model.
- `tests/test_cpm_forward_pass.py`.
- `tests/test_cpm_driving_slack.py` — SSI worked example verification.
- `tests/test_cpm_constraints.py` — one test per constraint type.
- `tests/test_cpm_cycles.py` — cycle-tolerance regression.

**Skills referenced.** `driving-slack-and-paths` (§§2, 3, 4, 8),
`mpp-parsing-com-automation` (§3.5 units).

**Estimated sessions.** 1.

### Milestone 5 — DCMA metrics 1–4 (Logic, Leads, Lags, Relationship Types)

**Dependencies.** Milestones 3, 4.

**Deliverables.** Per-metric modules under `app/metrics/` (**AM4,
shipped 2026-04-18 in the M5 PR:** the as-implemented package is
`app/metrics/`, not `app/engine/dcma/` as originally scoped here.
Rationale: the engine layer (`app/engine/`) owns CPM forward /
backward pass and duration arithmetic; the metrics layer
(`app/metrics/`) is its sibling consumer. The split keeps the
engine free of DCMA-specific threshold logic and lets the
manipulation engine (M11) consume metric results without touching
the CPM surface. Downstream milestones read `app.metrics`.) Each
function takes `Schedule`, returns `MetricResult` with `metric_id`,
`numerator`, `denominator`, `computed_value`, `threshold`,
`severity`, and `offenders: tuple[Offender, ...]` (each carrying
`unique_id`, `name`, and the causing field value). Per
`dcma-14-point-assessment §4`:

- Metric 1a (Missing Logic): incomplete tasks with zero predecessors or
  zero successors, excluding project start/finish milestones; threshold
  ≤5%. **Shipped in M5.**
- Metric 1b (Dangling): tasks with SS-only predecessor (dangling
  finish) or FF-only successor (dangling start); threshold ≤5%.
  **Deferred post-M5** (see M5 audit Minor 2 and §9 Out-of-Scope
  ledger entry). The M5 PR shipped "1a, 2, 3, 4"; 1b requires
  per-relation drivership that the engine will expose once M10
  driving-path plumbing lands.
- Metric 2 (Leads): relationships with negative lag / total
  relationships; threshold 0%.
- Metric 3 (Lags): relationships with positive lag / total
  relationships; threshold ≤5% with 09NOV09 5-day MSP/OpenPlan
  carve-out (P6 does not receive the carve-out — not applicable for
  MPP input, but carve-out handling documented for later P6 import).
  **Carve-out deferred** (see §9 ledger) to post-Phase-1 P6/XER
  ingestion work; Phase 1 ships the MPP-only numerator.
- Metric 4 (Relationship Types): FS / total; threshold ≥90%.

**Acceptance criteria.**

1. DCMA Metric 1a (Missing Logic) returns a per-task list of missing
   predecessor/successor flags, including `unique_id` and `name` for
   each flagged task, computed per `dcma-14-point-assessment §4.1`
   methodology and cross-referenced against DECM row `06A204b`
   threshold from `acumen-reference §4.4` (threshold label match).
2. Metric 2 returns `pass_flag = False` if any relationship has
   negative lag; the flagged-task list names predecessor + successor
   UniqueIDs.
3. Metric 3 applies the MSP 5-day carve-out: a 3-day lag does not
   contribute to the numerator; a 6-day lag does.
4. Metric 4 uses the 09NOV09 relationship-counting rule (relationships,
   not activities carrying relationships) per
   `dcma-14-point-assessment §3`.
5. Pre-check denominators — Total Tasks excludes summary / LOE /
   milestones / 100%-complete per `dcma-14-point-assessment §3`.
6. Every `FlaggedTask` record is rendered in the drill-down UI
   (Milestone 13) — no metric returns only an aggregate percentage.

**Test strategy.** Synthetic schedules hand-crafted to breach each
threshold exactly. `tests/test_dcma_metric_1a.py` through
`tests/test_dcma_metric_4.py`. Parametrized tests verify threshold
boundary behavior (4.9% passes, 5.1% fails).

**File-by-file scope** (as-shipped in the M5 PR, branch
`claude/milestone-5-dcma-metrics-1-4-2026-04-18`):

- `app/metrics/__init__.py` — public API re-exports.
- `app/metrics/base.py` — `MetricResult`, `Offender`,
  `ThresholdConfig`, `Severity`, `BaseMetric`.
- `app/metrics/options.py` — `MetricOptions` with per-metric
  threshold overrides; `__post_init__` range validation.
- `app/metrics/exceptions.py` — `MetricError`,
  `MissingCPMResultError`, `InvalidThresholdError`.
- `app/metrics/logic.py` — Metric 1a. (1b deferred — see
  deliverables.)
- `app/metrics/leads.py` — Metric 2.
- `app/metrics/lags.py` — Metric 3 (carve-out deferred).
- `app/metrics/relationship_types.py` — Metric 4.
- `tests/test_metrics_base.py`, `tests/test_metrics_options.py`,
  `tests/test_metrics_exceptions.py`, `tests/test_metrics_logic.py`,
  `tests/test_metrics_leads.py`, `tests/test_metrics_lags.py`,
  `tests/test_metrics_relationship_types.py`, plus
  `tests/test_metrics_integration.py` covering the four-metric
  integration fixture.
- `tests/fixtures/metric_schedules.py` — synthetic `Schedule`
  builders for the M5 metric tests.

**Skills referenced.** `dcma-14-point-assessment` (§§3, 4.1, 4.2, 4.3,
4.4), `acumen-reference` (§4.4 DECM cross-reference).

**Estimated sessions.** 1.

### Milestone 6 — DCMA metrics 5–8, 10 (Hard Constraints, High Float, Negative Float, High Duration, Resources)

(Metric 10 groups with M6 — simple ratio, no CPM or date-comparison
dependency; Metric 9 groups with M7's date-sensitive metrics.)

**Dependencies.** Milestones 3, 4, 5.

**Deliverables.** Per-metric modules under `app/metrics/` (per
AM4 / §2.14 — the metrics package is `app/metrics/`, not
`app/engine/dcma/`; confirmed in the M6 PR shipped 2026-04-19) per
`dcma-14-point-assessment §§4.5–4.8, §4.10`:

- Metric 5 (Hard Constraints): tasks with MSO/MFO/SNLT/FNLT / Total
  Tasks; threshold ≤5% (09NOV09 four-constraint list).
- Metric 6 (High Float): incomplete tasks with `total_slack > 44 WD` /
  Incomplete Tasks; threshold ≤5%.
- Metric 7 (Negative Float): tasks with `total_slack < 0` / Total
  Tasks; threshold 0%.
- Metric 8 (High Duration): incomplete tasks with
  `remaining_duration > 44 WD` / Incomplete Tasks; threshold ≤5%;
  rolling-wave-tagged tasks exempt.
- Metric 10 (Resources): incomplete tasks with `resource_count == 0` /
  Incomplete Tasks; ratio only, no threshold.

**Acceptance criteria.**

1. Metric 5 uses only the four 09NOV09 hard constraints (MSO, MFO,
   SNLT, FNLT); ALAP and SNET / FNET are not counted (ALAP has its
   own detection path in Milestone 11, per
   `forensic-manipulation-patterns §5.3`).
2. Metric 6 threshold boundary: a task with `total_slack = 44.0 WD`
   does not flag; `44.01 WD` does.
3. Metric 7 raises a flag for **any** task with negative float — the
   0% threshold is absolute.
4. Metric 8 exemption: a task with `is_rolling_wave = True` and
   `remaining_duration = 60 WD` is excluded from the numerator; the
   same task with `is_rolling_wave = False` is included.
5. Metric 10 returns the ratio without a pass/fail flag —
   `MetricResult.pass_flag = None` by design; UI renders the ratio
   with interpretive context.
6. All flagged tasks carry `unique_id` and `name`.

**Test strategy.** One synthetic-schedule file per metric exercising
the numerator, denominator, and threshold boundary. Parametrized
rolling-wave exemption. Tests under `tests/test_dcma_metric_5.py`
through `tests/test_dcma_metric_10.py` (9 is covered in Milestone 7).

**File-by-file scope** (as-shipped in the M6 PR, branch
`claude/milestone-6-dcma-metrics-5-8-10-2026-04-19`):

- `app/metrics/hard_constraints.py` — Metric 5.
- `app/metrics/high_float.py` — Metric 6 (consumes CPMResult).
- `app/metrics/negative_float.py` — Metric 7 (consumes CPMResult).
- `app/metrics/high_duration.py` — Metric 8.
- `app/metrics/resources.py` — Metric 10 (indicator-only per §2.15).
- `app/metrics/options.py` — extended with M6 threshold fields.
- `app/metrics/__init__.py` — extended with M6 exports.
- `app/metrics/README.md` — threshold table + grouping rationale.
- `tests/test_metrics_hard_constraints.py`,
  `tests/test_metrics_high_float.py`,
  `tests/test_metrics_negative_float.py`,
  `tests/test_metrics_high_duration.py`,
  `tests/test_metrics_resources.py`.
- `tests/_utils.py` — `cpm_result_snapshot` mutation-invariance
  helper.
- `tests/fixtures/metric_schedules.py` — extended with M6 builders
  and the `m6_integration_schedule` nine-metric fixture.
- `tests/test_metrics_integration.py` — extended to cover all nine
  M5 + M6 metrics.

**Skills referenced.** `dcma-14-point-assessment` (§§4.5–4.8, §4.10),
`acumen-reference` (§4.4 DECM row cross-reference for 06A209a,
06A211a).

**Estimated sessions.** 1.

### Milestone 7 — DCMA metrics 9, 11–14 (Invalid Dates, Missed Tasks, CPT, CPLI, BEI)

**Dependencies.** Milestones 3, 4, 5.

**Deliverables.** Per-metric modules under `app/metrics/` (per
§2.14 — the metrics package is `app/metrics/`, not
`app/engine/dcma/`) per `dcma-14-point-assessment §§4.9,
4.11–4.14`:

- Metric 9 (Invalid Dates): a pure date-validity validator. Flags
  (a) actuals after `status_date`, (b) forecasts before
  `status_date` on incomplete work, and (c) `actual_finish <
  actual_start` (temporal inversion). Threshold 0%. No baseline
  dependency, no CPMResult dependency.
- Metric 11 (Missed Tasks): incomplete tasks with `baseline_finish
  ≤ status_date` / tasks with `baseline_finish ≤ status_date`;
  threshold ≤5%. Baseline-required — no-baseline schedules
  return an indicator-only result per §2.15. Rolling-wave and LOE
  tasks exempt from the numerator; denominator unchanged.
- Metric 12 (Critical Path Test): structural verification of an
  unbroken zero-total-slack path from project start to project
  finish via CPMResult read-only traversal. Binary pass / fail
  encoded on `MetricResult` with `threshold.direction =
  "structural-pass-fail"`. No baseline dependency. Consumes
  CPMResult read-only per §2.17.
- Metric 13 (Critical Path Length Index): `CPLI = (baseline_cp_length
  + total_slip) / baseline_cp_length`; threshold ≥ 0.95.
  Baseline-required and CPMResult-required.
- Metric 14 (Baseline Execution Index): `BEI = tasks_completed /
  tasks_baseline_due_by_status_date`; threshold ≥ 0.95;
  cumulative-hit definition per Edwards (`§5.1`). Baseline-required;
  zero-denominator window returns indicator-only.
- Baseline comparison plumbing: `app/metrics/baseline.py` providing
  `has_baseline`, `baseline_slip_minutes`,
  `tasks_with_baseline_finish_by`,
  `baseline_critical_path_length_minutes`, and
  `has_baseline_coverage` helpers. Baseline lives on
  `Task.baseline_start / baseline_finish /
  baseline_duration_minutes` (per M2 data model); baseline is **not**
  a separate `Schedule` object. No-baseline cases are handled
  gracefully (helpers return `None` / `False`; metrics return
  indicator-only MetricResult per §2.15).

**M7 scope notes:**

- `CPMOptions.auto_synthesize_calendar` default-flip (True → False)
  considered during M4 / M5 / M6 and **deferred** to a post-M14
  cleanup session: the existing M6 fixtures do not universally
  carry an explicit calendar, so flipping the default would force a
  wide fixture sweep. Captured in §9 ledger.
- Metric 12 CPT is rebuilt around a structural read of CPMResult's
  zero-slack set rather than the 600-WD `model_copy` probe
  originally sketched in this milestone. Rationale: the M4 engine
  already emits `critical_path_uids` and per-task
  `total_slack_minutes`; a structural traversal produces the same
  pass / fail verdict with fewer moving parts and satisfies
  §6 AC bar #3 (forensically defensible evidence) without the
  mutation risk of a +600-WD probe. The `model_copy` probe remains
  available as a Phase 2 cross-check; it is not the Phase 1 CPT
  implementation.

**Acceptance criteria.**

1. Metric 12 rebuilds the schedule via `model_copy(update=...)` — no
   mutation of the original `ScheduleData` (verified by hashing the
   input's JSON before and after).
2. Metric 13 worked example from `dcma-14-point-assessment §5.2`: CP
   length 250 WD, TF = –10 WD → CPLI = 0.96 (pass); same CP length,
   TF = –20 WD → 0.92 (fail).
3. Metric 14 worked example from `dcma-14-point-assessment §5.1`:
   200-task schedule, 80 baseline-due by status date, 68 hit → BEI =
   0.85 (fail). Early-finishing tasks with later baselines are excluded
   from the numerator.
4. Metric 9a flags any forecast date before `status_date` regardless
   of whether the task is critical; Metric 9b flags any actual after
   `status_date`.
5. Every flagged task carries `unique_id` and `name`; CPT additionally
   reports the selected critical task's UniqueID and the actual
   project-finish shift observed.

**Test strategy.** Synthetic schedules crafted to hit each boundary.
CPT test verifies no-mutation invariant via `hash(input.model_dump_json())`
before and after. BEI and CPLI worked examples are pytest parametrized
against the §5 values in `dcma-14-point-assessment`.

**File-by-file scope** (M7 build session; branch
`claude/milestone-7-dcma-metrics-9-11-12-13-14-2026-04-19`):

- `app/metrics/baseline.py` — baseline comparison plumbing
  (`has_baseline`, `baseline_slip_minutes`,
  `tasks_with_baseline_finish_by`,
  `baseline_critical_path_length_minutes`,
  `has_baseline_coverage`).
- `app/metrics/invalid_dates.py` — Metric 9 (all three invalid-date
  kinds as one module per §2.14 single-result contract).
- `app/metrics/missed_tasks.py` — Metric 11.
- `app/metrics/critical_path_test.py` — Metric 12 (structural).
- `app/metrics/critical_path_length_index.py` — Metric 13.
- `app/metrics/baseline_execution_index.py` — Metric 14.
- `app/metrics/options.py` — extended with `missed_tasks_threshold_pct`,
  `cpli_threshold_value`, `bei_threshold_value` (defaults per
  `dcma-14-point-assessment §§4.11, 4.13, 4.14`).
- `app/metrics/__init__.py` — extended with M7 exports.
- `app/metrics/README.md` — extended with M7 rows in the threshold
  and CPM-consumer tables; mixed-shape metrics grouping rationale;
  baseline-plumbing contract; no-baseline graceful behavior;
  updated deferral ledger.
- `tests/test_metrics_baseline.py` — baseline-plumbing unit tests.
- `tests/test_metrics_invalid_dates.py`.
- `tests/test_metrics_missed_tasks.py`.
- `tests/test_metrics_critical_path_test.py`.
- `tests/test_metrics_critical_path_length_index.py`.
- `tests/test_metrics_baseline_execution_index.py`.
- `tests/fixtures/metric_schedules.py` — extended (chunked-heredoc
  appends) with per-metric fixtures and an `m7_integration_schedule`
  fourteen-metric builder.
- `tests/test_metrics_integration.py` — extended to cover all 14
  M5 + M6 + M7 metrics.

**Skills referenced.** `dcma-14-point-assessment` (§§4.9, 4.11–4.14,
§5), `acumen-reference` (§4.4 DECM cross-reference).

**Estimated sessions.** 1.

### Milestone 8 — NASA SMH overlay

**Dependencies.** Milestones 5, 6, 7.

**Deliverables.** (**AM5, landed 2026-04-20 in the M8 PR:** the
overlay is packaged under `app/overlay/` rather than under
`app/engine/`. Rationale: `app/engine/` is the pure-computation
layer (CPM forward/backward, calendar math, constraint application,
topology, duration helpers) and `app/metrics/` is the frozen-contract
DCMA layer (§2.14). The NASA overlay is neither pure CPM computation
nor a new DCMA metric — it is a governance-triage layer that reads
existing `MetricResult`s and `Task` flags read-only and emits a
sibling `OverlayResult` with adjusted denominators and informational
notes. Placing it at `app/overlay/` preserves the engine-never-
mutates and metrics-never-mutate invariants in §2.13 / §2.14 and
gives the M11 manipulation engine a stable, single-package import
surface for consuming governance-triage notes. The class-name
`TaskData` in the original AC text is superseded by `Task` per AM2
— the M8 overlay reads `Task.is_schedule_margin` and
`Task.is_rolling_wave`, both present since M2.) The overlay layers
NASA Schedule Management Handbook rules on top of the frozen-contract
DCMA metrics per `nasa-schedule-management §6`:

- High-Float denominator excludes tasks flagged as schedule margin
  (`Task.is_schedule_margin = True`) per
  `nasa-schedule-management §3`.
- Governance-milestone constraint triage: tasks with MSO/FNLT/MFO/SNLT
  whose name matches a governance-milestone pattern (KDP, SRR, MDR,
  PDR, CDR, SIR, ORR, MCR, FRR) produce a triage note that identifies
  the constraint as governance-driven per
  `nasa-program-project-governance §§4, 5`. M11's manipulation engine
  is the downstream consumer and is responsible for suppressing the
  hard-constraint manipulation raise on flagged tasks; M8 is strictly
  emit-side for the triage note.
- Rolling-wave window cross-check: tasks exempted from Metric 8 via
  `is_rolling_wave` are additionally validated against the 6–12 month
  window per `nasa-schedule-management §4`; a near-term rolling-wave
  tag emits an informational note.

**Acceptance criteria.**

1. A schedule with 10 incomplete tasks, 3 of which carry
   `is_schedule_margin = True` and have `total_slack > 44 WD`, reports
   Metric 6 overlay-adjusted denominator = 7 (not 10). The base
   Metric 6 `MetricResult.denominator` is unchanged; the adjusted
   denominator lives on the `OverlayResult` sibling.
2. A task named "CDR Review" with an MFO constraint produces a
   governance-triage note on the `OverlayResult`. The note is
   emitted in a consumer-agnostic structured format (named note kind,
   `unique_id`, task name, detail string) that M11's manipulation
   engine will later read.
3. The overlay runs after base DCMA metrics and reads their
   `MetricResult`s read-only; it does not mutate the original result.
   Adjusted numerator / denominator / ratio / severity live on the
   `OverlayResult`. The original `MetricResult.offenders` list is
   preserved; transparency per §6 is preserved.
4. Governance-milestone pattern list is externalized to
   `app/overlay/nasa_milestones.py` so analysts can edit without
   touching overlay logic or metric code.

**Test strategy.** Synthetic schedule with tagged schedule-margin
tasks, a named CDR milestone, and an out-of-window rolling-wave tag.
Tests verify denominator exclusion, triage-note emission, rolling-
wave window cross-check, and mutation-invariance of the upstream
`MetricResult`s via the `tests/_utils.py` snapshot pattern (adapted
for `MetricResult` in this milestone).

**File-by-file scope.**

- `app/overlay/__init__.py` — re-exports the overlay public API.
- `app/overlay/nasa_overlay.py` — overlay orchestrator; frozen
  `OverlayResult`, `OverlayNote`, `OverlayNoteKind`,
  `ExclusionRecord` contract types; rule functions
  `apply_schedule_margin_exclusion`,
  `apply_governance_milestone_triage`,
  `apply_rolling_wave_window_check`.
- `app/overlay/nasa_milestones.py` — governance-milestone name-pattern
  taxonomy (`GOVERNANCE_PATTERNS`, `is_governance_milestone`,
  `match_governance_pattern`).
- `app/overlay/exceptions.py` — `OverlayError`,
  `MissingMetricResultError`.
- `app/overlay/README.md` — rule-by-rule documentation, skill
  citations, and M11-consumer contract.
- `tests/test_overlay_nasa.py` — rule tests.
- `tests/test_overlay_milestones.py` — pattern tests.

**Skills referenced.** `nasa-schedule-management` (§§3, 4, 6),
`nasa-program-project-governance` (§§4, 5), `dcma-14-point-assessment`
(§4.5, §4.6, §4.8, §8).

**Estimated sessions.** 1.

### Milestone 9 — Status-date windowing + cross-version comparator

**Dependencies.** Milestones 2, 3.

**Deliverables.** (**AM6, 2026-04-20 M9 Block 0 reconciliation:** the
M2 AM2 rename — the as-implemented container class is `Schedule`,
not `ScheduleData` — propagates into the M9 comparator surface. The
comparator matches two `Schedule` instances by UniqueID and emits
`ComparatorResult` with per-UID `TaskDelta`s and per-relationship
`RelationshipDelta`s. Field names on the `Task` model are flat
(`constraint_type`, `total_slack_minutes`, `free_slack_minutes`,
`duration_minutes`, etc.) per M2; the original §5 M9 AC#3 text
`constraint.type` / `total_slack` / `free_slack` is superseded by the
flat-field names below.) `app/engine/comparator.py` matches two
`Schedule` instances by UniqueID and emits `ComparatorResult` with
per-UID field deltas and per-relationship deltas. Filter per
`forensic-manipulation-patterns §3.2` and
`driving-slack-and-paths §10`: a matched task whose Period A `finish`
is less than or equal to Period B `status_date` is tagged
`is_legitimate_actual = True`. Filter tags rather than deletes; UI
separates "legitimate" from "candidate manipulation."

**Relationship-delta scope decision (Block 0 §2.3, Option A).**
`RelationshipDelta` is a separate frozen Pydantic v2 model added to
`app/engine/delta.py`. It carries predecessor/successor UniqueIDs,
a `RelationshipPresence` (MATCHED / ADDED_IN_B / DELETED_FROM_A),
and a tuple of `FieldDelta` rows for `relation_type` and
`lag_minutes` changes on matched pairs. Rationale: M10 (driving
path) will consume `RelationshipDelta` independently of
`TaskDelta`, and M11 (manipulation) will score both as distinct
Tier-2 patterns. Folding relationship changes into `TaskDelta`
would entangle the two consumer paths and break the frozen-
contract pattern.

**Acceptance criteria.**

1. Given two `Schedule` instances with 50 tasks each, 40 matching by
   UniqueID, 5 added in B, 5 deleted from A, the comparator emits
   40 matched `TaskDelta`s (`TaskPresence.MATCHED`) + 5
   `ADDED_IN_B` + 5 `DELETED_FROM_A`. Total records: 50.
2. A matched task whose Period A `finish = 2026-03-15` and Period B
   `status_date = 2026-03-31` is tagged `is_legitimate_actual = True`
   regardless of Period B field changes (the skill-anchored
   predicate: Period A finish ≤ Period B status date; see
   `forensic-manipulation-patterns §3.2` and
   `driving-slack-and-paths §10`).
3. Per-field deltas on matched tasks include (all verified
   present on `Task` as of Block 0): `total_slack_minutes`,
   `free_slack_minutes`, `baseline_finish`, forecast `finish`,
   `constraint_type` (flat enum field), `duration_minutes`,
   `actual_start`, `actual_finish`. Relationship-incident changes
   are emitted as `RelationshipDelta` rows, not as fields on
   `TaskDelta`.
4. UniqueID match only — `Task.task_id` and `Task.name` are never
   consulted (enforce via regression test that renames every task in
   Period B and verifies the matched-delta count is unchanged).
5. Timedelta vs. minutes convention. `FieldDelta` records
   `period_a_value` and `period_b_value` verbatim: datetime values
   for date fields (consumers derive the `timedelta`), integer
   minutes for duration / slack fields (per §2.16 minutes-as-
   canonical-internal-unit). Calendar-day conversion for date slips
   happens at the presentation layer; no `timedelta` is pre-computed
   on `FieldDelta`.
6. Status-date windowing. Either status date `None` ⇒
   `is_legitimate_actual = False` with an explanatory absence. Tasks
   with `TaskPresence.ADDED_IN_B` or `DELETED_FROM_A` are never
   tagged legitimate (structure change, not status-driven
   progression).

**Test strategy.** Paired synthetic schedules with known differences
(added task, deleted task, renamed task, legitimate actuals within
window, suspected manipulation outside window). One test module per
production module, following the M4–M8 `tests/test_engine_*.py`
convention: `tests/test_engine_comparator.py`,
`tests/test_engine_windowing.py`, `tests/test_engine_delta.py`.
Integration test in `tests/test_engine_comparator_integration.py`.
(Original §5 M9 test filenames `tests/test_comparator.py` /
`tests/test_windowing_filter.py` are superseded.)

**File-by-file scope.**

- `app/engine/delta.py` — `FieldDelta`, `TaskDelta`,
  `RelationshipDelta`, `ComparatorResult` Pydantic v2 models plus
  the `DeltaType`, `TaskPresence`, `RelationshipPresence`
  `StrEnum`s.
- `app/engine/windowing.py` — skill-anchored status-date predicate
  (`is_legitimate_actual`).
- `app/engine/comparator.py` — UniqueID-matched diff (task-field
  pass + relationship pass).
- `app/engine/__init__.py` — public-API exports for the above.
- `app/engine/README.md` — extended with the comparator section.
- `tests/test_engine_delta.py` — frozen-contract tests on the
  delta models and enums.
- `tests/test_engine_windowing.py` — predicate edge-case table.
- `tests/test_engine_comparator.py` — task-field diff + relationship
  diff + matching + legitimate-actual tagging.
- `tests/test_engine_comparator_integration.py` — paired 30-task
  integration scenario.

**Skills referenced.** `forensic-manipulation-patterns` (§3.2),
`driving-slack-and-paths` (§10), `nasa-schedule-management` (§8),
`mpp-parsing-com-automation` (§5).

**Estimated sessions.** 1.

### Milestone 10 — Task-specific driving path analysis

**Dependencies.** Milestones 4, 9.

**Deliverables.** (**AM8, 2026-04-22 M10 Block 7 remediation:** AM8
supersedes AM7's multi-branch tie-break decision. The "lowest-UID
tie-break" rule is **withdrawn**. Authority is `driving-slack-and-
paths §4` verbatim — "No path is dropped." — and §5 verbatim —
"Walking every relationship-slack-zero link backward … walks
recursively until every driving predecessor is exhausted." AM7
cited §7 of the same skill as authority for the tie-break; §7 is
about UniqueID cross-version matching and does not address multi-
branch walk. The AM7 §7 citation is retracted (finding F2 in the
three-session Block 7 audit cycle, 2026-04-21). The new contract
shape is an adjacency map (nodes keyed by UID + edges list + non-
driving-predecessor list) rather than the AM7 chain + parallel-
links pair. Implementation lands on branch
`claude/milestone-10-block-7-remediation-2026-04-22` atop the
existing M10 branch at tip `7beb4fa`; PR #31 remains the PR of
record.) (**AM7, 2026-04-20 M10 Block 0 reconciliation:** the
contract / reuse / filename decisions below supersede the original
§5 M10 scope text.) `app/engine/driving_path.py` with
`trace_driving_path(schedule, focus_spec, cpm_result) ->
DrivingPathResult` and `trace_driving_path_cross_version(...)
-> DrivingPathCrossVersionResult`. Backward walk along zero-
relationship-slack edges per `driving-slack-and-paths §5`. Emits
ordered chain + per-link relationship-slack table + non-driving
predecessor secondary list. Cross-version mode reports driving-
predecessor added/removed/retained from Period A to B (matched by
UniqueID per §2.7); Period A slack is the sole but-for reference
per `driving-slack-and-paths §9`.

**Block 0 reconciliation decisions.**

- **SSI skill coverage (Block 0 §2.1).** The skill explicitly covers
  the Y → X → Predecessor 3 → Focus Point four-node chain (§2 final
  paragraph / SSI slide 22) with FS links and zero relationship
  slack. The test fixture reconstructs this example from first
  principles (zero-lag FS means predecessor EF = successor ES, so
  working-minute gap = 0 on every link); per-tier DS values emerge
  from the CPM forward/backward pass and are asserted in the
  fixture test rather than taken verbatim from the skill.

- **Relationship-slack source (Block 0 §2.2).** `Relation` does not
  carry a `relationship_slack_minutes` field and will not. M10
  reuses `app.engine.relations.link_driving_slack_minutes` (M4) to
  compute per-link slack at query time from `CPMResult`
  early-start / early-finish + the relation's `lag_minutes`. This
  is the same path the M4 `driving_slack_to_focus` helper already
  uses.

- **M4 helper reuse (Block 0 §2.3).** The existing
  `app.engine.paths.driving_slack_to_focus` helper returns a
  `{unique_id: driving_slack_minutes}` map — useful as a CPM-level
  primitive but insufficient for M10's ordered-chain + per-link
  output. M10 selects **Option C**: a fresh backward-walk
  implementation in `app/engine/driving_path.py` that reuses the
  `link_driving_slack_minutes` primitive (M4's per-link slack
  calculator) but produces the ordered chain + parallel link list
  + non-driving-predecessor list that M11 and the UI consume.
  `driving_slack_to_focus` remains untouched as a lower-level
  primitive.

- **Cross-version comparator reuse (Block 0 §2.4).** M10 selects
  **Option B**: lightweight inline UniqueID matching on chain UID
  sets only. The M9 comparator emits full task-level and
  relationship-level deltas for the entire schedule, which is
  heavier than M10 needs — driving-path cross-version reporting is
  scoped to predecessor-chain churn, not full-schedule diff. M10
  calls `trace_driving_path` twice (once per period) and computes
  `A_uids − B_uids`, `B_uids − A_uids`, `A_uids ∩ B_uids` directly.

- **Result contract (Block 0 §2.5).** Frozen Pydantic v2 models —
  `DrivingPathNode`, `DrivingPathLink`, `NonDrivingPredecessor`,
  `DrivingPathResult`, `DrivingPathCrossVersionResult` — landing in
  `app/engine/driving_path_types.py` so the trace module stays
  focused on logic. `FocusPointAnchor` is a `StrEnum` with
  `PROJECT_FINISH` and `PROJECT_START`. Chain-link length invariant
  (`len(links) == max(0, len(chain) − 1)`) is enforced by a
  Pydantic `model_validator`.

- **Test filename alignment (Block 0 §2.7).** Tests follow the
  M4–M9 `tests/test_engine_*.py` convention:
  `tests/test_engine_driving_path_types.py`,
  `tests/test_engine_focus_point.py`,
  `tests/test_engine_driving_path.py`,
  `tests/test_engine_driving_path_ssi_example.py`,
  `tests/test_engine_driving_path_cross_version.py`,
  `tests/test_engine_driving_path_integration.py`. The original
  §5 M10 filenames `tests/test_driving_path_ssi_example.py` /
  `tests/test_driving_path_cross_version.py` are superseded.

- **`cpm_result` handling.** `trace_driving_path` requires a
  non-`None` `CPMResult` — the engine is the sole producer per
  §2.17; the trace module is a read-only consumer. Passing `None`
  raises `DrivingPathError` with an explanatory message.

- **Multi-driving-predecessor handling (AM8, 2026-04-22).** When a
  task has two or more driving predecessors (relationship slack = 0
  on every incoming link), the walk follows **every** zero-slack
  incoming edge recursively per `driving-slack-and-paths §4`
  ("No path is dropped.") and §5 ("Walking every relationship-
  slack-zero link backward … walks recursively until every driving
  predecessor is exhausted."). Every such edge appears on
  `DrivingPathResult.edges`; shared ancestors appear exactly once
  in `DrivingPathResult.nodes` (deduplication by UID). The AM7
  "lowest-UID tie-break" rule is withdrawn — tie-break is no longer
  a concept. Non-driving (positive-slack) predecessors still land
  on `non_driving_predecessors`, and the Block 7 validator enforces
  mutually exclusive slack regimes: edges have
  `relationship_slack_days ≈ 0`, non-driving predecessors have
  `slack_days > 0`. Placing a zero-slack alternate on
  `non_driving_predecessors` (the AM7 escape hatch) is structurally
  impossible under the Block 7 contract. See §2.18.

- **Cross-version focus-point disambiguation.** When
  `focus_spec = FocusPointAnchor.PROJECT_FINISH` (or `PROJECT_START`)
  resolves to different UIDs in Period A and Period B,
  `trace_driving_path_cross_version` raises `DrivingPathError`
  rather than silently comparing two different chains. The
  operator must pass an explicit integer UID to proceed.

**Acceptance criteria.**

1. On the SSI multi-tier worked example from
   `driving-slack-and-paths §2.4` / slide 22 (Y → X → Predecessor 3
   → Focus Point, all FS, all zero slack), `trace_driving_path`
   returns a four-node chain terminating at Focus Point with
   relationship slack = 0 on every link. Exercised by
   `tests/test_engine_driving_path_ssi_example.py::test_ssi_four_tier_chain`.
2. The Focus Point is operator-configurable — the function accepts
   any UniqueID, not just the project finish milestone, and also
   accepts `FocusPointAnchor.PROJECT_FINISH` / `PROJECT_START`. The
   project critical path is the special case `focus_spec =
   PROJECT_FINISH`. Exercised by
   `tests/test_engine_focus_point.py` and
   `tests/test_engine_driving_path.py::test_trace_with_int_uid`.
3. Non-driving predecessors (relationship slack > 0) terminate
   that branch of the walk and are reported in
   `DrivingPathResult.non_driving_predecessors` with their slack
   values, predecessor / successor UID+name, and relation type.
   Exercised by
   `tests/test_engine_driving_path_ssi_example.py::test_ssi_multi_branch_non_driving`
   and `tests/test_engine_driving_path.py::test_branching_non_driving_predecessor`.
4. Period A slack is used exclusively for but-for analysis per
   `driving-slack-and-paths §9`. The cross-version result frames
   added / removed / retained UID sets from Period A's perspective;
   Period B's trace is descriptive (displayed) but never
   prescriptive. Exercised by
   `tests/test_engine_driving_path_cross_version.py::test_period_a_slack_rule`.
5. Every chain node carries `unique_id` and `name`; every link
   carries predecessor / successor UIDs, `relation_type`,
   `lag_minutes`, and `relationship_slack_minutes` for drill-down.
   Exercised by
   `tests/test_engine_driving_path_types.py` and
   `tests/test_engine_driving_path.py::test_linear_fs_chain`.

**Test strategy.** SSI-anchored tests reconstruct the slide 22
example exactly and assert the four-node chain + zero relationship
slack on every link. Multi-branch test verifies non-driving
predecessors terminate correctly. Cross-version tests verify the
added / removed / retained UID sets and the Period A slack rule.
Mutation-invariance tests snapshot `Schedule.model_dump()` and
`cpm_result_snapshot(...)` before / after every trace call.

**File-by-file scope.**

- `app/engine/driving_path_types.py` — frozen Pydantic v2 result
  contract: `DrivingPathNode`, `DrivingPathLink`,
  `NonDrivingPredecessor`, `DrivingPathResult`,
  `DrivingPathCrossVersionResult`, `FocusPointAnchor`.
- `app/engine/focus_point.py` — `resolve_focus_point` and the
  `FocusPointError` exception.
- `app/engine/driving_path.py` — `trace_driving_path`,
  `trace_driving_path_cross_version`, and the `DrivingPathError`
  exception.
- `app/engine/__init__.py` — additive re-exports of the M10
  public API.
- `app/engine/README.md` — extended with a "Driving path analysis
  (Milestone 10)" section.
- `tests/test_engine_driving_path_types.py` — frozen-contract
  tests.
- `tests/test_engine_focus_point.py` — resolver edge cases.
- `tests/test_engine_driving_path.py` — unit tests for the trace.
- `tests/test_engine_driving_path_ssi_example.py` — the AC #1
  SSI fixture reconstruction.
- `tests/test_engine_driving_path_cross_version.py` — cross-
  version mode + Period A slack rule.
- `tests/test_engine_driving_path_integration.py` — paired-
  schedule end-to-end integration.

**Skills referenced.** `driving-slack-and-paths` (§§2, 3, 5, 7, 9),
`mpp-parsing-com-automation` (§5).

**Estimated sessions.** 1.

### Milestone 11 — Manipulation scoring engine

**Dependencies.** Milestones 3, 4, 9, 10.

> **AM12 SUPERSEDES (4/23/2026).** The deliverables / file scope /
> detector-family decomposition below is reframed by BUILD-PLAN §2.22
> (AM12). M11 is narrowed to a constraint-driven cross-version
> erosion engine built on the M10.1 three-bucket partition and the
> M10.2 `skipped_cycle_participants` forensic trail. New file scope,
> contract shapes, state machine, scoring weights, and block
> decomposition live in §2.22. The original §5 M11 text below is
> preserved as historical context only; Block 2 implementation
> reads §2.22 as the authoritative spec.

**Deliverables.** `app/engine/manipulation/` package with five
sub-pattern groups from `forensic-manipulation-patterns §§4–8`: logic,
duration, date, float, critical-path. Rewrite addresses the archived
prior-build defects:

- **Fix the always-100 bug.** Manipulation score is computed as a
  weighted sum of per-pattern contributions normalized to [0, 100],
  not as a fixed return value. Score is driven by actual findings per
  the Tier-1/Tier-2/Tier-3 aggregation rule in
  `forensic-manipulation-patterns §10`.
- **Normalize per-pattern logic.** Each pattern detector returns an
  independent count of flagged tasks; aggregation multiplies counts by
  per-pattern weights and sums, then clamps to 100.
- **Route the CPM cascade correctly.** When a logic change cascades
  (removed predecessor → downstream forecast shift), the downstream
  tasks are flagged once under the root cause, not once per cascaded
  task. Per-UID deduplication runs after every detector.
- **Per-UID dedup.** A task that trips multiple detectors appears
  once in the final finding list with a composite reason string; its
  score contribution is the max of per-detector contributions, not the
  sum.

Every finding carries `unique_id`, `name`, root-cause pattern label,
contributing detector list, and the Period A / Period B field values
that raised the flag. Status-date windowing from Milestone 9 is
applied before scoring so legitimate actuals never contribute.

**Acceptance criteria.**

1. A schedule pair with zero manipulation signals returns score 0 —
   not 100. The always-100 bug regression test passes.
2. A schedule pair with exactly one constraint-injection on one task
   returns a non-zero score equal to the `constraint_injection` weight
   in `app/engine/manipulation/aggregator.py` per
   `forensic-manipulation-patterns §10`, verified within floating-point
   tolerance.
3. A schedule pair where tasks completed legitimately between Period
   A and Period B is filtered per `forensic-manipulation-patterns
   §3.2`; legitimate actuals contribute 0 to the score.
4. Per-UID dedup: a task that trips both constraint injection and
   duration compression appears once in the findings list.
5. Every finding has a drill-down record with Period A + Period B
   field values, the detector that flagged it, and the aggregation
   tier (1, 2, or 3) per `forensic-manipulation-patterns §10`.
6. ALAP constraint is detected as a separate finding category per
   `forensic-manipulation-patterns §5.3` — it does not count toward
   Metric 5 Hard Constraints but does count toward manipulation
   findings.

**Test strategy.** Explicit regression test for the always-100 bug
(`tests/test_manipulation_no_findings.py` asserts score == 0 on a
clean pair). Per-pattern unit tests. End-to-end integration test on a
10-task paired synthetic schedule with known signals.

**File-by-file scope.**

- `app/engine/manipulation/__init__.py`.
- `app/engine/manipulation/logic.py` — pattern §4 family.
- `app/engine/manipulation/duration.py` — pattern §5 family.
- `app/engine/manipulation/dates.py` — pattern §6 family.
- `app/engine/manipulation/float.py` — pattern §7 family.
- `app/engine/manipulation/critical_path.py` — pattern §8 family.
- `app/engine/manipulation/erosion.py` — cross-version erosion per
  §9.
- `app/engine/manipulation/aggregator.py` — Tier 1/2/3 aggregation
  from §10 + per-UID dedup.
- `app/engine/manipulation/result.py` — `ManipulationFinding` and
  `ManipulationResult` Pydantic models.
- `tests/test_manipulation_no_findings.py` — always-100 regression.
- `tests/test_manipulation_patterns.py` — per-pattern cases.
- `tests/test_manipulation_dedup.py`.

**Skills referenced.** `forensic-manipulation-patterns` (§§3–10),
`dcma-14-point-assessment` (§4), `driving-slack-and-paths` (§§5, 9,
10), `acumen-reference` (§§4.4, 5.2), `nasa-schedule-management`
(§§8, 9).

**Estimated sessions.** 1–2. Flag for possible decomposition into
"detectors" (11a) and "aggregator + dedup" (11b) at build time if the
first session under-runs on detector breadth.

### Milestone 12 — AI backend (Ollama default, Claude API toggle)

**Dependencies.** Milestones 5–8, 11.

**Deliverables.** `app/ai/base.py` abstract interface;
`app/ai/ollama_client.py` for localhost:11434; `app/ai/claude_client.py`
calling the Anthropic SDK with `claude-sonnet-4-6`.
`app/ai/router.py` reads `Config.is_cui_safe_mode()` (default True).
Classification toggle lives in the web UI (per-session). Claude client
constructed only when classification is explicitly "unclassified."
Persistent banner in `base.html` per `cui-compliance-constraints §2g`.
Silent-fallback prohibition per §2f: Ollama unreachable + CUI →
explicit halt.

**Acceptance criteria.**

1. With `is_cui_safe_mode() == True`, attempting to construct a
   `ClaudeClient` raises a `CuiViolationError` before any HTTP call
   is made.
2. With classification = "unclassified" and Claude API active,
   `base.html` renders a non-dismissible banner naming the model,
   endpoint, and that prompt content is being transmitted externally.
3. When Ollama is unreachable and classification is CUI, the
   `/ai-analyze` route returns HTTP 503 with body "Ollama unavailable
   — no cloud fallback permitted for CUI projects." The UI does not
   offer a "try Claude API" button.
4. The AI layer consumes only pre-computed metrics (`AnalysisResult`
   from Milestones 5–11); it never receives raw `ScheduleData`. This
   preserves `cui-compliance-constraints §2a` — Ollama still runs
   locally, but the Claude path never sees raw content.
5. `DataSanitizer` replaces task names with labels before the prompt
   reaches any client; `desanitize_text` restores them on stream
   emission.

**Test strategy.** Unit tests with mocked HTTP calls. The
`CuiViolationError` test is the primary regression gate — it must fail
against any code path that constructs `ClaudeClient` when
`is_cui_safe_mode()` returns True.

**File-by-file scope.**

- `app/ai/__init__.py`.
- `app/ai/base.py` — abstract `AIClient`.
- `app/ai/ollama_client.py`.
- `app/ai/claude_client.py`.
- `app/ai/router.py` — classification-gated construction.
- `app/ai/sanitizer.py` — UID → label map, one-shot per analysis.
- `app/ai/prompt_builder.py` — builds narrative prompt from
  `AnalysisResult`.
- `app/web/templates/base.html` — updated with conditional banner.
- `tests/test_ai_cui_gate.py` — `CuiViolationError` regression.
- `tests/test_ai_sanitizer.py`.
- `tests/test_ai_halt_on_ollama_unavailable.py`.

**Skills referenced.** `cui-compliance-constraints` (§§2a, 2b, 2d, 2f,
2g, 3).

**Estimated sessions.** 1.

### Milestone 13 — Web UI + transparency / drill-down integration

**Dependencies.** Milestones 5–11, 12.

**Deliverables.** Analyst-facing UI: upload form with 500 MB check;
dashboard listing all 14 DCMA metrics with pass/fail chips; per-metric
drill-down (Tabulator.js) listing every flagged UniqueID + name +
field value + threshold; side-by-side comparator view; driving-path
trace view for an operator-nominated Focus Point; manipulation-
findings view with Tier 1/2/3 bucketing; AI-narrative panel with
Ollama/Claude toggle and banner when cloud is active. Every numeric
conclusion is click-through — transparency (F) enforced by UI
convention, not just model shape.

**Acceptance criteria.**

1. Manual verification: open `localhost:5000`, upload two synthetic
   `.mpp` files, confirm the comparator table renders with per-task
   drill-down clickable, each row showing UniqueID + name + the
   delta that flagged it.
2. Every DCMA metric card has a "Show tasks" drill-down that renders
   all flagged tasks with UniqueID and name. No card shows only a
   percentage.
3. Driving-path view accepts a UniqueID input (or a dropdown of
   milestones) and renders the chain; clicking a chain node opens
   its drill-down.
4. Manipulation-findings view groups findings by Tier (1, 2, 3); each
   finding shows the contributing detector list and drill-down into
   Period A + Period B field values.
5. AI-narrative panel shows a prominent, non-dismissible banner when
   Claude API is active (§2g). The classification toggle is visible
   and requires double-confirmation to switch from CUI to
   unclassified.
6. Chart.js and SheetJS load via CDN with local-fallback placeholders
   per CLAUDE.md decision #9 (air-gapped deployments swap local
   UMD bundles).

**Test strategy.** Flask test-client integration tests verify every
route returns 200 and the rendered HTML contains drill-down anchors.
Manual UI verification is explicit in the acceptance criteria — type
checking and pytest do not substitute. The milestone build session
must start the dev server and exercise the UI in a browser before
reporting completion.

**File-by-file scope.**

- `app/web/routes.py` — expanded with `/analyze`, `/compare`,
  `/driving-path`, `/manipulation`, `/ai-analyze`.
- `app/web/templates/dashboard.html` — DCMA metric cards.
- `app/web/templates/metric_detail.html` — per-metric drill-down.
- `app/web/templates/compare.html` — comparator table.
- `app/web/templates/driving_path.html` — chain trace view.
- `app/web/templates/manipulation.html` — tiered findings view.
- `app/web/templates/classification_toggle.html` — toggle modal.
- `app/web/static/js/drilldown.js` — click-through handler.
- `app/web/static/js/classification.js` — double-confirm toggle.
- `app/web/static/lib/chart.min.js.placeholder` — local fallback.
- `app/web/static/lib/tabulator.min.js.placeholder` — local fallback.
- `tests/test_web_routes.py` — integration tests for every route.

**Skills referenced.** `cui-compliance-constraints` (§§2b, 2g),
`dcma-14-point-assessment`, `driving-slack-and-paths`,
`forensic-manipulation-patterns`, `nasa-schedule-management`.

**Estimated sessions.** 1–2. Flag for decomposition into "base UI +
DCMA cards" (13a) and "comparator + driving path + manipulation +
AI panel" (13b) at build time.

### Milestone 14 — Integration tests, regression tests, CI

**Dependencies.** Milestones 1–13.

**Deliverables.** End-to-end integration test over the full pipeline:
synthetic `.mpp` → monkey-patched parser
(`cui-compliance-constraints §2e`) → all DCMA metrics → NASA overlay →
comparator → driving path → manipulation engine → Ollama-mocked AI →
DOCX/XLSX/PDF export. Regression-test sweep covering every defensive
acceptance criterion in Milestones 1–13. GitHub Actions workflow
running `ruff` lint, `mypy` (skipping `win32com` on non-Windows), and
pytest with coverage. Targets: ≥80% `app/engine/` and `app/ai/`; ≥60%
`app/web/`.

**Acceptance criteria.**

1. `pytest -q` passes end-to-end with zero real `.mpp` files and no
   JVM/COM dependencies on the CI runner. The parser is monkey-patched
   per `cui-compliance-constraints §2e`.
2. Regression tests referenced in every prior milestone's "Test
   strategy" section exist and are named consistently
   (`tests/test_*_regression.py` or similar).
3. The always-100 manipulation bug regression test lives here or in
   Milestone 11 and is run in CI.
4. CI workflow runs on every push and every PR; a red run blocks
   merge (configured in branch protection rules, if available, or
   enforced by review discipline).
5. Coverage report is uploaded as a CI artifact; thresholds above are
   advisory in Phase 1, enforced in a later phase.

**Test strategy.** The milestone's test strategy is itself the test
strategy of the whole project codified — every prior milestone's
tests collectively run here.

**File-by-file scope.**

- `.github/workflows/ci.yml` — lint + test + coverage upload.
- `pyproject.toml` — ruff + mypy config.
- `tests/test_end_to_end.py` — full-pipeline integration test.
- `tests/conftest.py` — shared fixtures (synthetic `ScheduleData`
  factory, sanitized-temp-dir fixture).

**Skills referenced.** `cui-compliance-constraints` (§2e — synthetic
fixtures only, §2d — no CUI in logs).

**Estimated sessions.** 1.

---

## 6. Acceptance Criteria Conventions

Every acceptance criterion in this document — and in every build
session — must satisfy three properties:

1. **Specific.** References a named feature, metric, file, class,
   route, or output record. "Works correctly" is not acceptable.

2. **Testable.** Pass/fail reached via automated test (pytest) or a
   pre-specified manual verification step. Manual verification is
   permitted only for UI milestones.

3. **Forensically defensible.** For every metric, manipulation
   finding, or driving-path output, the criterion requires that the
   result cites the exact UniqueID(s) and task name(s) that drove it.
   No black-box percentage; no aggregate score without
   contributing-task drill-down. Indicators, not verdicts per
   `dcma-14-point-assessment §6 Rule 1` and
   `forensic-manipulation-patterns §1`.

A build session that cannot write criteria meeting all three
properties must pause and seek clarification, not ship the feature.

---

## 7. Test Strategy

**7.1 Test framework.** pytest, pinned in `requirements.txt`.

**7.2 Test data policy.** Fixtures are synthetic and generated at
test time. Real schedules (`.mpp`, `.xer`, `.xml`, `.pmxml`, cost
CSVs) are CUI per `cui-compliance-constraints §2e` and never
committed. Integration tests monkey-patch
`app.parser.com_reader.parse_mpp` to return synthetic `ScheduleData`.

**7.3 Unit test coverage targets.** `app/engine/` and `app/ai/`
≥80%; `app/web/` ≥60%. `app/parser/` — all ten Appendix D gotchas
have a named test; line-coverage target inapplicable. Advisory in
Phase 1, enforced later.

**7.4 Integration test scope.** One end-to-end test exercising
upload → monkey-patched parse → CPM → all 14 DCMA metrics → NASA
overlay → two-version comparator → driving path → manipulation
scoring → Ollama-mocked AI → DOCX/XLSX/PDF export, in
`tests/test_end_to_end.py`.

**7.5 Regression test scope.** Every bug fix ships a regression test
that fails pre-fix and passes post-fix. Named regression tests:
always-100 manipulation, duration-in-minutes conversion, CPT
mutation, parser null-task drop, silent cloud fallback. Milestone 14
consolidates the catalogue.

**7.6 CI.** `.github/workflows/ci.yml` runs `ruff check`,
`ruff format --check`, `mypy` (skipping `win32com` off Windows), and
pytest with `pytest-cov`. Coverage XML uploaded as artifact. No
Windows runner required because the parser is monkey-patched.

**7.7 Manual verification.** UI milestones require starting the dev
server, uploading two synthetic `.mpp` files, and exercising golden
paths and edge cases in a real browser. Type-check + pytest is not
sufficient for UI deliverables.

---

## 8. CLAUDE.md Role

`.claude/CLAUDE.md` is the institutional-memory preamble every Claude
Code session reads at the top of context. It is **not** this
BUILD-PLAN.md — CLAUDE.md is the context; BUILD-PLAN.md is the spec.
Milestone 1 rewrites CLAUDE.md with these eight fields:

1. **Project identity.** Repo, brand, install path convention,
   workstation constraints (enterprise-managed Windows 11, no local
   admin, OneDrive sync implications per
   `cui-compliance-constraints §7`), CUI locality posture.

2. **Phase identification.** Currently Phase 1; milestones numbered
   1–14; the two deferred phases named.

3. **Branch naming convention.**
   `claude/milestone-N-{scope}-YYYY-MM-DD` for milestone build
   sessions; other session types keep their current conventions
   (`claude/session-NN-{description}-YYYY-MM-DD`).

4. **One-session-per-milestone rule.** Each milestone is scoped for
   one Claude Code session. Milestones flagged for possible
   decomposition (11, 13) split at build time if the first session
   under-runs.

5. **Pointer to `docs/BUILD-PLAN.md`** as the canonical Phase 1
   specification — build sessions read BUILD-PLAN.md first, then the
   skills their milestone references.

6. **Pointer to `.claude/skills/`** as the domain knowledge base;
   enumerate the eight skill directories by name.

7. **Known bugs and environmental constraints from the handoff
   ledger.** COM parser setup requires MS Project installed on host;
   Java and Node PATH are manual per session when needed; HP ZBook
   corporate IT agents (SentinelOne, SCCM, Splunk) consume machine
   resources; auto-merge is disabled on this repo by policy; three
   impulse-merge incidents are recorded; stream-idle timeouts on
   long Write tool calls must be mitigated via chunked bash-heredoc
   append pattern (as used in writing this BUILD-PLAN.md).

8. **Communication style.** Build-chat voice is technical and
   terse; tool-to-user voice (end-user narrative in the web UI, DOCX
   exports, etc.) is neutral, professional, specification-grade and
   is codified in the UI milestone (13) and the export modules.

---

## 9. Out-of-Scope — Explicit NOT List

The following items are **not** built in Phase 1 and no milestone may
introduce them:

- **Multi-file trend analysis beyond two versions.** Deferred to
  Phase 2. Phase 1 supports exactly two schedules: Period A (prior
  / baseline) and Period B (current).
- **RAG / retrieval augmentation for Ollama.** Deferred to Phase 2.
  Phase 1 AI narrative consumes only pre-computed deterministic
  metrics.
- **Custom Modelfile iteration for the `schedule-analyst` model.**
  Deferred to Phase 2. Phase 1 uses the existing model as-is.
- **Earned Value Analysis — SPI, CEI, SPI(t), full BCWS/BCWP/ACWP
  reconciliation.** Deferred to Phase 3. BEI appears as DCMA Metric 14
  (a schedule-only cumulative-hit ratio) but full EVA is Phase 3.
- **Primavera P6 XER / XML imports.** Phase 1 is MPP-only. P6 support
  is a later-phase concern.
- **Acumen API runtime integration.** Acumen is consulted as a
  reference vocabulary only (`acumen-reference §7.4`). The tool never
  calls the Acumen client process or its API at runtime.
- **Resource leveling, probabilistic SRA / Monte Carlo, criticality-
  index calculation.** Out-of-scope for Phase 1 per
  `driving-slack-and-paths §11` and `nasa-schedule-management §7`.
- **Multi-user / multi-worker deployment.** Phase 1 is
  single-analyst, single-worker Flask. Redis-backed session state,
  authentication, and concurrent-analysis support are later-phase
  concerns.
- **Cloud telemetry, crash reporting, auto-update channels.**
  Forbidden by `cui-compliance-constraints §5`.
- **Source-file uploads to any remote storage** (GitHub forges for
  schedules, Acumen cloud, OpenAI/Gemini/other LLM APIs). Forbidden
  by `cui-compliance-constraints §§2a, 2c, 5`.

### 9.1 Post-milestone deferral ledger

Items descoped from a milestone mid-build; none are permanently
out-of-scope but none block any Phase 1 milestone from shipping.

| Item                                                   | Deferred from  | Target phase / session                  | Reason                                                                                                                               |
|--------------------------------------------------------|----------------|-----------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| Metric 1b "Dangling Logic" (SS-only / FF-only)         | M5 (Minor 2)   | Post-M10 — requires per-relation drivership the engine exposes after M10 driving-path plumbing lands | Defensible SS-only / FF-only detection needs per-relation drivership context. Tracked as backlog.                                    |
| DCMA Metric 3 — 09NOV09 5-day MSP/OpenPlan carve-out   | M5             | Post-Phase-1 (P6/XER ingestion work)    | Needs per-file tool-provenance detection (MSP / OpenPlan / P6). The Phase 1 parser is MPP-only, so the carve-out is latent.          |
| `CPMOptions.auto_synthesize_calendar` default flip T→F | M4 / M5 / M6   | Post-M14 cleanup session                | Existing M6 fixtures do not universally carry explicit calendars; flipping the default at M7 time would force a wide fixture sweep.  |
| Metric 12 CPT +600-WD `model_copy` probe               | M7             | Phase 2 cross-check                     | Phase 1 ships the structural zero-slack-traversal variant (see M7 deliverables); the +600-WD probe is available as a future check.   |
| Metric 9 / Metric 14 offender-value narrative enrichment | M7 (audit minors) | M13 (UI) or a dedicated narrative-layer sweep | M7 shipped structurally complete offender lists (UniqueID + name + machine-parseable value). Human-readable offender narratives (date-delta phrasing for M9; baseline-vs-actual pairing for M14) are a narrative-layer concern landing with the UI drill-down. |

Each entry is restated in the relevant milestone's deliverables /
notes so a build session reading only §5 does not miss it. The
ledger is the single source of truth for cross-session descopes.

---

## 10. References

### 10.1 Skills referenced

All eight skills under `.claude/skills/` are referenced by one or
more milestones above:

- `cui-compliance-constraints`
- `mpp-parsing-com-automation`
- `driving-slack-and-paths`
- `dcma-14-point-assessment`
- `nasa-schedule-management`
- `nasa-program-project-governance`
- `forensic-manipulation-patterns`
- `acumen-reference`

### 10.2 Source documents referenced (by tag)

Referenced via skill bracket-tags; skills are the authoritative
citation layer. Tag dictionary lives at `docs/sources/README.md`:

- `[LL]` — Schedule Forensics Lessons Learned
- `[SMH]` — NASA Schedule Management Handbook
- `[NPR8K]` — NPR 8000.4C
- `[NID]` — NID 7120.148 (NPR 7120.5 Rev F)
- `[GPR]` — GPR 7120.7B
- `[SSI]` — SSI NASA Driving Slack
- `[ED]` — Edwards DCMA 14-Point Assessment, 2016
- `[RW]` — Ron Winter DCMA 14-Point Assessment, 2011
- `[DECM]` — Deltek EVMS-DECM Metrics V5.0
- `[DMG]` — Deltek Acumen 8.8 Metric Developer's Guide
- `[ATO]`, `[AQS]`, `[AIG]`, `[ASI]`, `[API]`, `[ACD]`, `[ARN]` —
  Acumen 8.8 documentation set
- `[PERG]`, `[PRNS]`, `[UPT]`, `[UPT2]`, `[V3P]` — internal
  project sources

---

*End of Phase 1 Master Build Plan.*
