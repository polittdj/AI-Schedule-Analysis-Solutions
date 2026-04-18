---
name: dcma-14-point-assessment
description: DCMA 14-Point schedule health assessment — formulas, thresholds, forensic interpretation for all 14 checks; protocol versioning (pre-2009/early-2009/09NOV09/DCMA-EA PAM 200.1); Deltek DECM/Acumen 8 and NASA SMH overlays. Keywords DCMA 14-point, schedule health, schedule quality, IMS assessment, BEI, CPLI, missed tasks, high float, high duration, hard constraints, leads, lags, relationship types, logic check, critical path test, invalid dates, resources, DCMA-EA PAM 200.1, schedule assessment.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# DCMA 14-Point Assessment

Authoritative reference for running the DCMA 14-Point Schedule Health Assessment inside this forensic tool. Every substantive rule is cited to Ron Winter 2011 [RW], Edwards 2016 [ED], Deltek DECM Jan 2022 [DECM], Deltek Acumen 8.8 Metric Developers Guide [DMG], or the NASA Schedule Management Handbook 2024 update [SMH]. Rules not directly sourced are labelled `(inferred — not sourced)` with a Session-18 scope-defer note.

## 1. Purpose and scope

This skill covers the full 14-Point schedule quality check as published in the Defense Contract Management Agency's protocol: formula, threshold, rationale, and forensic interpretation for each check, plus protocol-versioning guidance, Deltek implementation deltas, and the NASA overlay. It is the deterministic-engine reference — the engine calculates the fourteen metrics from parsed schedule data, then the narrative layer phrases them.

This skill does **not** cover earned-value analysis (EVA). The 14-Point protocol formally decoupled from EVM in its 2012 publication as DCMA-EA PAM 200.1 [ED p.1], and in this tool EVA is deferred to Phase 3 per the build plan. This skill also does not restate parser-side field extraction, null handling, or dialog suppression (see §9 for cross-refs to `mpp-parsing-com-automation`), and does not restate driving-slack vs total-slack forensic distinctions (see `driving-slack-and-paths §2.3`).

The forensic framing is foundational: the 14-Point Assessment produces *indicators* that warrant further investigation, not pass/fail verdicts suitable for litigation on their own. Ron Winter is explicit that 14-Point results should never be used as the sole basis for a legal schedule dispute [RW p.20]. This caveat governs every downstream narrative this tool produces.

## 2. Protocol versioning and the DCMA-EA PAM 200.1 lineage

Three practitioner-recognized protocol revisions exist [RW pp.1–3]:

- **Pre-2009** — the original check list, activity-based counting, broader definition of "constraints," no 5%/5-day lag carve-out.
- **Early 2009** — transitional revision that tightened a handful of definitions but retained activity-based counting for the relationship check.
- **09 November 2009 revised ("09NOV09")** — the version most modern tools implement. It switches the relationship denominator from *activities* to *relationships* [RW p.5], introduces the 5-day / 5% leniency for lags in MSP and OpenPlan schedules [RW p.7], narrows "Hard Constraints" to four specific types (MFO, MSO, SNLT, FNLT) [RW p.8], adds an explicit rolling-wave exemption for the High Duration check [RW p.11], and clarifies the treatment of incomplete tasks in several denominators.

In 2012 the protocol was formally published as DCMA-EA PAM 200.1 and explicitly decoupled from EVM [ED p.1]. Subsequent contractor literature (including Edwards 2016) cites DCMA-EA PAM 200.1 as the authoritative text and restates several thresholds in slightly different language, but the numerics are substantively unchanged from 09NOV09.

**Version-selection rule for this tool:** default to the 09NOV09 definitions unless the schedule-under-test or the governing contract explicitly invokes an earlier revision. Where [RW] and [ED] disagree in formulation, the 09NOV09 text is used and the ED variant is noted inline. Where a numeric threshold is unresolved between the two, the skill labels it `(inferred — reconciliation deferred to Session 18)`.

