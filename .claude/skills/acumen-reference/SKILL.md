---
name: acumen-reference
description: Deltek Acumen 8.8 / DECM reference layer for this forensic tool. Metric-semantics dictionary — formula and tripwire mechanics, DECM Jan 2022 catalog structure, Special Fields (IsOutOfSequence, Number of Lags/Leads, FS/SS/FF/SF counts), MPP field mapping for COM-automation extraction, cost-data CSV structure (EVA deferred), Acumen API surface and why CUI forbids calling it, release-note deltas, schedule index and metric catalog. Trigger: Acumen, DECM, tripwire, metric formula, P6 export.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# Acumen Reference

## 1. Purpose and scope

This skill is a **metric-semantics and data-structure dictionary** for Deltek Acumen 8.8 and the DECM Jan 2022 metric catalog, used as a cross-reference layer against this tool's deterministic forensic output. It answers three questions: (a) what does an Acumen/DECM metric ID name? (b) what is the formula and tripwire threshold? (c) how do the fields that metric operates on map to MSP/MPP fields extractable via COM automation?

This skill is **not** a guide to running Acumen Fuse or Acumen Risk, not a prescription that our tool must replicate Acumen internals, and not an instruction to call the Acumen API. The forensic engine is deterministic and local (see `cui-compliance-constraints` §2); Acumen is used only as a vocabulary and threshold reference. DECM row IDs are cited so an analyst can map our engine output to the vocabulary an EVMS IBR or DCMA reviewer expects to see.

## 2. Acumen / DECM vocabulary and metric taxonomy

### 2.1 What Acumen calls a metric

A **metric** is a standard or measure for use in determining how well a project is planned and executed; metrics contain **formulas** and **tripwires (thresholds)** [DMG p.6]. Formulas calculate analysis results; tripwires flag activities that exceed given levels [DMG p.6]. Standard libraries shipped with Acumen include schedule quality, cost, project performance, risk exposure, Earned Value, DCMA 14-Point, NASA Health Check, and GAO [DMG p.6].

### 2.2 Analysis dimensions

Acumen groups analysis three ways: **Ribbons** (activity groupings regardless of time), **Phases** (time-segment groupings), and **Intersections** (where a ribbon and a phase meet) [DMG pp.6–7; p.39]. The **Activity Browser** lists activities that fail a tripwire [DMG p.29].

### 2.3 Acumen record levels

Metrics apply at three levels: **Activity** (ACT), **Work Package** (WP), and **Control Account** (CA) [DMG pp.11–13]. CA and WP metrics expose an additional **Secondary Tripwire Formula** to drill down to activities causing the CA/WP to fail [DMG pp.11, 30]. All CA/WP metrics require Cobra cost data [DMG p.11]. Scoring is **record-based** or **metric-based** [DMG p.14].

### 2.4 Acumen metric IDs vs DECM metric IDs

Two naming conventions appear. **DECM row IDs** follow the EIA-748 guideline structure `GG<A|I>NNN<a–z>` — e.g., `06A506c`, `22I102a` — where `GG` is the guideline number (01–32), `A` denotes an accepted/assertion test, `I` denotes an informational test [DECM sheet "Deltek EVMS-DECM Metrics V5.0", guideline header rows 4, 7, 10, 21, 23, 27, 57, 66, 84, 86, 95, 100, 102, 115, 117, 119, 123, 126, 141, 144]. **Acumen built-in metric IDs** are assigned by metric name inside `.aft` metric templates (e.g., `dcma_decm_metrics_88_DECM_V5.0.aft`) [ARN p.6]. Both conventions resolve to the same formula/tripwire structure.

### 2.5 Categories

Metrics partition into **logic** (predecessor/successor/open-end/dangling/lag/lead/relationship-type), **duration**, **float** (total/free/high-float), **constraint** (MSO/MFO/SNLT/FNLT), **progress** (actual dates, status-date validity), **baseline**, and **EVMS** (BCWS/BCWP/ACWP, CPI/SPI) — mapped by DECM Guideline groupings [DECM sheet guideline rows].

