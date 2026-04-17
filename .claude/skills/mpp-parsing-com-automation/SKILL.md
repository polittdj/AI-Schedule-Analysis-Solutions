---
name: mpp-parsing-com-automation
description: Parse Microsoft Project .mpp files via win32com COM automation as the primary reader. Covers the ten Appendix D gotchas, MPXJ subprocess fallback, UniqueID cross-version matching, and MS-Project-UI validation. Keywords: mpp, MS Project, win32com, COM automation, parser, parse schedule, read .mpp, extract tasks, MPXJ, JPype, Java, task iteration, Unique ID, Task ID, predecessor traversal, status date, duration minutes, zombie process, CoInitialize, DisplayAlerts.
license: Proprietary — polittdj / AI-Schedule-Analysis-Solutions
---

# MPP Parsing and COM Automation

Authoritative reference for reading native Microsoft Project `.mpp` files. All rules are sourced to `docs/sources/Schedule_Forensics_Lessons_Learned.md` ("Lessons Learned"); rules not present there are marked `(inferred — not sourced)`.

## 1. Overview — COM Automation Is the Primary Parser

**MS Project is installed natively on the target machine** (Lessons Learned §1). This is a confirmed environmental fact, not an assumption.

**COM automation via `win32com` is the primary reader.** Lessons Learned §2 ranks COM (Option A) at Reliability 9/10, Field Fidelity 10/10, User Effort 0/10. It uses the MS Project calculation engine directly, so all 300+ task fields are accessible — including `StatusDate`, `EarlyStart`/`EarlyFinish`, `LateStart`/`LateFinish`, `TotalSlack`, `FreeSlack`, calendars, constraint details, and custom fields that are lost through XML/CSV export (§6 "Fields Commonly Lost in Export").

**MPXJ + JPype1 is DEPRECATED as the primary parser.** Lessons Learned §3 records that build attempt v2 was *abandoned on MPXJ + JPype* (JVM init failures on Windows, null Status Date, field-mapping inconsistencies across Project 2010/2016/2019/2021). §2 states it flatly under **"CRITICAL LESSON: Do NOT Use JPype"**. MPXJ may appear only as a **subprocess** fallback (Option B: `java -jar mpp_reader.jar <path>` writing JSON to stdout), never as an in-process JPype bridge. Note: the repo-root `CLAUDE.md` lists JPype1 for an earlier build phase; that is superseded by Lessons Learned §§2–3.

**XML import is a last-resort fallback only.** §2 classifies Save-As-XML as "manual, slow, and loses data." §7 / Appendix A document specific defects (Acumen 1602082 TAB chars, 1119399 "Infinity" durations, 1365699 50-year span crashes), and calculated fields (`EarlyStart`, `EarlyFinish`, `LateStart`, `LateFinish`, `TotalSlack`, `FreeSlack`) are not stored in XML at all (§6). XML is offered only when neither MS Project nor Java is available.

## 2. COM Decision Tree (reproduced from Lessons Learned Appendix C)

The decision tree below is reproduced from Lessons Learned Appendix C. Do not deviate.

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

Short form: **MS Project installed? YES → COM. NO + Java 11+ → MPXJ subprocess. NO + no Java → XML last resort.** The subprocess fallback (Option B) runs MPXJ inside a separate `java -jar` process and communicates via JSON on stdout; the JVM never lives inside the Python process. See Lessons Learned §2 "Option B: MPXJ via subprocess (not JPype)" for the rationale.

## 3. The Ten Appendix D Gotchas (discovered through pain)

The ten items below are taken verbatim from Lessons Learned Appendix D ("COM Automation Gotchas — Discovered Through Pain"). Each is a hard rule. Each subsection gives: the rule as written in Appendix D, the forensic rationale (why the rule exists), and a minimal Python code pattern. Do not collapse or paraphrase. Every gotcha cites Appendix D by number.

### 3.1 Gotcha 1 — CoInitialize before COM, CoUninitialize after

**Rule (Lessons Learned Appendix D §1):** "Always `CoInitialize` before COM and `CoUninitialize` after. Failing to do this causes 'COM not initialized' errors."

