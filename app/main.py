"""Flask application for the Schedule Forensics Local Tool.

Entry point: ``python -m app.main``

The app factory (`create_app`) wires together the routes and the
per-request config. Nothing here touches the JVM at import time — the
MPP parser starts the JVM lazily on the first real ``parse_mpp`` call
so ``python -m app.main`` boots quickly even without Java configured.

Storage model
-------------
Flask sessions are cookie-based (4 KB cap), far too small to hold a
full ``ScheduleData`` tree. Instead we store analysis artifacts on
disk in the configured ``UPLOAD_FOLDER`` as pickle files keyed by a
UUID, and the session only carries that UUID. A real deployment would
add a TTL reaper; Phase 4 keeps it simple.
"""
from __future__ import annotations

import io
import json
import pickle
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from werkzeug.utils import secure_filename

from app.ai.claude_client import ClaudeClient
from app.ai.ollama_client import OllamaClient
from app.ai.sanitizer import DataSanitizer
from app.config import Config, load_config
from app.engine.comparator import compare_schedules
from app.engine.cpm import compute_cpm
from app.engine.dcma import compute_dcma
from app.engine.delay_analysis import analyze_delays
from app.engine.earned_value import compute_earned_value
from app.engine.float_analysis import analyze_float
from app.engine.manipulation import detect_manipulations
from app.parser.schema import ScheduleData

# --------------------------------------------------------------------------- #
# Pipeline helpers
# --------------------------------------------------------------------------- #


def _run_single_schedule_pipeline(schedule: ScheduleData) -> Dict[str, Any]:
    """Run every single-schedule engine module on `schedule`."""
    cpm = compute_cpm(schedule)
    return {
        "cpm": cpm,
        "dcma": compute_dcma(schedule, cpm),
        "earned_value": compute_earned_value(schedule),
    }


def _run_comparative_pipeline(
    prior: ScheduleData, later: ScheduleData
) -> Dict[str, Any]:
    """Run the full comparative pipeline on `prior` + `later`."""
    later_single = _run_single_schedule_pipeline(later)
    comparison = compare_schedules(prior, later)
    return {
        **later_single,
        "comparison": comparison,
        "manipulation": detect_manipulations(comparison, prior, later),
        "float_analysis": analyze_float(comparison, prior, later),
        "delay": analyze_delays(comparison, later),
    }


def _assemble_results(
    prior: ScheduleData, later: Optional[ScheduleData]
) -> Dict[str, Any]:
    """Merge prior/later schedules with the computed engine output."""
    if later is None:
        base: Dict[str, Any] = {
            "prior_schedule": prior,
            "later_schedule": None,
            "comparison": None,
            "manipulation": None,
            "float_analysis": None,
            "delay": None,
            "trend": None,
            **_run_single_schedule_pipeline(prior),
        }
    else:
        base = {
            "prior_schedule": prior,
            "later_schedule": later,
            "trend": None,
            **_run_comparative_pipeline(prior, later),
        }
    base["generated_at"] = datetime.utcnow().isoformat()
    return base


def _assemble_trend_results(schedules: List[ScheduleData]) -> Dict[str, Any]:
    """Run the full pipeline for a 3+ schedule trend analysis.

    The ``prior_schedule`` / ``later_schedule`` keys point at the first
    and last updates so the rest of the forensic engine (which is
    two-schedule-shaped) keeps working unchanged. The new ``trend``
    key carries the time-series built from every pairwise comparison.
    """
    from app.engine.trend_analysis import compute_trend_analysis

    earliest = schedules[0]
    latest = schedules[-1]
    base: Dict[str, Any] = {
        "prior_schedule": earliest,
        "later_schedule": latest,
        **_run_comparative_pipeline(earliest, latest),
        "trend": compute_trend_analysis(schedules),
    }
    base["generated_at"] = datetime.utcnow().isoformat()
    return base


# --------------------------------------------------------------------------- #
# Disk-backed analysis store
# --------------------------------------------------------------------------- #


def _store_path(upload_folder: Path, analysis_id: str) -> Path:
    return upload_folder / f"analysis_{analysis_id}.pkl"


def _save_analysis(upload_folder: Path, analysis_id: str, results: Dict[str, Any]) -> None:
    upload_folder.mkdir(parents=True, exist_ok=True)
    with _store_path(upload_folder, analysis_id).open("wb") as f:
        pickle.dump(results, f)


def _load_analysis(
    upload_folder: Path, analysis_id: str
) -> Optional[Dict[str, Any]]:
    path = _store_path(upload_folder, analysis_id)
    if not path.exists():
        return None
    with path.open("rb") as f:
        return pickle.load(f)


# --------------------------------------------------------------------------- #
# Serialization helpers for templates
# --------------------------------------------------------------------------- #


