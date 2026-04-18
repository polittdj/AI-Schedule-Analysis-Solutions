---
name: cui-compliance-constraints
description: CUI (controlled unclassified information) handling for this schedule-forensics tool. Schedule files (.mpp .xer .xml .pmxml .mpx .csv .xlsx) are CUI by default. Enforces data locality, local-only Ollama inference, cloud-egress prohibition, no-git-commit, dual-mode AI (Ollama default, Claude opt-in unclassified only). Covers no-admin-rights enterprise workstations with monitoring agents (SentinelOne), OneDrive sync, portable installs. Load before reading schedule files or configuring HTTP egress.
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

[Cite: [LL] §1 "Operating Environment." NASA cybersecurity-policy
authority (e.g., NPR 2810.1) is scope-deferred to post-Phase-B review —
topic not yet carried in cross-skill sources.]

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

[Cite: [LL] §9.1 "No schedule data egress"; [LL] §13 Commandment 8. The
underlying NASA cybersecurity-policy citation (e.g., NPR 2810.1) is
scope-deferred to post-Phase-B review — topic not yet carried in
cross-skill sources.]

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

[Cite: [LL] §9.5 "No silent cloud fallback"; [PRNS] dual-mode-AI scope
brief. System Security Plan authority is scope-deferred to post-Phase-B
review — topic not yet carried in cross-skill sources.]

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

[Cite: [LL] §9.4 "Git hygiene"; [LL] §10.4 "Test fixture boundary."
NASA records-retention authority is scope-deferred to post-Phase-B
review — topic not yet carried in cross-skill sources.]

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
explicitly change classification and resubmit. [Cite: [LL] §9.5 sources
the prohibition on silent fallback. The specific halt-versus-error-
fallback enforcement in this tool is (inferred — not sourced) from the
prohibition; it is the strictest implementation consistent with §9.5 and
is tagged for Session 19 or post-Phase-B review to confirm no less-strict
alternative is preferred.]

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
[LL] §9.5 rather than an explicit requirement cited in the approved
sources. Tagged for Session 19 or post-Phase-B review to upgrade or
relax the banner requirement once a primary source is located.]

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

[Cite: derived from [LL] §9.1, §9.4, §9.5, and §12. Watchdog signature
catalog as-implemented is (inferred — not sourced) in its specific
pattern enumeration, and is tagged for Session 19 or post-Phase-B review
to confirm the enumeration is complete as the tool matures.]

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
  boundary logic in [LL] §9.1; it is not written as an explicit bullet
  in the approved sources, and is tagged for Session 19 or post-Phase-B
  review to capture a primary source if one is identified.]

[Cite: [LL] §9.1 boundary logic distinguishing content from
metadata and from tooling.]

## 5. Cloud-Egress Prohibition — Comprehensive Enumeration

Section 2a states the no-egress rule in broad terms. This section enumerates
the specific external services the tool must never contact, so that a
reviewer can audit a diff against an explicit list rather than against a
principle.

- No Acumen cloud, licensing callbacks, or telemetry endpoints. Acumen
  reference data is consulted entirely offline (see acumen-reference §7.4
  for the API-isolation posture).
- No OpenAI, Google Gemini, Cohere, Mistral API, Together, Replicate, or
  any other third-party LLM API under any circumstance. The AI interface
  is restricted to Ollama and Anthropic, with Anthropic gated behind
  classification.
- Claude API is permitted only when classification is explicitly toggled
  to unclassified. It is never the default. The toggle lives in the web
  UI, not in a configuration file that an automated script could flip
  silently. [Cite: [LL] §9.5.]
- Ollama is the default for CUI work and runs on `http://localhost:11434`
  with no outbound network calls. Ollama model pulls happen at install
  time only, against a pre-approved base-image source, and never during
  analysis.
- No cloud Git forges for CUI data — schedule files, pickled analyses, or
  any CUI extract must never be pushed. Skills, prompts, and non-CUI
  source code go to GitHub; schedules never do. [Cite: [LL] §9.4.]
- No cloud telemetry, crash-reporting services, or anonymous usage
  statistics. Error reporting writes to local log files only, subject to
  the logging rule in Section 2d.
- No auto-update channels that pull from arbitrary URLs. Dependency
  updates are handled through the portable-install workflow described in
  [PRNS]; the tool does not phone home to check for updates, model
  revisions, or license entitlement.

(inferred — not sourced; to be reviewed in Session 19 master-build-plan
scope as a first-class enforcement table distinct from this narrative.)

## 6. Corporate-IT Monitoring — Posture and Boundaries

The workstation runs enterprise monitoring agents. SentinelOne EDR,
Microsoft SCCM/CcmExec, Intune, BigFix, Splunk forwarders, and Nessus
scanners are expected to be present. The tool is designed to coexist with
these agents, not to evade them.

- Tool operations, including in-memory parsed schedule content, are
  observable by EDR. The tool does not attempt memory isolation, process
  hiding, or anti-forensic techniques. If EDR flags the Python process,
  IT escalation is the correct response, not tool-side evasion.
- Without local administrator rights the tool cannot add firewall rules,
  register services, or install kernel modules. Controls are enforced
  entirely in-process and through file-system conventions the logged-in
  user can apply.
- The tool MUST NOT obfuscate its network behavior, mask process names,
  or persist credentials outside the user profile. Transparency to
  corporate IT is a security feature of this tool, not a bug.
- If corporate policy requires schedule data reporting to a central
  archive — for example a records-management SharePoint or a
  contract-closeout data room — the tool defers to that workflow; it
  does not attempt to substitute for compliance channels, nor does it
  duplicate the archival function.

