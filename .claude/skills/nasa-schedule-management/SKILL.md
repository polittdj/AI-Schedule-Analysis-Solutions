---
name: nasa-schedule-management
description: NASA Schedule Management Handbook (SMH) practice — IMS construction, schedule margin, rolling-wave planning, schedule BoE, schedule health, Schedule Risk Assessment (SRA), status-date discipline, replan vs. rebaseline. Keywords NASA Schedule Management Handbook, IMS, integrated master schedule, schedule margin, schedule health, NASA scheduling, NPR 7120, rolling wave, schedule basis, SMH, schedule risk assessment, SRA, critical path, NASA milestone, status date, baseline, replan, rebaseline.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# NASA Schedule Management

Authoritative reference for applying NASA Schedule Management Handbook (SMH, Revision 2, 15 March 2024) practice inside this forensic tool. Primary source is `[SMH]`. Where SMH is silent or topic crosses into risk governance, secondary sources are `[NPR8K]` (NPR 8000.4C) and `[NID]` (NID 7120.148). Term disambiguations cite `[ACR]` (NASA Acronyms). Rules without a direct source are labelled `(inferred — not sourced)` with a Session-18 scope-defer note in §11.

## 1. Purpose and scope

This skill codifies NASA's published expectations for schedule management so the forensic engine can (a) detect deviations from those expectations, and (b) phrase its narrative in the agency's own vocabulary. It covers the IMS as NASA defines it, schedule margin as a PM-owned reserve distinct from total float, rolling-wave planning, the Schedule Basis of Estimate (BoE), schedule health from the NASA angle, Schedule Risk Assessment (SRA), status-date discipline, and the replan-versus-rebaseline decision path.

It does **not** cover the programmatic lifecycle (KDP/SRR/PDR/CDR definitions, PMC structure, NPR 7120.5 phase gates) — see `nasa-program-project-governance`. It does not restate DCMA 14-Point formulas or thresholds — see `dcma-14-point-assessment §4, §8`. It does not restate driving-slack vs. total-slack mechanics — see `driving-slack-and-paths §2.3`. It does not cover `.mpp` field extraction — see `mpp-parsing-com-automation §3`. EVA is deferred to Phase 3.

Forensic framing: SMH describes NASA's *expected* schedule-management behaviours. A schedule that deviates from SMH is evidence of process drift, not automatically of manipulation. Many deviations (thin BoE, sparse rolling-wave decomposition, missing margin) are driven by funding, staffing, or contract structure. The narrative should cite the SMH expectation, characterise the deviation, and leave intent to the human investigator.

## 2. The Integrated Master Schedule (IMS) — NASA framing

NASA defines the IMS as the time-phased plan for performing the program/project's (P/p) approved total scope of work, containing tasks, milestones, and logical interdependencies that model implementation from start through completion based on the WBS [SMH §5.3.5 p.73]. The IMS integrates work scope, cost estimate, and programmatic risks to align with the integrated performance baseline (or Performance Measurement Baseline, PMB), and includes both government and contractor work. Detail must be sufficient to identify the longest path through the entire P/p [SMH §5.3.5 p.73].

Two IMS states are named: the **preliminary IMS** prior to baseline, and the **baseline IMS** once approved through the formal baseline process — typically an Integrated Baseline Review (IBR) [SMH §5.3.5 p.73; §5.6.1 p.285]. This two-state convention is the forensic anchor for version comparison: any comparator run is preliminary-vs-baseline or baseline-vs-current, and "current" means the baseline IMS updated through a named status date [SMH §7.3.2 p.285].

Required IMS attributes per NASA include granularity driven by the WBS, complete temporal span from ATP through the terminal milestone, vertical traceability to the organizational/hierarchical breakdown, and horizontal integration of government and contractor content [SMH §5.3.5 p.73; §6.2.2.1.1 p.166]. Activity attributes are set up as data fields during Schedule Management Planning so the schedule database interfaces cleanly with EVM, RMS, and SRA tooling downstream [SMH §4.3.1.2.4 p.49]. UniqueID and DS/TS/FS mechanics are not restated here — see `mpp-parsing-com-automation §3` and `driving-slack-and-paths §2.3`.

