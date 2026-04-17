---
name: nasa-program-project-governance
description: NASA program/project governance constraining schedule control — Programmatic vs. Institutional Authority, Technical Authority, program/project types, Key Decision Points (KDPs), Life-Cycle Reviews (MCR SRR MDR PDR CDR SIR ORR PIR DR), Decision Authority, PMC (APMC DPMC CMC), Standing Review Board, Agency Baseline Commitment, Management Agreement, JCL, rebaseline, Funded Schedule Margin, UFE, Decision Memorandum, BPR cadence, NPR 8000.4C, NID 7120.148, GPR 7120.7B.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# NASA Program and Project Governance

Authoritative reference for NASA governance as it constrains schedule control. Primary sources: `[NPR8K]` (NPR 8000.4C, 19 Apr 2022), `[NID]` (NID 7120.148 transmitting NPR 7120.5 Rev F, 9 Dec 2024), `[GPR]` (GPR 7120.7B, 17 Sep 2018). Supporting source `[SMH]` (NASA Schedule Management Handbook Rev 2, 15 Mar 2024) cited only where governance content overlaps schedule management. Unsourced rules are labelled `(inferred — not sourced)` with a Session-18 scope-defer note in §15.

## 1. Purpose and scope

This skill gives the forensic engine the governance context for a schedule — which KDP was imminent, which LCR had just closed, what baseline was in force, what Decision Authority signed what — and the vocabulary to name it. It covers the two-authority model, program/project types, life-cycle phases and KDPs, LCRs and the SRB, PMC hierarchy, authority documents, ABC and MA, JCL, governance-managed schedule margin, reporting cadence, and rebaseline triggers.

It does **not** restate IMS construction, margin placement, status-date discipline, or SRA procedure — see `nasa-schedule-management §§2, 3, 5, 7`. DCMA formulas are in `dcma-14-point-assessment §§4, 8`. Driving-path mechanics are in `driving-slack-and-paths §2.3`. `.mpp` extraction is in `mpp-parsing-com-automation §3`. CUI handling during governance reporting is in `cui-compliance-constraints`. Forensic interpretation of deviations is deferred to `forensic-manipulation-patterns (planned — future skill)`.

Forensic framing: these documents state *expected* governance posture. Deviation (CDR without a JCL update; KDP-C without an ABC; lost FSM without a replan) is process drift, not automatically manipulation — cite the rule, characterise the deviation, leave intent to the investigator.

## 2. The two-authority governance model

NASA governance runs on two parallel lines: **Programmatic Authority** (Mission Directorates and their programs/projects) and **Institutional Authority** (Center institutional organisations and other non-programmatic units) [NID §3.1.1 p.42]. **Technical Authority (TA)** is a subset of Institutional Authority providing independent safety-and-mission-success oversight through individuals with formally delegated authority funded independently of the Programmatic line [NID §3.1.1 p.42; §3.3.1 p.45; §3.3.2 p.46]. TA originates with the Administrator and is delegated to the NASA AA, then to the NASA Chief Engineer (Engineering TA), Chief SMA (SMA TA), Chief Health and Medical Officer (HMTA), and then to Center Directors [NID §3.3.2 p.46]. TA concurrence is required on technical and operational decisions involving safety and mission-success residual risk [NID §3.3.3.2 p.46].

Risk-acceptance decisions — including schedule-risk acceptance via rebaseline, waiver, or a decision to proceed past a KDP — require TA concurrence or elevation through formal dissent on nonconcurrence [NPR8K §2.3.4 p.18; §3.5.3–3.5.5 pp.27–28]. A KDP is "an integrated system-level roll-up of the many decisions… through which risk has been implicitly or explicitly accepted… and a decision to proceed represents both formal acceptance of this risk and accountability for this risk going forward" [NPR8K §3.5.1 p.27]. Each Acquirer oversees its Providers' risk management, and performance-requirement rebaselines must be negotiated with higher-level organisations, documented, and subject to configuration control [NPR8K §1.2.1.6 p.8; §1.2.4.5 p.15].

Forensic consequence: a schedule version crossing a KDP or a rebaseline is "before vs. after under a specific Decision Authority signature, with or without TA concurrence, with or without a documented basis." Provenance metadata lives outside the `.mpp`; the operator supplies it at import.

## 3. Program vs. project and categorization

