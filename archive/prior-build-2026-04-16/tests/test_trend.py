"""Unit tests for the multi-schedule trend analysis module.

Covers:
* auto-ordering schedules by ``project_info.status_date``
* ``chain_compare`` produces N-1 pairwise comparisons
* ``compute_trend_analysis`` captures completion-date drift across ≥3 updates
* float trend classifier flips to "eroding" when min float falls over time
* top-level shape checks (data_points length, baseline-reset detection)
* integration: a trend upload through the Flask test client
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import List, Optional

import pytest

from app.engine.comparator import chain_compare
from app.engine.trend_analysis import (
    TrendAnalysisResults,
    compute_trend_analysis,
)
from app.parser.schema import (
    ProjectInfo,
    Relationship,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Synthetic schedule builder — no JVM, no MPP fixtures
# --------------------------------------------------------------------------- #


def _make_schedule(
    label: str,
    status_date: datetime,
    finish_date: datetime,
    float_days: float = 5.0,
    percent_complete: float = 25.0,
    duration: float = 10.0,
    baseline_finish: Optional[datetime] = None,
    baseline_duration: Optional[float] = None,
) -> ScheduleData:
    """Build a minimal 2-task schedule that can be run through the engine."""
    baseline_finish = baseline_finish or finish_date
    baseline_duration = baseline_duration or duration

    tasks = [
        TaskData(
            uid=1,
            id=1,
            name="Task A",
            duration=duration,
            baseline_duration=baseline_duration,
            start=datetime(2026, 1, 1),
            finish=datetime(2026, 1, 1) + timedelta(days=duration),
            baseline_start=datetime(2026, 1, 1),
            baseline_finish=baseline_finish,
            percent_complete=percent_complete,
            total_slack=float_days,
            critical=float_days <= 0.01,
            predecessors=[],
            successors=[2],
        ),
        TaskData(
            uid=2,
            id=2,
            name="Task B",
            duration=duration,
            baseline_duration=baseline_duration,
            start=datetime(2026, 1, 1) + timedelta(days=duration),
            finish=finish_date,
            baseline_start=datetime(2026, 1, 1) + timedelta(days=duration),
            baseline_finish=baseline_finish,
            percent_complete=0.0,
            total_slack=float_days,
            critical=float_days <= 0.01,
            predecessors=[1],
            successors=[],
        ),
    ]
    return ScheduleData(
        project_info=ProjectInfo(
            name=label,
            status_date=status_date,
            start_date=datetime(2026, 1, 1),
            finish_date=finish_date,
        ),
        tasks=tasks,
        relationships=[Relationship(predecessor_uid=1, successor_uid=2)],
    )


# --------------------------------------------------------------------------- #
# Auto-ordering
# --------------------------------------------------------------------------- #


class TestAutoOrdering:
    def test_three_files_sort_by_status_date(self):
        """Shuffled schedules should sort chronologically by status_date."""
        s_mar = _make_schedule("S-Mar", datetime(2026, 3, 1), datetime(2026, 6, 1))
        s_jan = _make_schedule("S-Jan", datetime(2026, 1, 1), datetime(2026, 5, 1))
        s_feb = _make_schedule("S-Feb", datetime(2026, 2, 1), datetime(2026, 5, 15))
        shuffled = [s_mar, s_jan, s_feb]

        ordered = sorted(
            shuffled, key=lambda s: s.project_info.status_date or datetime.max
        )
        labels = [s.project_info.name for s in ordered]
        assert labels == ["S-Jan", "S-Feb", "S-Mar"]

    def test_auto_sort_detects_reorder(self):
        """The main.py sort detects a needed reorder via index comparison."""
        s1 = _make_schedule("s1", datetime(2026, 3, 1), datetime(2026, 6, 1))
        s2 = _make_schedule("s2", datetime(2026, 1, 1), datetime(2026, 5, 1))
        schedules = [s1, s2]

        indexed = list(enumerate(schedules))
        indexed.sort(
            key=lambda pair: pair[1].project_info.status_date or datetime.max
        )
        new_order = [pair[0] for pair in indexed]
        assert new_order != list(range(len(schedules)))

    def test_auto_sort_no_change_for_already_ordered(self):
        s1 = _make_schedule("s1", datetime(2026, 1, 1), datetime(2026, 5, 1))
        s2 = _make_schedule("s2", datetime(2026, 2, 1), datetime(2026, 5, 15))
        s3 = _make_schedule("s3", datetime(2026, 3, 1), datetime(2026, 6, 1))
        schedules = [s1, s2, s3]

        indexed = list(enumerate(schedules))
        indexed.sort(
            key=lambda pair: pair[1].project_info.status_date or datetime.max
        )
        new_order = [pair[0] for pair in indexed]
        assert new_order == list(range(len(schedules)))


# --------------------------------------------------------------------------- #
# chain_compare
# --------------------------------------------------------------------------- #


class TestChainCompare:
    def test_n_minus_one_pairwise_comparisons(self):
        schedules = [
            _make_schedule(
                f"S{i}", datetime(2026, i + 1, 1), datetime(2026, 6, 1)
            )
            for i in range(4)
        ]
        results = chain_compare(schedules)
        assert len(results) == 3  # N-1 where N=4

    def test_chain_compare_handles_two_schedules(self):
        s1 = _make_schedule("s1", datetime(2026, 1, 1), datetime(2026, 6, 1))
        s2 = _make_schedule("s2", datetime(2026, 2, 1), datetime(2026, 6, 1))
        results = chain_compare([s1, s2])
        assert len(results) == 1

    def test_chain_compare_empty_list(self):
        assert chain_compare([]) == []

    def test_chain_compare_single_schedule(self):
        s1 = _make_schedule("s1", datetime(2026, 1, 1), datetime(2026, 6, 1))
        assert chain_compare([s1]) == []


# --------------------------------------------------------------------------- #
# compute_trend_analysis
# --------------------------------------------------------------------------- #


class TestTrendAnalysis:
    def test_rejects_fewer_than_two_schedules(self):
        s = _make_schedule("s", datetime(2026, 1, 1), datetime(2026, 6, 1))
        with pytest.raises(ValueError):
            compute_trend_analysis([s])

    def test_data_points_length_matches_input(self):
        schedules = [
            _make_schedule(
                f"S{i}", datetime(2026, i + 1, 1), datetime(2026, 6, 1)
            )
            for i in range(5)
        ]
        result = compute_trend_analysis(schedules)
        assert isinstance(result, TrendAnalysisResults)
        assert result.update_count == 5
        assert len(result.data_points) == 5

    def test_completion_drift_captured(self):
        """Project finish moves 29 days later → drift == 29."""
        s1 = _make_schedule("S1", datetime(2026, 1, 1), datetime(2026, 6, 1))
        s2 = _make_schedule("S2", datetime(2026, 2, 1), datetime(2026, 6, 15))
        s3 = _make_schedule("S3", datetime(2026, 3, 1), datetime(2026, 6, 30))
        result = compute_trend_analysis([s1, s2, s3])
        assert result.completion_date_drift_days == pytest.approx(29.0)

    def test_completion_drift_pulled_in(self):
        """Project finish moves earlier → negative drift."""
        s1 = _make_schedule("S1", datetime(2026, 1, 1), datetime(2026, 7, 1))
        s2 = _make_schedule("S2", datetime(2026, 2, 1), datetime(2026, 6, 1))
        result = compute_trend_analysis([s1, s2])
        assert result.completion_date_drift_days == pytest.approx(-30.0)

    def test_float_trend_eroding_over_three_points(self):
        """Min float 10 → 5 → 0 must classify as eroding."""
        s1 = _make_schedule(
            "S1", datetime(2026, 1, 1), datetime(2026, 6, 1), float_days=10.0
        )
        s2 = _make_schedule(
            "S2", datetime(2026, 2, 1), datetime(2026, 6, 1), float_days=5.0
        )
        s3 = _make_schedule(
            "S3", datetime(2026, 3, 1), datetime(2026, 6, 1), float_days=0.0
        )
        result = compute_trend_analysis([s1, s2, s3])
        assert result.float_trend == "eroding"

    def test_float_trend_recovering(self):
        s1 = _make_schedule(
            "S1", datetime(2026, 1, 1), datetime(2026, 6, 1), float_days=0.0
        )
        s2 = _make_schedule(
            "S2", datetime(2026, 2, 1), datetime(2026, 6, 1), float_days=5.0
        )
        s3 = _make_schedule(
            "S3", datetime(2026, 3, 1), datetime(2026, 6, 1), float_days=10.0
        )
        result = compute_trend_analysis([s1, s2, s3])
        assert result.float_trend == "recovering"

    def test_float_trend_stable(self):
        s1 = _make_schedule(
            "S1", datetime(2026, 1, 1), datetime(2026, 6, 1), float_days=5.0
        )
        s2 = _make_schedule(
            "S2", datetime(2026, 2, 1), datetime(2026, 6, 1), float_days=5.0
        )
        s3 = _make_schedule(
            "S3", datetime(2026, 3, 1), datetime(2026, 6, 1), float_days=5.0
        )
        result = compute_trend_analysis([s1, s2, s3])
        assert result.float_trend == "stable"

    def test_data_point_fields_populated(self):
        schedules = [
            _make_schedule(
                f"S{i}",
                datetime(2026, i + 1, 1),
                datetime(2026, 6, 1),
                percent_complete=10.0 * (i + 1),
            )
            for i in range(3)
        ]
        result = compute_trend_analysis(schedules)
        first = result.data_points[0]
        assert first.update_label == "Update 1"
        assert first.update_index == 0
        assert first.manipulation_score is None  # nothing to compare first update to
        # Subsequent updates must have a manipulation score computed.
        for dp in result.data_points[1:]:
            assert dp.manipulation_score is not None

    def test_baseline_reset_detected(self):
        """Moving the baseline finish between updates should register a reset."""
        s1 = _make_schedule(
            "S1",
            datetime(2026, 1, 1),
            datetime(2026, 6, 1),
            baseline_finish=datetime(2026, 6, 1),
        )
        s2 = _make_schedule(
            "S2",
            datetime(2026, 2, 1),
            datetime(2026, 6, 1),
            baseline_finish=datetime(2026, 6, 20),  # moved 19 days — tasks 1 AND 2
        )
        s3 = _make_schedule(
            "S3",
            datetime(2026, 3, 1),
            datetime(2026, 6, 1),
            baseline_finish=datetime(2026, 6, 20),
        )
        result = compute_trend_analysis([s1, s2, s3])
        # One reset event between S1 and S2 (update_index=1 = "Update 2")
        reset_labels = [ev.update_label for ev in result.baseline_resets]
        assert "Update 2" in reset_labels

    def test_narrative_is_nonempty(self):
        schedules = [
            _make_schedule(
                f"S{i}", datetime(2026, i + 1, 1), datetime(2026, 6, 1)
            )
            for i in range(3)
        ]
        result = compute_trend_analysis(schedules)
        assert isinstance(result.narrative, str)
        assert len(result.narrative) > 20


# --------------------------------------------------------------------------- #
# Integration: upload 3 files through Flask and verify trend tab
# --------------------------------------------------------------------------- #


class TestTrendUploadFlow:
    @pytest.fixture
    def app_and_client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
        monkeypatch.setenv("SECRET_KEY", "trend-test-key")

        import app.parser.mpp_reader  # ensure module is importable

        # Build three schedules with different status dates; the fake
        # parser returns a different one per filename.
        s_late = _make_schedule(
            "Late",
            datetime(2026, 3, 1),
            datetime(2026, 6, 20),
            float_days=0.0,
        )
        s_mid = _make_schedule(
            "Mid",
            datetime(2026, 2, 1),
            datetime(2026, 6, 10),
            float_days=5.0,
        )
        s_early = _make_schedule(
            "Early",
            datetime(2026, 1, 1),
            datetime(2026, 6, 1),
            float_days=10.0,
        )
        by_filename = {
            "u1.mpp": s_late,
            "u2.mpp": s_mid,
            "u3.mpp": s_early,
        }

        def _fake_parse(path):
            for name, sched in by_filename.items():
                if name in path:
                    return sched
            raise FileNotFoundError(path)

        monkeypatch.setattr("app.parser.mpp_reader.parse_mpp", _fake_parse)

        from app.config import load_config
        from app.main import create_app

        app = create_app(load_config())
        app.config["TESTING"] = True
        return app, app.test_client()

    def test_trend_upload_auto_sorts_and_renders(self, app_and_client):
        app, client = app_and_client
        resp = client.post(
            "/analyze",
            data={
                "mode": "trend",
                "auto_sort": "on",
                "schedule_files": [
                    (io.BytesIO(b"fake"), "u1.mpp"),  # Late (should end up last)
                    (io.BytesIO(b"fake"), "u2.mpp"),  # Mid
                    (io.BytesIO(b"fake"), "u3.mpp"),  # Early (should be first)
                ],
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # The reorder flash message must be present.
        assert b"automatically reordered based on status dates" in resp.data
        # Trend tab button should exist.
        assert b'data-tab="trend"' in resp.data
        # Trend summary should reference 3 updates.
        assert b"3 updates" in resp.data

    def test_comparative_auto_swap(self, app_and_client):
        """Two files in the wrong order should auto-swap and flash."""
        app, client = app_and_client
        resp = client.post(
            "/analyze",
            data={
                "mode": "trend",  # unified multi-file path
                "auto_sort": "on",
                "schedule_files": [
                    (io.BytesIO(b"fake"), "u1.mpp"),  # Late
                    (io.BytesIO(b"fake"), "u3.mpp"),  # Early
                ],
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"automatically reordered based on status dates" in resp.data
