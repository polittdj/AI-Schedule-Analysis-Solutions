# Phase 1 Build Context — AI Schedule Analysis Solutions

## 1. Project Identity

- Repo: `polittdj/AI-Schedule-Analysis-Solutions`
- Brand: ScheduleForensics LLC
- Local path convention: `C:\Tool\AI-Schedule-Analysis-Solutions`
- Workstation: HP ZBook Fury 16 G11, Windows 11 Enterprise, no local
  admin rights; portable Python/Java/Ollama runtime tree synchronized
  via OneDrive (CUI working directory held outside OneDrive per
  `cui-compliance-constraints §7`).
- Data sensitivity: CUI by default. All schedule data stays local;
  schedule files and pickled analyses never commit to git
  (`cui-compliance-constraints §§2a, 2c`).

## 2. Phase Identification

- Currently executing: **Phase 1** (tool build).
- Milestones: M1–M14 per `docs/BUILD-PLAN.md §5`.
- Deferred phases: **Phase 2** (multi-version trend analysis, RAG
  upgrade, custom Modelfile iteration) and **Phase 3** (full Earned
  Value Analysis). Explicit scope per BUILD-PLAN §§1.4, 1.5.

## 3. Branch Naming Convention

- Milestone build sessions: `claude/milestone-N-{scope}-YYYY-MM-DD`.
- Cleanup / audit / other session types:
  `claude/session-NN-{scope}-YYYY-MM-DD`.
- Override the harness if it proposes a different branch name.

## 4. One-Session-Per-Milestone Rule

- Each milestone is scoped for a single Claude Code session.
- Milestones flagged in BUILD-PLAN §5 as potentially multi-session
  (M11 manipulation engine, M13 UI) may decompose into `a` / `b`
  sub-sessions at build time if the first session under-runs.
- A milestone that exceeds two sessions is a decomposition candidate
  at plan-review time.

## 5. Canonical Specifications

- Authoritative Phase 1 spec: `docs/BUILD-PLAN.md`. Read in full
  before writing code in any milestone.
- Tagged-source dictionary: `docs/sources/README.md`.
- Domain knowledge base: `.claude/skills/` (see §6).

## 6. Domain Knowledge Base (`.claude/skills/`)

Eight authoritative skill directories; each milestone reads the
skills it references before coding:

- `cui-compliance-constraints`
- `mpp-parsing-com-automation`
- `driving-slack-and-paths`
- `dcma-14-point-assessment`
- `nasa-schedule-management`
- `nasa-program-project-governance`
- `forensic-manipulation-patterns`
- `acumen-reference`

Skills are read-only reference material in Phase 1 — milestones do
not modify them.

## 7. Known Bugs and Environmental Constraints

- COM automation parser (Milestone 3) requires MS Project installed
  on the host. Parser fails fast if the COM interface is absent; no
  CI runner exercises it.
- Java and Node.js PATH must be set manually per session when
  operating from the portable-runtime tree on OneDrive/Desktop.
- HP ZBook corporate IT agents (SentinelOne EDR, SCCM/CcmExec,
  Intune, BigFix, Splunk forwarders, Nessus) consume workstation
  resources and cannot be modified. The tool coexists with them per
  `cui-compliance-constraints §6`; it does not evade them.
- Auto-merge is disabled at the repo level (confirmed by user
  settings check). Every Claude Code PR opens as **DRAFT**.
- Three impulse-merge incidents are recorded (Sessions 2, 6,
  17/18). Operational mitigation: do **not** open the PR tab in a
  browser before pasting the audit verdict into build-chat.
- Stream-idle timeouts have been observed on long Write tool calls.
  Documents exceeding ~3,000 words are written via the chunked
  bash-heredoc append pattern (the same pattern used to author
  `docs/BUILD-PLAN.md`).
- Session resumption risk: the Claude Code harness occasionally
  resumes a stale session. If audit reports surface with the wrong
  branch or skill name, kill the session and restart.

## 8. Communication Style

- **Build-chat scope** (between Papicito and Claude): technical,
  terse, one action per message, with a plain-language explanation
  preceding each command and both success and failure signatures
  shown when running commands.
- **Tool-to-user voice** (web UI copy, DOCX / PDF / XLSX export
  narrative, error messages surfaced to the analyst): neutral,
  professional, specification-grade. Codified in Milestone 13 (UI)
  and the export modules.