## 3. Pre-check activity universe

All fourteen checks depend on agreed denominators. Two populations recur: **Total Tasks** and **Incomplete Tasks**.

- **Total Tasks** — per [RW p.4], excludes summary tasks, subproject roll-ups, level-of-effort (LOE) tasks, zero-duration tasks (which are milestones), and any task at 100% complete. What remains is the working detail-task population used as the denominator for most checks.
- **Incomplete Task** — per the 09NOV09 clarification [RW p.5], a task with `% complete < 100%` as of the status date. This is the denominator used for high-float, high-duration, resources, and several other checks that only make sense against work still in the forecast.
- **Relationships** — the 09NOV09 revision counts **relationships** (links) rather than activities for the lag/lead/type checks [RW p.5]; earlier versions counted *activities carrying* a lag/lead/type, which double-counts tasks with multiple outgoing links. This tool uses the 09NOV09 relationship-counting rule by default.

Field extraction, null handling, and MS-Project dialog suppression are not duplicated here — see `mpp-parsing-com-automation §3.2` (dialog suppression) and `§3.4` (null tasks in Tasks collection).

## 4. The 14 checks

Each subsection gives the formula, threshold, rationale, and forensic interpretation in under six lines. Worked numeric examples live in §5.

### 4.1 Check 1 — Logic (1a Missing Logic, 1b Dangling)

- **1a Missing Logic.** Percentage of incomplete tasks with zero predecessors *or* zero successors, excluding the project start milestone (no predecessor) and project finish milestone (no successor) [RW pp.5–6; ED p.1]. Threshold: ≤5%.
- **1b Dangling.** Tasks whose *start* has no predecessor driver or whose *finish* has no successor driver — i.e. an SS-only predecessor leaves the finish dangling; an FF-only successor leaves the start dangling [RW p.6]. Threshold: ≤5% (09NOV09).
- **Rationale.** Missing or dangling logic means the CPM network cannot propagate delay end-to-end. A schedule that fails Logic cannot drive forecast dates reliably.
- **Forensic read.** High Logic failures frequently correlate with later CPT failure (§4.12) and are a classic precursor to manipulation patterns that hide slip behind unconnected tails.

### 4.2 Check 2 — Leads

- **Formula.** Count of relationships with negative lag, divided by total relationships [RW p.6].
- **Threshold.** 0% (any lead flags) [RW p.6; ED].
- **Rationale.** A lead lets a successor start before its predecessor finishes, violating the semantics of FS logic and producing undefined behaviour under time-impact analysis.
- **Forensic read.** Leads are a common "compression" tactic — used to manufacture end-date compliance without re-sequencing work.

### 4.3 Check 3 — Lags

- **Formula.** Count of relationships with positive lag, divided by total relationships.
- **Threshold.** 09NOV09 revision: ≤5% with a **5-day lag carve-out** — lags of five working days or fewer are excused, but *only in Microsoft Project and OpenPlan schedules*; Primavera P6 schedules do **not** receive the carve-out [RW p.7]. Earlier revisions: 0% (any lag flags).
- **Rationale.** Long lags conceal unmodeled work and are a standard vector for hiding duration.
- **Forensic read.** Pair with §4.1 (Logic) and §4.5 (Hard Constraints) — lag plus dangling logic plus constraint pinning is the classic compression fingerprint.

### 4.4 Check 4 — Relationship Types

- **Formula.** FS relationships divided by total relationships.
- **Threshold.** ≥90% FS [RW p.7; ED]. Ron Winter 2011 reports the 09NOV09 text explicitly; Edwards 2016 restates it as the same 90% floor.
- **Rationale.** Non-FS types (SS, FF, SF) are harder to interpret under delay-impact analysis and mask the work-flow sequence.
- **Forensic read.** A sudden drop in FS-share between versions is a re-baselining signature.