**Rationale:** Windows COM requires each calling thread to declare itself a COM apartment before dispatching to a COM server. Python has no implicit apartment, so `pythoncom.CoInitialize()` is mandatory at entry and `pythoncom.CoUninitialize()` is mandatory at exit. Omitting either produces `pywintypes.com_error 0x800401F0` ("CoInitialize has not been called") or leaks apartment state into the next call.

**Code pattern:**
```python
import pythoncom, win32com.client

def read_mpp_via_com(filepath: str) -> dict:
    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("MSProject.Application")
        # ... work ...
    finally:
        try:
            app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
```

### 3.2 Gotcha 2 — Set Visible=False and DisplayAlerts=False BEFORE opening any file

**Rule (Lessons Learned Appendix D §2):** "`app.Visible = False` and `app.DisplayAlerts = False` must be set BEFORE opening any file. Not after."

**Rationale:** MS Project shows modal dialog boxes on file open — "Update links?", "Convert to current format?", "This file was created in a newer version", "Recalculate the project?" — each of which blocks the COM call indefinitely on an unattended machine. Lessons Learned §2 Option A caveats and §10 item 5 ("Not handling MS Project dialog boxes") both confirm that a blocked automation thread is the single most common cause of apparent hangs. `DisplayAlerts = False` must be set *before* the `FileOpen` call because MS Project evaluates the flag at dialog-construction time.

**Code pattern:**
```python
app = win32com.client.Dispatch("MSProject.Application")
app.Visible = False          # headless
app.DisplayAlerts = False    # suppress all modal dialogs
app.FileOpen(filepath, ReadOnly=True)
```

### 3.3 Gotcha 3 — MS Project COM is single-threaded; do not parallelize

**Rule (Lessons Learned Appendix D §3):** "MS Project COM runs single-threaded. Do not try to parallelize file reading. Read files sequentially."

**Rationale:** MSProject.Application registers as a single-threaded apartment (STA). Driving it from multiple threads or `multiprocessing` workers that share the apartment produces nondeterministic RPC errors and zombie processes. §2 Option A is explicit: "single-threaded per COM apartment." Multi-file batches iterate serially.

**Code pattern:**
```python
def read_many(paths: list[str]) -> list[dict]:
    # Serial, not parallel. One COM apartment, one file at a time.
    return [read_mpp_via_com(p) for p in paths]
```

### 3.4 Gotcha 4 — Null tasks in the Tasks collection

**Rule (Lessons Learned Appendix D §4):** "Null tasks in the Tasks collection. MS Project's `Tasks` collection can contain `None` entries (blank rows). Always check `if task is None: continue`."

**Rationale:** MS Project preserves blank rows in the visible Gantt view as sparse entries in `project.Tasks`. These come back as Python `None` over COM. A field access on `None` (`task.UniqueID` on a blank row) raises `AttributeError` and aborts the parse mid-schedule, silently dropping every task after the first blank row. Lessons Learned §2 Option A example code guards every iteration.

**Code pattern:**
```python
for task in project.Tasks:
    if task is None:
        continue
    tasks.append({"unique_id": task.UniqueID, "name": task.Name, ...})
```

### 3.5 Gotcha 5 — Duration and slack are in MINUTES, not days

**Rule (Lessons Learned Appendix D §5):** "Duration and slack are in MINUTES. A 5-day task at 8 hours/day = 2400 minutes. TotalSlack of 0 means 0 minutes. Divide by 480 to get working days (assuming 8-hour days — check the calendar)."

**Rationale:** COM stores `Duration`, `RemainingDuration`, `ActualDuration`, `BaselineDuration`, `TotalSlack`, `FreeSlack`, and relationship `Lag` as integer minutes with 1/10-minute precision (Appendix B). A 5-working-day task on an 8-hour calendar returns `2400`, not `5`. Treating the raw integer as days produces 480× errors in every float metric, CPM pass, and DCMA test. Convert via `minutes / (hours_per_day * 60)` using the **project default calendar's** hours-per-day, not a hard-coded 480. All downstream forensic values must be normalized to working days before leaving the parser.

