# Schedule Forensics Local Tool

A local web application for forensic CPM (Critical Path Method) schedule analysis of Microsoft Project (`.mpp`) files. Parses MPP files locally via Java + MPXJ, runs deterministic forensic analysis, and generates AI-powered narrative reports — all while keeping sensitive data on the local machine.

**Status: Complete — all six build phases shipped, 136 tests passing.**

---

## What it does

Drop in one `.mpp` (single-schedule health check) or two (prior + later comparative analysis) and get:

- **DCMA 14-Point Schedule Health Assessment** — every check in the Defense Contract Management Agency's industry-standard scorecard
- **Critical Path calculation** — forward + backward pass across all four relationship types with lag, summary/milestone handling, and cycle detection
- **Schedule comparator** — per-task date/duration/float deltas, added/deleted/completed tracking, logic-change detection
- **Delay root-cause analysis** — first-mover identification, cascade tracing, concurrent-delay windows
- **Manipulation detection** — 14 deterministic patterns across duration, logic, baseline, float, and progress categories, with HIGH/MEDIUM/LOW confidence scoring
- **Float consumption analysis** — tasks that became critical, WBS rollups, trend detection
- **Earned Value metrics** — PV/EV/AC/BAC/SV/CV/SPI/CPI/TCPI/EAC, auto-switching between cost mode and working-day mode
- **AI-generated narrative** streamed into the dashboard and embeddable in exports
- **Word / Excel / PDF exports** with professional formatting

The forensic engine does ~90% of the work deterministically. The AI layer only writes prose from pre-computed metrics, so CUI data can be fully analyzed without ever touching an AI model.

---

## Architecture

```
  ┌────────────────────────────────────────────────────────────────┐
  │                    Flask web UI (app/main.py)                  │
  └─────────┬──────────────┬──────────────┬──────────────┬─────────┘
            │              │              │              │
            ▼              ▼              ▼              ▼
      app/parser/    app/engine/      app/ai/       app/export/
      MPXJ via     Deterministic    Abstract AI    Word / Excel /
      JPype1       forensic         backend +      PDF generators
                   analysis         Ollama/Claude
            │              │              │              │
            └──────────────┴──────────────┴──────────────┘
                                  │
                      All results are Pydantic v2 models
                      pickled to UPLOAD_FOLDER per analysis
```

### Dual-mode AI backend

- **Local mode (Ollama)** — `schedule-analyst` model on `localhost:11434`. Required for any project rated CUI or higher. Raw data never leaves the workstation.
- **Cloud mode (Anthropic Claude API)** — `claude-sonnet-4-20250514` by default. Available only for projects explicitly marked unclassified. Higher narrative quality but sends the pre-computed prompt over the public internet.

Every AI interaction goes through the abstract `AIBackend` interface in `app/ai/base.py`. The engine never sends raw MPP content to any cloud service — only the pre-computed metric prompt built by `app/ai/prompt_builder.py`, and only after an explicit operator action.

---

## Requirements

| Dependency | Version | Why |
|------------|---------|-----|
| Python     | 3.11+   | Backend runtime |
| Java       | OpenJDK 17+ | Required by MPXJ for MPP parsing |
| Ollama     | Latest  | Local AI (only needed for CUI-rated projects) |
| Anthropic API key | optional | Cloud AI (only for unclassified projects) |

All Python dependencies are listed in `requirements.txt` and pin to major versions that work together.

---

## Installation

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/polittdj/AI-Schedule-Analysis-Solutions.git
cd AI-Schedule-Analysis-Solutions
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate              # Windows PowerShell
```

### 2. Install Java

MPP parsing uses Java under the hood. Any OpenJDK 17+ is fine:

- **macOS:** `brew install openjdk@21`
- **Ubuntu/Debian:** `sudo apt install openjdk-21-jre-headless`
- **Windows:** download from https://adoptium.net/ and add `bin/` to `PATH`

Verify with:

```bash
java -version
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, Pydantic v2, JPype1, the `mpxj` package (which bundles the MPXJ JARs), `anthropic`, `requests`, `python-docx`, `openpyxl`, and `reportlab`.

### 4. Install Ollama (optional, for CUI-rated projects)

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start the daemon
ollama serve
```

Create a `schedule-analyst` model from the provided Modelfile (once the Modelfile is added to `ollama/`):

```bash
ollama create schedule-analyst -f ollama/Modelfile
```

Or point the tool at any other model by setting the `OLLAMA_MODEL` environment variable.

### 5. (Optional) set the Claude API key for unclassified work

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Never set this on a workstation that handles CUI data.

---

## Running the app

### Quick start

```bash
# macOS / Linux
./run.sh

