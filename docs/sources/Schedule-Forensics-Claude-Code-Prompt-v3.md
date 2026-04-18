# CLAUDE CODE — SCHEDULE FORENSICS WEB APPLICATION
## Master Build Prompt v2.1

---

## AGENT ROLE

You are acting as a **senior project controls engineer, forensic schedule analyst, and full-stack software architect** operating in fully autonomous mode inside Claude Code on a **Windows desktop** environment.

You may:
- Read/write/delete any file in this repo.
- Run shell commands via **PowerShell** or **cmd.exe** (Windows environment — no bash).
- Install Python packages via `pip` (Python 3.13 is installed).
- Install Node.js packages via `npm` (only if Node.js is confirmed available — see Environment Verification below).
- Scaffold directories, create configs, write boilerplate.
- Commit and push to GitHub using `git` (if authenticated).
- Create branches, open PRs, and merge them when CI passes.
- Run tests iteratively and self-correct until they pass.
- Generate synthetic test data as needed.
- Make all architecture decisions without asking unless a hard blocker is hit.

**You do NOT need permission to:**
- Create folders, files, configs, or boilerplate.
- Write and run tests.
- Push commits.
- Install Python packages via `pip`.
- Scaffold CI workflows.

**STOP and ask the user ONLY if:**
1. A piece of software is needed that may not be installed (Java, Node.js, etc.) — verify with the user before proceeding.
2. A true ambiguity would cause irreversible architectural damage if guessed wrong.
3. A missing secret or credential cannot be synthesized.
4. There is a conflict you cannot resolve by defaulting to the more privacy-preserving or evidence-based option.

Otherwise, make the call, document the reasoning in a commit message, and continue.

---

## ENVIRONMENT VERIFICATION (CRITICAL — DO THIS FIRST)

Before writing a single line of code, run the following checks and report results to the user. **Do not assume anything is installed.**

```powershell
# Check Python
python --version

# Check pip
pip --version

# Check Java (required for MPXJ .mpp parsing)
java -version

# Check Node.js (required for React frontend)
node --version

# Check npm
npm --version

# Check Git
git --version
```

### Decision Matrix After Verification

| Dependency | If Missing | Action |
|---|---|---|
| **Python 3.13** | Should be present | Fatal error if missing — user confirmed it exists |
| **Java 11+** | ASK the user | Required for MPXJ. Cannot proceed with .mpp parsing without it. Ask: "Do you have Java 11 or later installed? If not, can you install it? I need it to read .mpp files natively." |
| **Node.js 18+** | ASK the user | Required for React frontend. Ask: "Do you have Node.js installed? If not, can you install it? I need it for the web interface." If unavailable, fall back to a Python-only solution using Flask + Jinja2 templates with vanilla JavaScript. |
| **npm** | Comes with Node.js | If Node.js is present, npm should be too |
| **Git** | ASK the user | Required for GitHub. If missing, work locally without version control |

### If Java Is NOT Available

If the user cannot install Java, switch the .mpp parsing strategy:
1. Ask the user to export .mpp files as .xml (Microsoft Project XML format) from MS Project.
2. Parse .xml files using Python's `xml.etree.ElementTree` or `lxml`.
3. Adjust all file upload UI to accept both `.mpp` and `.xml` formats.
4. Document this limitation in the README.

### If Node.js Is NOT Available

If the user cannot install Node.js, build the entire frontend using:
- **Flask** as the web server (Python-only).
- **Jinja2** templates with vanilla HTML/CSS/JavaScript.
- **Bootstrap 5** via CDN (loaded on first run, cached locally).
- **Plotly.js** via CDN for charts.
- **Cytoscape.js** via CDN for network graphs.
- The app must still be accessible at `http://localhost:5173` (or whatever port Flask uses).

---

## GITHUB SETTINGS PRE-CHECK (DO THIS BEFORE ANYTHING ELSE)

Before running environment verification or writing any code, **direct the user to verify and update the following GitHub repository settings**. Do NOT proceed until the user confirms each item is complete.

Present these instructions to the user and wait for confirmation:

---

**Go to: https://github.com/polittdj/Claude-Code-Schedule-Analysis-v3/settings**

### 1. Allow Auto-Merge on Pull Requests
- Navigate to **Settings → General → Pull Requests** section
- Check **"Allow auto-merge"**
- Check **"Allow squash merging"** (recommended for clean history)
- Check **"Automatically delete head branches"** (keeps repo clean after PR merge)

### 2. Branch Protection Rules (Configure AFTER PR-01 creates the `main` branch with CI)
- Navigate to **Settings → Branches → Add branch protection rule**
- Branch name pattern: `main`
- Check **"Require a pull request before merging"**
  - Set "Required approvals" to **0** (allows auto-merge without manual review)
- Check **"Require status checks to pass before merging"**
  - After CI workflow exists (PR-01), add the CI check name here
- Do NOT check "Require review from Code Owners"
- Do NOT check "Restrict who can push to matching branches"
- **NOTE:** If the repo is on a free GitHub plan, some branch protection features may be limited. If any setting is unavailable, tell me and I will adjust the workflow accordingly.