**Code pattern:**
```python
def minutes_to_working_days(minutes: int, hours_per_day: float = 8.0) -> float:
    if minutes is None:
        return 0.0
    return minutes / (hours_per_day * 60.0)

duration_wd = minutes_to_working_days(task.Duration)
total_slack_wd = minutes_to_working_days(task.TotalSlack)
```

### 3.6 Gotcha 6 — StatusDate returns a date, "NA", or a sentinel

**Rule (Lessons Learned Appendix D §6):** "The `StatusDate` property returns a date or 'NA'. If the project has no Status Date set, it returns the string 'NA' or a sentinel date (12/30/1899 or 1/1/1984). Check for both."

**Rationale:** Status Date anchors every variance calc, DCMA test, and multi-version comparison. §3 records null Status Date as one of the two failures that killed build v2. Over COM an unset value can surface as (a) the string `"NA"`, (b) `datetime(1899, 12, 30)` (OLE zero), or (c) `datetime(1984, 1, 1)` (MS Project epoch). A naive truthiness check accepts all three and propagates a fake status date into every metric.

**Code pattern:**
```python
from datetime import datetime

_STATUS_DATE_SENTINELS = {datetime(1899, 12, 30), datetime(1984, 1, 1)}

def parse_status_date(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip().upper() == "NA":
        return None
    if isinstance(raw, datetime) and raw.replace(tzinfo=None) in _STATUS_DATE_SENTINELS:
        return None
    return raw
```

### 3.7 Gotcha 7 — File paths must be absolute

**Rule (Lessons Learned Appendix D §7):** "File paths must be absolute. COM automation doesn't resolve relative paths the same way as Python. Always use `os.path.abspath()`."

**Rationale:** The MS Project COM server resolves relative paths against its own current working directory, which is typically `C:\Program Files\Microsoft Office\...\OFFICEnn\`, not the Python process's CWD. Passing `"./schedules/baseline.mpp"` produces a "file not found" that points at the Office install directory and is misleading to debug. Lessons Learned §10 item 4 ("PowerShell vs. Bash confusion") expands on Windows-path pitfalls more generally.

**Code pattern:**
```python
import os

def open_mpp(app, filepath: str) -> None:
    abs_path = os.path.abspath(filepath)
    app.FileOpen(abs_path, ReadOnly=True)
```

### 3.8 Gotcha 8 — Kill zombie MSPROJECT.EXE processes

**Rule (Lessons Learned Appendix D §8):** "Kill zombie processes. If the script crashes mid-execution, `MSPROJECT.EXE` may remain running in the background. Add cleanup code in a `finally` block and consider a startup check that kills orphaned processes."

**Rationale:** A Python crash between `FileOpen` and `app.Quit()` leaves an invisible `MSPROJECT.EXE` holding a file lock on the `.mpp`. The next parse attempt hits Lessons Learned §10 item 6 ("Not handling file locking") and gets a read-only copy or an outright RPC failure. Zombies also accumulate across sessions and can exhaust user-session handles. Two defenses: (a) `app.Quit()` inside `finally`, (b) a startup sweep that kills any orphan MSPROJECT.EXE before the first parse.

**Code pattern:**
```python
import subprocess

def kill_orphan_msproject() -> None:
    # Windows only. Safe no-op if none are running.
    subprocess.run(
        ["taskkill", "/F", "/IM", "MSPROJECT.EXE"],
        capture_output=True, check=False,
    )