The forensic pair is the baseline IMS and the current IMS as of a status date: date-slip, logic changes, duration changes, and margin consumption are computed on this pair.

## 3. Schedule margin (NASA-specific)

NASA schedule margin is a **separately planned quantity of time (working days) above the planned work-duration estimate, used to absorb the impacts of risks and uncertainties** [SMH §5.5.11 p.118]. It is risk-informed, loaded into the IMS as activities prior to baseline, and carries no defined scope and no associated budget [SMH §5.5.11 pp.118–119]. SMH notes that "reserve" is obsolete NASA terminology, replaced by "schedule margin" for time and "UFE" (Unallocated Future Expenses) for funds [SMH §5.5.11 p.119 note].

Schedule margin is not total float. Float is an automatic CPM calculation (Late Dates − Early Dates); schedule margin is a deliberately placed, PM-owned activity [SMH §5.5.11 pp.119–120]. Four guideline rules apply [SMH §5.5.11.1 p.120]: margin must be allocated throughout the schedule; it must always be identifiable; it must be managed and controlled by the PM; and sufficient budget must cover the added duration.

Placement conventions [SMH §5.5.11.3 pp.122–124]: along the primary critical path; along secondary and tertiary driving paths when risks are off the primary path; prior to key milestones and events (AI&T milestones, contractual milestones, lifecycle review milestones); and prior to end-item deliverables or the P/p finish milestone. Indicative allocations early in formulation [SMH §5.5.11.2 Fig 5-30 p.120]: 1–2 months per year from Confirmation Review to I&T start; 2–2.5 months per year from I&T start to shipment; roughly 1 day per week / 1 week per month / 1 month per year from delivery to launch. These are starting points validated against a probabilistic SRA (§7).

**Forensic rule for DCMA §4.6 (High Float):** schedule-margin tasks must be excluded from the High-Float denominator, or the rate inflates and produces a false manipulation flag [SMH §5.5.11 pp.118–119; cross-ref `dcma-14-point-assessment §8` for mechanics].

Consumption tracking is a leading indicator of programme health. SMH prescribes a margin burndown curve tracked each status cycle, with working-day "margin" separated from non-working-day "contingency" [SMH §7.3.3.1.6 pp.308–310]. "Effective margin" is the margin on the current critical path; as the critical path shifts, non-effective margin can become effective, so the log must be recomputed each cycle [SMH §7.3.3.1.6 pp.309–310]. A Margin Log recording each consumption event and its cause is a recommended practice [SMH §7.3.3.1.6 p.310]. Accelerating margin consumption with no commensurate movement in the schedule completion is the SMH-style fingerprint of a programme burning reserve without reducing residual risk.

## 4. Rolling-wave planning

NASA defines rolling-wave planning as a progressive-elaboration method that schedules work in waves — near-term work planned at discrete, detailed level; far-term work planned at summary or planning-package level — with successive refinement as future work becomes clearer [SMH §5.5.7.3 pp.94–95]. It is widely used across NASA P/ps, often alongside EVM [SMH §5.5.7.3 p.95].

Two specific rules apply [SMH §5.5.7.3 p.95]. **Near-term window:** activities within roughly 6–12 months of the current date are planned to discrete, lower level. **Near-term duration cap:** near-term activity durations should be less than two times the status-update cycle — for a monthly cycle, less than two months — so start and finish of each near-term activity can be reported within one or two cycles. Exceptions: long-lead procurement and level-of-effort (LOE) activities.

Rolling-wave content beyond the near-term window must still provide enough definition to allow critical-path and driving-path identification [SMH §5.5.7.3 p.95]. Rolling-wave is not a licence to suppress detail that is already known; it is not a substitute for detail where information exists [SMH §5.5.7.3 p.95, paraphrased]. Planning packages must be periodically revisited and brought into the near-term window as they approach [SMH §5.5.7.3 pp.95–96]. Use of rolling-wave must be defensible and BoE-documented [SMH §5.5.7.3 p.95].