def _to_json_safe(obj: Any) -> Any:
    """Deep-convert Pydantic models and datetimes into JSON-friendly types."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _results_for_template(results: Dict[str, Any]) -> Dict[str, Any]:
    return _to_json_safe(results)


# --------------------------------------------------------------------------- #
# File upload helpers
# --------------------------------------------------------------------------- #


def _valid_extension(filename: str, allowed: set[str]) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in allowed


def _save_upload(file_storage, upload_folder: Path, prefix: str) -> Path:
    safe = secure_filename(file_storage.filename or "unnamed.mpp")
    unique = f"{prefix}_{uuid.uuid4().hex[:8]}_{safe}"
    upload_folder.mkdir(parents=True, exist_ok=True)
    target = upload_folder / unique
    file_storage.save(str(target))
    return target


# --------------------------------------------------------------------------- #
# Export dispatchers (DOCX / XLSX / PDF)
#
# The real report-building code lives in app/export/. This layer just
# pulls the saved analysis from disk, wraps the bytes in a BytesIO, and
# hands it to `send_file`. Keeps the web layer thin and makes the
# exporters independently testable.
# --------------------------------------------------------------------------- #

from app.export.docx_report import generate_docx_report
from app.export.pdf_report import generate_pdf_report
from app.export.xlsx_export import generate_xlsx_export


def _primary_schedule(results: Dict[str, Any]) -> Optional[ScheduleData]:
    return results.get("later_schedule") or results.get("prior_schedule")


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #


def create_app(config: Optional[Config] = None) -> Flask:
    cfg = config or load_config()

    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_FILE_SIZE
    app.config["APP_CONFIG"] = cfg

    cfg.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #

    @app.context_processor
    def inject_config() -> Dict[str, Any]:
        return {"config": cfg}

    # ------------------------------------------------------------------ #
    # Template filters
    # ------------------------------------------------------------------ #

    def _parse_date(value: Any) -> Optional[datetime]:
        """Parse a datetime, ISO string, or date into a Python datetime."""
        if value is None or value == "" or value == "—":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @app.template_filter("short_date")
    def short_date_filter(value: Any) -> str:
        """Format any date value as short US date: M/D/YYYY.

        Examples: "1/5/2026", "2/13/2026", "12/31/2029".
        Returns "—" for None/empty values.
        """
        dt = _parse_date(value)
        if dt is None:
            return "—"
        return f"{dt.month}/{dt.day}/{dt.year}"

    # Keep the old name as an alias so existing templates don't break
    # during the transition. Both filters return the same M/D/YYYY format.
    @app.template_filter("readable_date")
    def readable_date_filter(value: Any) -> str:
        return short_date_filter(value)

    @app.template_filter("readable_datetime")
    def readable_datetime_filter(value: Any) -> str:
        """Format a datetime with time: "1/5/2026 8:00 AM"."""
        dt = _parse_date(value)
        if dt is None:
            return "—"
        return f"{dt.month}/{dt.day}/{dt.year} {dt.strftime('%I:%M %p').lstrip('0')}"

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/analyze", methods=["POST"])
    def analyze():
        mode = request.form.get("mode", "auto")
        auto_sort_raw = request.form.get("auto_sort", "on").strip().lower()
        auto_sort = auto_sort_raw in {"on", "1", "true", "yes"}

        # Collect every uploaded file from both the new multi-file input
        # (`schedule_files`) and the legacy `prior_file` / `later_file`
        # fields that the Phase 4 UI shipped with. The legacy fields are
        # treated as "prior goes first" only when the user has explicitly
        # disabled auto-sort.
        uploaded = []
        for f in request.files.getlist("schedule_files"):
            if f and (f.filename or "").strip():
                uploaded.append(("schedule", f))
        prior_file = request.files.get("prior_file")
        if prior_file and (prior_file.filename or "").strip():
            uploaded.append(("prior", prior_file))
        later_file = request.files.get("later_file")
        if later_file and (later_file.filename or "").strip():
            uploaded.append(("later", later_file))

        if not uploaded:
            flash("Please upload at least one schedule file.", "error")
            return redirect(url_for("index"))

        for _, f in uploaded:
            if not _valid_extension(f.filename, set(cfg.ALLOWED_EXTENSIONS)):
                flash(
                    f"Unsupported file type: {f.filename}. Allowed: "
                    f"{', '.join(sorted(cfg.ALLOWED_EXTENSIONS))}.",
                    "error",
                )
                return redirect(url_for("index"))

        try:
            from app.parser.mpp_reader import parse_mpp  # lazy: avoids JVM at import
        except Exception as exc:
            flash(f"Parser unavailable: {exc}", "error")
            return redirect(url_for("index"))

        # Save and parse every file. The order on disk preserves the
        # upload order so we can detect auto-sort reorders below.
        try:
            schedules: List[ScheduleData] = []
            for idx, (kind, f) in enumerate(uploaded):
                prefix = kind if kind != "schedule" else f"update{idx}"
                path = _save_upload(f, cfg.UPLOAD_FOLDER, prefix)
                schedules.append(parse_mpp(str(path)))
        except Exception as exc:
            app.logger.error("Parse failed: %s", exc)
            app.logger.error(traceback.format_exc())
            flash(f"Analysis failed: {exc}", "error")
            return redirect(url_for("index"))

        # Auto-sort by status_date (earliest → latest). We only flash the
        # reorder message when the order actually changed — no point
        # nagging the user when they already dropped things in sequence.
        if auto_sort and len(schedules) >= 2:
            indexed = list(enumerate(schedules))
            indexed.sort(
                key=lambda pair: pair[1].project_info.status_date or datetime.max
            )
            new_order = [pair[0] for pair in indexed]
            if new_order != list(range(len(schedules))):
                schedules = [pair[1] for pair in indexed]
                flash(
                    "Files were automatically reordered based on status dates.",
                    "info",
                )

        # Dispatch: 1 → single, 2 → comparative, 3+ → trend.
        try:
            if len(schedules) == 1:
                results = _assemble_results(schedules[0], None)
            elif len(schedules) == 2:
                results = _assemble_results(schedules[0], schedules[1])
            else:
                results = _assemble_trend_results(schedules)
        except Exception as exc:
            app.logger.error("Analysis failed: %s", exc)
            app.logger.error(traceback.format_exc())
            flash(f"Analysis failed: {exc}", "error")
            return redirect(url_for("index"))

        analysis_id = uuid.uuid4().hex
        _save_analysis(cfg.UPLOAD_FOLDER, analysis_id, results)
        session["analysis_id"] = analysis_id
        flash("Analysis complete.", "success")
        return redirect(url_for("analysis_page"))

    @app.route("/analysis")
    def analysis_page():
        analysis_id = session.get("analysis_id")
        if not analysis_id:
            flash("No analysis in progress. Upload a schedule to get started.", "info")
            return redirect(url_for("index"))
        results = _load_analysis(cfg.UPLOAD_FOLDER, analysis_id)
        if results is None:
            session.pop("analysis_id", None)
            flash("Analysis artifacts were purged. Please re-upload.", "info")
            return redirect(url_for("index"))

        template_ctx = _results_for_template(results)
        return render_template(
            "analysis.html",
            results=template_ctx,
            results_json=json.dumps(template_ctx, default=str),
            has_comparison=results.get("comparison") is not None,
            has_trend=results.get("trend") is not None,
        )

    @app.route("/ai-analyze", methods=["POST"])
    def ai_analyze():
        analysis_id = session.get("analysis_id")
        if not analysis_id:
            return jsonify({"error": "No analysis loaded"}), 400
        results = _load_analysis(cfg.UPLOAD_FOLDER, analysis_id)
        if results is None:
            return jsonify({"error": "Analysis artifacts purged"}), 404

        user_request = request.form.get(
            "request", "Provide a comprehensive forensic analysis."
        )
        backend_name = request.form.get("backend") or cfg.AI_MODE
        if backend_name == "cloud":
            backend = ClaudeClient(
                api_key=cfg.ANTHROPIC_API_KEY, model=cfg.ANTHROPIC_MODEL
            )
        else:
            backend = OllamaClient(
                url=cfg.OLLAMA_URL,
                model=cfg.OLLAMA_MODEL,
                timeout=cfg.OLLAMA_TIMEOUT,
            )

        if not backend.is_available():
            return (
                jsonify(
                    {
                        "error": f"AI backend '{backend_name}' is not available. "
                        "Check settings."
                    }
                ),
                503,
            )

        sanitizer = DataSanitizer() if cfg.SANITIZE_DATA else None
        engine_results = results
        if sanitizer is not None:
            engine_results = sanitizer.sanitize(results)

        def generate():
            try:
                for chunk in backend.stream_analyze(engine_results, user_request):
                    if sanitizer is not None and chunk:
                        chunk = sanitizer.desanitize_text(chunk)
                    if chunk:
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/task-focus", methods=["GET", "POST"])
    def task_focus():
        analysis_id = session.get("analysis_id")
        if not analysis_id:
            flash("No analysis loaded. Upload a schedule first.", "error")
            return redirect(url_for("index"))
        results = _load_analysis(cfg.UPLOAD_FOLDER, analysis_id)
        if results is None:
            session.pop("analysis_id", None)
            flash("Analysis artifacts were purged. Please re-upload.", "info")
            return redirect(url_for("index"))

        if request.method == "POST":
            raw_uid = request.form.get("task_uid", "").strip()
        else:
            raw_uid = request.args.get("uid", "").strip()
        try:
            target_uid = int(raw_uid)
        except ValueError:
            flash("Invalid task UID.", "error")
            return redirect(url_for("analysis_page"))

        schedule = results.get("later_schedule") or results.get("prior_schedule")
        if schedule is None:
            flash("No schedule data available for task focus.", "error")
            return redirect(url_for("analysis_page"))

        from app.engine.driving_path import (
            analyze_driving_path,
            filter_engine_results_by_uids,
        )

        try:
            dp_result = analyze_driving_path(
                schedule, target_uid, cpm_results=results.get("cpm")
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("analysis_page"))

        chain_uids = set(dp_result.all_chain_uids)
        filtered = filter_engine_results_by_uids(results, chain_uids)

        task_lookup = {t.uid: t for t in schedule.tasks}
        return render_template(
            "task_focus.html",
            driving=_to_json_safe(dp_result),
            target=_to_json_safe(task_lookup.get(target_uid)),
            task_name_lookup={
                t.uid: (t.name or f"Task {t.uid}") for t in schedule.tasks
            },
            has_comparison=results.get("comparison") is not None,
            filtered_task_deltas=_to_json_safe(
                filtered.get("filtered_task_deltas", [])
            ),
            filtered_manipulation_findings=_to_json_safe(
                filtered.get("filtered_manipulation_findings", [])
            ),
            filtered_float_changes=_to_json_safe(
                filtered.get("filtered_float_changes", [])
            ),
            filtered_dcma_metrics=_to_json_safe(
                filtered.get("filtered_dcma_metrics", [])
            ),
            all_tasks_for_search=[
                {"uid": t.uid, "name": t.name or f"Task {t.uid}"}
                for t in schedule.tasks
                if not t.summary
            ],
        )

    @app.route("/export/<string:fmt>")
    def export(fmt: str):
        analysis_id = session.get("analysis_id")
        if not analysis_id:
            flash("No analysis to export.", "error")
            return redirect(url_for("index"))
        results = _load_analysis(cfg.UPLOAD_FOLDER, analysis_id)
        if results is None:
            flash("Analysis artifacts were purged. Please re-upload.", "error")
            return redirect(url_for("index"))

        ai_narrative = results.get("ai_narrative")
        analyst_name = results.get("analyst_name")

        try:
            if fmt == "docx":
                data = generate_docx_report(
                    results, ai_narrative=ai_narrative, analyst_name=analyst_name
                )
                return send_file(
                    io.BytesIO(data),
                    mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    as_attachment=True,
                    download_name="schedule_forensics_report.docx",
                )
            if fmt == "xlsx":
                data = generate_xlsx_export(results)
                return send_file(
                    io.BytesIO(data),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    as_attachment=True,
                    download_name="schedule_forensics_data.xlsx",
                )
            if fmt == "pdf":
                data = generate_pdf_report(
                    results, ai_narrative=ai_narrative, analyst_name=analyst_name
                )
                return send_file(
                    io.BytesIO(data),
                    mimetype="application/pdf",
                    as_attachment=True,
                    download_name="schedule_forensics_report.pdf",
                )
        except Exception as exc:
            app.logger.error("Export failed: %s", exc)
            flash(f"Export failed: {exc}", "error")
            return redirect(url_for("analysis_page"))

        flash(f"Unsupported export format: {fmt}", "error")
        return redirect(url_for("analysis_page"))

    @app.route("/settings", methods=["GET", "POST"])
    def settings_page():
        # Probe Ollama status for the UI indicator
        ollama_up = OllamaClient(url=cfg.OLLAMA_URL, model=cfg.OLLAMA_MODEL).is_available()
        claude_up = ClaudeClient(api_key=cfg.ANTHROPIC_API_KEY).is_available()

        if request.method == "POST":
            # Settings changes are process-ephemeral in Phase 4. A real
            # deployment would persist to a local .env / secret store.
            flash(
                "Phase 4 note: settings are read from environment variables and "
                "cannot be persisted from the UI yet. Set env vars and restart.",
                "info",
            )
            return redirect(url_for("settings_page"))

        return render_template(
            "settings.html",
            ollama_up=ollama_up,
            claude_up=claude_up,
            cfg_snapshot=cfg.as_dict(),
        )

    # ------------------------------------------------------------------ #
    # Error handlers
    # ------------------------------------------------------------------ #

    @app.errorhandler(413)
    def too_large(_exc):
        flash(
            f"File exceeds the {cfg.MAX_FILE_SIZE // (1024 * 1024)} MB upload limit.",
            "error",
        )
        return redirect(url_for("index")), 302

    @app.errorhandler(404)
    def not_found(_exc):
        return render_template("base.html"), 404

    @app.errorhandler(500)
    def server_error(exc):
        app.logger.error("Server error: %s", exc)
        flash("Unexpected server error. Check the console log.", "error")
        return redirect(url_for("index")), 302

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
