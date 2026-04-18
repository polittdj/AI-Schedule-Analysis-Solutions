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
(`claude-sonnet-4-20250514`) only for unclassified projects
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

**Deliverables.** Pydantic v2 models: `ScheduleData`, `TaskData`,
`Relationship`, `Constraint`, `CalendarData`, `ProjectData`,
`AnalysisResult`. All use `ConfigDict(extra="forbid")` and
`model_dump(mode="json")`. Durations in minutes; working-day
conversion is a method on `TaskData`. `TaskData` fields cover
`unique_id`, `task_id`, `name`, `wbs`, all date fields (start, finish,
baseline, actual, early, late), duration and slack in minutes,
`percent_complete`, `is_milestone`, `is_summary`, `is_critical_from_msp`,
`is_loe`, `is_rolling_wave`, `is_schedule_margin`, `resource_count`,
`constraint`, `predecessors`, `successors`.

**Acceptance criteria.**

1. `from app.schema import ScheduleData` imports cleanly with no JVM,
   COM, or network side effects.
2. A `TaskData` populated with integer `duration_minutes = 2400`
   returns `2400 / (8*60) = 5.0` from its `duration_working_days(8)`
   method, matching `mpp-parsing-com-automation §3.5` Gotcha 5.
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

**Deliverables.** Per-metric modules under `app/engine/dcma/`. Each
function takes `ScheduleData`, returns `MetricResult` with
`metric_id`, `numerator`, `denominator`, `percentage`, `threshold`,
`pass_flag`, and `flagged_tasks: list[FlaggedTask]` (each carrying
`unique_id`, `name`, and the causing field value). Per
`dcma-14-point-assessment §4`:

- Metric 1a (Missing Logic): incomplete tasks with zero predecessors or
  zero successors, excluding project start/finish milestones; threshold
  ≤5%.
- Metric 1b (Dangling): tasks with SS-only predecessor (dangling
  finish) or FF-only successor (dangling start); threshold ≤5%.
- Metric 2 (Leads): relationships with negative lag / total
  relationships; threshold 0%.
- Metric 3 (Lags): relationships with positive lag / total
  relationships; threshold ≤5% with 09NOV09 5-day MSP/OpenPlan
  carve-out (P6 does not receive the carve-out — not applicable for
  MPP input, but carve-out handling documented for later P6 import).
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

**File-by-file scope.**

- `app/engine/dcma/__init__.py`.
- `app/engine/dcma/result.py` — `MetricResult` and `FlaggedTask` models.
- `app/engine/dcma/denominators.py` — Total Tasks, Incomplete Tasks,
  Relationships populations.
- `app/engine/dcma/logic.py` — Metrics 1a, 1b.
- `app/engine/dcma/leads.py` — Metric 2.
- `app/engine/dcma/lags.py` — Metric 3 (with carve-out).
- `app/engine/dcma/relationships.py` — Metric 4.
- `tests/test_dcma_metric_*.py` — one file per metric.

**Skills referenced.** `dcma-14-point-assessment` (§§3, 4.1, 4.2, 4.3,
4.4), `acumen-reference` (§4.4 DECM cross-reference).

**Estimated sessions.** 1.

### Milestone 6 — DCMA metrics 5–8, 10 (Hard Constraints, High Float, Negative Float, High Duration, Resources)