## 3. Metric formula and tripwire mechanics

### 3.1 Formula syntax

Acumen metrics use **MS Excel syntax/scripting language** for formulas, validated by the in-editor Check Formula feature [DMG p.16]. Each metric can include up to four formulas: **Primary**, **Secondary**, **Tripwire**, and **Secondary Tripwire** (CA/WP only) [DMG p.17]. Each formula is built using a three-level hierarchy — **Inclusions → Filters → Formula** — where Inclusions are top-level status/type/time filters, Filters are field-level AND-compound filters, and Formula is the advanced custom expression [DMG pp.18–19].

### 3.2 Array formulas

Primary, Secondary, and derivatives are **Single Value Result Array formulas**: they operate across a population, aggregate with a container function (`SUM`, `AVERAGE`, `COUNT`), and return one value [DMG p.16]. Duration/work/cost fields get pro-rated when activities span multiple phases [DMG p.16; p.34]. The Tripwire formula is **not** an array formula — it is a classic cell formula that returns a Boolean per activity/WP/CA [DMG p.29].

### 3.3 Tripwire thresholds

A **tripwire threshold** is a defined value that, if exceeded, classifies the metric as *triggered* [DMG p.35]. Thresholds can have multiple color-coded intervals as either **normal** (binary) or **gradient** (proximity-aware) scales [DMG pp.35–36]. Three standard scales: **Lowest is Better**, **Highest is Better**, **Ideal Value** [DMG p.35]. This is "indicator-not-verdict" framing — same as `dcma-14-point-assessment` §1 — a breached threshold is a flag, not a finding.

### 3.4 Commonly used syntax

The six functions that carry most of DECM and built-in metrics are `IF`, `SUM`, `AND`, `MAX`, `AVERAGE`, `COUNTIF` [DMG pp.40–41]. IF shorthand: `IF(TaskStatus="Inprogress",1,0)` ≡ `(TaskStatus="Inprogress")` [DMG p.40]. Shorthand is used throughout the DECM formula columns.

### 3.5 Dynamic period fields

`_PeriodStart` and `_PeriodFinish` resolve to the start/finish of the current ribbon or phase [DMG pp.8, 33]. Prorating (on by default) splits durations across periods; off treats each activity as one unit [DMG p.34]. Our tool has no analog — it reports working days at the task level (see `driving-slack-and-paths` §2) — so these fields are vocabulary only.

### 3.6 Weighting

Metric weighting for scorecards uses `(metric A * weight A) * (metric B * weight B) / 10` on a -10 to +10 sliding scale [DMG p.32]. Bad/Neutral/Good classification determines whether a failing task contributes positively or negatively [DMG p.14]. Our tool does not compute a composite score; it reports per-metric pass/fail (inferred — not sourced). *Scope-defer:* confirm in Session 18 review.


## 4. DECM Jan 2022 metric catalog

### 4.1 Sheet and column structure

DECM ships as **DeltekDECMMetricsJan2022.xlsx** with two sheets: the live **"Deltek EVMS-DECM Metrics V5.0"** (325 rows × 18 cols) and a back-history **"Deleted in V5.0"** (2 rows) [DECM workbook sheet list]. Row-3 header: *Metric Count / Metric ID / New\Updated / Attribute / Version / Test Definition / Test Metric Numerator (X) / Test Metric Denominator (Y) / Metric Threshold / Test Type / Acumen Metric Level / Acumen Test Type / Notes / Primary Formula / Secondary Formula / Tripwire Formula / Secondary Tripwire Formula / Deltek Notes* [DECM row 3, cols 1–18].

### 4.2 Row grouping

Rows partition by 32 EIA-748 guidelines. Each guideline starts with a header row, followed by metric rows [DECM "Guideline 1" row 4 … "Guideline 32" row 203]. Guideline 6 (schedule) occupies rows 27–55 and holds most forensic-relevant rows. Column 11 `Acumen Metric Level` marks ACT, WP, or CA; dual-level metrics appear twice with "(Exists at both WP & CA level)" [DECM rows 28, 30].