### 3. GitHub Actions Permissions
- Navigate to **Settings → Actions → General**
- Under "Actions permissions," select **"Allow all actions and reusable workflows"**
- Under "Workflow permissions," select **"Read and write permissions"**
- Check **"Allow GitHub Actions to create and approve pull requests"**

### 4. Confirm Git Authentication
- Confirm you are authenticated to push to this repo from your local machine. Run in PowerShell:
  ```powershell
  git remote -v
  git push --dry-run
  ```
- If using HTTPS, confirm a credential helper or personal access token is configured.
- If using SSH, confirm your SSH key is added to your GitHub account.

---

**Do NOT proceed until the user has confirmed all settings above are complete.** If any setting cannot be configured (e.g., free plan limitations), document the limitation and adjust the automation strategy to work within those constraints (e.g., manual merge instead of auto-merge).

---

## REPO TARGET

- **GitHub:** `polittdj/Claude-Code-Schedule-Analysis-v3`
- **GitHub URL:** `https://github.com/polittdj/Claude-Code-Schedule-Analysis-v3`
- **Default branch:** `main`
- **Branch strategy:** feature branches → PRs → auto-merge on green CI

### GREENFIELD WIPE (MANDATORY FIRST ACTION AFTER SETTINGS CONFIRMED)

The repository must be **completely wiped clean** before any scaffolding begins. This ensures a true greenfield start with zero legacy artifacts.

**Execute the following steps in order:**

```powershell
# Step 1: Clone the repo (or navigate to existing local clone)
git clone https://github.com/polittdj/Claude-Code-Schedule-Analysis-v3.git
cd Claude-Code-Schedule-Analysis-v3

# Step 2: Verify you are on the default branch
git checkout main

# Step 3: Delete ALL files and folders in the repo (except .git directory)
Get-ChildItem -Path . -Exclude .git | Remove-Item -Recurse -Force

# Step 4: Commit the wipe
git add -A
git commit -m "GREENFIELD WIPE: Remove all existing files to start fresh build"

# Step 5: Force push the clean state
git push origin main --force

# Step 6: Delete ALL remote branches except main (clean slate)
git branch -r | Where-Object { $_ -notmatch 'origin/main' -and $_ -notmatch 'origin/HEAD' } | ForEach-Object {
    $branch = $_.Trim() -replace 'origin/', ''
    git push origin --delete $branch
}

# Step 7: Verify the repo is empty (should show nothing or just .git)
Get-ChildItem -Path . -Force | Where-Object { $_.Name -ne '.git' }
```

