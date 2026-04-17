---
name: cui-compliance-constraints
description: Controlled Unclassified Information (CUI) handling rules for this schedule-forensics tool. Schedule data in .mpp, .xer, .mpx, .xml, .pmxml, and CSV/XLSX exports is treated as CUI by default. Constrains how the tool parses, uploads, and stores schedule content; blocks network transmit to cloud or external API endpoints; governs log and telemetry emission; prevents commit to git; and enforces dual-mode AI routing (local Ollama default, Claude API opt-in only for unclassified work). Load before any code path that reads schedule files, constructs AI prompts, logs task data, or configures outbound HTTP.
---

# CUI Compliance Constraints

## 1. Overview and Operating Environment

The primary user of this tool is a senior forensic schedule analyst performing
independent CPM schedule analysis on NASA and DoD contracts. A large fraction
of the schedules reviewed are export-controlled, procurement-sensitive, or
otherwise Controlled Unclassified Information (CUI) under the federal CUI
program. The tool's entire design posture flows from one assumption: every
schedule file handed to this tool is CUI until proven otherwise, and the cost
of a false negative (treating a CUI file as unclassified) is categorically
worse than the cost of a false positive (treating an unclassified file as
CUI).

Files that enter this tool are typically one of: Microsoft Project `.mpp`,
Primavera P6 XER `.xer`, Primavera P6 XML `.xml` / `.pmxml`, MPX `.mpx`, or
tabular exports (`.csv`, `.xlsx`) derived from one of the above. Any of these
formats can contain CUI content in the task names, WBS structure, resource
names, note fields, cost data, and baseline history. Parsed derivatives
(Pydantic `ScheduleData`, pickled analysis blobs, Chart.js payloads, exported
DOCX/PDF/XLSX narratives) inherit the CUI classification of their source file.

The workstation that runs this tool is an enterprise-managed Windows 11
machine. The analyst does not have local administrator rights. Python, Java,
Ollama, and the tool itself run from a portable runtime tree synchronized via
OneDrive. There is no local package manager, no system-level service
registration, and no elevated-privilege install step. Network egress is
gated by enterprise DLP controls, but this skill does not rely on those
controls — the tool is responsible for not attempting egress in the first
place.

[Cite: Lessons Learned §1 "Operating Environment"; NPR 8000.4C p.5 Chapter 1
Introduction referencing NPD 2810.1; NPR 8000.4C p.18 §2.2.7 CIO
cybersecurity policy responsibilities.]

## 2. Eight Non-Negotiable CUI Rules

Each rule below lists (a) the rule itself, (b) the rationale, and (c) how
the rule is enforced in the code or configuration of this tool.

### 2a. Schedule file contents never leave the local machine

Rule: No raw bytes from a schedule file, and no parsed derivative of those
bytes, may be transmitted off the workstation by any code path in this tool
except an explicitly authorized Claude API call (see rule 2b) for an
analyst-confirmed unclassified project.

Rationale: The tool cannot distinguish CUI from non-CUI by inspecting file
contents alone. Classification is a property of the contract and the
originator's marking, not of the file's text. Therefore the tool treats all
schedule content as CUI and forbids egress by default.

Enforcement: The forensic engine in `app/engine/` is a pure-Python,
offline computation. The parser `app.parser.mpp_reader.parse_mpp` uses a
locally bundled JVM via JPype1 against MPXJ JARs shipped with the `mpxj` pip
package; it opens no sockets. No module under `app/` imports `requests`,
`httpx`, `urllib3`, `boto3`, or any SDK other than the explicitly gated
Anthropic client. Chart.js and Tabulator.js load from
`app/web/static/lib/` with a CDN fallback that an air-gapped deployment
strips at install time.

[Cite: Lessons Learned §9.1 "No schedule data egress"; Lessons Learned §13
Commandment 8; NPR 8000.4C p.18 §2.2.7 CIO cybersecurity policy.]

### 2b. Default to Ollama schedule-analyst; Claude API is explicit opt-in

Rule: The tool's default AI backend is the local Ollama `schedule-analyst`
custom model built on `qwen2.5:7b-instruct` running on
`http://localhost:11434`. The Anthropic Claude API backend may only be
constructed for a project the analyst has manually toggled to the
"unclassified" classification level in the web UI.

