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

CURRENT PHASE: Complete — All Phases Built (Phases 0–6)

KEY DECISIONS (captured during the build):

1. Pydantic v2 (not v1). The installed `pydantic` is 2.12; all schema models use `ConfigDict(extra="forbid")` and `model_dump(mode="json")` for JSON serialization. Anything that needs a dict representation of a Pydantic model must use `model_dump`, never `.dict()` (which is deprecated).

2. JPype lazy-start. `app.parser.mpp_reader._ensure_jvm()` only starts the JVM on the first `parse_mpp()` call, never at import time. This keeps `python -m app.main` booting in under a second on machines without Java configured. The lazy import `from app.parser.mpp_reader import parse_mpp` is done *inside* the `/analyze` route handler for the same reason.

3. Working days vs. calendar days. Every duration and float value in the parser/engine is expressed in **working days** (the parser normalizes via `duration_to_days`). Date slips in the comparator are reported in **calendar days** because that's what practitioners expect when reading "the project slipped 5 days."

4. Disk-backed analysis store. Flask's cookie-based session has a 4 KB cap that cannot hold a full `ScheduleData` tree. Analysis results are pickled to `UPLOAD_FOLDER/analysis_<uuid>.pkl` and only the UUID lives in the session. A multi-worker deployment would swap this for Redis.

5. DCMA Critical Path Test uses `model_copy`. Metric #12 (CPT) needs to rebuild the schedule with +1 day on a critical task and re-run CPM. We use `TaskData.model_copy(update={"duration": ...})` + `ScheduleData.model_copy(update={"tasks": ...})` — no mutation of the original.

6. `DataSanitizer` is one-shot per analysis run. The UID → label mapping is instance state, not global. The Flask route instantiates a new sanitizer per `/ai-analyze` call, sanitizes before the backend call, then `desanitize_text`s each streaming chunk on the way out. (Per-chunk desanitization may miss labels that straddle chunk boundaries; a future phase can buffer before emitting.)

7. CUI gate lives in `Config.is_cui_safe_mode()`. The web layer is responsible for refusing to construct a `ClaudeClient` for CUI-rated projects. The AI client classes themselves don't know about classification levels — they just honor `is_available()`.

8. Export modules return `bytes`, not `BytesIO`. Keeps the web layer thin (it wraps bytes in `io.BytesIO` for `send_file`) and makes the exporters trivially testable without any stream plumbing.

9. CDN + local fallback for Chart.js / Tabulator.js. `base.html` loads the local placeholder first, then the CDN as a working fallback. Air-gapped deployments should download the real UMD bundles to `app/web/static/lib/` and strip the CDN `<script>` tags — the procedure is documented at the top of each placeholder file.

10. Cycle handling is lenient. `cpm.compute_cpm` reports stuck UIDs in `CPMResults.cycles_detected` but still produces best-effort numbers for the non-cyclic subgraph. A broken schedule is still a forensic target — we don't crash on it.

11. `ws.freeze_panes = "A2"` not `ws["A2"]`. openpyxl materializes a phantom blank row if you dereference a cell before it exists. Assign the coordinate string directly.

12. AI narrative HTML-escape before reportlab. `Paragraph` parses a subset of HTML (`<b>`, `<i>`, `<font>`), so operator-supplied text must have `&`, `<`, `>` escaped or the PDF builder raises a parse error. Only the narrative is escaped; machine-generated table content is trusted.

13. The `mpxj` pip package exposes `mpxj.mpxj_dir` pointing at bundled JARs. We use JPype1 directly (not `mpxj.startJVM()`) to match the architecture requirement that JPype1 is the bridge, and to keep classpath control explicit.

14. Test fixtures never touch the JVM. Integration tests monkey-patch `app.parser.mpp_reader.parse_mpp` to return synthetic `ScheduleData` so the full web-layer pipeline can be exercised in under a second without Java, without MPP fixtures, and without JVM startup overhead.