(inferred — not sourced; derived from the CLAUDE.md workstation context
described in Section 1, to be reviewed in Session 19 master-build-plan
scope.)

## 7. Data-at-Rest — OneDrive Sync Implications

Portable installs of Python, Java, Ollama, and the tool tree live under
`C:\Users\{user}\OneDrive - NASA\Desktop\` per the project's operating
context. OneDrive replicates this path to Microsoft cloud storage, which
creates a subtle exposure path if CUI data is written anywhere inside the
sync scope.

- The tool's working directory for parsing, pickling, and exporting CUI
  schedules MUST live outside OneDrive sync scope. A safe convention is
  `C:\Tool\AI-Schedule-Analysis-Solutions\workspace\` or any equivalent
  non-synced local path; the specific path is an install-time choice as
  long as it sits outside the OneDrive root.
- Non-CUI configuration — skill files, the Ollama Modelfile, UI theme
  preferences — may reside within the user profile and OneDrive scope.
  These are source-code artifacts and carry no customer schedule data.
- Log files that could capture exception text traceable to a schedule
  MUST target a non-synced path. The tool's default log directory is
  configured in the workspace root above, not under the user profile.
- Pickled analysis blobs (`analysis_<uuid>.pkl`) are by policy
  short-lived and session-scoped (Section 2h). Those blobs also MUST NOT
  be written to any OneDrive-synced path, even transiently, because the
  sync engine can capture a file between write and delete.

(inferred — not sourced; derived from the CLAUDE.md workstation context
described in Section 1, to be reviewed in Session 19 master-build-plan
scope.)

## 8. Cross-Skill Pointers

CUI discipline intersects several other skills in this project. When
working in a code path that sits at one of those intersections, consult
the target skill for authoritative treatment of the non-CUI dimensions.

- NASA governance framing for CUI-rated programs →
  nasa-program-project-governance §2 (two-authority governance) and §3
  (program categorization).
- IMS quality and schedule-health expectations that overlay CUI handling
  → nasa-schedule-management §6 (schedule health and quality).
- Driving-path and driving-slack analysis data locality and cross-version
  matching → driving-slack-and-paths.
- MSP COM-automation data-handling gotchas, including zombie-process
  hygiene that could otherwise leak open-file handles on CUI data →
  mpp-parsing-com-automation §3 (Appendix D gotchas).
- Forensic manipulation-detection workflow under CUI — including why
  certain detection patterns must run offline — see
  forensic-manipulation-patterns.
- Acumen and DECM reference lookups that the tool consults offline rather
  than via the Acumen API → acumen-reference §7.4.
- DCMA 14-Point assessment overlays and the interaction between DCMA
  thresholds and CUI-safe reporting → dcma-14-point-assessment.

## 9. References

Approved sources for this skill (tag → file):

- [LL] `Schedule_Forensics_Lessons_Learned.md` — §1 Operating Environment;
  §8B; §9.1 No schedule data egress / telemetry clause; §9.3 Session
  lifecycle and retention; §9.4 Git hygiene; §9.5 No silent cloud
  fallback; §9.6; §9.7; §10.4 Test fixture boundary; §12 Tier 1
  Synthetic fixtures only; §13 Commandment 8.

- [PERG] `Schedule_Forensics_Prompt_Engineering_Reference_Guide_Ed1_4.docx`
  — authoring source for the A.4 watchdog prompt consumed by the
  enforcement signatures in Section 3.

- [PRNS] `Papisito_Paste_Ready_Next_Steps.docx` — scope brief for
  dual-mode-AI routing referenced in Section 2b and for the portable-
  install update workflow referenced in Section 5.

- [UPT] `Universal_Claude_Code_Master_Prompt_Template.txt` — template
  inputs to the A.4 watchdog prompt; referenced by Section 3 through
  [PERG].

- [UPT2] `Universal_Claude_Code_Master_TooL_Development_Prompt_Template.txt`
  — tool-development template inputs referenced by Section 3 through
  [PERG].

- [V3P] `Schedule-Forensics-Claude-Code-Prompt-v3.md` — current-generation
  operator prompt that consumes this skill at runtime.

Cross-skill pointers used in place of direct rule-bearing citations to
NASA-governance documents (NPR 8000.4C, NID 7120.148, GPR 7120.7B,
SMH, NPR 2810.1) and to Deltek Acumen documentation:

- nasa-program-project-governance — holds the authoritative NASA
  programmatic-governance citations (NPR 8000.4C, NID 7120.148, GPR
  7120.7B, SMH overlap). NASA cybersecurity, records-retention, and
  System Security Plan authorities (e.g., NPR 2810.1) are scope-deferred
  to post-Phase-B review — these topics are not yet carried in
  cross-skill sources.

- nasa-schedule-management — holds SMH IMS-integrity framing consulted
  where CUI handling intersects schedule-health expectations (Section 8).

- forensic-manipulation-patterns — holds DECM/DMG/manipulation-detection
  references consulted where CUI data-egress concerns intersect
  manipulation-pattern detection.

- acumen-reference — holds Deltek Acumen documentation references
  consulted entirely offline; this skill points at §7.4 rather than
  inlining Acumen quotations.

Citations labeled "(inferred — not sourced)" inside Sections 2, 3, 5, 6,
and 7 indicate a rule or control that is the strictest tool-level
implementation consistent with the sourced principle but is not itself
verbatim in an approved citation. These are tagged for Session 19 or
later review so a later reviewer can upgrade the citation when a primary
source is located, or relax the control if policy evolves.