def read_mpp_via_com(filepath: str) -> dict:
    kill_orphan_msproject()                          # startup sweep
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.Dispatch("MSProject.Application")
        app.Visible = False
        app.DisplayAlerts = False
        app.FileOpen(os.path.abspath(filepath), ReadOnly=True)
        # ... extract ...
        app.FileClose(Save=0)                         # pjDoNotSave
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
```

### 3.9 Gotcha 9 — Always open with ReadOnly=True

**Rule (Lessons Learned Appendix D §9):** "Read-only mode. Always open files with `ReadOnly=True` to avoid locking conflicts and accidental modifications."

**Rationale:** A forensic parser must never mutate the source file. Opening read-write gives MS Project permission to silently re-save the file on close (recalculated float, updated last-saved date, re-keyed auto-links) which invalidates chain-of-custody for any delay claim, DCMA submission, or dispute record. Read-only mode also avoids the exclusive file lock that prevents other readers (including the user's own MS Project UI) from opening the same file.

**Code pattern:**
```python
app.FileOpen(os.path.abspath(filepath), ReadOnly=True)
# ... read-only extraction ...
app.FileClose(Save=0)   # pjDoNotSave == 0; never write back
```

### 3.10 Gotcha 10 — Normalize dates to ISO immediately (locale trap)

**Rule (Lessons Learned Appendix D §10):** "Date format handling. COM returns dates as `datetime` objects via `win32com`, but the format depends on the Windows locale settings. Always normalize to ISO format immediately."

**Rationale:** `win32com` surfaces COM `VARIANT DATE` values as Python `datetime` instances, but string coercion (for example `str(task.Start)` or `task.Start.strftime("%x")`) formats using the Windows regional settings — `MM/DD/YYYY` on en-US, `DD/MM/YYYY` on en-GB, `YYYY/MM/DD` on ja-JP. Any downstream string parsing (CSV export, JSON serialization, log lines, comparison between versions generated on different machines) silently misinterprets the month and day. Normalize to ISO 8601 (`YYYY-MM-DDTHH:MM:SS`) at the parser boundary and keep every internal value as a tz-naive `datetime` until presentation.

**Code pattern:**
```python
from datetime import datetime

def to_iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):            # covers "NA" and similar sentinels
        return None
    if not isinstance(dt, datetime):
        return None
    return dt.replace(microsecond=0).isoformat()

record = {
    "start": to_iso(task.Start),
    "finish": to_iso(task.Finish),
    "status_date": to_iso(parse_status_date(project.StatusDate)),
}
```

## 4. Validation Methodology — Validate Against the MS Project UI

**Authoritative passage (Lessons Learned §3, Key Recurring Failure Pattern #4):** "A parser that 'runs without errors' is not a parser that 'extracts correct values.' Every field extracted must be validated against what MS Project actually shows for the same file. Without a validation step, bad data propagates silently into every analysis module."

A successful COM call proves the RPC succeeded, not that extraction is correct. Correctness is established only by field-by-field comparison against the MS Project UI.

**Procedure (Lessons Learned §4 Phase 1, reinforced by §10 item 3):**

1. Open the target `.mpp` in the MS Project UI.
2. Select 10+ representative tasks covering summary, milestone, critical, LOE, constrained, nonzero-`TotalSlack`, baselined, and in-progress cases.
3. Hand-record every Appendix B field for each task (`UniqueID`, `ID`, `Name`, `WBS`, `OutlineLevel`, `Start`, `Finish`, `BaselineStart`, `BaselineFinish`, `ActualStart`, `ActualFinish`, `EarlyStart`, `EarlyFinish`, `LateStart`, `LateFinish`, `Duration`, `RemainingDuration`, `ActualDuration`, `BaselineDuration`, `TotalSlack`, `FreeSlack`, `PercentComplete`, `Critical`, `Milestone`, `Summary`, `ConstraintType`, `ConstraintDate`, `Deadline`).
4. Run the parser with duration/slack converted to working days (§3.5) and dates to ISO (§3.10).
5. Diff parser output against the UI values. Any mismatch is a parser defect.
6. Validate project-level fields too: `StatusDate`, `Start`, `Finish`, default calendar, `LastSavedDate` (§6).

**Validation harness discipline (§10 item 3, §12 Tier 2):** Build `scripts/validate_against_msp.py` that opens the same `.mpp` via the parser and via a second COM session and diffs field-by-field. Runs locally only; never in CI, because real `.mpp` files are CUI (§9).

**No analysis before parser validation.** §3 item 1 and §13 commandment 2: every build attempt that wrote analysis before the parser was proven failed. No CPM, no DCMA, no float burn-rate, no driving path — until validation passes.

## 5. The Unique-ID-Not-Task-ID Rule

**Rule (Lessons Learned §5 "The Unique ID Rule — Non-Negotiable"):** "When comparing two or more versions of the same project schedule that have different status dates, the Unique ID is ALWAYS the sole identifier for matching tasks across versions. … This is not optional. This is not a suggestion. This is a hard rule."

Lessons Learned §5 details the mechanics:

- `Task.ID` is a row number. It changes when tasks are inserted, deleted, or reordered. It is **useless** for cross-version matching.
- `Task.UniqueID` is assigned at task creation and **never changes** for the life of that task within that project file.
- If a `UniqueID` exists in Version A but not Version B → the task was **deleted** between versions.
- If a `UniqueID` exists in Version B but not Version A → the task was **added**.
- `Task.Name` is **not** a reliable identifier — names can be changed, and duplicate names are common.
- Reinforced by Lessons Learned §13 commandment 3: "Thou shalt match tasks by UniqueID and nothing else."

**The Predecessors-column trap *(inferred — not sourced)*:** The visible "Predecessors" column in the MS Project Gantt view displays predecessor *Task IDs*, not *UniqueIDs*. Pulling that string as a cross-version key silently re-keys every relationship when a row is inserted or deleted. §5 establishes the underlying principle (Task ID is useless for matching); the specific column-display claim is a working hypothesis until validated. The safe, sourced path is to iterate `task.TaskDependencies` and read `dep.From.UniqueID` / `task.UniqueID` directly (§2 Option A example; Appendix B "Relationship Fields").

**Code pattern (relationships keyed by UniqueID, sourced to Lessons Learned §2 Option A):**
```python
relationships = []
for task in project.Tasks:
    if task is None:
        continue
    for dep in task.TaskDependencies:
        relationships.append({
            "predecessor_uid": dep.From.UniqueID,     # UniqueID, not ID
            "successor_uid":   task.UniqueID,          # UniqueID, not ID
            "type": dep.Type,                           # COM enum: 0=FF, 1=FS, 2=SF, 3=SS
            "lag_minutes": dep.Lag,                     # minutes; convert per §3.5
        })