**Interaction with DCMA §4.8 (High Duration):** the 09NOV09 revision provides a rolling-wave exemption. Mechanics in `dcma-14-point-assessment §4.8, §8` — not restated here.

**Forensic read:** rolling-wave mis-tagging is a manipulation pattern. Known-detail work is flagged as a rolling-wave placeholder to evade High-Duration (via the exemption) or to park unresolved scope where no baseline can yet fail. Fingerprints: a near-term activity coded rolling-wave across multiple status cycles despite the 6–12-month window, or a far-term placeholder whose scope is clearly decomposed in the contract but undecomposed in the IMS. Cross-ref `forensic-manipulation-patterns`.

## 5. Schedule basis and documentation

The Schedule Basis of Estimate (BoE) is the structured dossier documenting ground rules, assumptions, and drivers used in developing the IMS, plus assessment and analysis findings, reporting artifacts, and primary source data [SMH §5.4 p.73]. The BoE enables IMS development, provides the medium for assessing schedule reliability, guides evolution, and enables dialogue between the P/p and Independent Assessment teams [SMH §5.4 pp.73–74].

BoE content must include, at minimum, basis rationale for each IMS element, primary data sources, and an explicit trace from rationale to source [SMH §5.4 p.74]. It must house current and past IMS versions so prior-cycle comparators can be reproduced. It must document calendar conventions, working-time rules, duration-estimate assumptions, procurement/test-facility/partner-driven logical constraints, and margin-allocation methodology [SMH §5.5.11 pp.120–124; §5.5.9.2 p.107]. BoE maturity is staged against the P/p life cycle: Preliminary at SRR/SDR, Baseline at PDR/CDR, Updates thereafter [SMH §5.4.1 p.74].

**Forensic read:** missing or contradictory schedule-basis documentation is primary evidence in delay disputes. A schedule without a BoE cannot be reproduced or independently validated and cannot support either a delay claim or defence. A BoE that contradicts its own IMS (e.g., assumed calendars or durations outside the claimed uncertainty band) is forensically suspect independent of any manipulation question. The narrative should treat BoE-vs-IMS consistency as a first-tier check when the BoE is available and should explicitly flag its absence when it is not.

## 6. Schedule health and quality — NASA overlay on DCMA 14-Point

SMH references the DCMA 14-Point Assessment as a recommended schedule-health check [SMH §6.2.2 pp.161–169; §6.2.2.1.2 *Procedure 2. Health Check* pp.168–174]. NASA endorses the protocol without overriding its thresholds; where SMH cites DCMA numerics, it restates them, and NASA-specific rules are additive. DCMA mechanics, formulas, denominators, and protocol-version handling are in `dcma-14-point-assessment §2, §3, §4` — not restated here.

NASA-specific overlay rules the engine must apply:

- **High Float denominator exclusion.** Tagged schedule-margin tasks are excluded from §4.6's denominator. Rationale in §3; mechanics in `dcma-14-point-assessment §8`.
- **Governance-milestone constraint triage.** NASA governance milestones (KDP, SRR/MDR/SDR, PDR, CDR, SIR, ORR, MRR/FRR, DR, DRR) legitimately drive MSO and FNLT constraints on IMS tasks tied to review dates [SMH §2.1; governance detail in `nasa-program-project-governance`]. Elevated §4.5 Hard-Constraint rates therefore require governance triage before any manipulation inference. Cross-ref `dcma-14-point-assessment §8`.
- **Rolling-wave exemption interaction.** DCMA §4.8's rolling-wave exemption is endorsed by NASA usage (§4), but the engine must cross-check that exempted tasks are actually in the far-term window [SMH §5.5.7.3 p.95].
- **No known numeric conflicts.** DCMA numerics default.

NASA's broader health catalogue [SMH §6.2.2.1.2 p.170] includes High Durations, Incomplete Task Status, High Float, Missed Tasks, Invalid Actual Dates, Invalid Forecast Dates, tasks improperly reflected as milestones, tasks without a baseline, and inconsistent-rollup items. These overlap DCMA 14-Point but are not identical; the engine treats DCMA 14-Point as the computation core and the SMH key-indicator list as the phrasing layer for NASA audiences.

