PROJECT: Schedule Forensics Local Tool
DESCRIPTION: Local web application for forensic CPM schedule analysis of Microsoft Project (.mpp) files. Parses MPP files locally via Java/MPXJ, runs deterministic forensic analysis (DCMA 14-point, manipulation detection, critical path, delay analysis), and generates AI-powered narrative reports via dual-mode AI backend (Ollama for CUI-rated data, Claude API for unclassified).

TECH STACK:
- MPP Parser: Java (OpenJDK) + JPype1 + MPXJ (org.mpxj.reader.UniversalProjectReader)
- Backend: Python 3.12+, Flask, Pydantic
- Frontend: HTML/CSS/JS, Chart.js, Tabulator.js (all local, no CDN)
- AI Local: Ollama (schedule-analyst custom model on localhost:11434)
- AI Cloud: Anthropic Python SDK (for unclassified projects only)
- Export: python-docx, openpyxl, reportlab
- Future RAG: ChromaDB + sentence-transformers (bolt-on, no refactor needed)

CONVENTIONS:
- Type hints on all Python functions
- Pydantic models for all data schemas
- Flask blueprints for route organization
- All AI interaction through app/ai/base.py abstract interface
- NEVER send raw MPP data to any cloud service
- All times displayed in ET (Eastern Time)
- Test files in tests/fixtures/ must NEVER contain CUI data
- Use the MPXJ API: org.mpxj (not net.sf.mpxj), getPredecessorTask()/getSuccessorTask() for relations

CRITICAL ARCHITECTURE RULE: The forensic engine (app/engine/) does 90% of the analysis with deterministic code. The AI layer only generates narrative text from pre-computed metrics. This ensures CUI data can be fully analyzed without any AI involvement if needed.

CURRENT PHASE: Phase 0 - Project Setup