### 4.5 Check 5 — Hard Constraints

- **Formula.** Count of tasks carrying a hard constraint, divided by Total Tasks.
- **Threshold.** ≤5% [RW p.8].
- **Definition delta.** The 09NOV09 revision narrows "hard" to exactly four constraint types: Must-Finish-On (MFO), Must-Start-On (MSO), Start-No-Later-Than (SNLT), and Finish-No-Later-Than (FNLT) [RW p.8]. Earlier revisions also counted As-Late-As-Possible and several soft constraints, which produced false-positive spikes. Both [RW p.8] and [ED] cite the 09NOV09 four-constraint list; this skill follows that definition.
- **Forensic read.** Hard constraints override CPM float and are the single most common manipulation vector — §4.5 drives most constraint-abuse findings downstream in `forensic-manipulation-patterns`.

### 4.6 Check 6 — High Float

- **Formula.** Count of incomplete tasks with total float greater than 44 working days, divided by Incomplete Tasks.
- **Threshold.** ≤5% [RW p.10].
- **Rationale.** Float above ~two months suggests missing logic, an inflated baseline, or unresourced parallel work; it also broadens the near-critical band artificially.
- **Forensic read.** High float is rarely *the* problem — it is a tell for one of the three root causes above, typically uncovered by correlating §4.6 with §4.1 and §4.10.

### 4.7 Check 7 — Negative Float

- **Formula.** Count of tasks with total float less than zero, divided by Total Tasks.
- **Threshold.** 0% [RW p.11].
- **Rationale.** Negative float means the schedule is forecasting a miss against its driving constraint as of the status date.
- **Forensic read.** Zero tolerance is enforced because negative float indicates the network is internally infeasible; any occurrence is a finding.


### 4.8 Check 8 — High Duration

- **Formula.** Count of incomplete tasks with remaining working duration greater than 44 working days, divided by Incomplete Tasks.
- **Threshold.** ≤5% [RW p.11].
- **Rolling-wave exemption.** The 09NOV09 revision excludes planning packages and rolling-wave placeholders that are marked as such in the schedule [RW p.11]; earlier versions applied the 44-day ceiling uniformly and therefore false-flagged routine rolling-wave planning. Ron Winter 2011 cites the 09NOV09 carve-out; Edwards 2016 preserves the carve-out; this skill defaults to the 09NOV09 text.
- **Rationale.** Long-duration activities obscure progress and defer discovery of slip until late in the period of performance.
- **Forensic read.** A jump in high-duration share across revisions is an early warning for baseline inflation.

### 4.9 Check 9 — Invalid Dates (9a Forecast, 9b Actual)

- **9a Forecast-before-status.** Any forecast (early/late) start or finish dated before the status date [RW p.12]. Threshold: 0%.
- **9b Actual-after-status.** Any actual-start or actual-finish dated after the status date [RW pp.12–13]. Threshold: 0%.
- **Rationale.** Forecast dates before the status date mean the update did not refresh the forecast; actuals after the status date are temporally impossible and usually indicate a data-entry error or a status-date misalignment.
- **Forensic read.** §4.9 hits almost always signal a broken update cycle — correlate with the dangling-logic count before blaming the scheduler.

### 4.10 Check 10 — Resources

- **Formula.** Count of incomplete tasks with zero resource assignments (labor, material, or equipment), divided by Incomplete Tasks.
- **Threshold.** **Ratio only, no pass/fail threshold** under the 09NOV09 protocol — the protocol reports the percentage but does not define a flag line [RW p.13].
- **Rationale.** Unresourced tasks cannot participate in cost or labour-hour projections, and therefore decouple the schedule from earned-value and capacity analysis.
- **Forensic read.** Interpret %-unresourced in context: a schedule that is 100% unresourced is normal for a programme where cost is tracked outside the IMS; a schedule that is 30% unresourced is a hybrid that needs explanation. Edwards 2016 restates the "no threshold" framing [ED]; Ron Winter 2011 is explicit that the 09NOV09 protocol does not set one [RW p.13].