# Windows
run.bat
```

Both scripts check for Python + Java, install dependencies, and start the Flask dev server on <http://localhost:5000>.

### Or manually

```bash
python -m app
# equivalent:
python -m app.main
```

The Flask app binds to `127.0.0.1:5000` by default (localhost only). Press `Ctrl+C` to stop.

---

## Usage walkthrough

### 1. Upload

Open <http://localhost:5000>. Choose a mode:

- **Single schedule** — runs CPM, DCMA 14-point, earned value on one `.mpp` file
- **Comparative (2 updates)** — all of the above plus comparator, manipulation detection, float consumption, and delay root-cause analysis

Drag the file(s) into the dropzone(s) or click to browse. Click **Run Analysis**.

> *(Screenshot placeholder: dark-themed upload page with two dropzones labeled "Prior Update" and "Later Update", a mode toggle at the top, and a blue "Run Analysis" button at the bottom.)*

### 2. Analysis dashboard

After the parser and engine finish, you land on a tabbed dashboard:

| Tab | Content |
|-----|---------|
| **Executive Summary** | AI narrative panel with "Generate AI Analysis" button + project overview cards |
| **DCMA Scorecard** | 14 metrics with PASS/FAIL badges and the underlying values |
| **Critical Path** | Sortable/filterable table of CP tasks with ES/EF/LS/LF/float |
| **Slippage** *(comparative only)* | Top-10 finish-slip bar chart + full slip table + root-cause list |
| **Manipulation** *(comparative only)* | Score gauge + findings grid colored by HIGH/MEDIUM/LOW confidence |
| **Float Analysis** *(comparative only)* | Float delta histogram + became/dropped-off critical tables |
| **All Tasks** | Full task list with search, filters, pagination, CSV export |

> *(Screenshot placeholder: dashboard showing the DCMA Scorecard tab — 14-row table with some green PASS badges and a few red FAIL rows, a metric ribbon at the top, and tab navigation along the middle.)*

### 3. Generate the AI narrative

On the **Executive Summary** tab, edit the "Request" textbox if you want to steer the narrative, then click **Generate AI Analysis**. The response streams into the panel in real time via SSE. Narratives take a few seconds (Claude) or up to a minute (Ollama, depending on hardware).

> *(Screenshot placeholder: the Executive Summary tab with a streaming AI narrative visible in a monospace panel on the left and a project overview card stack on the right.)*

### 4. Export

Click **DOCX**, **XLSX**, or **PDF** in the top-right of the analysis page:

- **DOCX** — full narrative report with cover page, DCMA table, critical path, slippage analysis, manipulation findings, float summary, earned value, recommendations, conclusion
- **XLSX** — six-sheet workbook: Summary, All Tasks, Critical Path, Slippage, DCMA Scorecard, Manipulation
- **PDF** — same structure as DOCX, formatted for email / claim-package attachment

---

## Configuration

Everything is driven by environment variables. The `Config` class in `app/config.py` reads them at startup; there are no config files to edit.

| Variable | Default | Meaning |
|----------|---------|---------|
| `AI_MODE` | `local` | `local` (Ollama, CUI-safe) or `cloud` (Claude API) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `schedule-analyst` | Model name served by Ollama |
| `OLLAMA_TIMEOUT` | `120` | Seconds to wait for an Ollama response |
| `ANTHROPIC_API_KEY` | *(unset)* | Required for cloud mode |
| `ANTHROPIC_MODEL` | `claude-opus-4-6` | Claude model ID (Opus 4.6 is the default) |
| `ANTHROPIC_MAX_TOKENS` | `16384` | Hard ceiling on a single Claude response (must exceed `ANTHROPIC_THINKING_BUDGET`) |
| `ANTHROPIC_THINKING` | `true` | Enable Claude extended thinking — private chain-of-thought reasoning before the final narrative |
| `ANTHROPIC_THINKING_BUDGET` | `10000` | Token budget for extended thinking (counted separately from output tokens) |
| `SANITIZE_DATA` | `false` | Replace task/resource/project names with `Task A`-style labels before any AI call |
| `UPLOAD_FOLDER` | `./uploads` | Where uploads and analysis artifacts are stored |
| `MAX_FILE_SIZE` | `524288000` (500 MB) | Upload size cap |
| `SECRET_KEY` | insecure dev key | Flask session signing key — **set to a real secret in production** |
| `MAX_PROMPT_TOKENS` | `6000` | Hard ceiling on the AI prompt size (fits in 8K Ollama context) |

### AI mode toggle

- **For CUI-rated work:** leave `AI_MODE=local` and make sure Ollama is running locally. `Config.is_cui_safe_mode()` returns `True` in this configuration.
- **For unclassified work:** set `AI_MODE=cloud` and `ANTHROPIC_API_KEY=sk-ant-...`. The sidebar badge in the web UI flips to "Cloud Mode" and the settings page shows the Claude status indicator.

### Data sanitization

Set `SANITIZE_DATA=true` to strip all task/resource/project names before any AI call. `DataSanitizer` replaces names with deterministic labels (`Task A`, `Task B`, ...), calls the AI backend, and then substitutes the original names back into the response. Numeric data (dates, durations, slack, percentages) is preserved.

---

## Project layout

```
app/
├── __main__.py            # python -m app entry point
├── main.py                # Flask app factory + routes
├── config.py              # env-var driven Config class
├── parser/
│   ├── schema.py          # Pydantic v2 models (ScheduleData, TaskData, ...)
│   ├── mpp_reader.py      # JPype1 + MPXJ bridge, lazy JVM
│   └── calendar_parser.py # Work calendar extraction + calendar-day helper
├── engine/
│   ├── cpm.py             # Forward/backward pass + critical path
│   ├── comparator.py      # Two-schedule diff with logic-change detection
│   ├── dcma.py            # DCMA 14-point assessment
│   ├── delay_analysis.py  # First-mover / cascade / concurrent windows
│   ├── earned_value.py    # PV/EV/AC/SPI/CPI/TCPI/EAC
│   ├── float_analysis.py  # Float delta tracking and WBS rollups
│   └── manipulation.py    # 14 manipulation detection patterns
├── ai/
│   ├── base.py            # AIBackend abstract class
│   ├── prompt_builder.py  # Structured prompt from engine results
│   ├── sanitizer.py       # Task-name anonymization + reverse mapping
│   ├── ollama_client.py   # Local Ollama HTTP client (CUI-safe)
│   └── claude_client.py   # Anthropic SDK wrapper (unclassified only)
├── export/
│   ├── docx_report.py     # python-docx report
│   ├── xlsx_export.py     # openpyxl workbook
│   └── pdf_report.py      # reportlab PDF
├── web/
│   ├── templates/         # base, index, analysis, settings
│   └── static/
│       ├── css/style.css  # dark theme
│       ├── js/app.js      # vanilla JS (no build step)
│       └── lib/           # Chart.js / Tabulator.js placeholders
└── knowledge_base/        # future RAG knowledge store

