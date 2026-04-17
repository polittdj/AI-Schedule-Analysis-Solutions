---
name: forensic-manipulation-patterns
description: Forensic schedule-manipulation patterns across IMS versions: logic tampering, constraint injection, duration compression, date edits, float inflation, critical-path gaming, cross-version erosion. Detection protocol for two-or-more MPP revisions matched by UniqueID. Keywords forensic, manipulation, schedule fraud, logic tampering, constraint injection, float inflation, critical-path gaming, cross-version erosion, as-planned vs as-built, TIA, collapsed as-built, delay claim, baseline tampering.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# Forensic Manipulation Patterns

Detection protocol and interpretation of forensic schedule-manipulation signatures across two or more versions of a Microsoft Project IMS. Every substantive rule cites an approved source: [SSI] Arnold/SSI NASA Driving Slack, [LL] Schedule Forensics Lessons Learned, [SMH] NASA Schedule Management Handbook (2024 update), [DECM] Deltek DECM Metrics (Jan 2022), [DMG] Deltek Acumen 8.8 Metric Developers Guide, [RW] Ron Winter 2011, and [ED] Edwards 2016. Rules not directly sourced are labelled `(inferred — not sourced)` with a Session-18 scope-defer note in §13.

## 1. Purpose and scope

This skill describes how to recognise schedule-manipulation patterns in parsed IMS data — logic tampering, duration compression, date edits, float inflation, critical-path gaming, cross-version erosion — and the aggregation rule that converts signals into a defensible finding.

It does **not** re-derive DCMA 14-Point mechanics — [RW]/[ED] thresholds appear only as diagnostic context; formulas and denominators live in `dcma-14-point-assessment §4`. It does not re-derive CPM or driving-slack math — see `driving-slack-and-paths §§2–5`. It does not restate MPP field extraction — see `mpp-parsing-com-automation §3`. Aggregation is protocol-level, not a score formula.

Forensic framing, per [RW p.20]: findings are *indicators* warranting investigation, not verdicts suitable for litigation alone. Signals motivate questions; evidence answers them.

## 2. What manipulation detection IS — and what it is NOT