### 4.11 Check 11 — Missed Tasks

- **Formula.** Count of incomplete tasks whose baseline finish is on or before the status date, divided by Total Tasks [RW p.13; ED p.2].
- **Threshold.** ≤5% [RW p.13].
- **Rationale.** A task that should have finished by the status date but has not is direct evidence of slip against baseline.
- **Forensic read.** Missed-task share trending upward across versions is the clearest leading indicator of schedule failure and is the ground-truth input to §4.14 BEI.

### 4.12 Check 12 — Critical Path Test (CPT)

- **Formula.** Select a task on the critical path, add a delay (canonical value: 600 working days) to its remaining duration, re-run CPM, and compare the new project finish to the original. If the project finish moves by the full delay amount, the network passed; if it moves by less (or not at all), the network failed [RW p.14].
- **Threshold.** Boolean pass/fail — no percentage.
- **Rationale.** A well-connected network must propagate delay end-to-end. Failure indicates open-ended successors, broken logic, or hard constraints that pin the finish.
- **Forensic read.** A CPT failure is rarely the whole story — always trace the test task's driving path (`driving-slack-and-paths §5`) to identify where propagation stopped.

### 4.13 Check 13 — Critical Path Length Index (CPLI)

- **Formula.** CPLI = (Critical Path Length + Total Float to contractual finish) / Critical Path Length [RW p.15; ED].
- **Threshold.** ≥0.95.
- **Rationale.** CPLI measures the schedule's remaining float as a fraction of its driving-path length. Values below 0.95 mean the schedule has lost more than 5% of its planned float against the contract-finish anchor.
- **Forensic read.** CPLI is the single most sensitive lagging indicator of programmatic compression. A drop from 1.02 to 0.94 across two periods is a more serious finding than a drop from 1.50 to 1.40, even though the delta is smaller.

### 4.14 Check 14 — Baseline Execution Index (BEI)

- **Formula.** BEI = (Number of tasks actually completed by the status date) / (Number of tasks with baseline finish on or before the status date) [ED p.2; RW p.16]. The 09NOV09 protocol uses cumulative counts — tasks completed *at any time* up to the status date divided by tasks whose baseline finish was *on or before* the status date. Edwards 2016 emphasises that the numerator counts tasks that "hit" the status-date target even if they hit late [ED].
- **Threshold.** ≥0.95 [RW p.16; ED].
- **Rationale.** BEI is the cumulative execution-velocity ratio — values below 0.95 mean the project has not been finishing tasks at the baseline rate.
- **Forensic read.** BEI pairs with Missed Tasks (§4.11): BEI is the velocity lens, Missed Tasks is the inventory lens, and they almost always move together. Ron Winter 2011 and Edwards 2016 both cite the 0.95 floor; this skill uses ED's cumulative-with-hit-task definition because it is the restatement most tools now implement.

## 5. Worked examples

Only two worked examples are included; every other check's formula and threshold stand alone in §4.

### 5.1 BEI cumulative calculation [ED p.2]

200-task schedule, status date 30 Jun. Baseline shows 80 tasks due by 30 Jun; 68 actually completed by 30 Jun (on-time or late but hit). A further 3 tasks with baseline 15 Jul also finished early by 30 Jun.

- Denominator = baseline finish ≤ status date = 80.
- Numerator = tasks completed by status date *whose baseline was ≤ status date* = 68. Early-finishing tasks with later baselines are excluded — their denominator row is outside the BEI window.
- BEI = 68 / 80 = 0.85 → < 0.95 ⇒ flag.

### 5.2 CPLI calculation [RW p.15; ED]

Critical path length 250 working days; total float to contractual finish –10 WD (forecast 10 WD late):

- CPLI = (250 + (–10)) / 250 = 0.96 ⇒ pass.