A **program** is a strategic Mission Directorate investment with a defined architecture, requirements, funding, and management structure that initiates and directs one or more projects [NID §2.1.1.1.a p.16]. A **project** is a specific investment identified in a Program Plan with defined requirements, an LCC, a beginning, and an end [NID §2.1.1.1.b p.16]. Four program types — **single-project**, **uncoupled**, **loosely coupled**, **tightly coupled** — are distinguished by the dependence relationship among constituent projects [NID §2.1.2.1 pp.16–17].

Projects are **categorized 1, 2, or 3** on LCC and priority per `[NID]` Table 2-1 p.18: bands are LCC < $365M, $365M ≤ LCC ≤ $2B, LCC > $2B (human spaceflight or significant radioactive material default to Category 1). Programs and Category 1 projects are governed at Agency level (NASA AA Decision Authority, APMC); Category 2/3 at Directorate level (MDAA, DPMC) [NID §2.3 p.28; §2.3.2 p.28]. Categorization is the first governance variable the tool must capture at import — it determines applicable LCR set, PMC, SRB convening authority, EVM/JCL thresholds, and margin rules.

## 4. Life cycles, phases, and KDPs

NASA P/ps follow a four-part management process: **Formulation**, **Approval (for Implementation)**, **Implementation**, **Evaluation** [SMH §2.1 pp.14–15]. Projects and single-project programs use Pre-Phase A, A (Concept/Technology Development), B (Preliminary Design/Technology Completion), C (Final Design/Fabrication), D (Assembly, Integration, Test, Launch), E (Operations/Sustainment), F (Closeout) [NID Fig 2-5 p.23]. Program life cycles differ by type [NID Figs 2-2 through 2-4 pp.20–22]. Schedule detail increases through the life cycle [SMH §2.1 pp.14–15].

A **Key Decision Point (KDP)** is the event at which the Decision Authority determines readiness to progress and **establishes the content, cost, and schedule commitments for the ensuing phase(s)** [NID §2.2.7 p.26]. Programs use Roman-numeral KDPs (0, I, II, …); projects and single-project programs use letters (A, B, C, D, E, F). Transition occurs immediately at KDP approval except D → E, which transitions after on-orbit checkout [NID §2.2.7 p.26].

The **Decision Authority** determines whether and how the P/p proceeds and authorises the key cost, schedule, and content parameters that govern the remaining life-cycle activities [NID §2.3 p.28]. For programs and Category 1 projects: NASA AA (delegable to MDAA). For Category 2/3 projects: MDAA (delegable to Center Director for phase transitions, retaining program-level requirements, funding limits, launch dates, external commitments) [NID §2.3 p.28]. Forensic relevance: a schedule weeks before a KDP is a product under active Decision Authority negotiation, not a stable plan; versions across a KDP are governed by different Decision Memoranda.

## 5. Life-Cycle Reviews (LCRs), the SRB, and the PMC hierarchy

LCRs provide periodic assessment of technical and programmatic status and health against six criteria: alignment with Agency strategic goals, adequacy of management approach, adequacy of technical approach, adequacy of integrated cost and schedule estimates and funding strategy, adequacy and availability of resources other than budget, and adequacy of the risk-management approach [NID §2.2.4 p.24]. An LCR is complete when the governing PMC and Decision Authority sign the Decision Memorandum at the KDP [NID §2.2.4 p.24].

Space-flight LCR set: **MCR**, **SRR**, **SDR/MDR**, **PDR**, **CDR**, **PRR** (multi-build only), **SIR**, **ORR**, **FRR/MRR**, **PLAR**, **CERR**, **PFAR**, **PIR**, **DR** [NID §2.2.5 p.25; Tables 2-3/2-4/2-5 pp.29–36]. The **Standing Review Board (SRB)** conducts SRR, SDR/MDR, PDR, CDR, SIR, ORR, PIR; the MCR uses an independent assessment team consistent with the PFAL [NID §2.2.5 p.25]. Convening authorities vary by program type and project category per `[NID]` Table 2-2 p.25. PM, SRB chair, and Center Director (or Engineering TA designee) mutually assess LCR readiness 30–90 calendar days pre-LCR [NID §2.2.5.3 p.26].