## 7. Schedule Risk Assessment (SRA)

Schedule Analysis under SMH denotes the process of performing a Schedule Risk Analysis (SRA), a statistical technique that analyses the potential impact of duration uncertainties and discrete risks on the plan reflected in the IMS [SMH §6.3 p.190; §6.3.2.3 p.201]. The SRA supports NPR 7120.5 and NPD 1000.5 requirements for Schedule Completion Ranges and Schedule Confidence Levels / Joint Cost and Schedule Confidence Levels (JCLs) at applicable P/p milestones [SMH §6.3.2 p.191].

SRA inputs [SMH §6.3.1 p.190; §6.3.2 pp.191–193]: an IMS or Analysis Schedule; task duration uncertainties as probability distributions; a current, complete discrete risk list with clarity on mitigation planning and funding; EVM reports where EVM is run. Outputs include probability distributions over completion dates, stochastic critical/driving path analysis, risk sensitivity and prioritisation, schedule confidence levels, and margin sufficiency analysis [SMH §6.3.2 pp.192–193].

When to run [SMH §6.3 pp.190–191]: at pre-planned initiating events (major reviews, monthly/quarterly routine reviews), on special request during schedule-impacting events, and semi-annually (or more) for multi-mission campaigns. An Integrated Cost and Schedule Risk Analysis (ICSRA) / JCL is **required** at KDP I / KDP C prior to baseline and at rebaselines for tightly coupled programs, single-project programs, and projects with estimated Life-Cycle Cost (LCC) > $250M; for single-project programs and projects with LCC ≥ $1B, also required at KDP B, CDR, and KDP D [SMH §5.5.11.2 pp.121–122].

**Scope covered here:** SRA purpose, inputs, outputs, and when to run. Forensic relevance: the SRA confidence-level timeline (P10/P50/P90 across cycles) is a superior leading indicator to any deterministic metric — a P50 that slides right monotonically is the SMH-style fingerprint of a programme that is not recovering.

**Scope deferred — Phase 3 (inferred — Session-18 scope-defer):** Monte Carlo engine mechanics, distribution-family selection (triangular/PERT/lognormal), inter-activity correlation, risk-driver ranking, and SRA output parsing are Phase-3 work. This skill names SRA scope and forensic use; it does not implement the SRA.

## 8. Status-date discipline

NASA's status-date convention [SMH §7.3.2 pp.285–286]: the status date ("time now") is a single date, typically month-end closeout. Work to the left reflects actuals; work to the right reflects future work. All incomplete tasks and milestones must be updated to the single status date, including tasks that should have started or completed but have not [SMH §7.3.2.1 p.287]. In-progress activities are statused primarily via "Remaining Duration" to keep projected finish dates and successor time-phasing accurate [SMH §7.3.2.1 p.288]. SMH explicitly names MS Project as a tool that does not force the user to update status of on-going or behind-schedule tasks — a parser-validation trap [SMH §7.3.2.1 p.288; cross-ref `mpp-parsing-com-automation §3`].

**Retrospective vs. prospective statusing.** Retrospective statusing — entering actuals for work completed between the prior and current status date — is required. Prospective statusing — entering actuals with dates to the right of time-now — is prohibited and is called out by SMH as "Invalid Actual Dates" [SMH §6.2.2.1.2 p.170]. "Invalid Forecast Dates" — activities planned in the future with status in the past — is the mirror defect [SMH §6.2.2.1.2 p.170].

**Forensic rule (inferred — not sourced, see §11):** legitimate actuals that fall between a Period A status date (earlier snapshot) and a Period B status date (later snapshot) are *not* evidence of manipulation — they are what SMH's update cycle produces. A comparator that flags every actual-start or actual-finish between Period A and Period B as "changed" will report most of a healthy schedule as "manipulated." The but-for comparator must restrict actual-date-change detection to actuals dated *before* Period A that moved, or actuals in Period B that contradict dates already recorded in Period A. SMH does not name Period A / Period B; the citation is inferred-and-deferred per §11. Status-date *extraction* mechanics (COM `StatusDate` returning "NA" or sentinel dates) are in `mpp-parsing-com-automation §3`.