```

Note the COM relationship-type enum (Lessons Learned Appendix B "COM Automation Type Mappings"): `0=FF, 1=FS, 2=SF, 3=SS`. This differs from MPXJ's enum; never share relationship-type values between COM and MPXJ code paths without conversion.

## 6. Cleanup and Resource Management

Driven by Appendix D §§1, 8 and the `try/finally` pattern in §2 Option A.

```python
import os, subprocess, pythoncom, win32com.client

def read_mpp_via_com(filepath: str) -> dict:
    # Appendix D §8 — orphan MSPROJECT.EXE sweep
    subprocess.run(["taskkill", "/F", "/IM", "MSPROJECT.EXE"],
                   capture_output=True, check=False)

    pythoncom.CoInitialize()                                  # §1
    app = None
    try:
        app = win32com.client.Dispatch("MSProject.Application")
        app.Visible = False                                    # §2
        app.DisplayAlerts = False                              # §2
        app.FileOpen(os.path.abspath(filepath), ReadOnly=True) # §§7, 9
        project = app.ActiveProject
        # ... extract project-level + tasks + relationships ...
        app.FileClose(Save=0)                                  # pjDoNotSave
        return result
    finally:
        if app is not None:
            try: app.Quit()                                    # §8
            except Exception: pass
        pythoncom.CoUninitialize()                             # §1
