"""End-to-end integration tests.

These tests exercise the Flask stack without starting the JVM by
monkey-patching ``app.parser.mpp_reader.parse_mpp`` to return a
pre-built synthetic schedule. Doing so lets us cover the whole
upload → engine → render → export pipeline in under a second while
keeping the tests deterministic and CI-friendly.

Coverage
--------
* GET / returns the upload form
* Direct engine pipeline runs without Flask (guards the forensic
  core against import-order regressions)
* POST /analyze with a single file renders the analysis dashboard
* POST /analyze with two files activates the comparative view with
  Slippage/Manipulation/Float tabs
* /export/docx|xlsx|pdf return downloadable files with correct
  MIME types and magic bytes
* /settings GET + POST
* Missing-file error path flashes and redirects
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List, Optional

import pytest

from app.engine.comparator import compare_schedules
from app.engine.cpm import compute_cpm
from app.engine.dcma import compute_dcma
from app.engine.delay_analysis import analyze_delays
from app.engine.earned_value import compute_earned_value
from app.engine.float_analysis import analyze_float
from app.engine.manipulation import detect_manipulations
from app.parser.schema import (
    ProjectInfo,
    Relationship,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Synthetic schedule factory
# --------------------------------------------------------------------------- #


def _make_task(
    uid: int,
    name: str,
    duration: Optional[float] = None,
    start: Optional[datetime] = None,
    finish: Optional[datetime] = None,
    baseline_start: Optional[datetime] = None,
    baseline_finish: Optional[datetime] = None,
    baseline_duration: Optional[float] = None,
    percent_complete: Optional[float] = 0.0,
    total_slack: Optional[float] = None,
    critical: bool = False,
    predecessors: Optional[List[int]] = None,
    successors: Optional[List[int]] = None,
    wbs: Optional[str] = None,
    notes: Optional[str] = None,
) -> TaskData:
    return TaskData(
        uid=uid,
        id=uid,
        name=name,
        wbs=wbs,
        duration=duration,
        start=start,
        finish=finish,
        baseline_start=baseline_start,
        baseline_finish=baseline_finish,
        baseline_duration=baseline_duration,
        percent_complete=percent_complete,
        total_slack=total_slack,
        critical=critical,
        predecessors=predecessors or [],
        successors=successors or [],
        notes=notes,
    )


def _build_prior_schedule() -> ScheduleData:
    tasks = [
        _make_task(
            1, "Mobilization",
            duration=5.0,
            start=datetime(2026, 1, 5), finish=datetime(2026, 1, 9),
            baseline_start=datetime(2026, 1, 5), baseline_finish=datetime(2026, 1, 9),
            baseline_duration=5.0, percent_complete=100.0, total_slack=0.0,
            critical=True, successors=[2], wbs="1.1",
        ),
        _make_task(
            2, "Foundation",
            duration=10.0,
            start=datetime(2026, 1, 12), finish=datetime(2026, 1, 23),
            baseline_start=datetime(2026, 1, 12), baseline_finish=datetime(2026, 1, 23),
            baseline_duration=10.0, percent_complete=50.0, total_slack=0.0,
            critical=True, predecessors=[1], successors=[3], wbs="1.2",
        ),
        _make_task(
            3, "Framing",
            duration=15.0,
            start=datetime(2026, 1, 26), finish=datetime(2026, 2, 13),
            baseline_start=datetime(2026, 1, 26), baseline_finish=datetime(2026, 2, 13),
            baseline_duration=15.0, percent_complete=0.0, total_slack=0.0,
            critical=True, predecessors=[2], wbs="1.3",
            notes="Weather-sensitive exterior framing.",
        ),
    ]
    return ScheduleData(
        project_info=ProjectInfo(
            name="Integration Test Project",
            status_date=datetime(2026, 1, 19),
            start_date=datetime(2026, 1, 5),
            finish_date=datetime(2026, 2, 13),
        ),
        tasks=tasks,
        relationships=[
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=2, successor_uid=3),
        ],
    )


def _build_later_schedule() -> ScheduleData:
    """Same project one update later — task 3 slipped 5 days (weather)."""
    prior = _build_prior_schedule()
    tasks = [t.model_copy(deep=True) for t in prior.tasks]
    tasks[2] = tasks[2].model_copy(
        update={
            "start": datetime(2026, 1, 31),
            "finish": datetime(2026, 2, 20),
            "notes": "Delayed 5 days by storm system; work suspended.",
        }
    )
    return ScheduleData(
        project_info=ProjectInfo(
            name="Integration Test Project",
            status_date=datetime(2026, 1, 26),
            start_date=datetime(2026, 1, 5),
            finish_date=datetime(2026, 2, 20),
        ),
        tasks=tasks,
        relationships=prior.relationships,
    )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_and_client(tmp_path, monkeypatch):
    """Build a fresh Flask app against a temp upload folder + fake parser."""
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "integration-test-key")

    # Replace parse_mpp so the /analyze handler never touches the JVM.
    import app.parser.mpp_reader  # ensure the module is imported first

    def _fake_parse(path: str) -> ScheduleData:
        if "prior" in path.lower():
            return _build_prior_schedule()
        return _build_later_schedule()

    monkeypatch.setattr("app.parser.mpp_reader.parse_mpp", _fake_parse)

    from app.config import load_config
    from app.main import create_app

    cfg = load_config()
    app = create_app(cfg)
    app.config["TESTING"] = True
    # Redirect feedback writes to the tmp dir so tests don't pollute
    # the in-tree app/knowledge_base/feedback.jsonl file.
    app.config["FEEDBACK_PATH"] = tmp_path / "feedback.jsonl"
    return app, app.test_client()


def _upload_single(client) -> None:
    """POST a single-file upload and follow redirect to /analysis."""
    client.post(
        "/analyze",
        data={
            "mode": "single",
            "prior_file": (io.BytesIO(b"fake mpp bytes"), "prior.mpp"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _upload_comparative(client) -> None:
    client.post(
        "/analyze",
        data={
            "mode": "comparative",
            "prior_file": (io.BytesIO(b"fake prior"), "prior.mpp"),
            "later_file": (io.BytesIO(b"fake later"), "later.mpp"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


# --------------------------------------------------------------------------- #
# Direct engine pipeline test (Flask-free)
# --------------------------------------------------------------------------- #


class TestEnginePipelineIntegration:
    def test_all_engines_run_in_sequence(self):
        """Every engine module must run cleanly on synthetic data."""
        prior = _build_prior_schedule()
        later = _build_later_schedule()

        cpm = compute_cpm(later)
        assert cpm.project_duration_days > 0

        dcma = compute_dcma(later, cpm)
        assert len(dcma.metrics) == 14

        comparison = compare_schedules(prior, later)
        assert comparison.completion_date_slip_days is not None

        manipulation = detect_manipulations(comparison, prior, later)
        assert isinstance(manipulation.overall_score, float)

        ev = compute_earned_value(later)
        assert ev.budget_at_completion > 0

        fa = analyze_float(comparison, prior, later)
        assert fa.trend in {"consuming", "recovering", "stable"}

        delay = analyze_delays(comparison, later)
        # Task 3 slipped 5 days on the critical path.
        assert delay.first_mover_uid == 3


# --------------------------------------------------------------------------- #
# Upload / analysis flow
# --------------------------------------------------------------------------- #


class TestUploadFlow:
    def test_index_page_loads(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Upload Schedule" in resp.data
        assert b"Single schedule" in resp.data
        assert b"Comparative" in resp.data

    def test_analyze_single_file_returns_dashboard(self, app_and_client):
        app, client = app_and_client
        resp = client.post(
            "/analyze",
            data={
                "mode": "single",
                "prior_file": (io.BytesIO(b"fake mpp bytes"), "prior.mpp"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Integration Test Project" in resp.data
        assert b"Executive Summary" in resp.data
        assert b"DCMA Scorecard" in resp.data
        # Single-schedule mode should NOT show comparison-only tabs.
        assert b"Manipulation</button>" not in resp.data

    def test_analyze_comparative_activates_comparison_tabs(self, app_and_client):
        app, client = app_and_client
        resp = client.post(
            "/analyze",
            data={
                "mode": "comparative",
                "prior_file": (io.BytesIO(b"fake"), "prior.mpp"),
                "later_file": (io.BytesIO(b"fake"), "later.mpp"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Comparative-only tabs should be present.
        assert b'data-tab="slippage"' in resp.data
        assert b'data-tab="manipulation"' in resp.data
        assert b'data-tab="float"' in resp.data

    def test_analyze_without_file_flashes_error(self, app_and_client):
        app, client = app_and_client
        resp = client.post(
            "/analyze",
            data={"mode": "single"},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should land back on index with an error flash. The refactor
        # for multi-file uploads changed the error message to a unified
        # "at least one" wording.
        assert b"Please upload at least one schedule file." in resp.data

    def test_analysis_page_without_session_redirects(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/analysis", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Upload Schedule" in resp.data  # landed back on index


# --------------------------------------------------------------------------- #
# Export endpoints
# --------------------------------------------------------------------------- #


class TestExportEndpoints:
    def test_docx_export_after_analyze(self, app_and_client):
        app, client = app_and_client
        _upload_comparative(client)
        resp = client.get("/export/docx")
        assert resp.status_code == 200
        assert (
            resp.mimetype
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert resp.data[:2] == b"PK"
        assert len(resp.data) > 3000

    def test_xlsx_export_after_analyze(self, app_and_client):
        app, client = app_and_client
        _upload_comparative(client)
        resp = client.get("/export/xlsx")
        assert resp.status_code == 200
        assert (
            resp.mimetype
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert resp.data[:2] == b"PK"
        assert len(resp.data) > 2000

    def test_pdf_export_after_analyze(self, app_and_client):
        app, client = app_and_client
        _upload_comparative(client)
        resp = client.get("/export/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF")
        assert b"%%EOF" in resp.data[-64:]

    def test_export_without_session_redirects(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/export/docx", follow_redirects=True)
        assert resp.status_code == 200
        assert b"No analysis to export." in resp.data

    def test_unknown_format_flashes(self, app_and_client):
        app, client = app_and_client
        _upload_single(client)
        resp = client.get("/export/csv", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Unsupported export format" in resp.data


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


class TestSettingsPage:
    def test_settings_get_returns_page(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert b"AI Backend" in resp.data
        assert b"Ollama" in resp.data

    def test_settings_post_redirects_with_flash(self, app_and_client):
        app, client = app_and_client
        resp = client.post("/settings", data={}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"settings are read from environment variables" in resp.data

    def test_settings_shows_mode_badge(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/settings")
        # Local mode is the default — either "Local" or "online/offline" should appear
        body = resp.data
        assert b"Ollama:" in body
        assert b"Claude API key:" in body


# --------------------------------------------------------------------------- #
# Feedback endpoint
# --------------------------------------------------------------------------- #


class TestFeedbackEndpoint:
    """`/api/feedback` appends rated AI analyses to feedback.jsonl."""

    def test_valid_post_appends_jsonl_line(self, app_and_client):
        import json as _json

        app, client = app_and_client
        resp = client.post(
            "/api/feedback",
            json={
                "rating": 5,
                "comment": "Caught the SPI=0.71 callout perfectly.",
                "analysis_hash": "abc123",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

        feedback_path = app.config["FEEDBACK_PATH"]
        assert feedback_path.is_file()
        lines = feedback_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = _json.loads(lines[0])
        assert entry["rating"] == 5
        assert entry["comment"] == "Caught the SPI=0.71 callout perfectly."
        assert entry["analysis_hash"] == "abc123"
        assert "timestamp" in entry
        # Timestamp must be ISO-8601 with explicit Z suffix so the
        # prompt_builder's parser can read it back.
        assert entry["timestamp"].endswith("Z")

    def test_two_posts_append_two_lines(self, app_and_client):
        app, client = app_and_client
        client.post("/api/feedback", json={"rating": 4, "analysis_hash": "h1"})
        client.post("/api/feedback", json={"rating": 5, "analysis_hash": "h2"})
        feedback_path = app.config["FEEDBACK_PATH"]
        lines = feedback_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_missing_rating_returns_400(self, app_and_client):
        app, client = app_and_client
        resp = client.post("/api/feedback", json={"comment": "no rating"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["status"] == "error"
        assert "integer" in body["message"]

    def test_rating_out_of_range_returns_400(self, app_and_client):
        app, client = app_and_client
        resp = client.post("/api/feedback", json={"rating": 7})
        assert resp.status_code == 400
        assert "between 1 and 5" in resp.get_json()["message"]

    def test_non_numeric_rating_returns_400(self, app_and_client):
        app, client = app_and_client
        resp = client.post("/api/feedback", json={"rating": "five"})
        assert resp.status_code == 400

    def test_creates_parent_directory(self, app_and_client, tmp_path):
        app, client = app_and_client
        nested = tmp_path / "deep" / "nested" / "feedback.jsonl"
        app.config["FEEDBACK_PATH"] = nested
        resp = client.post("/api/feedback", json={"rating": 4})
        assert resp.status_code == 200
        assert nested.is_file()

    def test_long_comment_is_truncated(self, app_and_client):
        import json as _json

        app, client = app_and_client
        long_comment = "x" * 5000
        resp = client.post(
            "/api/feedback",
            json={"rating": 4, "comment": long_comment, "analysis_hash": "h"},
        )
        assert resp.status_code == 200
        line = app.config["FEEDBACK_PATH"].read_text(encoding="utf-8").strip()
        entry = _json.loads(line)
        assert len(entry["comment"]) == 2000


# --------------------------------------------------------------------------- #
# Static asset sanity check (regression guard for the /static/lib paths)
# --------------------------------------------------------------------------- #


class TestStaticAssets:
    def test_css_is_served(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200
        assert b"app-shell" in resp.data

    def test_js_is_served(self, app_and_client):
        app, client = app_and_client
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200
        assert b"initUploadPage" in resp.data

    def test_lib_placeholders_are_served(self, app_and_client):
        app, client = app_and_client
        for name in ("chart.min.js", "tabulator.min.js"):
            resp = client.get(f"/static/lib/{name}")
            assert resp.status_code == 200, f"missing {name}"