## 9. Replan vs. rebaseline

SMH draws a sharp distinction between replan and rebaseline — the single most consequential governance decision in schedule control [SMH §7.3.4 pp.329–332].

**Replan [SMH §7.3.4.5 pp.330–331].** A replan occurs when the schedule baseline is revised to reflect approved changes to the remaining ("to go") P/p work. Replans typically redistribute budget and may revise activities, sequencing, durations, calendars, codes, constraints, and resources. Two sub-types: *Internal replanning* — remaining effort rescheduled due to internal scope changes, new technical approaches, re-sequencing, recovery/workarounds, or more realistic remaining-work plans; external commitments (control milestones, launch date, ABC date) are unchanged; PM typically authorises within the approved Schedule MA. *External replanning* — driven by changes outside the P/p's control (launch-date change, budget cut, facility conflict, MA threatened by poor performance); typically requires direction from above the PM.

**Rebaseline [SMH §7.3.4.7 pp.331–332; cross-ref [NPR8K] rebaseline-as-RIDM-outcome].** A rebaseline is a special case of replanning that requires changing the external commitment (ABC) in addition to the internal commitment (MA). It occurs when the existing baseline is no longer achievable and measuring performance against it is of little practical value. Triggers: sustained poor performance, external budget cuts, launch priority changes, or direction under the NASA Authorization Act of 2005 §103. Rebaselines are independently validated by the SRB or independent-assessment team and are recorded with an updated Decision Memorandum (DM); the original schedule baseline is preserved for traceability [SMH §7.3.4.6 p.331; §7.3.4.7 p.332].

**Forensic read.** Serial replans without a rebaseline trigger are the SMH-style fingerprint of governance drift. Diagnostic pattern: a programme that consumes margin, misses baseline dates on control milestones, shows CPLI < 0.95 and BEI < 0.95 across multiple status cycles, yet continues internal replans without a rebaseline decision or a formal retain-with-risk decision is operating outside SMH expectations. The narrative should state SMH-defined rebaseline triggers, compare to observed programme state across comparator cycles, and identify whether the governance chain (PM, Decision Authority, PMC) appears engaged. PMC composition, KDP-tied rebaseline approvals, and NPR 7120.5 decision thresholds live in `nasa-program-project-governance`.

## 10. Cross-skill dependencies

- **IMS field extraction, null handling, status-date extraction** — see `mpp-parsing-com-automation §3`.
- **Driving slack vs. total slack; relationship slack; driving-path traces; secondary/tertiary paths; Period A slack rule** — see `driving-slack-and-paths §2.3, §3`.
- **DCMA 14-Point formulas, thresholds, Deltek DECM / Acumen 8 mapping, NASA overlay** — see `dcma-14-point-assessment §2, §3, §4, §7, §8`.
- **Data locality; CUI gate** — see `cui-compliance-constraints`. Schedule data is CUI and never leaves the host.
- **Governance lifecycle (KDP/SRR/PDR/CDR/SIR/ORR/MRR/FRR/DR/DRR), PMC, Decision Authority, DM, ABC, MA, NPR 7120.5 phases** — see `nasa-program-project-governance`.
- **Manipulation-pattern signatures (rolling-wave mis-tagging, status overrides, constraint abuse, duration compression)** — see `forensic-manipulation-patterns`.
- **Deltek Acumen 8 Fuse metric overlay** — see `acumen-reference`.

## 11. Inferred content + scope-defers (single-table summary)

