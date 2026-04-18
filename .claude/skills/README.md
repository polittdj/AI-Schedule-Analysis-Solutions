# Skill Library

This directory holds the Claude Code skill library for the Schedule
Forensics Local Tool. Each subdirectory is a single skill with a
`SKILL.md` manifest; each skill's body is the authoritative reference
for its scope.

## Skills (all populated, Phase B complete)

- `cui-compliance-constraints/` — Controlled Unclassified Information
  (CUI) handling rules, cloud-egress prohibition, dual-mode AI routing
  (Ollama default, Claude API opt-in only for unclassified work), and
  posture for no-admin-rights enterprise workstations with monitoring
  agents and OneDrive-sync scope.
- `nasa-schedule-management/` — NASA Schedule Management Handbook (SMH,
  2024 Rev 2) practice: IMS construction, schedule margin, rolling-wave
  planning, schedule BoE, schedule health overlay on DCMA 14-Point,
  Schedule Risk Assessment (SRA), status-date discipline, replan vs.
  rebaseline.
- `nasa-program-project-governance/` — NASA programmatic and
  institutional authority, Technical Authority, program/project
  categorization, Key Decision Points (KDPs), Life-Cycle Reviews,
  Decision Authority, PMC hierarchy, Agency Baseline Commitment,
  Management Agreement, JCL, Funded Schedule Margin (FSM) and UFE,
  Decision Memoranda, BPR cadence.
- `dcma-14-point-assessment/` — DCMA 14-Point schedule-health formulas,
  thresholds, and forensic interpretation for all 14 checks; protocol
  versioning (pre-2009 / early-2009 / 09NOV09 / DCMA-EA PAM 200.1); NASA
  SMH and Deltek DECM/Acumen 8 overlays.
- `driving-slack-and-paths/` — Forensic CPM driving path and driving
  slack analysis; SSI focus-point methodology vs. total slack and free
  slack; task-specific driving path trace from a UniqueID; near-critical
  band classification; eroding slack across versions; Period A slack
  rule for but-for analysis; CPM discipline invariants.
- `forensic-manipulation-patterns/` — Manipulation-pattern detection
  protocol across IMS versions: logic tampering, constraint injection,
  duration compression, date edits, float inflation, critical-path
  gaming, cross-version erosion, red-flag aggregation.
- `mpp-parsing-com-automation/` — Microsoft Project `.mpp` parsing via
  win32com COM automation as the primary reader; ten Appendix D
  gotchas; MPXJ / JPype1 subprocess fallback; UniqueID cross-version
  matching; MS-Project-UI validation discipline.
- `acumen-reference/` — Deltek Acumen 8.8 / DECM reference layer:
  metric-semantics dictionary, DECM Jan 2022 catalog structure, Special
  Fields, MPP field mapping, cost-data CSV structure (EVA deferred to
  Phase 3), Acumen API surface and why this tool does not call it,
  release-note deltas.

## Status

All 8 skills are populated and merged on `main`. Phase B is complete.
The build sequence across Phase B was:

| Session | Skill                                   | PR  |
| ------- | --------------------------------------- | --- |
| 11      | `nasa-schedule-management`              | #10 |
| 12      | `driving-slack-and-paths`               | #11 |
| 13      | `nasa-program-project-governance`       | #13 |
| 14      | `mpp-parsing-com-automation`            | #14 |
| 15      | `dcma-14-point-assessment`              | #15 |
| 16      | `acumen-reference`                      | #16 |
| 17      | `forensic-manipulation-patterns`        | #17 |
| 18      | `cui-compliance-constraints`            | #18 |

Session counts: 18 sessions total across Phase B, 8 skills merged via
PRs #10, #11, #13, #14, #15, #16, #17, #18. Session 18a ran the
cross-skill audit; Session 18b applies the audit's cleanup backlog;
Session 19 produces the master build plan at `docs/BUILD-PLAN.md`.

## Conventions

- **File path convention.** Each skill lives at
  `.claude/skills/{skill-name}/SKILL.md` with the directory name
  matching the skill `name` in the YAML frontmatter. No loose skill
  files at the top level.
- **Branch naming convention.** Per-skill branches follow
  `claude/populate-{skill}-skill-YYYY-MM-DD` during Phase B. Cleanup
  branches follow `claude/session-{N}-cleanup-sweep-YYYY-MM-DD`.
- **Source-approval matrix.** Each skill enforces a per-skill
  source-approval matrix; cross-skill pointers are used where a skill
  would otherwise need to cite a document outside its approved set.
  See `docs/sources/README.md` for the full tag dictionary and file
  manifest.
- **Structural gates.** YAML `description` ≤ 500 characters; body
  2,800–3,450 words; body + references ≤ 3,500 words. Enforced
  per-commit by audit.