Three **Program Management Council** levels periodically evaluate performance (cost, schedule, risk, risk mitigation): **APMC** for programs and Category 1 projects; **DPMC** for Category 2/3 projects; **CMC** at each Center; **ICMC** for multi-Center P/ps [NID §2.3.2 p.28; §2.3.4 pp.28–29]. After each LCR, the SRB chair and PM brief the applicable councils [NID §2.3.5 p.29]. LCR entrance/success criteria specifics beyond `[NID]`'s six-criteria framework are `(inferred — not sourced)` and deferred to Session 18.

Forensic anchor: LCR schedules and surrounding KDPs are the skeleton of a P/p's narrative. A `.mpp` "three weeks before CDR" is a different artefact than "three weeks after CDR" — expected maturity differs and the governing DM may change at the next KDP.

## 6. Authority documents and the Decision Memorandum

Governance commitments are carried in a controlled set of authority documents [NID §2.2.3 p.19]:

- **PFAL.** MDAA-issued; authorises pre-formulation work for single-project programs, Category 1 projects, and select Category 2 projects [NID §2.2.3.1 p.23].
- **FAD** (program and project). Prepared by the Mission Directorate; authorises planning, AoA, and (for projects) requirements, schedules, and funding [NID §2.2.3.2/4 pp.23–24].
- **PCA.** MDAA–NASA AA agreement authorising program transition from Formulation to Implementation; documents requirements, objectives, management/technical approach, technical performance, schedule, time-phased cost plans, safety/risk factors, agreements, LCRs [NID §2.2.3.3 p.23].
- **Program Plan / Project Plan.** Signed agreement among MDAA, Center Director(s), and manager; documents objectives, scope, implementation approach, interfaces, time-phased cost plans consistent with the PCA [NID §2.2.3.4/7 p.24].
- **Formulation Agreement.** Defines technical and acquisition work and Phase A/B schedule and funding [NID §2.2.3.5 p.24].

The **Decision Memorandum** summarises Decision Authority decisions at KDPs or between; describes the constraints and parameters within which the Agency and PM operate; carries the supporting cost and schedule data sheet [NID §2.4.1.1 p.37]. Once signed at the conclusion of the governing PMC, it is appended to the FA, Program Plan, or Project Plan [NID §2.4.1 p.37]. It includes the ABC (if applicable), the MA cost and schedule, UFE, and schedule margin held above the project [NID App. A p.56 DM definition]. Forensic anchor: where the `.mpp` baseline disagrees with the DM cost-and-schedule data sheet, the `.mpp` is not authoritative.

## 7. ABC and Management Agreement

The **Management Agreement (MA)** within the DM defines the parameters and authorities over which the PM has management control; the PM is accountable for its terms [NID §2.4.1.2 p.38]. The MA is documented at every KDP and may be changed between KDPs; a significant divergence requires a DM amendment [NID §2.4.1.2 p.38].

The **Agency Baseline Commitment (ABC)** is documented in the DM for Implementation (KDP-C) and becomes the baseline against which Agency performance is measured during Implementation [NID §2.4.1.5 p.39]. For LCC ≥ $250M the ABC is the basis of the Agency's external commitment to OMB and Congress [NID §2.4.1.5 p.39]. For P/ps with a definite Phase E end point, the LCC estimate and other parameters become the ABC; for those with unspecified Phase E, the initial capability cost does [NID §2.4.1.5 pp.39–40]. The DM also documents resources the Decision Authority determines appropriate beyond those estimated — including schedule margin and UFE held above the project [NID §2.4.1.4 p.38]. Forensic anchor: the ABC is the schedule's sovereign; a replan that keeps the working schedule intact but breaches the ABC triggers different governance than one that stays inside it.

## 8. JCL and schedule confidence

Single-project programs (any LCC) and projects with LCC > $250M develop probabilistic analyses quantifying the likelihood the estimate will be met [NID §2.4.3 p.40]. Rules tier by LCC and KDP:

