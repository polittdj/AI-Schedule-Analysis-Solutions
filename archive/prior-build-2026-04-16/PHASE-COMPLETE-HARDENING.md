# Phase: Hardening — CI, Dependencies, Offline Bundles

This document records the hardening pass that took the Schedule Forensics
Local Tool from "all phases built" to "reproducibly runnable on a clean
workstation, green on CI, and fully offline-capable." Every change here
was committed on branch `hardening/ci-deps-cleanup` and is intended to
land on `main` as a single pull request.

## Tasks

### Task 1 — Pin every dependency in `requirements.txt`

Commit: `abd3364`

Every direct dependency **and** every transitive dependency the tool
relies on is now pinned to an exact version. No `>=`, no ranges. The
pinned set is exactly what was confirmed working during Phases 1–6.

- Primary: `flask==3.1.3`, `jpype1==1.6.0`, `mpxj==16.1.0`,
  `pydantic==2.12.5`, `python-docx==1.2.0`, `openpyxl==3.1.5`,
  `reportlab==4.4.10`, `anthropic==0.93.0`, `requests==2.33.1`
- Test: `pytest==9.0.3`
- Transitive: Flask stack (Jinja2, Werkzeug, itsdangerous, click,
  blinker, MarkupSafe); Pydantic core (pydantic-core,
  typing-extensions, typing-inspection, annotated-types); Anthropic
  SDK stack (anyio, httpx, httpcore, h11, sniffio, jiter, distro);
  export libs (lxml, pillow, et_xmlfile); pytest stack (iniconfig,
  pluggy, Pygments)

**Update policy**: bump a pin only after re-running `python -m pytest
tests/ -v` and manually smoke-testing `python -m app` in a browser.

### Task 2 — CI workflow (`.github/workflows/ci.yml`)

Commit: `48026c5`

A single `test` job that runs every test on push to `main` and on
every pull request. Steps:

1. Checkout
2. Set up OpenJDK 21 (required by JPype1 / MPXJ)
3. Set up Python 3.13 with pip cache
4. `python -m pip install --upgrade pip`
5. `pip install -r requirements.txt`
6. Show environment (python --version, java -version, pip list)
7. `python -m pytest tests/ -v --tb=short`

No deploy job — this tool is explicitly local-only, so there is no
environment to deploy to.

### Task 3 — Windows PowerShell launcher (`scripts/start.ps1`)

Commit: `657d747`

A one-shot launcher so a Windows operator can clone the repo and run
the tool without touching Python packaging. The script:

1. Verifies Python 3.11+ is on PATH (tries `python`, `py -3`, `python3`).
2. Verifies Java 17+ is on PATH (parses `java -version` output).
3. Creates `.venv` if it doesn't exist and activates it.
4. `pip install --upgrade pip` then `pip install -r requirements.txt`.
5. Launches `python -m app` (http://localhost:5000).

Each step prints a clearly-coloured status line and bails on failure
with a specific remediation hint. Run it from the repo root:

```powershell
PowerShell -ExecutionPolicy Bypass -File scripts\start.ps1
```

The POSIX equivalents (`run.sh`, `run.bat`) already shipped in Phase 4
and were not touched.

### Task 4 — Vendor the real JS library bundles

Commit: `6841377`

Replaced the empty placeholder files under `app/web/static/lib/` with
the actual minified UMD bundles so the Flask UI renders charts and
tables with **zero outbound HTTP**. Also removed the CDN `<script>`
and `<link>` fallback tags from `app/web/templates/base.html`.

| File | Source | Size |
|---|---|---|
| `app/web/static/lib/chart.min.js` | Chart.js v4.4.0 (`chart.umd.js`) | 204 KB |
| `app/web/static/lib/tabulator.min.js` | Tabulator v5.5.2 | 392 KB |
| `app/web/static/lib/tabulator.min.css` | Tabulator v5.5.2 | 25 KB |

The upstream release artifacts were pulled from their GitHub
releases:

- https://github.com/chartjs/Chart.js/releases/tag/v4.4.0
- https://github.com/olifolkerd/tabulator (tag `5.5.2`)

**Refresh procedure**: download the new release tarball, copy the
`dist/chart.umd.js` or `dist/js/tabulator.min.js` + `dist/css/tabulator.min.css`
file into `app/web/static/lib/`, and update the version number in the
comment block at the top of `base.html`.

### Task 5 — Ollama Modelfile (`ollama/Modelfile`)

Commit: `76d98e3`

Creates the custom `schedule-analyst` model the README and
`app/ai/ollama_client.py` reference. Build locally with:

```bash
ollama create schedule-analyst -f ollama/Modelfile
```

The Modelfile:

- **Base model**: `llama3.1:8b-instruct-q4_K_M` (swap the `FROM` line
  for a different base — any 8K+ context model works).
- **Sampling**: `temperature=0.2`, `top_p=0.9`, `top_k=40`,
  `repeat_penalty=1.1`, `num_ctx=8192`, `num_predict=2048`.
- **Stop tokens**: `<|eot_id|>`, `<|start_header_id|>`,
  `<|end_header_id|>`, `[CONTEXT_END]`.
- **System prompt**: mirrors `app/ai/prompt_builder.SYSTEM_INTRO` and
  expands it with the 10 formatting rules forensic narratives must
  follow (working vs. calendar days, no invented task names, DCMA
  pass/fail framing, etc.). Keep the Modelfile and `prompt_builder.py`
  in sync when either changes.

### Task 6 — Delete the stale feature branch + this document

The stale branch `claude/init-schedule-forensics-tool-9rk98` was the
original Phase 0–2 development branch. It was fully merged into
`main` in PR #2 and has not received any commits since. Keeping it
around just clutters the branch list.

- **Local**: deleted with `git branch -d
  claude/init-schedule-forensics-tool-9rk98` (clean merge, no
  `-D` needed).
- **Remote**: the local git proxy used in this environment rejects
  `git push origin --delete` with HTTP 403, and the GitHub MCP tools
  exposed to this session do not include a `delete_branch` /
  `delete_ref` endpoint. **The remote stale branch must be deleted
  manually** — either from the GitHub UI
  (`https://github.com/polittdj/ai-schedule-analysis-solutions/branches`)
  or with `git push origin --delete claude/init-schedule-forensics-tool-9rk98`
  from a terminal that can reach GitHub directly.

## Verification

After this branch is merged to `main`, the expected state is:

- `pip install -r requirements.txt` yields a reproducible environment
  on any machine with Python 3.11+ and Java 17+.
- `python -m pytest tests/ -v` passes on Ubuntu + Python 3.13 in CI.
- `scripts/start.ps1` boots the tool on a clean Windows workstation.
- `python -m app` opens http://localhost:5000 with Chart.js and
  Tabulator rendering from local files (no CDN requests in devtools'
  Network tab).
- `ollama create schedule-analyst -f ollama/Modelfile` builds the
  narrator model on a workstation that already has Ollama installed.

Nothing in this pass changes the forensic engine, the AI layer, or
any existing test. It is purely infrastructure and offline-operability.