```

**Ordering invariants (all Appendix D):**

1. Orphan `taskkill` sweep first (§8).
2. `CoInitialize()` before any `Dispatch` (§1).
3. `Visible=False` and `DisplayAlerts=False` before `FileOpen` (§2).
4. `FileOpen` with absolute path and `ReadOnly=True` (§§7, 9).
5. On every exit path, `Quit()` before `CoUninitialize()` — both in `finally` (§§1, 8).
6. Serial only; no shared-apartment threading or pooling (§3).

## 7. Out of Scope for This Skill

This skill covers *reading* `.mpp` files. The following belong to other skills or later phases and must not be built into the parser:

- **CPM math** (forward/backward pass, float calculation, critical-path trace) — see the `driving-slack-and-paths` skill and Lessons Learned §11.1–11.2.
- **Diff engine** (cross-version task/field deltas, added/deleted detection) — Lessons Learned §4 Phase 3 (`diff_engine.py`). Handled by a future diff-engine module, not this skill.
- **Report generation** (Word, Excel, PDF narrative) — Lessons Learned §4 Phase 4 (Excel/Word/narrative exporters). Handled by a future reporting module, not this skill.
- **Earned Value Management** (SPI, CEI, BEI, SPI(t)) — Lessons Learned §§11.4–11.6; EVM is deferred to a later phase and is not a parser concern.
- **AI narrative generation** — the `cui-compliance-constraints` skill and Lessons Learned §8 govern Ollama/Claude routing. The parser never calls an AI backend.
- **Manipulation-pattern detection** — the `forensic-manipulation-patterns` skill.

The parser's only job is to return a validated, ISO-normalized, minutes-converted-to-working-days data structure keyed by `UniqueID`. Everything else is downstream.

## 8. References

Every rule in this skill cites Lessons Learned. The table below maps each section of this skill to its sourced passage so that a reviewer can verify no rule is invented.

| Skill section | Lessons Learned source |
|---|---|
| §1 COM primary, MS Project installed | §1 Executive Context |
| §1 MPXJ + JPype deprecated | §2 "CRITICAL LESSON: Do NOT Use JPype"; §3 build attempt v2 row |
| §1 MPXJ subprocess allowed as fallback | §2 Option B; Appendix C |
| §1 XML last resort, lossy | §2 "Attempt: Direct XML export fallback"; §6 "Fields Commonly Lost in Export"; §7 XML Export Defects; Appendix A |
| §2 COM decision tree | Appendix C (reproduced verbatim); §2 Option C hybrid |
| §3.1 Gotcha 1 — CoInitialize/CoUninitialize | Appendix D §1 |
| §3.2 Gotcha 2 — Visible=False, DisplayAlerts=False before open | Appendix D §2; §2 Option A caveats; §10 item 5 |
| §3.3 Gotcha 3 — single-threaded, no parallelism | Appendix D §3; §2 Option A caveats |
| §3.4 Gotcha 4 — null tasks in Tasks collection | Appendix D §4; §2 Option A example |
| §3.5 Gotcha 5 — duration/slack in minutes | Appendix D §5; Appendix B "COM Automation Type Mappings" |
| §3.6 Gotcha 6 — StatusDate NA / sentinel dates | Appendix D §6; §3 build-v2 Status-Date-null failure |
| §3.7 Gotcha 7 — absolute paths | Appendix D §7; §10 item 4 |
| §3.8 Gotcha 8 — zombie MSPROJECT.EXE cleanup | Appendix D §8; §10 item 6 file-locking |
| §3.9 Gotcha 9 — ReadOnly=True | Appendix D §9 |
| §3.10 Gotcha 10 — ISO date normalization | Appendix D §10 |
| §4 Validate against MS Project UI | §3 item 4 (authoritative); §4 Phase 1 validation step; §10 item 3 validation harness; §12 Tier 2 |
| §4 No analysis before parser validated | §3 item 1; §13 commandment 2 |
| §5 UniqueID non-negotiable | §5; §13 commandment 3 |
| §5 Predecessors column trap | *(inferred — not sourced)*; underlying Task-ID-is-useless principle from §5 |
| §5 COM relationship-type enum 0=FF 1=FS 2=SF 3=SS | Appendix B "COM Automation Type Mappings" |
| §6 try/finally lifecycle | §2 Option A example; Appendix D §§1, 2, 7, 8, 9; Appendix D §3 (serial) |
| §7 Out-of-scope cross-references | §11 Analysis Module Specifications; §8 Local AI integration; §9 Security |

**Citation discipline:** Every rule above is anchored to a numbered section, appendix, or commandment in Lessons Learned except the single item in §5 explicitly marked *(inferred — not sourced)*. Any future edit that introduces a new rule must either add a citation to the table or mark the rule `(inferred — not sourced)`. Uncited, unmarked rules must be removed.