tests/
├── test_parser.py         # 25 tests
├── test_engine_core.py    # 23 tests — CPM, comparator, delay
├── test_engine_forensics.py  # 22 tests — DCMA, manipulation, EV, float
├── test_ai.py             # 32 tests — prompt builder, sanitizer, clients, config
├── test_export.py         # 17 tests — DOCX, XLSX, PDF
└── test_integration.py    # 17 tests — Flask end-to-end (parser mocked)

ollama/                    # Modelfile + prompts for the schedule-analyst model
run.sh / run.bat           # Launchers
requirements.txt
```

---

## Adding documents for the future RAG upgrade

The `app/knowledge_base/` directory and the `[CONTEXT_START]` / `[CONTEXT_END]` tags in `app/ai/prompt_builder.py` are reserved for a future retrieval-augmented generation layer. To prepare:

1. **Drop markdown or text files into `app/knowledge_base/`** — forensic delay-analysis methodologies, contract clauses, historical case studies, etc.
2. **The future RAG module** will:
   - Embed every document chunk via `sentence-transformers`
   - Store embeddings in ChromaDB (planned dependency, not yet installed)
   - On each `build_prompt` call, retrieve the top-K relevant chunks and inject them between `[CONTEXT_START]` and `[CONTEXT_END]`
3. **No refactor is required** — the hooks are already in place. The prompt builder honors the placeholders today, and the AI backends don't care what's inside them.

Until the RAG module ships, anything between the tags is ignored by the AI.

---

## Testing

```bash
python -m pytest tests/ -v
```

136 tests across 6 files, all passing. The integration tests monkey-patch `parse_mpp` so the full Flask → engine → export pipeline runs in under 2 seconds without starting the JVM.

---

## Security

- Raw MPP content never leaves the machine in either mode.
- Cloud mode only transmits the structured metric prompt built from pre-computed engine output.
- `DataSanitizer` provides an additional opt-in layer that anonymizes names before the prompt is built.
- Uploads are written to `UPLOAD_FOLDER` (defaults to `./uploads`). A production deployment should configure a restricted filesystem location and a TTL reaper.
- `SECRET_KEY` defaults to an insecure dev key — override it in any real deployment.

---

## License

Internal tool — license TBD by the owner organization.

## Contributing

Bug reports and patches welcome. Run the full test suite before opening a PR:

```bash
python -m pytest tests/ -v
```

And keep the architectural rule in mind: **the forensic engine must do the analysis; the AI layer only writes prose.**