Manipulation detection is the comparison of two or more IMS revisions — matched **exclusively by UniqueID** [LL §5; §13 commandment #3] — to isolate edits that change forecast outcome, critical-path membership, or float distribution without a commensurate change in recorded work. A signal motivates a question; absence is not a clean bill of health. [RW p.20] applies.

The following are **not** manipulation and must be excluded before any finding is raised:

- **Contractually-authorized changes.** Change orders, directed-scope additions, and NASA-governed replans documented in the Schedule BoE [SMH §5.4 pp.73–74] or a Decision Memorandum [SMH §7.3.4.7 pp.331–332] are legitimate edits.
- **Legitimate recorded actuals inside the status-date window.** Retrospective statusing between Period A and Period B status dates is what SMH's update cycle produces [SMH §7.3.2 pp.285–288; §7.3.2.1 p.288]; filtered out per §3.2. *(Inferred — not sourced; SMH does not name Period A / Period B. Session-18 scope-defer.)*
- **Owner-directed resequencing with documentation.** Changes captured in an SMH replan [SMH §7.3.4.5 pp.330–331] are not manipulation; the absence of documentation is the concern.
- **Rolling-wave decomposition.** Progressive elaboration is expected practice [SMH §5.5.7.3 pp.94–96]; a growing task count is not a signal unless paired with duration or float redistribution on unrelated scope.

## 3. Cross-version detection protocol

### 3.1 UniqueID matching is the sole cross-version key

The match key is `UniqueID` — nothing else [LL §5; §13 commandment #3]. The `ID` (row-number) field shifts on insertion/deletion/reorder. Name-based matching silently fails on renames. UniqueID extraction lives in `mpp-parsing-com-automation §3.4, §5`.

### 3.2 Status-date windowing (legitimate-progress filter)

For each matched UniqueID where Period A `Finish` ≤ Period B `StatusDate`, Period-B field deltas are treated as recorded actuals and excluded *(inferred — not sourced; SMH describes retrospective statusing at [SMH §7.3.2 pp.285–288] but does not name the filter predicate; Session-18 scope-defer to `driving-slack-and-paths §10`)*. Without this filter, a healthy schedule with a month of recorded progress reads as 500 manipulated tasks.

### 3.3 Period A slack rule for but-for tests

When a but-for test removes a logic link, reverses a constraint, or reverts a duration edit, the engine re-runs CPM and compares resulting dates against **Period A** — Period B slack is circular *(inferred — not sourced; rule in `driving-slack-and-paths §9`)*. Finish-date delta in calendar days is the authoritative slip metric (working days internal; calendar days at presentation).

### 3.4 Aggregate pattern vs. single-task anomaly

A single edit is an item; a sustained trend across three revisions is a pattern. §10 governs aggregation. *(Inferred — Session-18 scope-defer.)*

## 4. Logic manipulation

Logic manipulation edits the predecessor/successor network between IMS revisions. The engine tests for five sub-patterns.

### 4.1 Predecessor or successor removal

A task that carried a predecessor or successor link in Period A but does not in Period B — no change-order reference, no §3.2 filter hit — has had its logic altered. Removed predecessors may pull forecast start left; removed successors may appear to gain float or drop off the critical path despite no work change. Missing-logic rates are the DCMA §4.1 diagnostic [RW pp.5–6; ED p.1]; mechanics in `dcma-14-point-assessment §4.1`. SMH's health check restates the concern: missing predecessors/successors "may lead to improper float/critical path calculations" [SMH §6.2.2.1.2 *Figure 6-9*].

### 4.2 FS → SS/FF conversion

Converting a Finish-to-Start (FS=1) relationship to Start-to-Start (SS=3) or Finish-to-Finish (FF=0) [LL Appendix B: TaskDependency.Type enum] alters how the successor receives predecessor pressure. SS conversions let the successor start before the predecessor finishes; FF conversions let two tasks finish simultaneously without either driving the other's start. DCMA §4.4 Relationship-Types (≥90% FS) is the aggregate diagnostic [RW p.7]; mechanics in `dcma-14-point-assessment §4.4`.

### 4.3 Lag insertion or removal

Positive lag inserted on a Period B link conceals unmodeled work or defers downstream pressure; SMH flags lags as hiding detail that "cannot be statused like normal activities … Lags should be replaced with activities" [SMH §6.2.2.1.2 *Figure 6-9*]. Negative lag (lead) inserted in Period B violates FS semantics. DCMA §4.2 (Leads, 0%) and §4.3 (Lags, ≤5% with 09NOV09 5-day MSP/OpenPlan carve-out) are the aggregate diagnostics [RW pp.6–7]; mechanics in `dcma-14-point-assessment §4.2, §4.3`. [DECM row 06A205a] probes lag usage at the EVMS-metric level. Per-activity counts via [DMG p.37] `Number of Lags` / `Number of Leads`.

### 4.4 Constraint injection (MSO, MFO, SNLT, FNLT)

Adding a hard constraint — Must-Start-On, Must-Finish-On, Start-No-Later-Than, Finish-No-Later-Than — to a task that carried ASAP in Period A pins the task and overrides CPM float. SMH: "Hard constraints can prevent the logical flow … distorting the total float (slack) and critical path calculations … Hard constraints should be avoided except where absolutely necessary" [SMH §5.5.8.3]. The four-constraint list follows the 09NOV09 definition [RW p.8; ED]; threshold mechanics in `dcma-14-point-assessment §4.5`. Enum values (MSO=2, MFO=3, SNLT=5, FNLT=7) per [LL Appendix B]; [DECM row 06A209a] probes constraint limitation at the EVMS-metric level.

### 4.5 Constraint removal hiding slip

A task that carried MFO or FNLT in Period A, anchoring a forecast finish, has the constraint removed in Period B. Float re-inflates from the constraint-forced value; CPLI improves cosmetically [RW p.15]; the schedule looks healthier without any recorded progress. Detectable only by cross-version diffing — a single-snapshot DCMA §4.5 run reports the Period B rate as low.

## 5. Duration manipulation

Duration manipulation edits `Duration`, `RemainingDuration`, `ActualDuration`, or `BaselineDuration` [LL §6] between revisions without commensurate status evidence. Internal units are minutes (480 = 1 working day at 8h) per [LL Appendix B, D #5]; presentation uses working days per repo convention.

### 5.1 Remaining-duration compression without status evidence

`RemainingDuration` drops from Period A to Period B on an in-progress task, but `PercentComplete` and `ActualDuration` are unchanged and no actuals fall in the window. Forecast finish pulls left without any recorded work. Remaining Duration is the primary SMH statusing mechanism — "Use 'Remaining Duration' as the primary method for providing status of in-progress activities" [SMH §7.3.2.3 *Steps for Updating the Schedule*] — so edits without actuals are directly evidentiary.

### 5.2 Original-duration edits on in-progress or completed tasks

Editing `Duration` on a task whose `ActualStart` is populated, or whose `PercentComplete` is 100, is forensically anomalous: the original estimate is historical once work has begun. Edits to `BaselineDuration` without a rebaseline Decision Memorandum [SMH §7.3.4.7 pp.331–332] are baseline tampering — a separate, more serious finding under the [SMH §7.3.4] baseline-stability rule.

### 5.3 As-Late-As-Possible and constraint-type tricks

Setting constraint type to As-Late-As-Possible (ALAP, enum value 1 per [LL Appendix B]) pushes the task as late as possible while preserving the finish milestone, collapsing total float upstream. SMH is categorical: "It is a recommended practice that the ALAP constraint never be used (specific to MS Project). This constraint uses total float to calculate its Early Finish date instead of free float. This can cause the P/p end date to slip" [SMH §5.5.8.3]. ALAP is excluded from the 09NOV09 Hard-Constraint list [RW p.8; ED] and therefore does not raise DCMA §4.5; explicit constraint-type scan is required. Cross-version appearance of ALAP on an ASAP-in-Period-A task is a direct manipulation signal.

### 5.4 Rolling-wave mis-tagging as a duration-manipulation vector

A near-term activity coded rolling-wave across multiple status cycles despite the SMH 6–12-month window, or a far-term placeholder whose scope is contract-decomposed but IMS-undecomposed, is using the DCMA §4.8 rolling-wave exemption [RW p.11] to park scope where no baseline can yet fail. SMH states rolling-wave is not a licence to suppress detail already known [SMH §5.5.7.3 p.95]. Mechanics in `dcma-14-point-assessment §4.8`.

## 6. Date manipulation

Date manipulation edits `ActualStart`, `ActualFinish`, forecast `Start`/`Finish`, or the project `StatusDate` between revisions. SMH's rule is explicit: actual dates must be entered as accurately as possible, and planned dates must be calculated by the scheduling tool, not manually entered [SMH §7.3.2.1 *Revise Activity/Milestone Data*; SMH §7.3.2.3 *Steps for Updating the Schedule*].

### 6.1 Actual-date edits after first reporting

An `ActualStart` or `ActualFinish` populated in Period A that changes in Period B — without a documented correction and outside the §3.2 window — is a direct manipulation signal. [DECM row 06A504a] probes starts and [DECM row 06A504b] probes finishes as stand-alone "actual dates changed after first reported" EVMS tests. The comparator diffs each matched UniqueID's actuals and surfaces every change as a candidate finding.

### 6.2 Forecast-date edits not tied to status

Forecast `Start`/`Finish` "should be calculated by the scheduling tool used, not manually entered" [SMH §7.3.2.1]. A forecast date that moves with no predecessor shift, no duration change, no constraint change, and no status implies manual override. [DECM row 06A506b] anchors single-snapshot validity; the forensic tool extends it to cross-version delta.

### 6.3 Forecast dates "riding" the status date

A Period B forecast start/finish matching the status date that reappears matching each successive status date is a concealment signature: the task remains just-about-to-start forever. [DECM row 06A506c] names the probe — "Are forecast start/finish dates riding the status date of the IMS for two consecutive months?" Detection requires three revisions and a status-date sequence.

### 6.4 Status-date backdating and progress-line re-anchoring

The status date is the single "time now" anchor [SMH §7.3.2 *Procedure 2*]. A Period B `StatusDate` earlier than Period A's, or shifted without a formal status cycle, moves the progress line and turns "late" tasks into "not yet due." SMH's Invalid-Actual-Dates / Invalid-Forecast-Dates indicators [SMH §6.2.2.1.2 *Figure 6-9* p.170] catch the downstream effect; the status-date edit itself is the root signal. Extraction mechanics live in `mpp-parsing-com-automation §3.6`.

### 6.5 Baseline date edits

[DECM row 29I401a] asks directly: "Are baseline dates being updated to mask legitimate variances?" Changes to `BaselineStart`/`BaselineFinish`/`BaselineDuration` without a documented rebaseline [SMH §7.3.4.7 pp.331–332] are baseline tampering. SMH posture: "The schedule baseline (and PMB) should remain stable and only be modified due to authorized changes in work scope" [SMH §7.3.4 *Corrective Actions*].

## 7. Float manipulation

Float is an emergent CPM property (Total Float = Late Dates − Early Dates) [SMH §5.5.11]. Float manipulation is therefore always indirect: the edit targets logic, duration, or constraint, and float moves as a consequence. The forensic engine examines three aggregate float signatures.

### 7.1 Total-float inflation via constraint removal

Removing an MFO/SNLT/FNLT constraint that anchored a task in Period A releases TF from the constraint-forced value to the CPM-computed value. Aggregate TF shifts upward across the workstream. Pair with §4.5: constraint gone, float conspicuously higher on the same chain. [DECM row 06A211a] probes "high total float rationale/justification" at the aggregate level; the cross-version delta makes it unambiguous.

### 7.2 Free-float redistribution

Free Slack is flexibility to the nearest successor [SSI slide 10]. Editing a predecessor's finish, a lag, or a relationship type so FS rolls from one task to another — without a work-driven reason — masks where pressure actually lives. Single-snapshot metrics miss this; cross-version FS delta per matched UniqueID is the only diagnostic. DS/FS/TS mechanics in `driving-slack-and-paths §2.3`.

### 7.3 Negative-float masking

[SMH §5.5.11]: "negative float arises when an activity's completion date … is constrained … Date constraints causing negative float need to be justified or removed." SMH's health check: "Negative float is the result of an artificially accelerated or constrained schedule" [SMH §6.2.2.1.2 *Figure 6-9*]. Masking negative float by removing the causing constraint — rather than re-sequencing — converts an honest flag into cosmetic zero-float. DCMA §4.7 (0% threshold) is the single-snapshot diagnostic [RW p.11]; cross-version disappearance of a negative-float task is the manipulation signal.

## 8. Critical-path manipulation

Critical-path manipulation changes which chain carries zero driving slack to the project finish Focus Point [SSI slides 5–6, 12]. The engine examines two sub-patterns.

### 8.1 Driving-path hand-offs

A driving path in Period A runs A → B → C → Finish. In Period B the same UniqueIDs are present but the driving path now runs A → D → E → Finish and B/C carry positive driving slack. If the work has not changed and no documented resequencing applies, the hand-off is manipulation — pressure has been moved to a less-visible chain. Detection requires the driving-path-trace output of both revisions [LL §11 #2] and a UniqueID-matched diff [LL §11 #3; §5]. SMH: driving path is "the critical path to an end item other than P/p completion … based on zero free float identifying the drivers" [SMH §5.5.10].

### 8.2 Float-threshold gaming at the near-critical boundary

SMH endorses "primary, secondary, and tertiary critical paths" based on a minimum-float threshold [SMH §5.5.10]. Manipulation games this: a Period-A task with TF = 1 inside the threshold band can be edited to TF = 6 in Period B by adding a downstream FS link with a small lag, dropping it from near-critical reporting without changing the work. Threshold bands themselves are a `driving-slack-and-paths §5` concept *(inferred — not sourced; Session-18 scope-defer for canonical band widths)*. SMH: "unless the IMS represents the entire scope of effort and the effort is correctly sequenced through the logic network, the scheduling software will report an incorrect or invalid critical path" [SMH §5.5.10].

## 9. Cross-version erosion detection

Erosion is the multi-revision pattern where a task's float or its distance from the critical path decreases monotonically without any single revision crossing a DCMA threshold. Per [LL §11 #3], the engine emits trend labels — CRITICAL, SEVERE EROSION, ERODING, STABLE, IMPROVING — plus newly-critical / recovered / added / deleted flags across UniqueID-matched revisions.

### 9.1 UniqueID-matched task deltas

Per matched UniqueID the comparator emits: TotalFloat delta, FreeFloat delta, DrivingSlack-to-Focus-Point delta, BaselineFinish delta, forecast Finish delta, constraint-type change, relationship-type changes on incident edges. Each delta carries a status-date timestamp. Deletions and insertions are recorded separately.

### 9.2 Aggregate pattern vs. single-task anomaly

A single erosion event is weak evidence; sustained erosion on multiple tasks in the same workstream is strong evidence. §10 codifies the aggregation rule. The `driving-slack-and-paths §6` *TotalFloat trend classification* field is the per-task output this skill aggregates.

### 9.3 Out-of-sequence masking and legitimate-progress filtering

Erosion on a task that completed inside the Period A → Period B window is not manipulation — it is the §3.2 filter's target. Out-of-sequence tasks [DECM row 06A212a]; [DMG p.37] `IsOutOfSequence` are a separate diagnostic: erosion is masked by out-of-sequence progressing, and "Out-of-sequence task cause questionable total float calculations" [SMH §6.2.2.1.2 *Figure 6-9*].

## 10. Red-flag aggregation

A single deviation is a question; a pattern is a finding. The aggregation rule has three tiers and is applied *after* §3.2 status-date filtering and §3.3 Period-A-slack but-for testing.

### 10.1 Tier 1 — multiple DCMA thresholds breached in one revision

A single revision simultaneously breaches §4.5 Hard Constraints (>5%) [RW p.8], §4.1 Missing/Dangling Logic (>5%) [RW pp.5–6; ED p.1], §4.6 High Float (>5%) [RW p.10], and §4.13 CPLI (<0.95) [RW p.15]. Mechanics in `dcma-14-point-assessment §4`. The aggregation rule itself is tool-side *(inferred — not sourced; Session-18 scope-defer for empirical breach-combination thresholds)*.

### 10.2 Tier 2 — cross-version trend across matched revisions

Three consecutive revisions show monotonically worsening CPLI [RW p.15], BEI [RW p.16; ED p.2], and Hard-Constraint rate [RW p.8] with erosion on the same workstream (§9). SMH treats serial replans without a rebaseline decision as governance drift [SMH §7.3.4]. [DECM row 23A301a] aligns at the EVMS-metric level: "SV analysis documents impact to critical / near-critical / driving paths."

### 10.3 Tier 3 — specific EVMS-metric manipulation probes

[DECM row 29I401a] (baseline dates masking variances), [DECM row 06A504a/b] (actuals changed after first reported), and [DECM row 06A506c] (forecast dates riding status date) are stand-alone EVMS manipulation probes. A single hit, corroborated by a Tier-1 or Tier-2 pattern, is sufficient to raise a finding for human investigation. None is sufficient on its own — [RW p.20]'s indicators-not-verdicts posture applies.

## 11. Deltek DECM / Acumen cross-reference

The Deltek EVMS-DECM catalog (V5.0, Jan 2022) supplies complementary EVMS-layer probes cited in §§4–10: `06A204b` (dangling), `06A205a` (lags), `06A209a` (constraints), `06A211a` (high float), `06A212a` (out-of-sequence), `06A504a/b` (actuals changed), `06A506b/c` (forecast validity; riding status date), `23A301a` (SV analysis vs. CP/near-CP/driving), `29I401a` (baseline masking variances), `31A101a` and `32A101a/b` (authorized baseline traceability). [DMG p.1] frames metrics as "formulas and tripwires"; [DMG p.12] defines the four-formula schema; [DMG p.37] lists special fields `IsOutOfSequence`, `Number of Lags`, `Number of Leads`, and FF/FS/SF/SS counts. Full Acumen Fuse mapping in `acumen-reference (planned — future skill)`.

## 12. Cross-skill dependencies

- **DCMA 14-Point thresholds (diagnostic context only)** — `dcma-14-point-assessment §4.1, §4.2, §4.3, §4.4, §4.5, §4.7, §4.8, §4.12, §4.13, §4.14`.
- **Driving slack, driving path, float semantics, Period-A slack rule, secondary/tertiary near-critical bands** — `driving-slack-and-paths §2, §3, §5, §9`.
- **Field extraction fidelity (actual/forecast/remaining-duration, status-date extraction, constraint-type enum, relationship-type enum)** — `mpp-parsing-com-automation §3`.
- **NASA IMS quality/integrity baseline, replan-vs-rebaseline governance, status-date discipline** — `nasa-schedule-management §2, §6, §8, §9`.
- **Data locality during manipulation analysis; CUI gate** — `cui-compliance-constraints`.
- **Deltek Acumen Fuse metric cross-reference** — `acumen-reference (planned — future skill)`.

## 13. What this skill does NOT cover

- DCMA 14-Point formula, denominator, or threshold derivation — see `dcma-14-point-assessment §4`.
- CPM forward/backward pass, driving-path/critical-path math — see `driving-slack-and-paths §§2–4`.
- MPP parsing, COM automation, JVM lifecycle — see `mpp-parsing-com-automation`.
- Earned-value variance analysis (EVA) — deferred to Phase 3.
- Scoring weights, probability models, or severity-ranking formulas — the aggregation rule in §10 is protocol-level, not quantitative.
- Implementation code for detection rules — this skill defines protocol; engine code lives in `app/engine/`.

## 14. Inferred content + scope-defers (single-table summary)

| # | Section | Inferred claim | Scope-defer |
|---|---------|----------------|-------------|
| 1 | §2 | "Legitimate recorded actuals inside the status-date window" formalised as filter predicate | Session 18 — formalise Period A / Period B naming when comparator is versioned |
| 2 | §3.2 | Status-date windowing filter predicate (Period A `Finish` ≤ Period B `StatusDate`) | Session 18 — cross-check against authoritative but-for literature |
| 3 | §3.3 | Period-A slack rule for but-for tests | Session 18 — mirror of `driving-slack-and-paths §9` |
| 4 | §3.4, §10 | Aggregate-pattern vs. single-anomaly empirical thresholds | Session 18 — empirical thresholds once RAG case-history suffices |
| 5 | §5.3 | ALAP-abuse prevalence as distinct manipulation vector | Session 18 — confirm against authoritative constraint-abuse literature |
| 6 | §8.2 | Secondary/tertiary near-critical band threshold widths | Session 18 — cross-ref `driving-slack-and-paths §5` once canonical bands are added |
| 7 | §10.1 | Tier-1 DCMA-threshold-combination rule | Session 18 — empirical breach-combination thresholds |

## 15. References

| Claim | Source |
|-------|--------|
| Indicators-not-verdicts framing | [RW p.20] |
| BoE, replan, rebaseline, baseline-stability, retrospective statusing | [SMH §5.4 pp.73–74; §7.3.2 pp.285–288; §7.3.2.1; §7.3.4; §7.3.4.5 pp.330–331; §7.3.4.7 pp.331–332] |
| Rolling-wave elaboration | [SMH §5.5.7.3 pp.94–96] |
| UniqueID-sole match key; COM enum/units | [LL §5; §13 #3; Appendix B] |
| Trend labels; driving-path trace | [LL §11 #2; §11 #3] |
| Missing Logic; Leads/Lags; Hard Constraints; High Float; Negative Float; High Duration; CPLI; BEI | [RW pp.5–16; ED pp.1–2] |
| SMH health-check indicators (Fig 6-9) | [SMH §6.2.2.1.2 p.170] |
| Hard-constraint distortion; MSO/MFO override; ALAP never used | [SMH §5.5.8.3] |
| Remaining Duration primary; actuals accurate; forecasts tool-calculated | [SMH §7.3.2.1; §7.3.2.3] |
| Float = Late − Early; constraint-driven negative float | [SMH §5.5.11] |
| Driving path = zero free float; primary/secondary/tertiary paths | [SMH §5.5.10] |
| SSI DS definition; DS ≠ TS/FS; DS most-accurate; worked example | [SSI slides 5–12, 14–22] |
| Free Slack to nearest successor | [SSI slide 10] |
| EVMS-DECM manipulation probes — actuals changed (06A504a/b); forecast riding status date (06A506c); baseline masking variances (29I401a); dangling logic (06A204b); lags (06A205a); constraints limited (06A209a); high-float rationale (06A211a); out-of-sequence (06A212a); SV analysis to CP/near-CP/driving (23A301a); forecast validity (06A506b); authorized baseline change (31A101a; 32A101a/b) | [DECM sheet *Deltek EVMS-DECM Metrics V5.0*] |
| Acumen four-formula schema; tripwires; special fields | [DMG p.1; p.12; p.37] |
| Cross-skill cross-refs | `dcma-14-point-assessment §4`; `driving-slack-and-paths §2, §3, §5, §6, §9`; `mpp-parsing-com-automation §3, §3.4, §3.6, §5`; `nasa-schedule-management §2, §6, §8, §9`; `cui-compliance-constraints`; `acumen-reference (planned)` |
