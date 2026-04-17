---
name: driving-slack-and-paths
description: Forensic CPM driving path and driving slack analysis. SSI focus-point methodology vs total slack and free slack. Critical path via forward pass / backward pass. Task-specific driving path trace from a UniqueID. Float, near-critical, secondary path, tertiary path bands. Eroding slack across versions. Period A slack rule for but-for analysis. CPM discipline invariants.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# Driving Slack and Paths

Forensic analysis of a CPM schedule's driving path, critical path, and near-critical bands, anchored on the Structured Solutions Incorporated (SSI) driving-slack methodology authored by Kenny Arnold (SSI, CTO). This skill is the forensic engine's CPM-path reasoning layer. It tells the engine what to compute, what to label, what to cite, and what NOT to compute (those belong to sibling skills).

## 1. Overview — driving slack vs. total slack, driving path vs. critical path

A CPM schedule carries three distinct slack quantities that are routinely conflated by non-forensic tools:

- **Total Slack (TS)** — "the amount of schedule flexibility any given task has to any tasks within its work stream that have a deadline set or the end of the schedule" (SSI slide 9).
- **Free Slack (FS)** — "the amount of schedule flexibility any given task has to its *nearest successor*" (SSI slide 10).
- **Driving Slack (DS)** — "the amount of Schedule Flexibility a task has before it begins to drive a Focus Point" (SSI slide 5). **Driving Slack is ONLY calculated to a specific focus point** (SSI slide 6).

SSI states plainly: **Driving Slack ≠ Total Slack** and **Driving Slack ≠ Free Slack** (SSI slide 7). The three quantities answer three different questions and generally return three different numbers for the same task.

The downstream consequence is the paper's central forensic claim: *"Calculating a Critical or Driving Path using Total Slack or Free Slack can be unreliable because neither values are calculated to a specific focus point"* (SSI slide 11). Correspondingly, *"Using Driving Slack is the MOST ACCURATE way to calculate the project's Critical Path or any Driving Paths"* (SSI slide 12).

A **driving path** is the chain of tasks whose driving slack to a nominated Focus Point equals zero. The project **critical path** is the driving path whose Focus Point is the project finish milestone (or equivalent end-of-schedule anchor). Every critical path is a driving path; not every driving path is the critical path. The distinguishing input is which Focus Point the analyst picks.

Per SSI's learning objectives (slide 3), this skill covers (a) the concept of Driving Slack vs. Total Slack and Free Slack, (b) how Driving Slack is used to calculate a Driving Path, and (c) how a dependency-analysis tool consumes Driving Slack to reason about predecessor chains.

## 2. The SSI driving slack methodology

### 2.1 Definition (verbatim, SSI slides 5–6)

> "Driving Slack is the amount of Schedule Flexibility a task has before it begins to drive a Focus Point." (SSI slide 5)
>
> "Driving Slack is ONLY calculated to a specific focus point." (SSI slide 6)

A Focus Point is any task, milestone, or date-bearing node that the analyst selects as the target. It may be the project finish milestone (→ critical path), an interim delivery milestone, a contract-bearing milestone, or any operator-selected UniqueID.

### 2.2 Calculation method

For a given Focus Point F and any task T upstream of F in the logic network, Driving Slack DS(T → F) is computed by tracing every forward logic path from T to F and asking: by how many working days can the earliest position of T be delayed (or extended, subject to its relationship type) before the earliest occurrence of F is pushed later than its currently computed early date? If the answer is zero, T is **driving** F. If the answer is positive, T has that many working days of flexibility relative to F specifically — not relative to the project end, not relative to its nearest successor.

Driving Slack is path-specific. A task with two forward logic chains to F yields a single DS value equal to the minimum slack along the driving chain. Tasks off the forward-reachable subgraph of F have no defined Driving Slack to F.

### 2.3 How DS differs from TS and FS

- **TS** is calculated against the end of the schedule (or the nearest deadline in the workstream) — so a task whose workstream dead-ends on a deadline that is *later* than F will report TS > 0 while actually being a driver of F (SSI slides 9, 11).
- **FS** is calculated against the nearest successor only — so a task with a short-duration non-driving successor will report FS = 0 while contributing no pressure to F (SSI slides 10, 11).
- **DS** is calculated against F and only F (SSI slide 6) — so DS is the only quantity that correctly labels "drives this specific milestone" versus "does not drive this specific milestone."

