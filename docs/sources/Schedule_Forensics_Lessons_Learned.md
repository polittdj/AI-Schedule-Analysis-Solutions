# Schedule Forensics Tool — Lessons Learned & Implementation Guidance

> **Document Purpose:** This is a living reference for Claude (any instance) to consult before attempting to build or revise the Schedule Forensics tool. It captures what worked, what failed, why it failed, and what to do differently. Read this ENTIRE document before writing a single line of code.
>
> **Document Owner:** David Politt
> **Last Updated:** April 2026
> **Version History:** v1 (initial), v2 (TBD after next build attempt)
> **Associated Repo:** https://github.com/polittdj/Claude-Code-Schedule-Analysis-v3

---

## TABLE OF CONTENTS

1. [Executive Context — What We're Building and Why](#1-executive-context)
2. [The .mpp File Problem — The #1 Recurring Failure](#2-the-mpp-file-problem)
3. [What Has Been Tried and What Happened](#3-what-has-been-tried)
4. [Recommended Architecture for Next Attempt](#4-recommended-architecture)
5. [The Unique ID Rule — Non-Negotiable](#5-the-unique-id-rule)
6. [Field Extraction Requirements](#6-field-extraction-requirements)
7. [Known Defects and Pitfalls from Industry Tools](#7-known-defects-and-pitfalls)
8. [Local AI / CoPilot Integration Options](#8-local-ai-copilot-integration)
9. [Security and Privacy — Absolute Requirements](#9-security-and-privacy)
10. [Development Process Lessons](#10-development-process-lessons)
11. [Analysis Module Specifications](#11-analysis-module-specifications)
12. [Testing Strategy](#12-testing-strategy)
13. [Recommendations for Next Build Attempt](#13-recommendations)
14. [Appendix A: Deltek Acumen Known Defects Relevant to MPP Import](#appendix-a)
15. [Appendix B: Complete Field List Required from .mpp Files](#appendix-b)
16. [Appendix C: Decision Tree for .mpp Reading Strategy](#appendix-c)

---

## 1. Executive Context — What We're Building and Why {#1-executive-context}

### The Tool
A local-only web application ("Schedule Forensics") that reads native Microsoft Project (.mpp) files, performs multi-version comparative schedule analysis, and produces professional reports. It must run entirely on a Windows desktop with zero data leaving the machine.

### The User
A senior project controls professional / forensic schedule analyst who works with government contracts (NASA, DoD) where schedule data is CUI (Controlled Unclassified Information). The user has MS Project installed on the machine. The user has access to Microsoft CoPilot. The user has Deltek Acumen 8.8 available.

### Why This Is Hard
The .mpp file format is proprietary, binary, undocumented, and changes between MS Project versions. Every attempt to build this tool has hit the same wall: **reliably reading .mpp files with full field fidelity, including metadata like the Status Date, without requiring the user to manually export data.** Manual export is unacceptable because:

- It is extremely time-consuming (the user manages multiple large schedules).
- MS Project limits the number of fields you can export at once.
- You lose access to underlying metadata, calculated fields, and project-level properties (especially the Status Date).
- Custom fields, calendars, and relationship details are often truncated or lost.
- It defeats the purpose of automation.

---

## 2. The .mpp File Problem — The #1 Recurring Failure {#2-the-mpp-file-problem}

### What Has Failed

#### Attempt: MPXJ via Python `mpxj` package (JPype bridge)
- **What it is:** MPXJ is a Java library that reads .mpp files natively. The Python `mpxj` package wraps it via JPype (Java-Python bridge).
- **The Problem:** JPype requires a Java Virtual Machine (JVM) running inside the Python process. This introduces:
  - **JVM startup failures** — Java version mismatches, JAVA_HOME not set, 32-bit vs 64-bit conflicts.
  - **Memory issues** — The JVM has its own heap, and large .mpp files can cause OutOfMemoryError.
  - **Threading conflicts** — JPype's JVM is global per-process. If any part of the app tries to start a second JVM, it crashes.
  - **Installation complexity** — The user must have Java 11+ installed, and the JAVA_HOME environment variable correctly configured. This is a common point of failure on managed Windows desktops where IT controls software installation.
  - **Field access inconsistencies** — Some MPXJ field accessors return null when the field exists but is stored differently than expected in different .mpp versions (Project 2010 vs 2016 vs 2019 vs 2021).
  - **Status Date extraction** — Sometimes returns null even when the file clearly has a Status Date set in MS Project.
  - **Calendar data** — Working time exceptions and calendar assignments are sometimes incomplete.

#### Attempt: Direct XML export fallback
- **What it is:** Ask the user to File → Save As → XML from MS Project, then parse the XML.
- **The Problem:** This is exactly what the user does NOT want. It's manual, slow, and loses data. The whole point of the tool is to avoid this step.

#### Attempt: OLE2 binary parsing with `olefile`
- **What it is:** Reading the .mpp file as an OLE2 compound document and manually parsing the binary structures.
- **The Problem:** The .mpp internal structure is undocumented, version-specific, and changes with every MS Project release. This is a reverse-engineering effort that would take months and break with every update. Not viable.

### What Actually Works (Ranked by Reliability)

#### OPTION A: MS Project COM Automation (BEST — but requires MS Project installed)
**Reliability: 9/10 | Field Fidelity: 10/10 | User Effort: 0/10**

Since the user HAS MS Project installed on the machine, the most reliable way to read .mpp files is to use MS Project itself via COM automation. Python can control MS Project through `win32com`.

```python
import win32com.client
import pythoncom

def read_mpp_via_com(filepath):
    """
    Open .mpp file using MS Project COM automation.
    This uses the actual MS Project engine — 100% field fidelity.
    MS Project must be installed on the machine.
    """
    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("MSProject.Application")
        app.Visible = False  # Run headless
        app.FileOpen(filepath, ReadOnly=True)
        project = app.ActiveProject
        
        # Project-level fields
        status_date = project.StatusDate
        project_start = project.Start
        project_finish = project.Finish
        calendar_name = project.Calendar.Name
        
        tasks = []
        for task in project.Tasks:
            if task is None:  # Blank rows in MS Project
                continue
            tasks.append({
                'unique_id': task.UniqueID,
                'id': task.ID,
                'name': task.Name,
                'duration': task.Duration,
                'start': task.Start,
                'finish': task.Finish,
                'baseline_start': task.BaselineStart,
                'baseline_finish': task.BaselineFinish,
                'actual_start': task.ActualStart,
                'actual_finish': task.ActualFinish,
                'early_start': task.EarlyStart,
                'early_finish': task.EarlyFinish,
                'late_start': task.LateStart,
                'late_finish': task.LateFinish,
                'total_slack': task.TotalSlack,
                'free_slack': task.FreeSlack,
                'percent_complete': task.PercentComplete,
                'critical': task.Critical,
                'milestone': task.Milestone,
                'summary': task.Summary,
                'remaining_duration': task.RemainingDuration,
                'actual_duration': task.ActualDuration,
                'constraint_type': task.ConstraintType,
                'constraint_date': task.ConstraintDate,
                # ... ALL fields are available
            })
        
        # Relationships
        relationships = []
        for task in project.Tasks:
            if task is None:
                continue
            for dep in task.TaskDependencies:
                relationships.append({
                    'predecessor_uid': dep.From.UniqueID,
                    'successor_uid': task.UniqueID,
                    'type': dep.Type,  # 0=FF, 1=FS, 2=SF, 3=SS
                    'lag': dep.Lag,
                })
        
        app.FileClose(Save=0)  # pjDoNotSave
        return {
            'status_date': status_date,
            'project_start': project_start,
            'project_finish': project_finish,
            'calendar': calendar_name,
            'tasks': tasks,
            'relationships': relationships,
        }
    finally:
        try:
            app.Quit()
        except:
            pass
        pythoncom.CoUninitialize()
```

**Why this is the winner:**
- Uses the actual MS Project calculation engine — no field interpretation errors.
- Every single field MS Project exposes is accessible (300+ fields per task).
- Status Date, calendars, custom fields, earned value fields — ALL available.
- No Java dependency. No JVM. No JPype. Just Python + pywin32.
- The file never leaves the machine.
- MS Project runs headless (invisible) — the user doesn't see it open.

**Caveats:**
- MS Project must be installed on the machine (it is, in this case).
- Opening/closing .mpp files via COM is slower than MPXJ (5-15 seconds per file for large schedules).
- COM automation on Windows requires `pythoncom.CoInitialize()` and is single-threaded per COM apartment.
- If MS Project crashes or hangs, the app hangs. Need timeout/watchdog logic.
- MS Project may show dialog boxes (e.g., "This file was created in a newer version") that block automation. Suppress with `app.DisplayAlerts = False`.

#### OPTION B: MPXJ via subprocess (not JPype)
**Reliability: 6/10 | Field Fidelity: 7/10 | User Effort: 1/10 (Java install)**

Instead of using the fragile JPype in-process bridge, run MPXJ as a separate Java process and communicate via JSON.

```python
import subprocess
import json

def read_mpp_via_mpxj_subprocess(filepath):
    """
    Run a small Java program that uses MPXJ to read the .mpp
    and outputs JSON to stdout. No JPype, no JVM-in-Python.
    """
    result = subprocess.run(
        ['java', '-jar', 'mpp_reader.jar', filepath],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"MPXJ failed: {result.stderr}")
    return json.loads(result.stdout)
```

This requires writing a small Java program (`mpp_reader.jar`) that does the MPXJ reading and outputs JSON. This isolates the JVM from the Python process entirely.

**Pros:** No JPype crashes. JVM is isolated. If it hangs, the subprocess can be killed.
**Cons:** Still requires Java installed. MPXJ still has field fidelity gaps vs. actual MS Project.

#### OPTION C: Hybrid — COM primary, MPXJ fallback
**Reliability: 9/10 | The recommended approach.**

```
IF MS Project is installed on the machine:
    Use COM automation (Option A)
ELSE IF Java is installed:
    Use MPXJ subprocess (Option B)
ELSE:
    Tell the user: "Install MS Project or Java 11+ to read .mpp files natively."
    Offer XML import as last resort.
```

### CRITICAL LESSON: Do NOT Use JPype

The Python `mpxj` package (via JPype) has caused more build failures than any other component. **Do not use it.** If MPXJ is needed, use the subprocess approach (Option B). Better yet, use COM automation (Option A) since MS Project is confirmed installed on the target machine.

---

## 3. What Has Been Tried and What Happened {#3-what-has-been-tried}

### Build Attempt Summary

| Version | Primary Issue | Outcome |
|---------|--------------|---------|
| v1 | Scope too large, tried to build everything at once. Parser, CPM, UI, reports all in parallel. Nothing worked end-to-end. | Abandoned. |
| v2 | Focused on MPXJ + JPype for .mpp parsing. JPype JVM initialization failures on Windows. Status Date coming back null. Field mapping inconsistencies. | Abandoned. Hit .mpp reading wall. |
| v3 (current prompt) | Comprehensive master prompt created. 13-PR milestone plan. Repo wiped and restarted. MPXJ + JPype still specified as primary parser. XML fallback documented. | Prompt complete, build not yet successful end-to-end. |

### Key Recurring Failure Patterns

1. **Trying to solve .mpp parsing and analysis simultaneously.** The .mpp parser must be a PROVEN, TESTED, WORKING module before ANY analysis code is written. Every attempt that tried to build analysis features before confirming the parser worked ended in wasted effort when the parser failed and the analysis code had to be thrown away because its assumptions about available data were wrong.

2. **Underestimating COM automation reliability vs. MPXJ.** COM automation through `win32com` was never tried in prior attempts because the prompt specified "no MS Project required." But MS Project IS installed on the target machine. This changes everything. Use it.

3. **Scope creep in a single build session.** Claude Code sessions have context limits. Trying to build 13 PRs worth of code in a single session leads to degraded output quality as context fills up. Build in focused phases.

4. **Not validating field extraction against known values.** A parser that "runs without errors" is not a parser that "extracts correct values." Every field extracted must be validated against what MS Project actually shows for the same file. Without a validation step, bad data propagates silently into every analysis module.

5. **Ignoring Windows-specific issues.** The target environment is Windows, not Linux. Path separators, PowerShell vs. bash, COM automation, Windows Task Scheduler, file locking (MS Project locks .mpp files when open) — all of these have caused issues.

---

## 4. Recommended Architecture for Next Attempt {#4-recommended-architecture}

### Phase 0: Environment Validation (DO THIS FIRST)
Before writing ANY code:
```powershell
python --version          # Must be 3.11+ (3.13 confirmed)
pip --version
java -version             # Needed only for MPXJ fallback
node --version            # Needed only for React frontend
git --version
# Check if MS Project is installed:
python -c "import win32com.client; app = win32com.client.Dispatch('MSProject.Application'); print('MS Project version:', app.Version); app.Quit()"
```

### Phase 1: .mpp Parser — COM Automation (PROVE THIS WORKS FIRST)
Build `mpp_parser_com.py` and NOTHING ELSE until it can:
- Open a real .mpp file via COM
- Extract every field listed in Appendix B
- Correctly read the Status Date (verify against MS Project UI)
- Extract all predecessor/successor relationships with types and lags
- Extract calendar working time data
- Handle .mpp files from Project 2016, 2019, and 2021
- Handle edge cases: blank rows, summary tasks, milestones, LOE tasks
- Close MS Project cleanly without leaving zombie processes

**Validation:** Open the same .mpp in MS Project, manually check 10+ tasks across all fields, confirm exact match with parser output.

### Phase 2: Data Model + Multi-Version Matching
Build `schemas.py` with Pydantic models. Build `version_matcher.py` that:
- Accepts 2+ parsed schedules
- Matches tasks across versions BY UNIQUE ID
- Identifies added/deleted tasks
- Orders versions by Status Date

### Phase 3: Analysis Modules (one at a time, tested independently)
1. CPM engine (`cpm.py`) — verify against MS Project's own forward/backward pass
2. Driving path trace (`driving_path.py`)
3. Diff engine (`diff_engine.py`)
4. Float comparison (`float_analysis.py`)
5. SPI / CEI / BEI calculators (`performance_indices.py`)
6. SRA Monte Carlo (`sra.py`)

### Phase 4: Report Generation
- Excel reports via `openpyxl`
- Word reports via `python-docx`
- Executive summary narrative generator

### Phase 5: Web UI
- FastAPI backend
- React frontend (or Flask + Jinja2 if Node.js unavailable)
- Single-window design, all panels accessible from sidebar

### Phase 6: Integration Testing + Polish

---

## 5. The Unique ID Rule — Non-Negotiable {#5-the-unique-id-rule}

**When comparing two or more versions of the same project schedule that have different status dates, the Unique ID is ALWAYS the sole identifier for matching tasks across versions.**

This is not optional. This is not a suggestion. This is a hard rule.

- The `ID` field (row number) changes when tasks are inserted, deleted, or reordered. It is USELESS for cross-version matching.
- The `UniqueID` field is assigned by MS Project when a task is created and NEVER changes for the life of that task within that project file.
- If a task's UniqueID exists in Version A but not Version B, the task was deleted between versions.
- If a UniqueID exists in Version B but not Version A, the task was added.
- Task Name is NOT a reliable identifier — names can be changed, and duplicate names are common.

Every module that compares versions must use UniqueID as the primary key. No exceptions.

---

## 6. Field Extraction Requirements {#6-field-extraction-requirements}

### Minimum Required Fields Per Task
These fields MUST be extractable for the tool to function. If any are missing, the analysis is compromised.

**Identity:**
- UniqueID, ID, Name, WBS, OutlineLevel

**Dates:**
- Start, Finish, BaselineStart, BaselineFinish, ActualStart, ActualFinish
- EarlyStart, EarlyFinish, LateStart, LateFinish

**Durations:**
- Duration, RemainingDuration, ActualDuration, BaselineDuration

**Float:**
- TotalSlack (TotalFloat), FreeSlack (FreeFloat)

**Progress:**
- PercentComplete, PhysicalPercentComplete

**Flags:**
- Critical, Milestone, Summary, Active/Inactive

**Constraints:**
- ConstraintType, ConstraintDate, Deadline

**Earned Value (if available):**
- BCWP, BCWS, BAC, EAC, CV, SV

**Relationships (per link):**
- PredecessorUniqueID, SuccessorUniqueID, Type (FS/SS/FF/SF), Lag

**Project-Level:**
- StatusDate, ProjectStart, ProjectFinish, DefaultCalendarName, LastSavedDate

### Fields That Are Commonly Lost in Export
These fields are available via COM automation or MPXJ but are frequently missing or corrupted in XML/CSV export:
- EarlyStart, EarlyFinish, LateStart, LateFinish (calculated fields — not stored in XML)
- TotalSlack, FreeSlack (calculated — requires CPM recalculation if not exported)
- Calendar assignments per task
- Constraint details
- Custom field values
- Resource assignments with units and costs
- Status Date (project-level property, not a task field)

**This is exactly why manual export is unacceptable.** COM automation gets ALL of these directly from MS Project's calculation engine.

---

## 7. Known Defects and Pitfalls from Industry Tools {#7-known-defects-and-pitfalls}

Even professional tools like Deltek Acumen 8.8 have documented issues reading .mpp files. These serve as warnings about what can go wrong:

### Acumen MPP Import Defects (from Release Notes)
- **Defect 1552644:** Native import showed incorrect Start Variance and Finish Variance. Workaround: use Active import (which requires MS Project). This confirms that reading .mpp without MS Project introduces variance calculation errors.
- **Defect 1419295:** Importing certain .mpp files caused "Index was outside the bounds of the array." No workaround. Some .mpp files simply can't be read by non-MS-Project parsers.
- **Defect 1633307:** Active import (via MS Project) failed to populate Suspend and Resume dates. Even COM-based import has edge cases.
- **Defect 1633312:** Active import via MS Project failed to populate Percent Complete on Resource Assignments.
- **Defect 1501271:** Native import did not set Activity Type for Milestones and Summary tasks, causing filter failures.
- **Defect 1728697:** Percent Complete for Resource Assignments was incorrect when imported from MPP.

### Acumen XML Export Defects
- **Defect 1602082:** TAB characters in resource or calendar names caused MSP XML export to produce unreadable files.
- **Defect 1119399:** Duration fields showed "Infinity" in XML export.
- **Defect 1365699:** Activities spanning 50+ years caused crash on XML export.

### Lessons from These Defects
1. Even Acumen — a commercial, enterprise-grade tool — has persistent issues with .mpp native import. Our custom tool will have MORE issues unless we use COM automation.
2. The "Active Import" (which uses MS Project COM/API) is consistently MORE reliable than "Native Import" (which reads the binary file directly). This validates our recommendation to use COM automation.
3. XML export from MS Project is lossy and fragile. Never depend on it as the primary path.
4. Edge cases with milestones, summary tasks, resource assignments, and constraint types are where parsers break most often.

---

## 8. Local AI / CoPilot Integration Options {#8-local-ai-copilot-integration}

### Option A: Local LLM for Analysis Interpretation (Recommended for Future Phase)

Embed a small local language model to generate narrative interpretations of analysis results. This keeps everything on-machine.

**How it would work:**
1. The analysis engine produces structured JSON results (float trends, SPI values, critical path, etc.).
2. A local LLM receives the JSON as a prompt and generates a plain-English executive summary.
3. The LLM runs on the local GPU or CPU — no API calls.

**Recommended models (as of early 2026):**
- **Llama 3.x (8B or 13B)** via `llama.cpp` or `ollama` — runs on CPU, good for structured interpretation.
- **Mistral 7B** — similar capability, slightly different strengths.
- **Phi-3** (Microsoft) — smaller, faster, designed for on-device use.

**Implementation:**
```python
# Using Ollama (easiest local LLM setup on Windows)
import requests

def generate_narrative(analysis_json):
    """Send structured analysis to local Ollama instance for interpretation."""
    prompt = f"""You are a senior project controls analyst. Based on the following 
    schedule analysis data, write a professional executive summary in plain English.
    Focus on: what changed, why it matters, and what should be done about it.
    
    Analysis Data:
    {json.dumps(analysis_json, indent=2)}
    
    Write the summary in 3-5 paragraphs. Use specific task names, dates, and numbers."""
    
    response = requests.post('http://localhost:11434/api/generate', json={
        'model': 'llama3:8b',
        'prompt': prompt,
        'stream': False,
    })
    return response.json()['response']
```

**Setup for the user:**
1. Install Ollama: https://ollama.ai (one-click Windows installer)
2. Run: `ollama pull llama3:8b` (downloads ~4.7GB model)
3. Ollama runs as a local service on port 11434. No internet required after download.

**This is 100% local. The model runs on your machine. No data leaves.**

### Option B: Microsoft CoPilot (Partial — for non-CUI summary review only)

The user has access to CoPilot. CoPilot CANNOT read native .mpp files. However, CoPilot CAN:
- Review and refine narrative summaries (after the local tool generates them).
- Help interpret trends if given sanitized/anonymized data.
- Assist with building Excel/Word report templates.

**CRITICAL LIMITATION:** CUI schedule data MUST NOT be loaded into CoPilot unless the CoPilot instance is within the organization's approved CUI boundary (e.g., GCC High tenant). Verify with the user's security officer before using CoPilot with any schedule data.

**Recommended CoPilot use:**
- Paste the executive summary TEXT (no raw schedule data) into CoPilot for grammar/clarity review.
- Use CoPilot to help design report templates.
- Use CoPilot to explain analysis concepts to stakeholders.
- NEVER paste UniqueIDs, task names, dates, or any identifiable project data into CoPilot unless confirmed CUI-approved.

### Option C: Train a Custom Model (Future / Advanced)

Not recommended for the initial build. But for the future:
- Fine-tune a small model on schedule analysis reports to improve narrative quality.
- Use retrieval-augmented generation (RAG) with NASA/DCMA standards documents as the knowledge base.
- The fine-tuning and RAG data would stay local.

---

## 9. Security and Privacy — Absolute Requirements {#9-security-and-privacy}

These are non-negotiable. If any of these are violated, the tool cannot be used.

1. **No schedule data may EVER leave the local machine.** Zero external API calls containing schedule content. Zero cloud storage. Zero telemetry that includes task names, dates, or project metadata.

2. **All processing is local.** The web app runs on localhost only (127.0.0.1). No external network access required after initial dependency installation.

3. **Session wipe on exit.** When the user closes the tool or clicks "End Session," ALL uploaded files, parsed data, analysis results, and temporary files are destroyed. No residual data on disk.

4. **`.gitignore` must block all schedule data:** `*.mpp`, `*.mpp.bak`, `*.xml` (schedule exports), `*.csv` (schedule data), `session_data/`, `uploads/`, `exports/`, `*.json` (schedule snapshots).

5. **If a local LLM is used:** The model must run locally (Ollama, llama.cpp, etc.). No cloud LLM APIs (OpenAI, Anthropic API, etc.) may be called with schedule data.

6. **If CoPilot is used:** Only sanitized narrative text may be pasted. Never raw schedule data unless CoPilot is in a CUI-approved tenant.

7. **The tool must work fully offline** after initial setup. Test by disconnecting from the network and running the full analysis pipeline.

---

## 10. Development Process Lessons {#10-development-process-lessons}

### What Went Wrong in Previous Attempts

1. **Building analysis before proving the parser.** Every time. The parser MUST be proven working with real .mpp files before ANY analysis code is written. If the parser can't extract TotalSlack, there's no point writing a float analysis module.

2. **Trying to build the entire tool in one Claude Code session.** Context window fills up. Quality degrades. Code gets repetitive or inconsistent. Break the build into focused sessions: one for the parser, one for CPM, one for the UI, etc.

3. **Not creating a validation harness.** There was no automated way to compare "what the parser extracted" with "what MS Project actually shows." Build a validation script that opens the same .mpp in MS Project (via COM) and the parser, then diffs every field for every task. This is your ground truth.

4. **PowerShell vs. Bash confusion.** The target is Windows. Claude Code sometimes generates bash commands. Always use PowerShell or cmd.exe. Test all scripts in PowerShell.

5. **Not handling MS Project dialog boxes.** When MS Project opens a file via COM, it may show dialog boxes (e.g., "Update links?", "Convert to current format?"). These block automation. Use `app.DisplayAlerts = False` before opening any file.

6. **Not handling file locking.** If the user has the .mpp file open in MS Project, COM automation to open the same file will fail or get a read-only copy. Detect this and warn the user.

### What Should Be Done Differently

1. **Phase-gated development.** Do not proceed to Phase N+1 until Phase N has passing tests verified against real data. No exceptions.

2. **One module per Claude Code session.** Each session should have a single, focused objective: "Build and test the CPM engine." Not "Build the CPM engine, the driving path module, the diff engine, and start on reports."

3. **Commit after each working module.** Don't accumulate uncommitted work. If the session crashes, uncommitted work is lost.

4. **Real .mpp file testing (locally).** Synthetic test data is necessary for CI, but final validation MUST use real .mpp files. The user will provide them. They stay local. They must never be committed to the repo.

5. **Error handling first, not last.** Every function should handle the "what if this field is null?" case from the start, not as an afterthought when the first real file exposes a NoneType error.

---

## 11. Analysis Module Specifications {#11-analysis-module-specifications}

### The Required Analyses (in order of implementation priority)

#### 1. Critical Path Trace
- Forward pass + backward pass using the extracted schedule network.
- Must handle all four relationship types (FS, SS, FF, SF) and lags/leads.
- Must respect constraints (SNET, SNLT, FNET, FNLT, MSO, MFO).
- Validate against MS Project's own critical path flag.
- Output: ordered list of critical path tasks with float values.

#### 2. Driving Path Trace (for a specific UniqueID)
- Trace backward from target task through driving predecessors.
- Calculate relationship slack for every predecessor link.
- Identify which predecessors are driving (relationship slack = 0) vs. non-driving.
- Output: ordered driving chain + relationship slack table.

#### 3. Comparative Float Analysis (multi-version)
- Match tasks across versions by UniqueID.
- Track TotalFloat change per task across all versions.
- Compute float burn rate (linear regression on float vs. time).
- Classify trends: CRITICAL, SEVERE EROSION, ERODING, STABLE, IMPROVING.
- Identify newly critical tasks, recovered tasks, deleted tasks, added tasks.
- Output: per-task float trend table + summary statistics.

#### 4. SPI (Schedule Performance Index)
- Cumulative earned value metric: SPI = BCWP / BCWS.
- Also compute SPI(t) using Earned Schedule method.
- Duration-weighted or cost-weighted (user selectable).
- Output: project-level SPI, task-level SPI, trend across versions.

#### 5. CEI (Current Execution Index)
- Period-specific metric using two consecutive schedule versions.
- Measures actual progress in the period vs. planned progress in the period.
- CEI = (actual % increment × baseline duration) / (planned working days in period overlap with baseline).
- Output: project-level CEI, task-level CEI, trend across version pairs.

#### 6. BEI (Baseline Execution Index)
- Count-based metric: tasks completed on time / tasks that should be complete.
- Simple, intuitive, non-technical.
- Output: BEI value, list of overdue tasks, list of late-completed tasks.

#### 7. SRA (Schedule Risk Analysis)
- Monte Carlo simulation (5,000–10,000 iterations).
- BetaPERT distribution for task durations using 3-point estimates.
- If no 3-point estimates available, use heuristic defaults (O=0.75×D, M=D, P=1.5×D).
- Output: P50, P80, P95 dates, criticality index per task, sensitivity index, finish date histogram.

#### 8. Executive Summary One-Pager
- Plain English narrative summarizing all findings.
- Color-coded health status (GREEN/YELLOW/RED).
- Key findings: critical path, float trends, risk, performance indices.
- Actionable recommendations.
- Must be generated automatically — no manual writing.

---

## 12. Testing Strategy {#12-testing-strategy}

### Two-Tier Testing

**Tier 1: Synthetic Data (for CI, automated, no real .mpp files)**
- Generate synthetic schedule data as Python dictionaries / JSON fixtures.
- Cover: linear schedule, complex network, constraints, negative float, missing logic, multi-version sets.
- Tests verify algorithm correctness against hand-calculated expected values.
- These tests run in CI (GitHub Actions). No .mpp files in the repo.

**Tier 2: Real .mpp Validation (local only, manual trigger)**
- User provides 2-3 real .mpp files from a real project.
- Validation script opens each file via COM, extracts all fields, and compares against parser output.
- Checks: field-by-field match for 100% of tasks, relationship match, status date match, calendar match.
- These tests NEVER run in CI. They run locally via `python scripts/validate_against_msp.py`.
- Results are logged to a local file, not committed.

### Test Coverage Requirements

| Module | Test File | Key Assertions |
|--------|-----------|---------------|
| Parser (COM) | test_parser_com.py | Opens .mpp, extracts all required fields, status date correct, relationships correct, handles blank rows |
| Parser (MPXJ) | test_parser_mpxj.py | Same as above, using MPXJ subprocess |
| CPM | test_cpm.py | Forward pass dates match, backward pass dates match, float correct, all 4 link types, constraints respected |
| Driving Path | test_driving_path.py | Correct driving chain identified, relationship slack values correct, handles multiple paths |
| Diff Engine | test_diff.py | Tasks matched by UniqueID, added/deleted detected, field deltas correct |
| Float Analysis | test_float.py | Burn rate calculation correct, trend classification correct, zero-float prediction correct |
| SPI | test_spi.py | BCWP/BCWS calculation correct, SPI(t) correct, handles edge cases (no baseline, 100% complete) |
| CEI | test_cei.py | Period increment calculation correct, handles tasks not active in period |
| BEI | test_bei.py | Count logic correct, handles missing baselines, milestones excluded/included per config |
| SRA | test_sra.py | Distribution sampling correct, finish date distribution reasonable, criticality index sums to expected range |

---

## 13. Recommendations for Next Build Attempt {#13-recommendations}

### The 10 Commandments for the Next Build

1. **Thou shalt use COM automation as the primary .mpp reader.** MS Project is installed. Use it. Do NOT default to MPXJ + JPype.

2. **Thou shalt prove the parser works BEFORE writing any analysis code.** Open a real .mpp file, extract every required field, validate against MS Project UI. If ANY field is wrong, fix the parser before proceeding.

3. **Thou shalt match tasks by UniqueID and nothing else.** When comparing versions, UniqueID is the key. Period.

4. **Thou shalt build one module per session.** Parser in session 1. CPM in session 2. Driving path in session 3. Etc. Commit after each.

5. **Thou shalt handle None/null in every field accessor from day one.** MS Project fields can be null. Every line of code that reads a field must handle null gracefully.

6. **Thou shalt suppress MS Project dialogs.** `app.DisplayAlerts = False` before opening any file. `app.Visible = False` to run headless.

7. **Thou shalt test on Windows with PowerShell.** The target is Windows. No bash. No Linux assumptions.

8. **Thou shalt keep all schedule data local.** No cloud APIs, no external network calls with data, no telemetry.

9. **Thou shalt not try to build the UI before the backend works.** A beautiful frontend with a broken parser is useless.

10. **Thou shalt write the executive summary generator LAST.** It depends on every other module being correct. If float analysis is wrong, the executive summary will confidently report wrong numbers.

### Suggested Session Plan for Claude Code

| Session | Objective | Deliverable |
|---------|-----------|-------------|
| 1 | Environment validation + COM parser | `mpp_parser_com.py` with all fields extracting correctly |
| 2 | MPXJ subprocess fallback parser | `mpp_parser_mpxj.py` + `mpp_reader.jar` |
| 3 | Data model + version matcher | `schemas.py` + `version_matcher.py` |
| 4 | CPM engine | `cpm.py` + `test_cpm.py` passing |
| 5 | Driving path + relationship slack | `driving_path.py` + `test_driving_path.py` passing |
| 6 | Diff engine + float analysis | `diff_engine.py` + `float_analysis.py` + tests |
| 7 | SPI + CEI + BEI | `performance_indices.py` + tests |
| 8 | SRA Monte Carlo | `sra.py` + tests |
| 9 | Report generation (Excel + Word) | `report_excel.py` + `report_word.py` |
| 10 | Executive summary generator | `executive_summary.py` |
| 11 | FastAPI backend + API endpoints | `main.py` + `session_manager.py` |
| 12 | Frontend — upload + dashboard | React/Flask UI |
| 13 | Frontend — visualization panels | Charts, graphs, network diagrams |
| 14 | Integration testing + polish | End-to-end smoke test |
| 15 | Local LLM integration (optional) | Ollama-based narrative enhancement |

---

## Appendix A: Deltek Acumen Known Defects Relevant to MPP Import {#appendix-a}

These defects from Acumen 8.8 release notes document known issues with .mpp reading that may also affect MPXJ or any non-MS-Project parser:

| Defect | Description | Relevance |
|--------|-------------|-----------|
| 1552644 | Native import shows incorrect Start/Finish Variance | Variance calculations differ between native readers and MS Project |
| 1419295 | "Index out of bounds" on certain .mpp files | Some .mpp binary structures are unreadable by non-MS-Project tools |
| 1633307 | Suspend/Resume dates not populated via Active import | Even COM-based import has gaps in less-common fields |
| 1633312 | Percent Complete on Resource Assignments not populated via Active import | Resource assignment data is fragile |
| 1501271 | Milestone and Summary task Activity Types not set on native import | Task type classification fails on native readers |
| 1728697 | Incorrect Percent Complete for Resource Assignments from MPP | Resource-level progress data is unreliable from any import path |
| 1602082 | TAB characters in resource/calendar names break XML export | Data hygiene issues in source files propagate through exports |
| 1119399 | "Infinity" in duration fields on XML export | Edge case durations cause export corruption |
| 1365699 | Activities spanning 50+ years crash XML export | Date range edge cases |

---

## Appendix B: Complete Field List Required from .mpp Files {#appendix-b}

### Task Fields
```
UniqueID, ID, Name, WBS, OutlineLevel, OutlineNumber
Duration, RemainingDuration, ActualDuration, BaselineDuration
Start, Finish, BaselineStart, BaselineFinish
ActualStart, ActualFinish
EarlyStart, EarlyFinish, LateStart, LateFinish
TotalSlack, FreeSlack
PercentComplete, PhysicalPercentComplete
Critical, Milestone, Summary, Active
ConstraintType, ConstraintDate, Deadline
CalendarName (task-level override)
BCWP, BCWS, BAC, ACWP, EAC, CV, SV
Notes (task notes/comments)
Priority
Type (FixedDuration, FixedUnits, FixedWork)
```

### Relationship Fields (per link)
```
PredecessorUniqueID
SuccessorUniqueID
Type (FS=1, FF=0, SF=2, SS=3) — NOTE: MS Project COM uses different enum values than MPXJ
Lag (in minutes in COM; convert to working days using calendar)
```

### Project-Level Fields
```
StatusDate
Start (project start)
Finish (project finish)
Calendar (default calendar name)
BaselineDate (when baseline was saved)
LastSavedDate
Author
Title
```

### COM Automation Type Mappings
```python
# MS Project COM ConstraintType enum:
# 0 = As Soon As Possible (ASAP)
# 1 = As Late As Possible (ALAP)
# 2 = Must Start On (MSO)
# 3 = Must Finish On (MFO)
# 4 = Start No Earlier Than (SNET)
# 5 = Start No Later Than (SNLT)
# 6 = Finish No Earlier Than (FNET)
# 7 = Finish No Later Than (FNLT)

# MS Project COM TaskDependency.Type enum:
# 0 = Finish-to-Finish (FF)
# 1 = Finish-to-Start (FS)
# 2 = Start-to-Finish (SF)
# 3 = Start-to-Start (SS)

# Duration units in COM are MINUTES (480 = 1 working day at 8hr/day)
# TotalSlack in COM is in MINUTES
# Lag in COM is in MINUTES (with 1/10th minute precision)
```

---

## Appendix C: Decision Tree for .mpp Reading Strategy {#appendix-c}

```
START: User provides .mpp file(s)
  │
  ├─ Is MS Project installed on this machine?
  │    │
  │    ├─ YES ──▶ Use COM Automation (Option A)
  │    │           │
  │    │           ├─ COM succeeds ──▶ Continue to analysis
  │    │           │
  │    │           └─ COM fails (file locked, dialog box, crash)
  │    │                 │
  │    │                 ├─ Is file open in MS Project? ──▶ Warn user to close it
  │    │                 │
  │    │                 ├─ Dialog box blocking? ──▶ Verify DisplayAlerts=False, retry
  │    │                 │
  │    │                 └─ MS Project crashed? ──▶ Kill msproject.exe, retry once
  │    │                       │
  │    │                       └─ Still fails? ──▶ Fall through to MPXJ
  │    │
  │    └─ NO
  │         │
  │         ├─ Is Java 11+ installed?
  │         │    │
  │         │    ├─ YES ──▶ Use MPXJ Subprocess (Option B)
  │         │    │           │
  │         │    │           ├─ MPXJ succeeds ──▶ Continue (with field fidelity warnings)
  │         │    │           │
  │         │    │           └─ MPXJ fails ──▶ Log error, suggest installing MS Project
  │         │    │
  │         │    └─ NO ──▶ Neither MS Project nor Java available
  │         │                │
  │         │                ├─ Offer XML import as last resort
  │         │                │   (warn: manual, slow, lossy)
  │         │                │
  │         │                └─ Suggest installing Java 11+ (free, ~150MB)
  │         │
  │         └─ END: Cannot proceed without MS Project or Java
  │
  └─ END
```

---

## Appendix D: COM Automation Gotchas (Discovered Through Pain)

1. **Always `CoInitialize` before COM and `CoUninitialize` after.** Failing to do this causes "COM not initialized" errors.

2. **`app.Visible = False` and `app.DisplayAlerts = False`** must be set BEFORE opening any file. Not after.

3. **MS Project COM runs single-threaded.** Do not try to parallelize file reading. Read files sequentially.

4. **Null tasks in the Tasks collection.** MS Project's `Tasks` collection can contain `None` entries (blank rows). Always check `if task is None: continue`.

5. **Duration and slack are in MINUTES.** A 5-day task at 8 hours/day = 2400 minutes. TotalSlack of 0 means 0 minutes. Divide by 480 to get working days (assuming 8-hour days — check the calendar).

6. **The `StatusDate` property returns a date or "NA".** If the project has no Status Date set, it returns the string "NA" or a sentinel date (12/30/1899 or 1/1/1984). Check for both.

7. **File paths must be absolute.** COM automation doesn't resolve relative paths the same way as Python. Always use `os.path.abspath()`.

8. **Kill zombie processes.** If the script crashes mid-execution, `MSPROJECT.EXE` may remain running in the background. Add cleanup code in a `finally` block and consider a startup check that kills orphaned processes.

9. **Read-only mode.** Always open files with `ReadOnly=True` to avoid locking conflicts and accidental modifications.

10. **Date format handling.** COM returns dates as `datetime` objects via `win32com`, but the format depends on the Windows locale settings. Always normalize to ISO format immediately.

---

*This document is a living reference. Update it after each build attempt with new lessons learned.*
*When in doubt, read this document again. The answers are here.*