(Metric 10 groups with M6 — simple ratio, no CPM or date-comparison
dependency; Metric 9 groups with M7's date-sensitive metrics.)

**Dependencies.** Milestones 3, 4, 5.

**Deliverables.** Per-metric modules under `app/engine/dcma/` per
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

**File-by-file scope.**

- `app/engine/dcma/constraints.py` — Metric 5 (hard-constraint list).
- `app/engine/dcma/high_float.py` — Metric 6.
- `app/engine/dcma/negative_float.py` — Metric 7.
- `app/engine/dcma/high_duration.py` — Metric 8.
- `app/engine/dcma/resources.py` — Metric 10.
- `tests/test_dcma_metric_5.py`, `…_6.py`, `…_7.py`, `…_8.py`,
  `…_10.py`.

**Skills referenced.** `dcma-14-point-assessment` (§§4.5–4.8, §4.10),
`acumen-reference` (§4.4 DECM row cross-reference for 06A209a,
06A211a).

**Estimated sessions.** 1.

### Milestone 7 — DCMA metrics 9, 11–14 (Invalid Dates, Missed Tasks, CPT, CPLI, BEI)

**Dependencies.** Milestones 3, 4, 5.

**Deliverables.** Per-metric modules under `app/engine/dcma/` per
`dcma-14-point-assessment §§4.9, 4.11–4.14`:

- Metric 9a (Forecast-before-status): any forecast start/finish before
  `status_date`; threshold 0%.
- Metric 9b (Actual-after-status): any actual start/finish after
  `status_date`; threshold 0%.
- Metric 11 (Missed Tasks): incomplete tasks with `baseline_finish ≤
  status_date` / Total Tasks; threshold ≤5%.
- Metric 12 (Critical Path Test): add 600 WD to a critical task's
  `remaining_duration`, re-run CPM via `ScheduleData.model_copy(…)` +
  `TaskData.model_copy(…)`, compare project finish — must shift by the
  full 600 WD to pass. Boolean pass/fail.
- Metric 13 (CPLI): `(CP_length + total_float_to_contract_finish) /
  CP_length`; threshold ≥0.95.
- Metric 14 (BEI): tasks completed by status date / tasks with
  `baseline_finish ≤ status_date`; threshold ≥0.95; cumulative-hit
  definition per Edwards.

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

**File-by-file scope.**

- `app/engine/dcma/invalid_dates.py` — Metric 9a, 9b.
- `app/engine/dcma/missed_tasks.py` — Metric 11.
- `app/engine/dcma/cpt.py` — Metric 12 with `model_copy` probe.
- `app/engine/dcma/cpli.py` — Metric 13.
- `app/engine/dcma/bei.py` — Metric 14.
- `tests/test_dcma_metric_9.py`, `…_11.py`, `…_12.py`, `…_13.py`,
  `…_14.py`.

**Skills referenced.** `dcma-14-point-assessment` (§§4.9, 4.11–4.14,
§5), `acumen-reference` (§4.4 DECM cross-reference).

**Estimated sessions.** 1.

### Milestone 8 — NASA SMH overlay

**Dependencies.** Milestones 5, 6, 7.

**Deliverables.** `app/engine/nasa_overlay.py` layering SMH rules on
the DCMA metrics per `nasa-schedule-management §6`:

- High-Float denominator excludes tasks flagged as schedule margin
  (`TaskData.is_schedule_margin = True`) per
  `nasa-schedule-management §3`.
- Governance-milestone constraint triage: tasks with MSO/FNLT whose
  name matches a governance-milestone pattern (KDP, SRR, PDR, CDR,
  SIR, ORR) produce a triage flag that suppresses the hard-constraint
  manipulation raise and adds an informational note per
  `nasa-program-project-governance §§4, 5`.
- Rolling-wave window cross-check: tasks exempted from Metric 8 via
  `is_rolling_wave` are additionally validated against the 6–12 month
  window per `nasa-schedule-management §4`; a near-term rolling-wave
  tag emits an informational note.

**Acceptance criteria.**

1. A schedule with 10 incomplete tasks, 3 of which carry
   `is_schedule_margin = True` and have `total_slack > 44 WD`, reports
   Metric 6 denominator = 7 (not 10).
2. A task named "CDR Review" with an MFO constraint produces a
   governance-triage note; Milestone 11's manipulation engine reads
   the note and does not raise the constraint as manipulation.
3. The overlay runs after base DCMA metrics; it modifies denominators
   and emits informational notes but does not rewrite
   `MetricResult.flagged_tasks` — transparency per §6 below is
   preserved.
4. Governance-milestone pattern list is externalized to
   `app/engine/nasa_milestones.py` so analysts can edit without
   touching metric code.

**Test strategy.** Synthetic schedule with tagged schedule-margin
tasks, a named CDR milestone, and an out-of-window rolling-wave tag.
Tests verify denominator exclusion, triage-note emission, and
rolling-wave window cross-check.

**File-by-file scope.**

- `app/engine/nasa_overlay.py` — overlay orchestrator.
- `app/engine/nasa_milestones.py` — governance-milestone name
  patterns.
- `tests/test_nasa_overlay.py`.

**Skills referenced.** `nasa-schedule-management` (§§3, 4, 6),
`nasa-program-project-governance` (§§4, 5), `dcma-14-point-assessment`
(§4.5, §4.6, §4.8, §8).

**Estimated sessions.** 1.

### Milestone 9 — Status-date windowing + cross-version comparator

**Dependencies.** Milestones 2, 3.

**Deliverables.** `app/engine/comparator.py` matching two
`ScheduleData` by UniqueID, emitting `ComparatorResult` with
per-UID field deltas. Filter per `forensic-manipulation-patterns §3.2`
and `driving-slack-and-paths §10`: Period A finish ≤ Period B status
date tags the delta `is_legitimate_actual = True`. Filter tags rather
than deletes; UI separates "legitimate" from "candidate manipulation."

**Acceptance criteria.**

1. Given two `ScheduleData` instances with 50 tasks each, 40 of them
   matching by UniqueID, 5 added in B, 5 deleted from A, the
   comparator emits 40 matched deltas + 5 additions + 5 deletions.
   Total records: 50.
2. A matched task whose Period A `finish = 2026-03-15` and Period B
   `status_date = 2026-03-31` is tagged `is_legitimate_actual = True`
   regardless of Period B field changes.
3. Per-field deltas include `total_slack`, `free_slack`,
   `baseline_finish`, forecast `finish`, `constraint.type`,
   `duration_minutes`, `actual_start`, `actual_finish`, and incident
   relationship changes.
4. UniqueID match only — `ID` and `name` are not used (enforce via
   regression test that renames all tasks in Period B and verifies the
   match count is unchanged).
5. Calendar-day conversion for date slips happens at the presentation
   layer; internal slip deltas are raw `timedelta`.

**Test strategy.** Paired synthetic schedules with known differences
(added task, deleted task, renamed task, legitimate actuals within
window, suspected manipulation outside window). Tests
`tests/test_comparator.py` and `tests/test_windowing_filter.py`.

**File-by-file scope.**

- `app/engine/comparator.py` — UniqueID-matched diff.
- `app/engine/windowing.py` — status-date predicate.
- `app/engine/delta.py` — `FieldDelta`, `TaskDelta`,
  `ComparatorResult` Pydantic models.
- `tests/test_comparator.py`.
- `tests/test_windowing_filter.py`.

**Skills referenced.** `forensic-manipulation-patterns` (§3.2),
`driving-slack-and-paths` (§10), `nasa-schedule-management` (§8),
`mpp-parsing-com-automation` (§5).

**Estimated sessions.** 1.

### Milestone 10 — Task-specific driving path analysis

**Dependencies.** Milestones 4, 9.

**Deliverables.** `app/engine/driving_path.py` with
`trace_driving_path(schedule, focus_uid) -> DrivingPathResult`.
Backward walk along zero-relationship-slack edges per
`driving-slack-and-paths §5`. Emits ordered chain + per-link slack
table. Cross-version mode reports driving-predecessor added/removed/
retained from Period A to B (matched by UniqueID per §2.7).

**Acceptance criteria.**

1. On the SSI multi-tier worked example from
   `driving-slack-and-paths §2.4` (Y → X → Predecessor 3 → Focus
   Point, all FS, all zero slack), `trace_driving_path` returns a
   four-node chain terminating at Focus Point with relationship slack
   = 0 on every link.
2. The Focus Point is operator-configurable — the function accepts any
   UniqueID, not just the project finish milestone. Project critical
   path is a special case where the focus is the project finish.
3. Non-driving predecessors (relationship slack > 0) terminate that
   branch of the walk and are reported in a secondary list with their
   slack values.
4. Period A slack is used exclusively for but-for analysis per
   `driving-slack-and-paths §9`. Cross-version call returns deltas
   against Period A, not Period B.
5. Every chain node carries `unique_id` and `name` for drill-down.

**Test strategy.** SSI-anchored tests reconstruct the slide 14–22
example exactly and assert DS values at each tier. Multi-branch test
verifies non-driving predecessors terminate correctly. Cross-version
test verifies Period A slack is used.

**File-by-file scope.**

- `app/engine/driving_path.py` — trace function.
- `app/engine/focus_point.py` — Focus Point resolver (UniqueID or
  predefined anchor).
- `tests/test_driving_path_ssi_example.py`.
- `tests/test_driving_path_cross_version.py`.

**Skills referenced.** `driving-slack-and-paths` (§§2, 3, 5, 7, 9),
`mpp-parsing-com-automation` (§5).

**Estimated sessions.** 1.

### Milestone 11 — Manipulation scoring engine

**Dependencies.** Milestones 3, 4, 9, 10.

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
2. A schedule pair with one constraint-injection on one task returns
   a score less than 10 (small finding, bounded contribution).
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
calling the Anthropic SDK with `claude-sonnet-4-20250514`.
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