### 2.4 Worked example (SSI slides 14–22)

Three predecessors feed Focus Point *2023-12-15*:

- **Predecessor 3 (FS → Focus)** finishes 2023-12-14. Direct driver. **DS = 0.** The same task's TS = 1 (because the schedule deadline falls one day past the Focus Point, 2023-12-16, DL; SSI slide 16). This is the clean illustration that DS and TS are not the same number for the same task.
- **Predecessor 2 (FS → Pred 3)** finishes 2023-12-12. Two working days of slack against Pred 3's 2023-12-14 start. **DS = 2** (SSI slide 17). Its Free Slack against its nearest successor (Pred 3) is **FS = 1** (SSI slide 18) — confirming DS ≠ FS.
- **Predecessor 1 (SS lag 0 → Pred 2)** starts 2023-12-11. Four working days of slack before it would begin to drive F. **DS = 4** (SSI slide 19). Its Free Slack is **FS = 0** because Pred 2 starts the day after Pred 1 ends (SSI slide 20) — so a task with zero Free Slack can still have four working days of Driving Slack to the Focus Point. This is the paper's strongest argument against using FS to infer drivers.

Tasks Y → X → Predecessor 3 → Focus Point, all FS links with no slack, yield **DS = 0 at every level** (SSI slide 22). A multi-tier driving chain is fully exposed by walking driving slack = 0 backward from F.

## 3. Critical path identification

Per Lessons Learned §11 #1 (Critical Path Trace), the forensic engine's critical-path module must:

- Run a **forward pass** and a **backward pass** on the full extracted schedule network (Lessons Learned §11 #1).
- Handle **all four relationship types**: Finish-to-Start (FS), Start-to-Start (SS), Finish-to-Finish (FF), Start-to-Finish (SF), and handle lead/lag on every link (Lessons Learned §11 #1).
- Respect **all six constraint types**: Start No Earlier Than (SNET), Start No Later Than (SNLT), Finish No Earlier Than (FNET), Finish No Later Than (FNLT), Must Start On (MSO), Must Finish On (MFO) (Lessons Learned §11 #1).
- **Validate against MS Project's own Critical flag** — if the forensic engine disagrees with MS Project's critical-path marking, the parser or CPM math is wrong and must be fixed before proceeding (Lessons Learned §11 #1).
- Emit an **ordered list of critical-path tasks with float values** (Lessons Learned §11 #1).

A task is on the critical path when its Total Slack ≤ MSP's configured critical-slack threshold (default 0, user-configurable via Tools → Options → Calculation → "Tasks are critical if slack is less than or equal to N days") — i.e., whatever TS value causes MSP's own Critical flag to fire for that task per §3's MSP-validation requirement — or when its Driving Slack to the project finish Focus Point = 0, which is the SSI-preferred test per slide 12.

**Multiple critical paths.** When two or more independent logic chains both terminate at the project finish with zero slack, the engine reports each chain separately as "Critical Path A," "Critical Path B," etc. No path is dropped; the analyst needs to see every zero-slack route. Per SSI slide 12, using Driving Slack to the project finish Focus Point is the most accurate way to distinguish genuine critical paths from near-critical tasks that merely happen to share a TS = 0 reading due to deadline coincidence.

## 4. Task-specific driving path analysis

Per Lessons Learned §11 #2 (Driving Path Trace), the engine's task-specific driving-path module must:

- Accept a **target UniqueID** nominated by the operator (the Focus Point in SSI terms; SSI slide 6).
- Trace **backward from the target task through driving predecessors** (Lessons Learned §11 #2).
- Calculate **relationship slack for every predecessor link** in the chain (Lessons Learned §11 #2).
- Identify which predecessors are **driving (relationship slack = 0)** vs. **non-driving** (Lessons Learned §11 #2).
- Emit an **ordered driving chain + relationship slack table** (Lessons Learned §11 #2).

Relationship slack is the per-link expression of SSI's Driving Slack: the number of working days the predecessor side of a link can shift before it begins to drive the successor side of that link. Walking every relationship-slack-zero link backward from the Focus Point produces the driving chain. Any link with relationship slack > 0 terminates that branch of the walk — by definition, the predecessor does not drive the Focus Point through that link.

SSI slide 22 demonstrates the multi-tier case: when Task Y drives Task X drives Predecessor 3 drives the Focus Point, all three upstream tasks carry DS = 0 to the Focus Point and all three are reported in the driving chain. The forensic engine must not stop at one tier; it walks recursively until every driving predecessor has been exhausted or a terminal anchor is reached.

Threshold-band secondary/tertiary path classification and cross-version erosion detection are forensic extensions of SSI driving path trace; detailed algorithm deferred to Session 18 cross-skill reconciliation (inferred — not sourced).

## 5. Path classification output fields

The engine emits the following fields per task in the driving-path analysis output. Every field is anchored to Lessons Learned §11 #2 or §11 #3, or removed.

- **UniqueID** — identity key (Lessons Learned §5, §11 #2).
- **Is on critical path (boolean)** — from §11 #1's critical-path list (Lessons Learned §11 #1).
- **Is on driving path to nominated Focus Point (boolean)** — from the §11 #2 driving chain (Lessons Learned §11 #2).
- **Relationship slack to driven successor (working days)** — per-link value from §11 #2 (Lessons Learned §11 #2).
- **Driving predecessor UniqueID(s)** — the §11 #2 "ordered driving chain" materialized as parent pointers (Lessons Learned §11 #2).
- **TotalFloat trend classification** across matched schedule versions: CRITICAL, SEVERE EROSION, ERODING, STABLE, IMPROVING (Lessons Learned §11 #3). These five labels come from comparative float analysis and carry forward into driving-path output because a task that is ERODING toward zero float is a candidate future driver.
- **Newly critical / recovered / added / deleted** flags across matched versions (Lessons Learned §11 #3).

Any output field beyond the above is either cut or labeled "(inferred — not sourced)" with a single-sentence scope defer to Session 18 cross-skill reconciliation.

## 6. UniqueID cross-version matching

When driving-path or critical-path output is compared across two or more schedule versions with different status dates, tasks are matched **exclusively by UniqueID** — the ID (row number) field changes on insertion, deletion, or reorder and is useless for cross-version work (Lessons Learned §5). See the `mpp-parsing-com-automation` skill for the full parser-level rule, null handling, and COM extraction path.

## 7. CPM calculation discipline

The forensic engine's CPM implementation produces a driving-path output only if its forward and backward passes match the reference implementation (MS Project) exactly. The following invariants apply:

- **Forward pass / backward pass dates must match MS Project's calculated values field-for-field.** Per Lessons Learned §11 #1, the module must "validate against MS Project's own critical path flag." If Early/Late Start and Early/Late Finish do not match MSP exactly, the parser or CPM math is defective and must be corrected first — this is Lessons Learned §13 commandment #2: *"Thou shalt prove the parser works BEFORE writing any analysis code."*
- **All four relationship types must be tested.** Per Lessons Learned §11 #1, the engine must "handle all four relationship types (FS, SS, FF, SF) and lags/leads." Each type alters forward and backward pass arithmetic differently; silently dropping to an FS-only implementation produces silently-wrong output on networks that rely on SS / FF / SF.
- **All six constraint types must be tested.** Per Lessons Learned §11 #1, the engine must "respect constraints (SNET, SNLT, FNET, FNLT, MSO, MFO)." MSO / MFO pin the date regardless of logic; SNET / FNET bound the earliest; SNLT / FNLT bound the latest. Each must be verified on a fixture.
- **Leads and lags must produce correct date offsets.** Per Lessons Learned §11 #1, "lags/leads" are part of the relationship-handling requirement. Negative lag (lead) is a frequent parser fault — a lost sign creates driving-chain slack that does not exist in MSP.
- **Multi-calendar schedules respect the task-assigned calendar for duration arithmetic.** When a project uses multiple working calendars, every duration calculation uses the calendar assigned to the specific task, not the project default. (Inferred — not sourced in the current Lessons Learned revision; derived from the §11 #1 requirement that CPM results match MSP and the §6 requirement that calendar assignments be extracted.)
- **UniqueID is the sole cross-version key** (Lessons Learned §5; commandment #3: *"Thou shalt match tasks by UniqueID and nothing else."*). Version-to-version driving-path deltas must not use the `ID` field.
- **Null handling on every field accessor** (Lessons Learned §13 commandment #5: *"Thou shalt handle None/null in every field accessor from day one."*). MS Project fields can be null on any row; a CPM implementation that crashes on a null Lag or ConstraintDate fails on real schedules regardless of logic correctness.
- **Dialogs suppressed during parse** (Lessons Learned §13 commandment #6: *"Thou shalt suppress MS Project dialogs."*). A blocking dialog produces a partial task set and a silent driving-path under-report.

## 8. But-for analysis — Period A slack rule

*(Inferred — not sourced in SSI or in the current Lessons Learned revision. Rule encoded in this skill for forensic consistency; to be cross-checked against authoritative but-for literature in Session 18 cross-skill reconciliation.)*

When a but-for analysis compares a Period A baseline schedule to a Period B current schedule to isolate the impact of a specific change (added delay, removed logic link, inserted constraint, etc.), the engine uses **Period A slack values exclusively** for the driving-impact test. Period B slack values already reflect the change under investigation and are therefore circular — a task that became a driver *because* of the Period B change will report zero slack in Period B, which proves nothing about what the schedule would have done absent the change.

- **Finish-date delta is the authoritative slip metric.** For each matched UniqueID, the Period B finish date minus the Period A finish date (later − prior, in calendar days per the repo-level convention that date slips are reported in calendar days) is the primary but-for output. Positive = the task's finish slipped later; negative = the task's finish pulled earlier. Sign convention aligns with CLAUDE.md decision #3 and the archived comparator implementation at `archive/prior-build-2026-04-16/app/engine/comparator.py:113`.
- **Logic-removal driving impact checked against Period A start dates.** When the but-for analysis removes a logic link to test its contribution, the engine re-runs CPM with the link removed and compares the resulting start dates against Period A start dates, not against the Period B start dates that already include the link.
- **DS-to-Focus-Point recomputed both with and without the change.** The delta in Driving Slack (SSI slide 5–6 definition) to the nominated Focus Point is the contribution attributable to the change.

## 9. Status-date filtering rule

*(Inferred — not sourced in SSI or in the current Lessons Learned revision. Rule encoded in this skill for forensic consistency; to be cross-checked in Session 18 cross-skill reconciliation.)*

When comparing two schedule versions for manipulation detection, task changes whose Period A finish date is less than or equal to Period B's status date represent **legitimate recorded actuals** — the task completed before the Period B cutoff, and the Period B change to the task's stored field values is the normal result of status update, not a forensic signal. Such changes are **excluded** from manipulation findings raised by this skill's driving-path delta output.

The filter is applied before path-classification deltas are emitted: tasks where Period A finish ≤ Period B status date are dropped from the "new driver" / "erosion" / "recovered" flag sets. The full list of manipulation patterns that are checked *after* status-date filtering lives in the `forensic-manipulation-patterns` skill; this skill only owns the filter predicate and the driving-path-specific delta output.

## 10. What this skill does NOT cover

- **Resource leveling** — the CPM-path reasoning here assumes an unlevelled network. Resource-constrained scheduling sits outside this skill.
- **Probabilistic / Schedule Risk Analysis (SRA)** — Monte Carlo, BetaPERT, P50/P80/P95 finish-date distributions, criticality index, sensitivity index. Owned by a future SRA skill per Lessons Learned §11 #7.
- **DCMA 14-point quality metrics** — logic, leads, lags, relationship types %, hard constraints %, high float %, negative float %, high duration %, invalid dates %, resources %, missed tasks %, critical path test, critical path length index (CPLI), baseline execution index (BEI). See the `dcma-14-point-assessment` skill.
- **Manipulation detection patterns** — suspect status overrides, constraint abuse, duration compression, logic-tie-in substitution, progress-override signatures. See the `forensic-manipulation-patterns` skill.
- **MPP parsing** — COM automation, MPXJ fallback, JPype lifecycle, duration-in-minutes, UniqueID extraction, calendar extraction, status-date extraction. See the `mpp-parsing-com-automation` skill.

## 11. References

Every rule in this skill traces to one of the three sources below. Any rule not traceable to SSI by slide number or to Lessons Learned by section / sub-item number is labeled "(inferred — not sourced)" in-line above.

| Rule in this skill | Source | Citation |
|---|---|---|
| Driving Slack definition | SSI paper | Slide 5 |
| DS only calculated to a specific focus point | SSI paper | Slide 6 |
| DS ≠ TS ; DS ≠ FS | SSI paper | Slide 7 |
| Total Slack definition | SSI paper | Slide 9 |
| Free Slack definition | SSI paper | Slide 10 |
| TS / FS unreliable for critical or driving path | SSI paper | Slide 11 |
| Driving Slack is MOST ACCURATE for critical / driving paths | SSI paper | Slide 12 |
| Worked example: Focus Point 2023-12-15 setup | SSI paper | Slides 14–15 |
| Worked example: Pred 3 DS=0, TS=1, DL 2023-12-16 | SSI paper | Slide 16 |
| Worked example: Pred 2 DS=2 | SSI paper | Slide 17 |
| Worked example: Pred 2 FS=1 (illustrating DS ≠ FS) | SSI paper | Slide 18 |
| Worked example: Pred 1 DS=4 | SSI paper | Slide 19 |
| Worked example: Pred 1 FS=0 (illustrating DS ≠ FS) | SSI paper | Slide 20 |
| Multi-tier chain: Y → X → Pred 3 → Focus, DS=0 everywhere | SSI paper | Slide 22 |
| Learning objectives framing | SSI paper | Slide 3 |
| Forward pass / backward pass required | Lessons Learned | §11 #1 |
| All 4 relationship types (FS, SS, FF, SF) + lags/leads | Lessons Learned | §11 #1 |
| All 6 constraint types (SNET, SNLT, FNET, FNLT, MSO, MFO) | Lessons Learned | §11 #1 |
| Validate against MS Project's Critical flag | Lessons Learned | §11 #1 |
| Output: ordered critical-path list with float values | Lessons Learned | §11 #1 |
| Driving path trace from nominated UniqueID | Lessons Learned | §11 #2 |
| Trace backward through driving predecessors | Lessons Learned | §11 #2 |
| Relationship slack per predecessor link | Lessons Learned | §11 #2 |
| Driving = relationship slack = 0 | Lessons Learned | §11 #2 |
| Output: ordered driving chain + relationship slack table | Lessons Learned | §11 #2 |
| Trend labels CRITICAL / SEVERE EROSION / ERODING / STABLE / IMPROVING | Lessons Learned | §11 #3 |
| Newly critical / recovered / added / deleted flags | Lessons Learned | §11 #3 |
| UniqueID is the sole cross-version match key | Lessons Learned | §5 |
| Prove parser works before analysis | Lessons Learned | §13 commandment #2 |
| Match tasks by UniqueID and nothing else | Lessons Learned | §13 commandment #3 |
| Handle None/null on every field accessor | Lessons Learned | §13 commandment #5 |
| Suppress MS Project dialogs | Lessons Learned | §13 commandment #6 |
| Threshold-band secondary/tertiary path classification | (inferred — not sourced) | Deferred to Session 18 |
| Cross-version erosion detection algorithm | (inferred — not sourced) | Deferred to Session 18 |
| Multi-calendar duration arithmetic rule | (inferred — not sourced) | Derived from §11 #1 + §6 |
| But-for analysis Period A slack rule | (inferred — not sourced) | §8 of this skill, labeled in-line |
| Finish-date delta as authoritative slip metric | (inferred — not sourced) | §8 of this skill, labeled in-line |
| Logic-removal impact checked vs. Period A start dates | (inferred — not sourced) | §8 of this skill, labeled in-line |
| Status-date filtering rule (Period A finish ≤ Period B status date) | (inferred — not sourced) | §9 of this skill, labeled in-line |

**Primary source**: Arnold, Kenny. *Understanding "Driving Slack" and its Uses*. Structured Solutions Incorporated. PDF at `docs/sources/SSINASAunderstandingdrivingslack.pdf`.

**Secondary source**: *Schedule Forensics Tool — Lessons Learned & Implementation Guidance*. Internal. Markdown at `docs/sources/Schedule_Forensics_Lessons_Learned.md`.