Rationale: Ollama traffic never leaves `localhost`. The Claude API does.
A project's classification level, not its content, gates cloud routing.

Enforcement: `Config.is_cui_safe_mode()` returns True unless the analyst
explicitly sets classification to unclassified. The Flask route for
`/ai-analyze` refuses to instantiate `ClaudeClient` when CUI-safe mode is
active. `app/ai/base.py` defines the abstract interface; concrete clients
honor `is_available()` but do not themselves inspect classification.

[Cite: Build State Summary §5 "Dual-mode AI"; Lessons Learned §9.5
"No silent cloud fallback"; NID 7120.148 p.112 §3.8 System Security Plan
and reference to NPR 2810.1.]

### 2c. No schedule file or derivative is ever committed to git

Rule: `.mpp`, `.mpx`, `.xer`, `.xml` when it is a P6 export, `.pmxml`, and
any `.csv` or `.xlsx` that originated as a schedule export, along with
pickled analysis blobs and any DOCX/PDF/XLSX produced by the export
subsystem, must be blocked from the git index.

Rationale: Once a CUI artifact enters a git history, purging it is
operationally difficult and the artifact may already have been pushed to a
remote. Prevention is the only tractable control.

Enforcement: `.gitignore` lists every schedule extension, the
`UPLOAD_FOLDER/` directory, `analysis_*.pkl`, and the export output
directory. Developers are expected to run `git status` before every commit.
A future pre-commit hook can assert these patterns programmatically;
absent that, the rule is enforced by reviewer discipline.

[Cite: Lessons Learned §9.4 "Git hygiene"; Lessons Learned §10.4 "Test
fixture boundary"; GPR 7120.7B p.3 P.8 records retention / NRRS 1441.1
implication that retention of controlled artifacts is governed
and not a developer discretion.]

### 2d. No schedule content to stdout, stderr, or log files

Rule: The tool may log file paths, UUIDs, task counts, durations in
aggregate, error classes, and timing metrics. It may not log task names,
resource names, WBS labels, note text, or any field value extracted from
a schedule file.

Rationale: Console output and log files are copied to enterprise
observability stacks, shared in screenshots, and retained beyond the
analyst's session. A log line that embeds a task name leaks CUI to every
system that ingests that log.

Enforcement: Logger calls in `app/` use structured keys that emit counts
and paths only. Exceptions raised from the parser are caught at the route
boundary and re-raised with a redacted message. A developer who needs to
debug parser output locally uses the pdb breakpoint or a temporary
`print(...)` that is deleted before commit; such prints must never land in
`main`.

[Cite: Lessons Learned §9.1 telemetry clause explicitly prohibiting
content-bearing log lines.]

### 2e. Tests and fixtures use synthetic data only

Rule: Every file under `tests/fixtures/` must be synthetic. No fixture
may have been derived from a real contract schedule, even partially, even
after hand-editing.

Rationale: Hand-editing a real schedule to "sanitize" it is a known-bad
pattern; structural fingerprints (WBS depth, calendar exception dates,
resource unit conventions) survive renaming. The only safe fixture is one
generated from scratch.

Enforcement: Integration tests monkey-patch
`app.parser.mpp_reader.parse_mpp` to return synthetic `ScheduleData`
instances built in Python. This both satisfies the rule and keeps the test
suite running without a JVM. Fixture DOCX/XLSX samples used to exercise
exporters are similarly synthesized in-test.

[Cite: Lessons Learned §12 Tier 1 "Synthetic fixtures only"; Lessons
Learned §10.4 "Test fixture boundary."]

### 2f. If Ollama is unavailable and Claude API is not explicitly toggled, the tool HALTS

Rule: When the user requests an AI narrative and the local Ollama endpoint
is unreachable (connection refused, model not loaded, timeout), the tool
must surface an explicit error and stop. It must not fall back to the
Claude API automatically.

Rationale: Silent fallback to a cloud API is the canonical way a CUI
incident happens. The analyst must make an affirmative classification
decision before any cloud call.

