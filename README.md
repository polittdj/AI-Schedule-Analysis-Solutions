# Schedule Forensics Local Tool

A local web application for forensic CPM (Critical Path Method) schedule analysis of Microsoft Project (`.mpp`) files. The tool parses MPP files locally, runs deterministic forensic analysis, and generates AI-powered narrative reports — all while keeping sensitive data on the local machine.

## Overview

Schedule Forensics Local Tool ingests a native Microsoft Project file and produces a comprehensive forensic analysis covering:

- **DCMA 14-point assessment** — the Defense Contract Management Agency's schedule health checklist
- **Manipulation detection** — flags suspicious schedule edits, constraint abuse, and logic breaks
- **Critical path analysis** — identifies driving paths and near-critical activities
- **Delay analysis** — quantifies slippage between baselines and current status
- **AI-generated narrative reports** — plain-language findings written by an LLM from pre-computed metrics

The forensic engine performs ~90% of the analysis using deterministic Python code. The AI layer only generates narrative text from the computed metrics, so classified/CUI data can be fully analyzed without ever touching an AI model if the operator chooses.

## Architecture

```
MPP file ──► Java/MPXJ parser ──► Pydantic schedule model
                                         │
                                         ▼
                              Deterministic forensic engine
                               (DCMA, CPM, delay, manipulation)
                                         │
                                         ▼
                                 Pre-computed metrics
                                         │
                                         ▼
                              AI narrative layer (abstract)
                              ├── Ollama (local, for CUI)
                              └── Claude API (unclassified only)
                                         │
                                         ▼
                          Web UI  +  Word / Excel / PDF export
```

### Dual-Mode AI Backend

- **Local mode (Ollama)** — uses a custom `schedule-analyst` model on `localhost:11434`. Required for any project marked as CUI or higher. Raw schedule data never leaves the machine.
- **Cloud mode (Anthropic Claude API)** — available only for projects explicitly marked unclassified. Offers higher quality narrative output.

All AI calls go through the abstract interface in `app/ai/base.py`. The engine never sends raw MPP content to any cloud service.

## Tech Stack

| Layer           | Technology                                                      |
|-----------------|-----------------------------------------------------------------|
| MPP parser      | Java (OpenJDK) + JPype1 + MPXJ (`org.mpxj.reader.UniversalProjectReader`) |
| Backend         | Python 3.12+, Flask, Pydantic                                   |
| Frontend        | HTML / CSS / JS, Chart.js, Tabulator.js (all local, no CDN)     |
| Local AI        | Ollama (`schedule-analyst` custom model)                        |
| Cloud AI        | Anthropic Python SDK                                            |
| Export          | `python-docx`, `openpyxl`, `reportlab`                          |
| Future RAG      | ChromaDB + sentence-transformers (bolt-on)                      |

## Repository Layout

```
app/
├── parser/            # MPP → Pydantic via JPype + MPXJ
├── engine/            # Deterministic forensic analysis
├── ai/                # Abstract AI interface + Ollama/Claude backends
├── export/            # Word, Excel, PDF report generation
├── web/               # Flask blueprints, templates, static assets
│   ├── templates/
│   └── static/
│       ├── css/
│       ├── js/
│       └── lib/       # Local copies of Chart.js, Tabulator.js
└── knowledge_base/    # Future RAG knowledge store
tests/
├── fixtures/          # Sample MPP files — NEVER CUI data
ollama/                # Modelfile + prompts for schedule-analyst model
```

## Requirements

- Python 3.12+
- Java (OpenJDK 17+) on the system PATH
- Ollama installed locally (for CUI-rated projects)
- Optional: `ANTHROPIC_API_KEY` environment variable (for unclassified projects)

## Installation

```bash
git clone <repo-url>
cd AI-Schedule-Analysis-Solutions
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Conventions

- Type hints on all Python functions
- Pydantic models for all data schemas
- Flask blueprints for route organization
- All AI interaction goes through `app/ai/base.py`
- **Raw MPP data must never be sent to any cloud service**
- All times displayed in Eastern Time (ET)
- Test fixtures in `tests/fixtures/` must never contain CUI data

## Security

This tool is designed for handling potentially sensitive schedule data (up to CUI). When a project is marked CUI or higher, the cloud AI backend is disabled and all analysis stays on the local machine.

## Current Phase

**Phase 0 — Project Setup.** Skeleton and directory structure only; no application code yet.