Same project, total float –20 WD:

- CPLI = (250 + (–20)) / 250 = 0.92 ⇒ fail.

Narrative should report the cross-period delta (0.96 → 0.92, four float points lost) rather than the single snapshot (see §6 Rule 2).

## 6. Forensic interpretation rules

Four rules govern how this tool uses 14-Point results:

1. **Results are indicators, not verdicts.** Ron Winter is emphatic that 14-Point output is *not* sufficient evidence for a legal schedule dispute on its own [RW p.20]. All tool-generated narratives must frame check failures as items for further forensic investigation, never as standalone findings of fault.
2. **Cross-version trend is more probative than a single snapshot.** A single IMS revision with 7% hard constraints is an issue; three consecutive revisions trending 4% → 6% → 9% is a pattern. This rule is not lifted from [RW] or [ED] (inferred — not sourced; Session-18 scope-defer: empirical trend-thresholds to be added once sufficient case-history is in the RAG corpus).
3. **Deltek tool output may differ from DCMA protocol.** Acumen and DECM reimplement the checks with their own denominators, filters, and occasionally different thresholds. Cross-check tool percentages against §4 before reporting [DECM; DMG]; §7 lists the known deltas.
4. **Expert-witness use routes through Appendix B.** Ron Winter 2011 Appendix B's fifteen expert-witness questions frame litigation-grade 14-Point use; any narrative flagged for litigation export must cite Appendix B and pre-answer the most relevant questions [RW Appendix B].


## 7. Deltek DECM / Acumen 8 implementation notes

Mapping and deltas for the Deltek DECM metric set and Acumen 8 Schedule Health ruleset:

- **Logic** → split into DECM "Missing Predecessors" + "Missing Successors"; aggregate before comparing to DCMA Logic [DECM *Metrics*].
- **Leads / Lags** → DECM "Negative Lag" / "Positive Lag"; thresholds match at 0% and ≤5%. DECM does not auto-apply the 09NOV09 MSP/OpenPlan 5-day carve-out, so Acumen %-lag reads higher than protocol on MSP schedules [DECM; DMG].
- **Relationship Types** → DECM "FS Relationship %"; threshold matches at ≥90% [DECM].
- **Hard Constraints** → DECM "Hard Constraint %"; constraint list is user-configurable — verify the rule-editor list before trust [DMG].
- **High Float / High Duration** → DECM "Total Float Days" / "Task Duration Days"; 44-day ceiling is a ruleset parameter — confirm it is set to 44 [DMG].
- **Negative Float, Invalid Dates, Missed Tasks, Resources** → DECM rows match DCMA thresholds (0%, 0%, ≤5%, ratio-only) [DECM].
- **CPT** → not a standard DECM row; Acumen's Logic Check covers integrity but not the 600-day propagation test — run through this tool's engine [DMG].
- **CPLI, BEI** → DECM rows match DCMA ≥0.95 floor; DECM BEI denominator matches the §4.14 cumulative-hit definition [DECM].

Custom Acumen 14-Point rulesets must follow [DMG] formula-syntax conventions; deeper Acumen content lives in `acumen-reference`.

## 8. NASA overlay

The NASA Schedule Management Handbook (2024 update) references the DCMA 14-Point Assessment as a recommended schedule-health check [SMH §*Schedule Health Assessment*]. Key overlay points:

- NASA endorses the 14-Point protocol without overriding its thresholds; [SMH] restates DCMA numerics where it cites them and layers agency-specific rules on top rather than replacing them.
- **Schedule margin ≠ total float.** NASA schedule margin is a deliberate reserve owned by the project manager; total float is an emergent CPM by-product. The §4.6 High-Float denominator must exclude tagged schedule-margin tasks [SMH §*Schedule Margin*].
- NASA governance milestones (KDP, SRR, PDR, CDR) legitimately drive MSO/FNLT use, so elevated §4.5 Hard-Constraint rates on NASA IMSs must be triaged against governance before being reported as manipulation. Governance conventions live in `nasa-program-project-governance`.
- No known [SMH]/DCMA numeric conflicts; DCMA numerics default.