### 4.3 Formula columns

Columns 14–17 hold the four formula slots from §3.1. DECM uses shorthand array syntax — e.g., row 5 `01A101b` reads `if(_01A101b_X < 0, -1, if(_01A101b_X > 0, _01A101b_X, 0))` where `_01A101b_X` is the test numerator [DECM row 5, col 14]. `Metric Threshold` (col 9) encodes tripwires with `X = 0`, `X/Y = 0%`, `X/Y ≤ 5%`, `X/Y ≤ 10%`, etc. [DECM col 9].

### 4.4 Forensic-relevant DECM rows (Guideline 6)

The rows below correspond to manipulation probes in `forensic-manipulation-patterns` §§4, 5, 6, 7, and 9 (cross-version erosion):

- **06A204b** dangling logic — `X/Y = 0%`, ACT [DECM row 32] → DCMA Check 1b (`dcma-14-point-assessment` §4.1).
- **06A205a** lag usage — `X/Y ≤ 10%`, ACT [DECM row 33] → DCMA Check 3 (§4.3).
- **06A208a** summary-task logic — `X = 0`, ACT [DECM row 34].
- **06A209a** schedule network constraints limited — `X/Y = 0%`, ACT [DECM row 35] → DCMA Check 5 (§4.5); `forensic-manipulation-patterns` §4.4 (constraint injection).
- **06A210a** LOE with discrete successors — `X/Y = 0%`, ACT [DECM row 37].
- **06A211a** high total float rationale — `X/Y ≤ 20%`, ACT [DECM row 38] → DCMA Check 6 (§4.6); `forensic-manipulation-patterns` §7.1.
- **06A212a** out-of-sequence tasks/milestones — `X = 0`, ACT [DECM row 39].
- **06A401a** schedule tool produces true driving path — `X = 0`, ACT [DECM row 42] → DCMA Check 12 CPT (§4.12).
- **06A504a / 06A504b** actual start/finish changed after first report — `X/Y ≤ 10%`, ACT [DECM rows 45, 46] → `forensic-manipulation-patterns` §6.1 and §9 (primary cross-version-erosion probe).
- **06A505a / 06A505b** in-progress/complete tasks have valid actuals — `X/Y ≤ 5%`, ACT [DECM rows 47, 48].
- **06A506a / 06A506b** actual / forecast start-finish valid — `X/Y ≤ 5%` / `X = 0`, ACT [DECM rows 49, 50].
- **06A506c** forecast dates riding the status date — `X/Y ≤ 1%`, ACT [DECM row 52] → `forensic-manipulation-patterns` §6.3 (classic "riding" probe).

### 4.5 EVMS rows — semantics only

Guidelines 8–32 (rows 59–325) govern EVMS (PMB, CPR, BCWS/BCWP/ACWP, CPI/SPI, MR/UB). Examples: **08A101a** PMB alignment with IMS — `X/Y ≤ 10%` CA [DECM row 59]; **22I102a** BCWP > BAC — `X/Y = 0%` WP [DECM row 143]; **23A101a** required VARs generated — `X/Y ≤ 2%` CA [DECM row 145]. Referenced for **semantics only**; EVA integration is **deferred to Phase 3**.

### 4.6 DECM template update rules

The template shipped with Acumen 8.8 is **V5.0** (`dcma_decm_metrics_88_DECM_V5.0.aft`) [ARN p.6]. Merging a newer DECM template does **not** remove metrics DCMA deleted — cleanup is manual (inferred — not sourced) [ARN p.6]. This matters when cross-version-matching a workbook built on an older template against a V5.0-based forensic analysis.

## 5. Special Fields and MSP/MPP field mapping

### 5.1 Acumen Special Fields reference table

Acumen exposes a fixed set of **Special Fields** for use in metric filters and formulas. These are pre-computed by Acumen at import time from the schedule's relationship graph [DMG pp.42–43]:

- `IsOutOfSequence` — returns true for any activity out of sequence for the group [DMG p.42].
- `NumberofPredecessors` / `NumberofSuccessors` — total count regardless of type [DMG pp.42–43].
- `NumberofFSPredecessors` / `NumberofFSSuccessors` — FS relationship count [DMG p.42].
- `NumberofSSPredecessors` / `NumberofSSSuccessors` — SS relationship count [DMG p.42].
- `NumberofFFPredecessors` / `NumberofFFSuccessors` — FF relationship count [DMG p.42].
- `NumberofSFPredecessors` / `NumberofSFSuccessors` — SF relationship count [DMG p.42].
- `NumberofLags` / `NumberofSuccessorLags` — positive-lag relationship counts [DMG pp.42–43].
- `NumberofLeads` / `NumberofSuccessorLeads` — negative-lag (lead) relationship counts [DMG pp.42–43]. Note: Acumen treats a lead as a negative lag, same convention as MPXJ.
- `NumberofDiscreteSuccessors` — counts successors whose EVT is not LOE [DMG p.42].
- `NumberofExternalPredecessors` / `NumberofExternalSuccessors` — inter-project relationships [DMG p.42].
- `NumberofResourceAssignments` — total count of resource assignments [DMG p.42].
- `PreviousActualStart` / `PreviousActualFinish` — the prior snapshot's actual start/finish for the same activity; empty if the activity did not exist in the prior snapshot; populated only when a snapshot is present [DMG p.43]. This is the Acumen equivalent of our cross-version erosion UniqueID match (see `forensic-manipulation-patterns` §9.1).

### 5.2 Mapping to MSP/MPP fields (COM automation)

The forensic tool extracts equivalent values from MS Project via win32com COM automation (see `mpp-parsing-com-automation` §3):

| Acumen Special Field | MS Project COM field / derivation |
| --- | --- |
| `NumberofPredecessors` | `len(task.PredecessorTasks)` from the Tasks collection |
| `NumberofSuccessors` | `len(task.SuccessorTasks)` |
| `NumberofFS/SS/FF/SFPredecessors` | enumerate `task.TaskDependencies` and group by `Type` |
| `NumberofLags` / `NumberofLeads` | partition `Lag` by sign (positive → lag, negative → lead); MPXJ returns minutes — see `mpp-parsing-com-automation` §3.5 |
| `IsOutOfSequence` | derived in our tool's CPM engine; no direct COM field |
| `NumberofResourceAssignments` | `task.Resources.Count` |
| `PreviousActualStart/Finish` | our `diff_engine.py` uses UniqueID-matched prior snapshot — see `mpp-parsing-com-automation` §5 and `driving-slack-and-paths` §7 |

### 5.3 UniqueID discipline