**After the wipe, verify on GitHub (https://github.com/polittdj/Claude-Code-Schedule-Analysis-v3) that the repo shows an empty state or only contains a bare commit.**

**Only after the wipe is confirmed successful, proceed to Environment Verification and then scaffolding.**

---

## MISSION

Build a **local-only, single-window "Schedule Forensics" web application** that:

1. **Reads native Microsoft Project `.mpp` files** with no MS Project installation required (via MPXJ + Java, or `.xml` fallback).
2. **Accepts drag-and-drop upload** of 1–10 `.mpp` (or `.xml`) files.
3. **Automatically determines the status date** from each file and orders files chronologically (earliest first → latest last). The user should NOT need to manually specify status dates or file order.
4. **Performs all analysis** in a single browser window — no popups, no separate terminals, no secondary windows.
5. **Operates entirely through buttons, dropdowns, toggles, and drag-and-drop** — the user should never have to type instructions or commands into the tool (except optional search/filter fields).
6. **Produces downloadable reports** in Microsoft Excel (.xlsx), Microsoft Word (.docx), and PDF (.pdf) formats.
7. Is accessible at **`http://localhost:5173`** (or configured port) after a single launch command.

---

## ABSOLUTE PRIVACY CONSTRAINT

**No schedule data may EVER leave the local machine.**

- Zero external API calls containing schedule content.
- Zero cloud storage dependencies.
- App must be fully functional offline after initial dependency install.
- CI and tests must use only synthetic or public-domain sample schedules committed to the repo.
- `.gitignore` must block: `*.mpp`, `*.mpp.bak`, `exports/`, `uploads/`, `*.xml` (schedule exports), `*.csv` (schedule exports), `session_data/`, `*.json` (schedule snapshots).
- **Session wipe:** When the user clicks "End Session" or after configurable TTL (default 4 hours), ALL uploaded files, derived artifacts, database records, and in-memory analysis must be destroyed. Frontend reloads to blank upload screen.

---

## TECH STACK

### Backend
- **Python 3.13**
- **FastAPI** (if Node.js available) or **Flask** (if Node.js unavailable)
- **MPXJ** via `mpxj` Python package using JPype bridge (requires Java 11+)
  - Fallback: XML parsing via `lxml` if Java unavailable
- **NetworkX** for graph construction and CPM calculations
- **SQLite** for session/diff storage (file-based, deleted on session wipe)
- **Uvicorn** as ASGI server (FastAPI) or Werkzeug (Flask)
- **openpyxl** for Excel report generation
- **python-docx** for Word report generation
- **matplotlib** + **Pillow** for chart image generation (embedded in reports)
- **WeasyPrint** or **fpdf2** for PDF generation

### Frontend (if Node.js available)
- **React 18 + Vite**
- Single-page application, all panels in one window
- **Tailwind CSS** or **Bootstrap 5** for clean, professional styling
- **Plotly.js** for Gantt charts and trend analytics
- **Cytoscape.js** for logic network graph visualization
- **Recharts** or **Chart.js** for bar/line/pie trend charts
- **react-dropzone** for drag-and-drop file upload

### Frontend (if Node.js NOT available — Flask fallback)
- **Flask + Jinja2** templates
- **Bootstrap 5** (CDN, cached locally)
- **Plotly.js** (CDN)
- **Cytoscape.js** (CDN)
- **Vanilla JavaScript** for interactivity
- **HTML5 drag-and-drop API** for file upload

---

## USER INTERFACE DESIGN

### Design Philosophy
- **One window. One screen. Everything accessible.**
- **No typing required** — all interactions via buttons, dropdowns, toggles, drag-and-drop.
- **Professional, clean aesthetic** — think Bloomberg Terminal meets modern SaaS dashboard.
- **Color scheme:** Dark sidebar navigation + light content area. Use a professional blue/gray palette.
- **Typography:** Clean sans-serif (Inter, Roboto, or system fonts).
- **Responsive:** Must work on 1920x1080 and larger screens. Optimize for desktop — this is a professional tool.

### Required UI Panels (all in single window, tabbed or sidebar-navigated)

#### 1. Upload & Session Panel (Landing Page)
- **Large drag-and-drop zone** — "Drag .mpp files here or click to browse"
- Accepts multiple files simultaneously
- After upload, displays a **file list table** showing:
  - File name
  - Auto-detected status date
  - Auto-assigned version order (earliest → latest)
  - File size
  - Upload timestamp
  - Remove button (X) per file
- **"Analyze" button** — large, prominent, starts all analysis
- **"End Session" button** — red, prominent, visible on every screen
- **"Add More Files" button** — allows adding files after initial upload
- Users can drag to reorder files if they disagree with auto-detection

#### 2. Executive Dashboard (Main Results Page)
- **Project Health Score** — single number/grade at top (A through F, or 0–100)
- **Key metrics cards** — schedule variance, critical path length, float distribution, completion percentage
- **Trend sparklines** across versions if multiple files loaded
- **Executive Summary** — auto-generated narrative paragraph (see Executive Summary section below)
- **Quick-action buttons:**
  - "View Critical Path"
  - "View DCMA Metrics"
  - "View Forensic Findings"
  - "Download Full Report"
  - "View Trend Analysis"

#### 3. Gantt Chart Panel
- Interactive Gantt chart (Plotly.js)
- Color-coded: critical tasks (red), near-critical (orange), on-track (blue), completed (green)
- Zoom, pan, filter by WBS
- Baseline bars shown as ghost/shadow bars behind actual bars
- Hover shows: Task Unique ID, Task Name, Start, Finish, Duration, Float, % Complete

#### 4. Critical Path & Driving Path Panel
- **Critical path** visualized as highlighted chain on network graph (Cytoscape.js)
- **Focal Task Selector** — dropdown (searchable) to select any task by Unique ID or name
- **"Trace Driving Path" button** — shows driving predecessor chain from project start to selected task
- Each link shows: relationship type, lag, float contribution
- **Near-critical paths** toggleable (configurable threshold, default TF ≤ 5 days)

#### 5. Multi-Version Diff Panel
- Side-by-side or tabular comparison across schedule versions
- Color-coded cells: green (improved), red (worsened), yellow (changed but neutral), white (unchanged)
- Filterable by: changed tasks only, critical tasks only, specific WBS areas
- **"What changed?" summary** — auto-generated narrative for each version transition

#### 6. DCMA 14-Point Metrics Panel
- **14 metric cards** — each showing: metric name, value, threshold, pass/fail/warning status
- **Traffic light indicators** — green/yellow/red per metric
- **DCMA score summary** at top
- **Trend line** per metric across versions (if multiple files)
- **Drill-down:** Click any metric to see the list of tasks that triggered it

#### 7. NASA Compliance Panel
- Checklist-style display of NASA Schedule Management Handbook compliance items
- Pass/fail with evidence citations
- Recommendations for each failed item

#### 8. Forensic Findings Panel
- **Findings cards** — each showing:
  - Finding title (e.g., "Driving Path Swap Detected")
  - Confidence rating badge: LOW (gray), MEDIUM (yellow), HIGH (red)
  - Suspicion explanation (plain English)
  - Raw evidence (task IDs, before/after values, dates)
  - Affected tasks table
- Sortable by confidence level
- Filterable by finding type

#### 9. Trend Analysis Panel (Multi-Version)
- **Completion S-Curve** — planned vs. actual vs. earned across versions
- **Float Erosion Chart** — average/median total float trend across versions
- **Critical Path Length Trend** — how CP duration changed version to version
- **Task Churn Analysis** — tasks added/removed/modified per version
- **Duration Growth Chart** — total project duration trend
- **Logic Change Heatmap** — which WBS areas had the most logic changes
- **Slip Waterfall Chart** — cumulative slip contribution by WBS area
- **Resource Loading Trend** — if resource data available
- **Any other trend chart** that would provide decision-makers with actionable insight (see Trend Analysis section below)

#### 10. "Ask the Schedule" Chat Panel (Sidebar or Modal)
- **Pre-built question buttons** — user clicks, answer appears. Examples:
  - "What is driving [task]?" (with task selector dropdown)
  - "Why did [milestone] slip?" (with milestone selector)
  - "Show critical path for version [N]" (with version selector)
  - "What changed between version [A] and [B]?" (with dual version selectors)
  - "Flag manipulation risks for [task]" (with task selector)
  - "What is the DCMA score for version [N]?"
  - "What are the top float risks?"
  - "Which tasks have missing logic?"
  - "Does the project have a valid critical path?"
- **No free-text typing required** — every query is button + dropdown driven
- Fallback: Display list of supported queries

#### 11. Reports & Export Panel
- **"Generate Full Report" button** — creates comprehensive analysis report
- **Format selector:** Excel (.xlsx), Word (.docx), PDF (.pdf), or All Three
- **Report customization checkboxes:**
  - Include Executive Summary
  - Include DCMA Metrics
  - Include Forensic Findings
  - Include Trend Analysis
  - Include Critical Path Analysis
  - Include NASA Compliance
  - Include Recommendations
  - Include All Charts and Graphs
- **Download button** — downloads selected format(s) as zip if multiple

---

## EXECUTIVE SUMMARY ENGINE (CRITICAL FEATURE)

The tool must auto-generate a **narrative executive summary** that tells a story. This is not a data dump — it is a **professional briefing** written in proper English grammar as if a senior schedule analyst wrote it.

### Single-File Analysis Summary Must Address:
1. **Overall project health** — Is the project on schedule, behind schedule, or ahead of schedule? By how much?
2. **Critical path status** — What is the critical path, how long is it, and are there concerns?
3. **Float distribution** — Is float healthy or eroded? Where is negative float?
4. **Schedule quality** — DCMA score summary, key failures, what they mean.
5. **Red flags** — Any forensic manipulation indicators, missing logic, constraint issues.
6. **Completion status** — What percentage is complete? Is progress consistent with the status date?
7. **Specific problem areas** — Name the WBS areas or specific tasks (by Unique ID, name, start, and finish dates) that are problematic and explain WHY.
8. **Recommendations** — What should the project team do? Be specific and actionable.

### Multi-File Trend Analysis Summary Must ADDITIONALLY Address:
1. **Trend direction** — Is the project getting better or worse over time? Cite specific evidence.
2. **Slip analysis** — Which milestones or tasks have slipped? By how much? What is driving the slips?
3. **Duration growth** — Has the overall project duration grown? By how many days? From what date to what date?
4. **Critical path evolution** — Has the critical path changed? What does that mean?
5. **Float erosion or recovery** — Is float being consumed or recovering? Where?
6. **Logic changes** — Have there been significant logic changes? Do they look legitimate or suspicious?
7. **Areas of concern** — Specific WBS areas showing negative trends. Name them. Cite task Unique IDs, names, and dates.
8. **Areas of improvement** — Any positive trends? Where is the project doing well?
9. **Forecasting** — Based on current trends, where is this project heading? Projected completion date based on trend extrapolation.
10. **Risk register items** — Top 5 schedule risks based on the analysis, with suggested mitigations.

### Writing Rules for Executive Summary:
- **Always reference tasks by:** Unique ID, Task Name, Start Date, and Finish Date.
  - Example: "Task 1045 — 'Install Electrical Rough-In' (Start: 06/15/2026, Finish: 07/02/2026) has slipped 12 working days from its baseline finish of 06/18/2026."
- **Use proper English grammar.** Complete sentences. Professional tone.
- **Tell a story.** The reader should understand what happened, why it happened, and what to do about it.
- **Be specific enough that the reader can cross-check** any cited result against the parent schedule file in Microsoft Project.
- **Do not hedge excessively.** State findings clearly. Use confidence qualifiers only where genuinely uncertain.

---

## TREND ANALYSIS ENGINE (MULTI-VERSION)

When multiple schedule versions are loaded, the tool must perform comprehensive trend analysis. **Do not limit yourself to the list below** — generate every meaningful trend metric that could help decision-makers.

### Required Trend Analyses:

1. **Project Completion Date Trend** — Plot projected finish date across versions. Is it moving forward or backward?
2. **Critical Path Duration Trend** — Is the critical path getting longer or shorter?
3. **Total Float Distribution Trend** — Histogram or box plot of total float across versions.
4. **Negative Float Trend** — Number and severity of negative float tasks per version.
5. **S-Curve (Planned vs. Actual Progress)** — Earned schedule style.
6. **Task Churn** — Tasks added, deleted, or significantly modified per version.
7. **Logic Change Volume** — Number of predecessor/successor changes per version.
8. **Duration Change Analysis** — Tasks with duration increases/decreases, by WBS area.
9. **Constraint Change Tracking** — New constraints added, removed, or modified.
10. **Milestone Slip Chart** — Key milestones plotted across versions showing slip trends.
11. **Baseline Execution Index (BEI)** — Tasks completed on time vs. late.
12. **Critical Path Length Index (CPLI)** — Ratio trend across versions.
13. **Resource Loading Trend** — If resources are assigned in the schedules.
14. **WBS Area Performance Heatmap** — Which areas are improving vs. degrading.
15. **Float Harvest Detection** — Unusual float movements that may indicate manipulation.
16. **Slip Contribution Waterfall** — Which tasks/areas contributed most to overall slip.
17. **Schedule Density Trend** — Tasks per month, identifying front-loading or back-loading shifts.
18. **Remaining Duration vs. Original Duration** — Are remaining durations growing beyond original estimates?

### Additional Trend Analyses (Generate Any That Are Relevant):
- Risk-weighted critical path analysis
- Parallelism ratio (concurrent task count trend)
- Lead/lag usage trend
- Hard constraint proliferation trend
- LOE task ratio trend
- Summary task vs. detail task ratio
- Calendar exception analysis
- Any other metric that provides actionable insight for project decision-makers

---

## ANALYSIS ENGINE

### CPM Engine
- **Forward pass:** ES = max(EF of all predecessors, considering relationship type and lag).
- **Backward pass:** LF = min(LS of all successors).
- **Total Float** = LF - EF.
- **Free Float** = min(ES of successors) - EF.
- Handle **FS, SS, FF, and SF** relationship types.
- Hard constraints must shift ES/EF/LS/LF accordingly and be flagged as constraint-driven float.

### Critical Path
- Default critical threshold: **TF ≤ 0 days**.
- Near-critical threshold: configurable, **default TF ≤ 5 days**.
- Critical path must be traceable from project end milestone back to project start.

### Driving Path Trace
For a selected Task Unique ID:
- Identify the driving predecessor chain.
- Produce a full trace from project start to focal task.
- Show each link, relationship type, lag, and computed float contribution.

### Multi-Version Diff
Diff these fields per task across versions:
- Duration, Remaining Duration, Percent Complete
- Actual Start, Actual Finish
- Early Start, Early Finish, Late Start, Late Finish
- Total Float
- All predecessor links, All successor links
- Baseline Start, Baseline Finish, Baseline Duration
- Constraints
- Custom text and flag fields if present

### DCMA 14-Point Metrics
Implement per **DCMA-EA PAM 200.1 Section 4**.

Exclusions from denominator: Completed tasks, LOE tasks, Summary tasks, Milestones.

Required metrics:
1. Missing Logic
2. Leads
3. Lags
4. Relationship Type Distribution
5. Hard Constraints
6. High Float
7. Negative Float
8. High Duration
9. Invalid Dates
10. Resources
11. Missed Actuals
12. Critical Path Test
13. CPLI
14. BEI

Treat red metrics as **investigative triggers**, not automatic failure.

### NASA Compliance Checks
Per NASA Schedule Management Handbook:
- All authorized work included
- Logic network complete
- Valid constraints
- Critical path identifiable and traceable
- Reasonable durations
- Resources assigned
- Baseline exists and is maintained

### Forensic Manipulation Detection
Detect and report with **evidence and confidence ratings** (LOW / MEDIUM / HIGH):

1. **Driving Path Swap** — Critical path predecessor chain changed without explanation
2. **Lag Laundering** — Excessive or unusual lag values used to absorb delay
3. **Constraint Pinning** — Hard constraints used to fix dates that should be logic-driven
4. **Duration Smoothing** — Remaining durations reduced without explanation
5. **Baseline Tampering** — Baseline dates changed after original baseline set
6. **Actuals Rewriting** — Actual start/finish dates modified after initial recording
7. **Progress Inflation** — Percent complete jumps inconsistent with remaining duration
8. **Logic Deletion** — Predecessor/successor links removed without replacement
9. **Float Harvesting** — Unusual float movements suggesting manipulation
10. **Near-Critical Suppression** — Near-critical tasks manipulated to appear non-critical

For each finding provide:
- Finding title
- Suspicion explanation (plain English)
- Raw evidence (task IDs, before/after values, dates)
- Confidence rating: LOW, MEDIUM, or HIGH
- Affected task list with Unique ID, Name, Start, Finish

---

## REPORT GENERATION (DOWNLOADABLE)

### Excel Report (.xlsx)
- **Tab 1: Executive Summary** — Key metrics, health score, narrative summary
- **Tab 2: Task List** — All tasks with all fields, sortable and filterable
- **Tab 3: Critical Path** — Critical and near-critical tasks
- **Tab 4: DCMA Metrics** — 14-point scorecard with drill-down task lists
- **Tab 5: Forensic Findings** — All findings with evidence
- **Tab 6: Trend Analysis** — Version-over-version comparisons (if multi-file)
- **Tab 7: Diff Details** — Field-level changes per task across versions (if multi-file)
- **Tab 8: NASA Compliance** — Checklist with pass/fail
- **Tab 9: Recommendations** — Prioritized action items
- Professional formatting: frozen header rows, auto-filter, conditional formatting (red/yellow/green), column widths auto-fit
- Include embedded charts where possible

### Word Report (.docx)
- Professional document with:
  - Cover page (project name, analysis date, version count)
  - Table of contents
  - Executive summary narrative
  - DCMA metrics section with table
  - Critical path discussion with embedded Gantt image
  - Forensic findings section
  - Trend analysis section with embedded charts
  - NASA compliance section
  - Recommendations section
  - Appendix: full task list table
- All charts embedded as images
- All task references include Unique ID, Name, Start Date, Finish Date

### PDF Report (.pdf)
- Same content as Word report, rendered as PDF
- Professional formatting, page numbers, headers/footers
- Charts and graphs embedded as high-resolution images

---

## TASK REFERENCE FORMAT (UNIVERSAL RULE)

**Every time a task is referenced anywhere in the tool** — in the UI, in reports, in the executive summary, in findings, in trend analysis — it MUST include:
- **Unique ID**
- **Task Name**
- **Start Date** (formatted MM/DD/YYYY)
- **Finish Date** (formatted MM/DD/YYYY)

Format: `Task [Unique ID] — "[Task Name]" (Start: MM/DD/YYYY, Finish: MM/DD/YYYY)`

Example: `Task 1045 — "Install Electrical Rough-In" (Start: 06/15/2026, Finish: 07/02/2026)`

---

## "ASK THE SCHEDULE" CHAT PANEL

Implement a **rule-based intent router**. No external LLM calls by default.

**All queries are button-driven** — the user selects a query type from buttons and uses dropdowns to specify parameters. No free-text input required.

### Supported Query Types (each is a button):
1. **"What is driving [task]?"** — Dropdown: select task → shows driving path
2. **"Why did [milestone] slip?"** — Dropdown: select milestone → shows slip analysis
3. **"Show critical path for version [N]"** — Dropdown: select version → highlights CP
4. **"What changed between version [A] and [B]?"** — Dual dropdown: select two versions → shows diff
5. **"Flag manipulation risks for [task]"** — Dropdown: select task → shows forensic findings
6. **"What is the DCMA score for version [N]?"** — Dropdown: select version → shows scorecard
7. **"What are the top float risks?"** — Button only → shows ranked list
8. **"Which tasks have missing logic?"** — Button only → shows task list
9. **"Does the project have a valid critical path?"** — Button only → yes/no with explanation
10. **"Show recommendations"** — Button only → shows prioritized recommendations

Fallback: Display list of supported query buttons.

---

## SESSION MANAGEMENT AND DATA WIPE

On **"End Session" click** or **TTL expiry** (default 4 hours, configurable):
1. Delete all files in `uploads/`.
2. Delete all files in `session_data/` and `exports/`.
3. Drop all in-memory and SQLite session state.
4. Clear frontend state and reload to blank upload screen.
5. Log wipe event to local console only.

TTL should run as a background async task.

---

## DATA MODEL

Implement these **Pydantic v2 models**:

### Task
```python
class Task(BaseModel):
    unique_id: int
    id: str
    name: str
    duration_days: float
    remaining_duration_days: float
    percent_complete: float
    actual_start: date | None
    actual_finish: date | None
    early_start: date | None
    early_finish: date | None
    late_start: date | None
    late_finish: date | None
    total_float: float | None
    free_float: float | None
    constraint_type: str | None
    constraint_date: date | None
    is_critical: bool
    is_milestone: bool
    is_summary: bool
    is_loe: bool
    wbs: str
    calendar_name: str | None
    resource_names: list[str]
    custom_fields: dict[str, Any]
```

### Link
```python
class Link(BaseModel):
    pred_unique_id: int
    succ_unique_id: int
    relationship_type: Literal["FS", "SS", "FF", "SF"]
    lag_days: float
```

### Baseline
```python
class Baseline(BaseModel):
    task_unique_id: int
    baseline_start: date | None
    baseline_finish: date | None
    baseline_duration_days: float | None
    baseline_work: float | None
```

### ScheduleVersion
```python
class ScheduleVersion(BaseModel):
    version_index: int
    filename: str
    status_date: date | None
    project_start: date
    project_finish: date
    tasks: list[Task]
    links: list[Link]
    baselines: list[Baseline]
    extracted_at: datetime
```

### Session
```python
class Session(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    versions: list[ScheduleVersion]
    upload_paths: list[Path]
```

---

## PROJECT STRUCTURE

```
Claude-Code-Schedule-Analysis-v3/
├── backend/
│   ├── __init__.py
│   ├── main.py                    # FastAPI/Flask app entry point
│   ├── mpp_parser.py              # MPXJ .mpp file reader
│   ├── xml_parser.py              # Fallback XML parser
│   ├── schemas.py                 # Pydantic data models
│   ├── cpm.py                     # CPM engine (forward/backward pass)
│   ├── driving_path.py            # Driving path trace
│   ├── diff_engine.py             # Multi-version diff
│   ├── dcma.py                    # DCMA 14-point metrics
│   ├── nasa.py                    # NASA compliance checks
│   ├── forensics.py               # Manipulation detection
│   ├── trend_analysis.py          # Multi-version trend engine
│   ├── executive_summary.py       # Narrative summary generator
│   ├── report_excel.py            # Excel report generator
│   ├── report_word.py             # Word report generator
│   ├── report_pdf.py              # PDF report generator
│   ├── intent_router.py           # "Ask the Schedule" query handler
│   ├── session_manager.py         # Session lifecycle + TTL + wipe
│   └── chart_generator.py         # Matplotlib chart image generation
├── frontend/                      # React app (or Flask templates)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UploadPanel.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── GanttPanel.jsx
│   │   │   ├── CriticalPathPanel.jsx
│   │   │   ├── DiffPanel.jsx
│   │   │   ├── DCMAPanel.jsx
│   │   │   ├── NASAPanel.jsx
│   │   │   ├── ForensicsPanel.jsx
│   │   │   ├── TrendPanel.jsx
│   │   │   ├── ChatPanel.jsx
│   │   │   ├── ReportsPanel.jsx
│   │   │   └── Sidebar.jsx
│   │   └── styles/
│   ├── package.json
│   └── vite.config.js
├── templates/                     # Flask Jinja2 fallback templates
├── static/                        # Static assets for Flask fallback
├── scripts/
│   ├── start.ps1                  # PowerShell launch script (Windows)
│   ├── start.bat                  # CMD launch script (Windows)
│   └── generate_test_data.py      # Synthetic schedule generator
├── tests/
│   ├── test_parser.py
│   ├── test_cpm.py
│   ├── test_diff.py
│   ├── test_dcma.py
│   ├── test_nasa.py
│   ├── test_forensics.py
│   ├── test_trend.py
│   ├── test_summary.py
│   ├── test_reports.py
│   ├── test_intent_router.py
│   └── test_session.py
├── uploads/                       # Temporary upload storage (gitignored)
├── exports/                       # Generated reports (gitignored)
├── session_data/                  # SQLite + session artifacts (gitignored)
├── .gitignore
├── .env.example
├── requirements.txt
├── README.md
└── .github/
    └── workflows/
        └── ci.yml
```

---

## ONE-COMMAND LAUNCH

### `scripts/start.ps1` (PowerShell — primary)
```
1. Verify Python 3.13+, Java 11+ (if MPXJ mode), Node.js 18+ (if React mode).
2. Create and activate Python virtual environment if not exists.
3. pip install -r requirements.txt
4. If React mode: cd frontend && npm install && npm run build (or npm run dev)
5. Start backend server on port 8000.
6. If React mode: Start Vite dev server on port 5173.
7. If Flask mode: Backend serves frontend on port 5173 directly.
8. Open default browser to http://localhost:5173
9. Print: "Schedule Forensics Tool running at: http://localhost:5173"
```

### `scripts/start.bat` (CMD — fallback)
Same logic as PowerShell script but in batch syntax.

---

## TESTING STRATEGY (CRITICAL)

### Philosophy
**Test continuously. Test modularly. Test in sandbox. Never ship broken code.**

### Test-Driven Development Cycle
For EVERY module:
1. **Write the module.**
2. **Write tests for the module** using synthetic data.
3. **Run tests in isolation** (sandbox — not against real data).
4. **If tests pass:** Commit and move to next module.
5. **If tests fail:**
   a. Perform **root cause analysis** — identify exactly which assertion failed and why.
   b. Formulate a **hypothesis** for the fix.
   c. Implement the fix.
   d. **Re-run tests.**
   e. If tests pass: commit the fix.
   f. If tests still fail: formulate next hypothesis and repeat.
   g. **Document each hypothesis and result** in commit messages.
   h. Continue until **100% of tests pass**.

### Synthetic Test Data
- Create `scripts/generate_test_data.py` that produces synthetic schedule data covering:
  - Simple linear schedule (10 tasks, all FS)
  - Complex network (50+ tasks, mixed FS/SS/FF/SF, lags, leads)
  - Schedule with constraints (SNET, SNLT, FNET, FNLT, MSO, MFO)
  - Schedule with negative float
  - Schedule with missing logic (open ends)
  - Schedule with forensic manipulation indicators
  - Multi-version set (3 versions with progressive changes)
  - Schedule with milestones, LOE tasks, and summary tasks
- Tests must NEVER use real .mpp files — only synthetic data or JSON fixtures.

### Required Test Suites
| Test File | Tests |
|---|---|
| `test_parser.py` | MPP/XML parsing, field extraction, status date detection |
| `test_cpm.py` | Forward pass, backward pass, float calculation, all 4 relationship types, constraints |
| `test_diff.py` | Field-level diff, logic change detection, version ordering |
| `test_dcma.py` | All 14 metrics, exclusion logic, threshold logic |
| `test_nasa.py` | All compliance checks |
| `test_forensics.py` | All 10 manipulation detection algorithms |
| `test_trend.py` | All trend analysis computations |
| `test_summary.py` | Narrative generation, task reference formatting |
| `test_reports.py` | Excel/Word/PDF generation, file validity |
| `test_intent_router.py` | All 10 query types, response accuracy |
| `test_session.py` | Session creation, TTL, wipe verification |

---

## PR MILESTONES (DEVELOPMENT ORDER)

### PR-01: Repo Scaffold + CI Skeleton
- All directories, placeholder modules, `.gitignore`, `.env.example`, `requirements.txt`, `package.json`
- GitHub Actions CI for lint and placeholder tests
- PowerShell and CMD launch scripts (skeleton)
- **Acceptance:** CI passes on empty scaffold

### PR-02: MPP/XML Parser + Data Model
- `mpp_parser.py`, `xml_parser.py`, `schemas.py`, `generate_test_data.py`
- Status date auto-detection logic
- **Acceptance:** `pytest tests/test_parser.py` passes

### PR-03: CPM Engine + Driving Path
- `cpm.py`, `driving_path.py`
- **Acceptance:** `pytest tests/test_cpm.py` passes

### PR-04: Diff Engine + Multi-Version Compare
- `diff_engine.py`
- **Acceptance:** `pytest tests/test_diff.py` passes

### PR-05: DCMA 14-Point + NASA Checks
- `dcma.py`, `nasa.py`
- **Acceptance:** `pytest tests/test_dcma.py && pytest tests/test_nasa.py` passes

### PR-06: Forensic Manipulation Detection
- `forensics.py`
- **Acceptance:** `pytest tests/test_forensics.py` passes

### PR-07: Trend Analysis + Executive Summary Engine
- `trend_analysis.py`, `executive_summary.py`, `chart_generator.py`
- **Acceptance:** `pytest tests/test_trend.py && pytest tests/test_summary.py` passes

### PR-08: Report Generation (Excel, Word, PDF)
- `report_excel.py`, `report_word.py`, `report_pdf.py`
- **Acceptance:** `pytest tests/test_reports.py` passes — generated files open correctly

### PR-09: Backend API + Session Management
- `main.py`, `session_manager.py`, `intent_router.py`
- All REST endpoints wired up
- **Acceptance:** Integration endpoint tests pass

### PR-10: Frontend — Upload + Dashboard + Navigation
- Upload panel with drag-and-drop, version timeline, sidebar navigation
- Dashboard with health score and executive summary
- **Acceptance:** Synthetic upload and analysis display works

### PR-11: Frontend — Visualization Panels
- Gantt chart, critical path network, diff view, DCMA panel, forensics panel, trend panel
- **Acceptance:** All visual components render with synthetic data

### PR-12: Frontend — Chat Panel + Reports Panel
- Button-driven chat panel, report download panel
- **Acceptance:** All supported queries return correct responses, reports download successfully

### PR-13: Polish, README, One-Command Launch
- Final `scripts/start.ps1` and `start.bat`
- README with screenshots and usage instructions
- End-to-end smoke test
- **Acceptance:** Running `powershell scripts/start.ps1` launches fully functional app

---

## OUTPUT AND QUALITY RULES

1. **Evidence-backed findings** — every conclusion cites file, version, status date, Task Unique ID, Task Name, Start/Finish dates, before/after field values, before/after logic links, and float/date impact.
2. **No external network calls** with schedule content — ever.
3. **CI and tests use synthetic data only.**
4. **Build until tests pass** — no partial implementations shipped.
5. **Prefer explicit, deterministic logic** over opaque heuristics.
6. **All dates displayed in MM/DD/YYYY format** (US convention).
7. **All times displayed in Eastern Time (ET)** — EST (UTC-5) or EDT (UTC-4) depending on DST.
8. **Professional English grammar** in all narratives, summaries, and findings.
9. **Modular architecture** — each analysis engine is independently testable and replaceable.

---

## FINAL GOAL

Deliver a **polished, local-only, single-window schedule forensics web application** at `http://localhost:5173` with:
- Complete backend (parsing, CPM, diff, DCMA, NASA, forensics, trends, summaries, reports)
- Professional frontend (drag-and-drop upload, dashboard, Gantt, network graph, diff view, findings, trends, chat panel, report downloads)
- Comprehensive test suite with 100% pass rate
- Session wipe behavior
- Downloadable reports in Excel, Word, and PDF
- Auto-generated executive summaries that tell a story
- One-command launch via PowerShell or CMD
- Clean, documented GitHub repository at `https://github.com/polittdj/Claude-Code-Schedule-Analysis-v3`

## MANDATORY EXECUTION ORDER

**You MUST follow this exact sequence. Do not skip or reorder steps.**

1. **GitHub Settings Pre-Check** — Present the settings checklist to the user. WAIT for confirmation before proceeding.
2. **Greenfield Wipe** — Delete all existing files in `polittdj/Claude-Code-Schedule-Analysis-v3`. Confirm empty state.
3. **Environment Verification** — Check Python, Java, Node.js, Git. Report findings. Ask about missing dependencies.
4. **Scaffolding (PR-01)** — Directories, configs, CI, launch scripts.
5. **Build module by module (PR-02 through PR-13)** — Test each module before moving to the next. Do not proceed to the next PR if current tests fail.
6. **Final smoke test** — Launch the app and verify end-to-end functionality.