Enforcement: The `/ai-analyze` route checks backend availability and
returns an error to the UI when the selected backend is unavailable. The
UI does not present a "try the other backend" button; the analyst must
explicitly change classification and resubmit. [Cite: Lessons Learned §9.5
sources the prohibition on silent fallback. The specific halt-versus-
error-fallback enforcement in this tool is (inferred — not sourced) from
the prohibition; it is the strictest implementation consistent with §9.5.]

### 2g. Persistent banner when Claude API is active

Rule: Whenever the Claude API backend is selected and active, the web UI
must display a persistent, visually distinct banner that names the model
in use, the external endpoint being called, and the fact that prompt
content is being transmitted to an external service.

Rationale: The analyst should never be uncertain which backend is
answering. A persistent banner prevents the "I thought I was on Ollama"
class of mistake.

Enforcement: `base.html` renders a conditional banner driven by the
active backend state. The banner is not dismissible for the duration of
an active cloud-backed session. [Label: (inferred — not sourced). This
UI affordance is a defense-in-depth control derived from the spirit of
Lessons Learned §9.5 rather than an explicit requirement cited in the
approved sources.]

### 2h. Session end or TTL expiry wipes uploads, session state, and in-memory analysis

Rule: When the analyst's session ends — whether by explicit logout, tab
close, TTL expiry, or server restart — the tool must delete uploaded
schedule files from `UPLOAD_FOLDER/`, delete the corresponding
`analysis_<uuid>.pkl`, and drop any in-memory `ScheduleData` referenced by
that session.

Rationale: CUI artifacts should not persist past the analytical need.
Retaining a pickled analysis blob "just in case" violates minimum
retention and creates exposure if the workstation is later imaged.

Enforcement: The Flask session stores only a UUID; the pickled analysis
lives on disk keyed to that UUID. A session-end handler removes the
pickle and upload. A periodic sweeper removes orphaned analysis files
older than the session TTL.

[Cite: Lessons Learned §9.3 "Session lifecycle and retention."]

## 3. Watchdog Enforcement Signatures (for Prompt A.4)

The A.4 watchdog prompt scans diffs, generated code, and proposed commits
for signatures that indicate a CUI rule is about to be violated. The
signatures below are the minimum set; the watchdog may flag additional
patterns.

- New imports of `requests`, `httpx`, `urllib3`, `aiohttp`, `boto3`,
  `google.cloud.*`, or any other HTTP-capable client outside the narrow
  Claude API client path in `app/ai/claude_client.py`. Even a "harmless"
  `requests.get` in an unrelated utility module is a finding.

- `logger.info`, `logger.debug`, `logger.warning`, `print`, or f-string
  formatting where the interpolated variable is known to carry parsed
  task content — e.g., `task.name`, `task.wbs`, `task.notes`,
  `resource.name`, or any iteration over `schedule.tasks` that emits
  string fields.

- Any commit whose file list contains `.mpp`, `.mpx`, `.xer`, `.xml` in a
  schedule context, `.pmxml`, `analysis_*.pkl`, or export artifacts
  under the documented export output directory.

- Test fixtures that resemble real schedules: more than roughly 20 tasks,
  a realistic multi-level WBS, named human resources, and dates clustered
  near the current calendar week. Synthetic fixtures are typically small,
  schematic, and use obviously fake names (`Task A`, `Resource 1`,
  epoch-relative dates).

- Claude API prompt construction that concatenates verbatim parsed task
  names, WBS labels, or resource names into the prompt string. The
  sanitizer in `app/ai/sanitizer.py` must have rewritten these to labels
  before the prompt is built; a prompt that contains a raw `task.name`
  is a finding even if classification is toggled to unclassified.

[Cite: derived from Lessons Learned §9.1, §9.4, §9.5, and §12. Watchdog
signature catalog as-implemented is (inferred — not sourced) in its
specific pattern enumeration.]

## 4. What CUI Compliance Does NOT Mean

CUI discipline is narrowly scoped. Over-interpretation makes the tool
unshippable and undebuggable. The following are explicitly NOT restricted
by this skill.