- **KDP-B.** Single-project programs < $1B and projects $250M–$1B provide probabilistic cost and schedule ranges with low/high confidence; JCL optional [NID §2.4.3.1.a p.40]. Single-project programs and projects ≥ $1B develop a **Joint Cost and Schedule Confidence Level (JCL)** with corresponding values (e.g., 50%, 70%) [NID §2.4.3.1.b p.40].
- **KDP-C.** Single-project programs (any LCC) and projects > $250M develop a cost-loaded schedule and perform a risk-informed probabilistic analysis producing a JCL — the product of a probabilistic analysis of coupled cost and schedule [NID §2.4.3.2 pp.40–41].
- **CDR.** Single-project programs and projects ≥ $1B update the KDP-C JCL and communicate values to the APMC [NID §2.4.3.3 pp.40–41].
- **KDP-D.** Same class updates the JCL if current development costs have exceeded development ABC cost by ≥ 5% [NID §2.4.3.4 p.41].
- **Rebaseline.** JCL is recalculated as part of the rebaselining approval process for any single-project program or project > $250M [NID §2.4.3.5 p.41].

Mission Directorates plan and budget single-project programs ≥ $1B at KDP-B and (any LCC) programs/projects > $250M at KDP-C at **70% JCL** or as approved by the Decision Authority [NID §2.4.4.1–2 p.41]. KDP-C funding shall be consistent with the MA and no less than a **50% JCL** equivalent [NID §2.4.4.4 p.41]. Deviations require justification and documentation in the DM [NID §2.4.4.3/5 p.41].

## 9. Funded Schedule Margin and UFE

**Funded Schedule Margin (FSM)** per `[GPR]` is the project-held priced time allowance in working days allocated to project schedules to protect them from uncertainty and risk [GPR §1.2 p.4; App. A.3 p.19]. FSM is expressed in working days and dollars but carries no specific scope [GPR §1.2 p.4]. Governing rules: FSM is relative to the critical path; funds use a phase-appropriate burn rate; FSM is **not** part of project-held UFE; contractor-held FSM not PM-controlled is excluded; working-day counts use a 5-day week (≈ 21 days/month); slack ≠ FSM [GPR §2.0 p.9; App. A.3/A.7 pp.18–19].

Mission-flight thresholds: from KDP-C to start of observatory I&T, **1.5 months per 12 months** (Interval 1); from I&T start to delivery to launch site, **2 months per 12 months** (Interval 2); from delivery to launch, **1 week per month** (Interval 3) [GPR §2.1 p.9; Table 1 p.6]. Standalone I/P and enterprise ground-system projects use analogous intervals tied to I/P I&T and to ORR or ground-system freeze [GPR §§2.2–2.3 p.11; Tables 2–3 pp.7–8].

**Budget margin** = project-held UFE ÷ remaining cost-to-go (less UFE) [GPR §1.2 p.4; §3.0 pp.12–13]. Mission-flight step-down: 25% required / 30% goal at KDP-A/B; 25% at KDP-C; 20% at KDP-D; 10% at delivery to launch site; plus 15% (reducing to 10%) for Phase E/F [GPR §3.1 p.13; Table 1 p.6]. Noncompliance is directed by the CMC, whose position is reflected in GSFC's letter to the KDP Decision Authority [GPR §1.5 p.5]. Forensic anchor: a `.mpp` whose critical path leaves required FSM unfilled is forensically distinct from one whose FSM was allocated and then consumed — the latter is a risk-realisation record, the former a non-compliant plan.

## 10. Status reporting cadence

Three governance cadences operate in parallel:

- **Monthly Agency.** The **Baseline Performance Review (BPR)** is a monthly Agency-level independent assessment informing senior leadership of performance against mission and P/p commitments; the NASA Chief Engineer leads mission and P/p performance assessment for the BPR [NID App. A p.54 BPR definition; §3.2.a/h pp.42–44].
- **Monthly Center.** The CMC monitors P/p status through mechanisms including Monthly Status Reviews [NID §3.2.d(4) p.43]. At Goddard, projects present FSM and budget-margin status at monthly FPD tag-ups and Center MSRs, with metrics reported monthly to the CMC [GPR §4.0 p.17; P.9 p.3].
- **Quarterly Agency repository.** Covered space-flight projects and single-project programs (and R&T projects ≥ $50M) submit IMS in native scheduling-tool format to the Agency Schedule Repository quarterly, SRR through LRR [SMH Fig 2-5 p.22].

Internal P/p reporting runs at least monthly against the IMS status date; LCR preparation uses the three-drop cadence (Data Access; Data Drop 1; Data Drop 2) negotiated in the SRB Terms of Reference [SMH §8.3.2.3.1 p.354; §8.3.2.3.2 pp.355–356]. EVM surveillance is continuous [NID §2.2.8.4 p.27]. DM amendments are issued between KDPs on significant MA divergence [NID §2.4.1.2 p.38].