Cross-version matching for any snapshot-dependent comparison (including Acumen's `PreviousActualStart`/`PreviousActualFinish`) requires the **UniqueID is the sole cross-version key** rule from `mpp-parsing-com-automation` §5 and `driving-slack-and-paths` §7. TaskID is reorderable and must not be used.

### 5.4 Unit convention

Acumen's `TotalFloat` in the API data model is exposed in **minutes** [API p.13]. MPXJ and our parser normalize durations and floats to **working days** via the `duration_to_days` normalizer. This mismatch matters when reading Acumen output or setting up a tripwire that quotes a day-threshold — see the Appendix-D gotcha on MINUTES units in `mpp-parsing-com-automation` §3.5.

### 5.5 Source-tool compatibility

Acumen's import layer reads MS Project 2013–2021 Standard/Professional, MSP Server 2013–2019, and Primavera P6 8.4–21.12 (XER/Web/XML) [ATO pp.12–13], plus IPMDAR SPD/CPD, UN/CEFACT, Phoenix 4.0–4.8, PowerProject 16.0.1, and Safran 5.0 [ATO p.13]. Importantly, "Acumen links to MS Project files through your installed copy of MS Project or by directly reading an MS Project file (without needing MSP installed on your PC)" [ATO p.12] — i.e., Acumen has its own MPP reader distinct from our JPype/MPXJ path.

## 6. Cost-data CSV structure (reference only — EVA deferred to Phase 3)

### 6.1 File-structure overview

Acumen accepts cost data via the **CSV Template.csv** file installed at `C:\Program Files (x86)\Deltek\Acumen 8.8\DECM Samples` [ACD p.4]. The format is a multi-section CSV: Calendars, CalendarDets, CPRs, Control Accounts, Work Packages, Planning Packages, and Resource Assignments, each with its own header row and field order [ACD pp.5–8]. Field types are enforced: String, Number, DateTime, or enum [ACD p.13].

### 6.2 Key fields (Control Accounts table)

Control-account fields include `ID` (String), `WbsID`, `ObsID`, `ActualStartDate`, `AcwpCum`, `AcwpCumHours`, `AcwpCur`, `Bac`, `BacHours`, `BaselineFinishDate` (DateTime), `BcwpCum`, `BcwpCur`, `BcwsCum`, `BcwsCur`, `EarlyStartDate`, `ForecastStartDate`, `LateFinishDate`, `PendingStartDate`, `CPICur`, `CPICum`, `SPICur`, `SPICum`, `Status`, `UnitsComplete`, `Manager` [ACD pp.14–17]. `PerformanceMethod` is enum-valued: `None`, `PercentComplete`, `PercentCompleteManualEntry`, `HundredZero`, `ZeroHundred`, `FiftyFifty`, `Apportioned`, `AssignmentPercentageComplete`, `CalculatedApportioned`, `EarnedAsSpent`, `EarningRules`, `LevelOfEffort`, `Milestone`, `PlanningPackage`, `UnitsComplete`, `UserDefined` [ACD p.16] — same enum as DMG's Performance Method table [DMG pp.12–13]. `Status` is `Unopened | Open | Closed` [ACD p.16].

### 6.3 Why this is reference-only

EVA (Earned Value Analysis) computation is **deferred to Phase 3** per the CLAUDE.md roadmap. The CSV schema is documented here so that when Phase 3 lands, a forensic analyst has the vocabulary to map our schedule-side output into the cost-side ingest Acumen expects. Until then, DECM Guideline-8-through-32 rows from §4.5 are **semantics-only** cross-references.


## 7. Acumen API surface — and why our tool does not call it

### 7.1 What the API exposes

The Acumen API is an **XML export interface** [API p.5] with three modules: API Configuration File (XML menu-item config), API Data Model (XML output structure), Platform Integration Framework [API p.6]. ViewLocation enum: `Projects`, `Analysis`, `Logic`, `Forensics` [API p.8].

### 7.2 Data model

`Workbook` contains `Activities`, `Relationships`, `Projects`, `LogicAnalyzer`, `RibbonViews`, `MetricLibrary`, plus `Costs` / `Durations` [API p.10]. `Activity` fields include `FfPredecessorCount`, `FsPredecessorCount`, `SfPredecessorCount`, `SsPredecessorCount`, `PredecessorLinkLagCount`, `PredecessorLinkLeadsCount`, `SuccessorLinkLagCount`, `SuccessorLinkLeadCount`, `IsCritical`, `LongestPath`, `TotalFloat` (minutes), `FreeFloat`, `PrimaryConstraint`/`Date`, `SecondaryConstraint`/`Date` [API pp.12–13]. `Relationship`: `Lag`, `LagUnit`, `PredecessorGuid`, `SuccessorGuid`, `Type` [API p.14]. `Project`: `BaselineStart`, `BaselineFinish`, `CriticalActivityDefinition`, `TimeNow` (status date) [API p.15].

### 7.3 LogicAnalyzer and Forensic Report

`LogicAnalyzer` exposes pre-computed lists: `CircularLogic`, `OpenEnds`, `OpenFinish`, `OpenStart`, `OutOfSequenceLogic`, `RedundantLogic`, `ReverseLogic`, plus relationship groupings (`FFRelationships`, `FSRelationships`, `SFRelationships`, `SSRelationships`, `Lags`, `Leads`, `LogicOnSummaries`) [API p.16] — same checks as Acumen's **S2 // Logic** tab [AQS p.7]. `ForensicReport` holds snapshot-comparison info via `ProjectsTab`, `ActivitiesTab`, `RelationshipsTab`, `ResourcesTab` [API p.19] — the Acumen **Forensics** tab surface [AQS p.8]; functionally equivalent to our `diff_engine.py` for UniqueID-matched analysis (see `forensic-manipulation-patterns` §9.1).

### 7.4 Why our tool does not call the Acumen API

Three reasons: **(1) CUI locality** — the API is reached inside the Acumen client, requiring the MPP to have been loaded into a workbook (see `cui-compliance-constraints` §2a). **(2) Licensing** — requires a licensed installation at `C:\Program Files (x86)\Deltek\Acumen 8.8` [AIG p.6], controlled by Deltek [DMG p.2]. **(3) No admin rights** — the installer must run in Administration mode [ARN p.6]; our envelope is a non-admin workstation. API semantics are documented so an analyst can map our output to what an Acumen user would see — not because we call it.

## 8. Release-note deltas worth tracking (Acumen 8.8 series)

Behavior changes in the 8.8 release that affect metric definitions or downstream reference semantics:

- **DECM V5.0** is the current metric catalog as of the 8.8 release date (October 7, 2022) [ARN p.1; p.6]; template `dcma_decm_metrics_88_DECM_V5.0.aft` [ARN p.6].
- Merging a newer DECM template does **not** remove metrics that DCMA deleted — cleanup is manual [ARN p.6]. Any cross-version comparison of DECM output should confirm the shipped template version before treating a missing metric as a pass.
- Mapping **parallel risks** is new in 8.8 — activities can now have both serial and parallel risks, and iteration math applies Max-of-parallel + Sum-of-non-parallel [ARN p.13]. This affects S3 // Risk output semantics but does not change any DECM schedule metric formula.
- Risk Driver chart can now display **all** drivers (previously capped at 20) [ARN p.14].
- Non-Workday is now its own category on the Risk Drivers chart (previously bundled into Logic) [ARN p.15].
- Risk Matrix now supports up to **10** probability/impact ranges (was 5) [ARN p.17].

None of the 8.8 changes change the DECM schedule-side formulas at the rows we cite in §4.4. The catalog-level change (V5.0) is the only one that matters for cross-referencing our tool's output.

## 9. Cross-skill dependencies

- **`dcma-14-point-assessment`** — DECM rows map onto DCMA checks at: §4.1 (Check 1 Logic, via 06A204b), §4.3 (Check 3 Lags, via 06A205a), §4.5 (Check 5 Hard Constraints, via 06A209a), §4.6 (Check 6 High Float, via 06A211a), §4.12 (Check 12 CPT, via 06A401a), §4.13 (Check 13 CPLI — no direct DECM row; Acumen DCMA library only), §4.14 (Check 14 BEI — no direct DECM row; Acumen DCMA library only).
- **`forensic-manipulation-patterns`** — §9 (cross-version erosion detection) is driven by DECM rows 06A504a/b (actual date changes after first reported) and 06A506c (forecast riding status). §10 (red-flag aggregation) groups DECM thresholds across revisions.
- **`mpp-parsing-com-automation`** — §3 Appendix D gotchas (MINUTES units at Gotcha 5; single-threaded COM at Gotcha 3); §5 UniqueID-not-TaskID rule is the precondition for any snapshot-based Special Field (`PreviousActualStart`/`Finish`).
- **`driving-slack-and-paths`** — §§2–5 cover CPM discipline that Acumen's `TotalFloat`/`FreeFloat`/`LongestPath`/`IsCritical` fields [API p.13] compute from the same relationship graph; our tool derives them locally.
- **`nasa-schedule-management`** — §6 (schedule health and quality, NASA overlay on DCMA 14-Point) explicitly invokes DECM rows as the EVMS backstop for NASA IMS quality expectations.
- **`cui-compliance-constraints`** — §2 (the eight non-negotiable CUI rules) is why we do not call the Acumen API, upload to Acumen cloud, or publish metric results to a remote database (see §7.5).

## 10. What this skill does NOT cover

- **Running Acumen Fuse or Acumen Risk.** Workflow for S1–S5 tabs, Ribbon/Phase view configuration, risk event authoring, and uncertainty slider operation are outside scope [AQS pp.1–14 — referenced only for tab nomenclature].
- **Installing Acumen.** Hardware sizing, deployment models, DSM download procedure, and Citrix/XenApp installation are not forensic-tool concerns [AIG pp.1–61 — referenced only for install location of templates]. Silent-install procedure via `SETUP.ISS` / `SETUP.LOG` is likewise out of scope [ASI pp.1–13].
- **Acumen UI workflows.** Metric editor click-paths, publishing to DOCX/XLSX, dashboard layout are out of scope.
- **Calling the Acumen API at runtime.** See §7.5 — our tool does not integrate with the Acumen client process.
- **Cost-side EVA computation.** Deferred to Phase 3; cost CSV schema documented in §6 for vocabulary only.
- **Replicating Acumen internals.** The forensic engine is deterministic and independent; Acumen is a **reference vocabulary**, not an implementation target.

## 11. Inferred content + scope-defers (single-table summary)

| Location | Statement | Why inferred / deferred | Resolution |
| --- | --- | --- | --- |
| §2.4 | DECM row-ID regex `GG<A|I>NNN<letter>` as an interpretive pattern | Pattern is inferred from the sheet row structure; Deltek does not publish an ID-grammar spec (inferred — not sourced) | Session 18 review; confirm against a fresh DECM release |
| §3.6 | "Our forensic tool does not compute a composite score" — design statement | Design choice not documented in sources (inferred — not sourced) | Session 18 review |
| §5.2 | MSP COM field mapping table (row-by-row mapping of Acumen Special Fields to COM derivations) | Mapping is a design aid; individual COM field identities are sourced in `mpp-parsing-com-automation` §3, but the Special-Field-to-COM-field crosswalk itself is inferred (inferred — not sourced) | Session 18 review |
| §4.6 | "cleanup is manual" — procedural interpretation | Release note states deleted metrics are not auto-removed; the word "manual" is an inference (inferred — not sourced) | Session 18 review |
| §8 | "None of the 8.8 changes change the DECM schedule-side formulas at the rows we cite in §4.4" | Review of ARN pp.13–48 did not find schedule-metric-formula deltas, but absence-of-evidence (inferred — not sourced) | Session 18 review; re-check on next ARN edition |

## 12. References

| Tag | Document | Edition |
| --- | --- | --- |
| DMG | Metric Developer's Guide | 2022-10-07, 44 pp. |
| DECM | EVMS-DECM Metrics V5.0 | 2022-01 xlsx, 325 rows |
| ATO | Technical Overview and System Requirements | 2022-10-07, 17 pp. |
| AQS | Quick Start Guide | 2022-10-07, 19 pp. |
| AIG | Installation Guide | 2022-10-07, 61 pp. (scope-only) |
| ASI | Silent Install guide | 2022-10-07, 13 pp. (scope-only) |
| API | API Guide | 2022-10-07, 46 pp. |
| ACD | Cost Data .CSV Structure | 2022-10-07, 26 pp. |
| ARN | Release Notes | 2022-10-07, 48 pp. |

All documents are Deltek Acumen 8.8 series. Cross-skill references in §9 resolve on `main` to: `dcma-14-point-assessment` §§4.1, 4.3, 4.5, 4.6, 4.12, 4.13, 4.14; `forensic-manipulation-patterns` §§4.4, 6.1, 6.3, 9, 9.1, 10; `mpp-parsing-com-automation` §§3, 3.3, 3.5, 5; `driving-slack-and-paths` §§2–5, 7; `nasa-schedule-management` §6; `cui-compliance-constraints` §§2, 2a.