- Metadata-only telemetry may be logged. Task counts, relation counts,
  CPM iteration count, elapsed parse time, file size in bytes, error
  class names, HTTP status codes on localhost calls to Ollama, and UUIDs
  for session and analysis objects are safe to emit to logs and to
  display in the UI. The prohibition in rule 2d is on content, not on
  metadata about the existence or shape of content.

- The tool's own source code is not CUI. The contents of `app/`,
  `tests/`, `docs/`, `.claude/`, and the build scripts are intended to be
  committed to a public or publicly-readable repository. Prompts, skill
  files, Pydantic schemas, exporter templates, and Chart.js rendering
  code contain no customer data and should be version-controlled
  normally.

- Internal project documentation is not CUI. The Build State Summary,
  the Lessons Learned document, the Prompt Engineering Reference Guide,
  and the approved NASA source extracts present in `docs/sources/` are
  authored by the analyst from public and internally-cleared material.
  They describe how the tool works, not what any particular customer's
  schedule contains.

- Open-source dependencies and model weights are not CUI. The Python
  package set declared in the tool's requirements, the bundled MPXJ
  JARs, the Chart.js and Tabulator.js libraries, and the
  `qwen2.5:7b-instruct` base model weights pulled by Ollama are publicly
  distributed and carry no CUI classification. Their presence in the
  tool's runtime tree, including the OneDrive-synced portable runtime,
  is not a CUI exposure. [Label: (inferred — not sourced). The
  open-source-and-weights carve-out is a practical corollary of the
  boundary logic in Lessons Learned §9.1; it is not written as an
  explicit bullet in the approved sources.]

[Cite: Lessons Learned §9.1 boundary logic distinguishing content from
metadata and from tooling.]

## 5. References

Sources cited in this skill are present in `docs/sources/` of this
repository unless otherwise noted.

- `Schedule_Forensics_Lessons_Learned.md` — §1 Operating Environment;
  §8B; §9.1 No schedule data egress / telemetry clause; §9.3 Session
  lifecycle and retention; §9.4 Git hygiene; §9.5 No silent cloud
  fallback; §9.6; §9.7; §10.4 Test fixture boundary; §12 Tier 1
  Synthetic fixtures only; §13 Commandment 8.

- `Schedule_Forensics_Prompt_Engineering_Reference_Guide_Ed1_4.docx` —
  referenced as the authoring source for the A.4 watchdog prompt that
  consumes the enforcement signatures in Section 3 of this skill.

- `N_PR_8000_004C_.pdf` (NPR 8000.4C) — p.5 Chapter 1 Introduction
  referencing NPD 2810.1; p.8 §1.2.1.4.d hackers and information
  system compromise, §1.2.1.5.a; p.14 §1.2.3.3 cybersecurity risk as
  an intentional threat; p.18 §2.2.7 CIO cybersecurity policy
  responsibilities (strongest NASA citation for the default-deny
  posture); p.23 item (9) information system Authorizing Official.

- `NID_7120_148_.pdf` (NID 7120.148) — p.111 §3.5 export control,
  sensitive and proprietary information handling; p.112 §3.8 System
  Security Plan with reference to NPR 2810.1.

- `GPR_7120_7B_Admin_Ext_08_09_2023.pdf` (GPR 7120.7B) — p.3 P.8
  Records retention with reference to NRRS 1441.1.

- `NASA_Acronyms.pdf` — present in `docs/sources/` but text extraction
  failed (the PDF is scanned or encrypted and not machine-readable in
  the current session). Referenced here for completeness; no textual
  citation is drawn from it.

External authority referenced but not stored in this repository:

- NPR 2810.1 (Security of Information and Information Systems) is
  referenced transitively via NPR 8000.4C p.5 and NID 7120.148 p.112.
  NPR 2810.1 itself is NOT present in `docs/sources/`. When this skill
  invokes NPR 2810.1 as authority, it does so through the two NASA
  documents that cite it, not from the NPR 2810.1 text directly.

Citations inside Sections 2 and 3 that are labeled
"(inferred — not sourced)" indicate a rule or control that is the
strictest tool-level implementation consistent with the sourced
principle, but is not itself verbatim in an approved citation. Those
labels exist so a later reviewer can upgrade the citation when a
primary source is located, or relax the control if policy evolves.