## 11. Rebaseline, replan, and configuration control

Programs and projects are **rebaselined** when any of three triggers is met [NID §2.4.1.8 pp.39–40]: (1) estimated development cost exceeds the ABC development cost by **30% or more** (and for projects > $250M, Congress has reauthorised); (2) the NASA AA judges external events make rebaseline appropriate; (3) the NASA AA judges the ABC scope has been changed or the project interrupted. ABCs are not rebaselined for growth failing these triggers [NID §2.4.1.8 p.40]. On rebaseline the Decision Authority directs an SRB (or equivalent) review of the new baseline; JCL is recalculated per §8 [NID §2.4.1.8 p.40; §2.4.3.5 p.41]. Risk documentation, the RMP, and risk-acceptance decisions are maintained under formal configuration control [NPR8K §3.2.2k p.26]. Performance-requirement changes are subject to configuration control and Acquirer approval [NPR8K §1.2.4.5 p.15].

A **replan** updates the schedule inside an unchanged ABC; **rebaseline** changes the ABC. This maps to the comparator's baseline-category choice; execution mechanics are in `nasa-schedule-management §8`.

## 12. Roles with schedule authority

- **NASA Administrator / NASA AA.** Agency Decision Authority for programs and Category 1 projects; sets Agency risk posture [NID §3.2.a–b pp.42–43; NPR8K §2.2.2 p.17].
- **MDAAs.** Programmatic Authority within their Mission Directorate; Decision Authority for Category 2/3 projects; approve Program/Project Plans; report cost/schedule/technical/risk deviations to Agency forums [NID §3.2.c p.43].
- **Center Directors.** Allocate Center resources to P/p schedules; concur on estimate adequacy; report executability to the Decision Authority [NID §3.2.d(3), (6), (9) pp.43–44].
- **Program Manager / Project Manager.** Accountable for technical, cost, and schedule performance and commitments [NID §3.2.e–f p.44; §3.3.1 p.45].
- **Technical Authorities (Engineering, SMA, H&M).** Concur on decisions involving safety and mission-success residual risk; elevate nonconcurrences via formal dissent [NID §3.3.3.2 p.46; NPR8K §2.3.4 p.18].
- **SRB.** Independent assessment of technical and programmatic status/health at LCRs; reports to convening authorities and PMCs [NID §2.2.5 p.25; §2.3.5 p.29].
- **CFO / OCFO.** Agency cost-and-schedule analysis leadership; sets policies, methods, standards [NID §3.2.g p.44].

Planner/Scheduler and Schedule Analyst detail is governed by `[SMH]` — see `nasa-schedule-management §11`.

## 13. Cross-skill anchors

- **nasa-schedule-management** — IMS mechanics, margin placement, status-date discipline, SRA procedure, replan-vs-rebaseline execution. Governance envelope here; mechanics there.
- **dcma-14-point-assessment** — schedule-health gates supporting the "adequacy of integrated cost and schedule estimates" LCR criterion [NID §2.2.4 p.24].
- **driving-slack-and-paths** — driving-path analysis for FSM sufficiency against the current critical path [GPR §2.0.b p.9].
- **mpp-parsing-com-automation** — `.mpp` extraction; governance provenance (KDP, LCR, ABC version) is supplied separately.
- **cui-compliance-constraints** — CUI handling during governance reporting, incl. Agency Schedule Repository submissions.
- **forensic-manipulation-patterns (planned — future skill)** — interpretation of governance-deviation signatures.
- **acumen-reference (planned — future skill)** — Acumen Fuse metric cross-reference.

## 14. What this skill does NOT cover

- **Systems-engineering NPR and SRB Handbook content.** Outside the approved source list; LCR entrance/success criteria beyond what `[NID]` restates are `(inferred — not sourced)` and deferred to Session 18.
- **NPD 1000-series governance.** Referenced by `[NPR8K]` and `[NID]` but not cited directly; Session 18 may add a supplemental module if in scope.
- **PMIAA implementation detail.** Referenced in `[NID]` footnotes only; outside scope.
- **Forensic interpretation of governance deviations.** Deferred to `forensic-manipulation-patterns (planned — future skill)`.
- **Engine-code mechanics.** DM-tag plumbing in the Flask layer is deferred to implementation.