## 9. Cross-skill dependencies

- **Field extraction, null handling, dialog suppression** — see `mpp-parsing-com-automation §3.4` (null tasks in Tasks collection) and `§3.2` (Visible=False, DisplayAlerts=False before open). Not duplicated here.
- **Driving slack vs total slack distinction; relationship-slack definition** — see `driving-slack-and-paths §2.3`. The §4.6 (High Float) and §4.7 (Negative Float) denominators use total slack per DCMA; driving-slack-based analyses are a separate forensic layer.
- **Local-only processing; CUI gate** — see `cui-compliance-constraints`. The 14-Point engine runs entirely on local data; no check result is transmitted off-host unless the project is classification-cleared and the operator has explicitly opted into the Claude API route.

## 10. Inferred content + scope-defers (single-table summary)

| # | Section | Inferred claim | Scope-defer |
|---|---------|----------------|-------------|
| 1 | §2 | Threshold reconciliation rule where RW/ED disagree numerically | Session 18 — extract full RW/ED threshold tables side-by-side |
| 2 | §6 Rule 2 | "Cross-version trend more probative than single-snapshot score" | Session 18 — empirical trend thresholds once RAG case-history suffices |

## 11. References

| Section | Claim | Source |
|---------|-------|--------|
| §1, §6 Rule 1, §6 Rule 4 | Indicators-not-verdicts framing; Appendix B expert-witness questions | [RW p.20; RW Appendix B] |
| §2 | Three protocol versions; 09NOV09 definitions; DCMA-EA PAM 200.1 2012 publication; EVM decoupling | [RW pp.1–3; ED p.1] |
| §3 | Total Tasks definition; Incomplete Task clarification; relationship-counting rule | [RW pp.4–5] |
| §4.1 | Missing Logic and Dangling definitions; ≤5% threshold | [RW pp.5–6; ED p.1] |
| §4.2 | Leads at 0% | [RW p.6; ED] |
| §4.3 | Lags ≤5% with 09NOV09 5-day MSP/OpenPlan carve-out | [RW p.7] |
| §4.4 | ≥90% FS | [RW p.7; ED] |
| §4.5 | Hard Constraints ≤5%; 09NOV09 4-constraint list (MFO/MSO/SNLT/FNLT) | [RW p.8; ED] |
| §4.6 | High Float >44 working days, ≤5% | [RW p.10] |
| §4.7 | Negative Float 0% | [RW p.11] |
| §4.8 | High Duration >44 working days, ≤5%; rolling-wave exemption | [RW p.11; ED] |
| §4.9 | Invalid-dates 9a forecast, 9b actual; 0% each | [RW pp.12–13] |
| §4.10 | Resources ratio with no threshold | [RW p.13; ED] |
| §4.11 | Missed Tasks ≤5% | [RW p.13; ED p.2] |
| §4.12 | CPT 600-day propagation test, Boolean pass/fail | [RW p.14] |
| §4.13 | CPLI ≥0.95 | [RW p.15; ED] |
| §4.14 | BEI ≥0.95; cumulative-hit numerator | [RW p.16; ED p.2] |
| §5.1 | BEI worked example | [ED p.2] |
| §5.2 | CPLI worked example | [RW p.15; ED] |
| §7 | Deltek DECM mapping and deltas | [DECM sheet *Metrics*; DMG] |
| §8 | NASA overlay and schedule-margin exclusion | [SMH §*Schedule Health Assessment*; §*Schedule Margin*] |
| §9 | Cross-skill cross-refs | `mpp-parsing-com-automation §3.2, §3.4`; `driving-slack-and-paths §2.3`; `cui-compliance-constraints` |