| # | Section | Inferred claim | Scope-defer |
|---|---------|----------------|-------------|
| 1 | §3 margin-placement guideline indicative allocations | Indicative allocations repeated from [SMH §5.5.11.2 Fig 5-30 p.120]; characterisation of "starting points" is editorial. | Session 18 — lock indicative allocations as ranges tied to P/p class. |
| 2 | §7 Phase 3 Monte Carlo mechanics | Distribution-family defaults, correlation rules, risk-driver ranking, SRA output parsing rules are not derivable from SMH §6.3 alone. | Session 18 or Phase 3 — populate when SRA engine is implemented. |
| 3 | §8 Period A vs. Period B actuals rule | SMH does not name Period A / Period B; the but-for comparator rule is tool-specific. | Session 18 — formalise when comparator cycle is versioned against a named Lessons-Learned section. |
| 4 | §9 "governance-drift fingerprint" | SMH describes replan/rebaseline decision gates but does not name the multi-cycle pattern as governance drift; label is editorial. | Session 18 — tie to empirical pattern frequencies once RAG case-history is available. |
| 5 | §6 "NASA key-indicator list as phrasing layer" | Relationship between DCMA 14-Point (engine) and SMH key indicators (narrative layer) is a tool-side posture, not an SMH directive. | Session 18 — audit when narrative-layer presets are built. |

## 12. References

| Section | Claim | Source |
|---------|-------|--------|
| §1 | SMH scope framing | [SMH §1.1 p.8; §1.2 p.9] |
| §2 | IMS definition, role, attributes, preliminary-vs-baseline states | [SMH §5.3.5 p.73; §5.6.1 p.285] |
| §2 | Temporal breadth; vertical traceability | [SMH §6.2.2.1.1 pp.166–167] |
| §2 | Activity attributes set during SMP | [SMH §4.3.1.2.4 p.49] |
| §3 | Margin definition; risk-informed; no scope/budget; "reserve" obsolete | [SMH §5.5.11 pp.118–119] |
| §3 | Four key margin guidelines | [SMH §5.5.11.1 p.120] |
| §3 | Indicative allocations (Confirmation→I&T, I&T→Ship, Ship→Launch) | [SMH §5.5.11.2 Fig 5-30 p.120] |
| §3 | Placement on driving paths, before milestones, before end-items | [SMH §5.5.11.3 pp.122–124] |
| §3 | Margin burndown; effective margin; margin log | [SMH §7.3.3.1.6 pp.308–310] |
| §4 | Rolling-wave definition; progressive elaboration; EVM compatibility | [SMH §5.5.7.3 pp.94–95] |
| §4 | 6–12 mo window; duration < 2× update cycle; LOE/procurement exceptions; defensible and BoE-documented | [SMH §5.5.7.3 pp.95–96] |
| §5 | Schedule BoE purpose, content, life-cycle maturity | [SMH §5.4 pp.73–74; §5.4.1] |
| §6 | NASA endorsement of DCMA 14-Point as health check | [SMH §6.2.2.1.2 pp.168–174] |
| §6 | High-Float denominator exclusion (cross-ref) | [SMH §5.5.11 pp.118–119]; `dcma-14-point-assessment §8` |
| §6 | NASA key indicators | [SMH §6.2.2.1.2 p.170] |
| §7 | SRA definition, inputs, outputs; NPR 7120.5 / NPD 1000.5 support | [SMH §6.3 pp.190–193] |
| §7 | ICSRA/JCL required points by P/p class and LCC | [SMH §5.5.11.2 pp.121–122] |
| §8 | Status-date convention; incomplete tasks updated; Remaining Duration primary | [SMH §7.3.2 pp.285–288] |
| §8 | Invalid Actual/Forecast Dates | [SMH §6.2.2.1.2 p.170] |
| §9 | Replan definition, internal vs. external | [SMH §7.3.4.5 pp.330–331] |
| §9 | Rebaseline definition, SRB validation, DM, baseline preservation | [SMH §7.3.4.6 p.331; §7.3.4.7 pp.331–332] |
| §9 | Rebaselining as RIDM-framed reset | [NPR8K §1.2.4.5 p.477; §2.4 p.997] |
| §10 | Cross-skill cross-refs | `mpp-parsing-com-automation §3`; `driving-slack-and-paths §2.3, §3`; `dcma-14-point-assessment §2, §3, §4, §7, §8`; `cui-compliance-constraints`; `nasa-program-project-governance`; `forensic-manipulation-patterns`; `acumen-reference` |