## 15. References

| Rule / concept | Source | Location |
|---|---|---|
| KDP as integrated risk-acceptance roll-up | NPR8K | §3.5.1 p.27 |
| TA concurrence on residual-risk decisions | NPR8K | §2.3.4 p.18; §3.5.3–5 pp.27–28 |
| Acquirer oversight; rebaseline negotiation, CM | NPR8K | §1.2.1.6 p.8; §1.2.4.5 p.15 |
| RMP elements incl. reporting frequency | NPR8K | §3.2.2i pp.21–23 |
| Risk documentation under configuration control | NPR8K | §3.2.2k p.26 |
| Program vs. project definitions; four program types | NID | §2.1.1.1 p.16; §2.1.2 pp.16–17 |
| Project categorization (LCC × priority) | NID | Table 2-1 p.18 |
| Four life-cycle figures | NID | Figs 2-2 through 2-5 pp.20–23 |
| Four-part management process | SMH | §2.1 pp.14–15 |
| KDP definition; content/cost/schedule commitments | NID | §2.2.7 p.26 |
| Decision Authority by category | NID | §2.3 p.28 |
| LCR six criteria; LCR completion at KDP DM sign | NID | §2.2.4 p.24 |
| LCR set and SRB scope; LCR readiness 30–90 days pre-LCR | NID | §2.2.5 p.25; §2.2.5.3 p.26 |
| LCR objective and maturity tables | NID | Tables 2-3/2-4/2-5 pp.29–36 |
| SRB convening-authority matrix | NID | Table 2-2 p.25 |
| APMC / DPMC / CMC / ICMC hierarchy | NID | §2.3.2 p.28; §2.3.4 pp.28–29 |
| Post-LCR SRB chair/PM council briefing | NID | §2.3.5 p.29 |
| PFAL / FAD / PCA / Program & Project Plans / FA | NID | §2.2.3 pp.23–24 |
| Decision Memorandum content; MA amendment rule | NID | §2.4.1.1 p.37; §2.4.1.2 p.38; App. A p.56 |
| ABC establishment at KDP-C | NID | §2.4.1.5 p.39 |
| UFE and above-project schedule margin in DM | NID | §2.4.1.4 p.38 |
| JCL at KDP-B/C, CDR, KDP-D, rebaseline | NID | §2.4.3 pp.40–41 |
| 70% JCL plan/budget; 50% JCL floor | NID | §2.4.4 p.41 |
| Rebaseline triggers (30%; external; scope) | NID | §2.4.1.8 pp.39–40 |
| EVM for LCC > $250M; EIA-748 | NID | §2.2.8 p.27 |
| IBR required when EVM required | NID | §2.2.8.3 p.27 |
| BPR monthly Agency assessment | NID | App. A p.54; §3.2.a/h pp.42–44 |
| Programmatic and Institutional Authority | NID | §3.1.1 p.42 |
| Technical Authority delegation chain | NID | §3.3.2 p.46 |
| PM / Project Manager accountability | NID | §3.2.e–f p.44; §3.3.1 p.45 |
| MDAA performance-deviation reporting | NID | §3.2.c p.43 |
| Center Director concurrence on estimates | NID | §3.2.d(9) p.44 |
| CFO cost-and-schedule policy leadership | NID | §3.2.g p.44 |
| FSM definition and rules | GPR | §1.2 p.4; §2.0 p.9; App. A.3 p.19 |
| FSM mission-flight intervals | GPR | §2.1 p.9; Table 1 p.6 |
| FSM standalone I/P and enterprise ground-system | GPR | §§2.2–2.3 p.11; Tables 2–3 pp.7–8 |
| Budget-margin step-down by KDP | GPR | §3.1 p.13; Table 1 p.6 |
| Slack ≠ FSM | GPR | App. A.7 p.18 |
| Monthly FSM/budget-margin reporting to CMC | GPR | P.9 p.3; §4.0 p.17 |
| CMC noncompliance direction in GSFC KDP letter | GPR | §1.5 p.5 |
| Quarterly IMS to Agency Schedule Repository | SMH | Fig 2-5 p.22 |
| Monthly IMS status; LCR three-drop cadence | SMH | §8.3.2.3.1 p.354; §8.3.2.3.2 pp.355–356 |
