"""Tests for the rolling-wave window cross-check overlay rule
(Milestone 8 Block 5).

Exercises :func:`apply_rolling_wave_window_check` against the
NASA SMH 6–12 month near-term window per
``nasa-schedule-management §4``: near-term rolling-wave tags emit
``ROLLING_WAVE_NEAR_TERM_WARNING``; far-term tags (> 12 months)
emit ``ROLLING_WAVE_OUT_OF_WINDOW``; in-band tags emit nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.metrics.high_duration import run_high_duration
from app.metrics.options import MetricOptions
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task
from app.overlay import (
    MissingMetricResultError,
    OverlayNoteKind,
    apply_rolling_wave_window_check,
)

STATUS = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _cal() -> Calendar:
    return Calendar(name="Standard")


def _task(uid: int, *, is_rolling_wave: bool, start: datetime | None,
          name: str | None = None, duration_minutes: int = 480) -> Task:
    return Task(
        unique_id=uid,
        task_id=uid,
        name=name or f"T{uid}",
        duration_minutes=duration_minutes,
        is_rolling_wave=is_rolling_wave,
        start=start,
    )


def _schedule_with(tasks: list[Task], *, status_date: datetime | None = STATUS,
                   project_start: datetime | None = STATUS) -> Schedule:
    return Schedule(
        project_calendar_hours_per_day=8.0,
        name="rolling_wave_fixture",
        status_date=status_date,
        project_start=project_start,
        tasks=tasks,
        relations=[],
        calendars=[_cal()],
    )


# --------------------------------------------------------------------
# Near-term warning — rolling-wave task inside 6 months
# --------------------------------------------------------------------


def test_near_term_rolling_wave_emits_warning() -> None:
    # 3 months into the future — inside the 6-month cutoff.
    near_date = STATUS + timedelta(days=90)
    tasks = [
        _task(10, is_rolling_wave=True, start=near_date, name="Near RW"),
        _task(20, is_rolling_wave=False, start=near_date),
    ]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert len(overlay.informational_notes) == 1
    note = overlay.informational_notes[0]
    assert note.note_kind is OverlayNoteKind.ROLLING_WAVE_NEAR_TERM_WARNING
    assert note.unique_id == 10
    assert note.task_name == "Near RW"
    assert "near-term" in note.detail.lower()
    assert "SMH §4" in note.detail


# --------------------------------------------------------------------
# In-band rolling-wave task (6-12 months) — no note
# --------------------------------------------------------------------


def test_in_band_rolling_wave_emits_no_note() -> None:
    # 9 months into the future — inside the 6-12 month band.
    in_band = STATUS + timedelta(days=275)
    tasks = [_task(10, is_rolling_wave=True, start=in_band)]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert overlay.informational_notes == ()


# --------------------------------------------------------------------
# Out-of-window — rolling-wave task beyond 12 months
# --------------------------------------------------------------------


def test_out_of_window_rolling_wave_emits_out_of_window() -> None:
    # 14 months into the future — beyond the 12-month cutoff.
    far = STATUS + timedelta(days=430)
    tasks = [_task(10, is_rolling_wave=True, start=far, name="Far RW")]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert len(overlay.informational_notes) == 1
    note = overlay.informational_notes[0]
    assert note.note_kind is OverlayNoteKind.ROLLING_WAVE_OUT_OF_WINDOW
    assert note.unique_id == 10
    assert "12-month" in note.detail
    assert "rolling-wave band" in note.detail


# --------------------------------------------------------------------
# Mixed cohort — one near, one in-band, one far
# --------------------------------------------------------------------


def test_mixed_rolling_wave_cohort() -> None:
    near = STATUS + timedelta(days=30)
    in_band = STATUS + timedelta(days=275)
    far = STATUS + timedelta(days=500)
    tasks = [
        _task(1, is_rolling_wave=True, start=near),
        _task(2, is_rolling_wave=True, start=in_band),
        _task(3, is_rolling_wave=True, start=far),
        _task(4, is_rolling_wave=False, start=near),  # non-RW; skipped
    ]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    kinds_by_uid = {
        n.unique_id: n.note_kind for n in overlay.informational_notes
    }
    assert kinds_by_uid == {
        1: OverlayNoteKind.ROLLING_WAVE_NEAR_TERM_WARNING,
        3: OverlayNoteKind.ROLLING_WAVE_OUT_OF_WINDOW,
    }
    # UID 2 (in-band) and UID 4 (non-RW) do not appear.
    assert 2 not in kinds_by_uid
    assert 4 not in kinds_by_uid


# --------------------------------------------------------------------
# No reference date — empty notes, no exception
# --------------------------------------------------------------------


def test_no_reference_date_returns_empty_notes() -> None:
    near = STATUS + timedelta(days=30)
    tasks = [_task(1, is_rolling_wave=True, start=near)]
    sched = _schedule_with(tasks, status_date=None, project_start=None)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert overlay.informational_notes == ()


# --------------------------------------------------------------------
# status_date preferred over project_start when both are present
# --------------------------------------------------------------------


def test_status_date_preferred_over_project_start() -> None:
    # project_start is a year earlier than status_date. A task 3
    # months past status_date should trigger NEAR_TERM_WARNING
    # relative to status_date (not project_start, which would put
    # the task 15 months out).
    project_start = STATUS - timedelta(days=365)
    task_start = STATUS + timedelta(days=90)  # 3 months past status
    tasks = [_task(1, is_rolling_wave=True, start=task_start)]
    sched = _schedule_with(
        tasks, status_date=STATUS, project_start=project_start
    )

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert len(overlay.informational_notes) == 1
    assert overlay.informational_notes[0].note_kind is (
        OverlayNoteKind.ROLLING_WAVE_NEAR_TERM_WARNING
    )


# --------------------------------------------------------------------
# project_start fallback when status_date is absent
# --------------------------------------------------------------------


def test_project_start_fallback_when_no_status_date() -> None:
    # With status_date=None, the overlay falls back to project_start.
    project_start = STATUS
    near = project_start + timedelta(days=30)
    tasks = [_task(1, is_rolling_wave=True, start=near)]
    sched = _schedule_with(
        tasks, status_date=None, project_start=project_start
    )

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert len(overlay.informational_notes) == 1


# --------------------------------------------------------------------
# Rolling-wave task with no forecast date — silently skipped
# --------------------------------------------------------------------


def test_rolling_wave_with_no_forecast_date_is_skipped() -> None:
    tasks = [_task(1, is_rolling_wave=True, start=None)]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert overlay.informational_notes == ()


# --------------------------------------------------------------------
# Mutation invariance
# --------------------------------------------------------------------


def test_original_result_preserved_after_rule() -> None:
    near = STATUS + timedelta(days=30)
    tasks = [_task(1, is_rolling_wave=True, start=near)]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    before = (
        original.numerator, original.denominator, original.severity,
        original.offenders, original.computed_value, original.threshold,
    )
    overlay = apply_rolling_wave_window_check(original, sched)
    after = (
        original.numerator, original.denominator, original.severity,
        original.offenders, original.computed_value, original.threshold,
    )
    assert before == after
    assert overlay.original_result is original


# --------------------------------------------------------------------
# MissingMetricResultError
# --------------------------------------------------------------------


def test_missing_metric_result_raises() -> None:
    sched = _schedule_with([_task(1, is_rolling_wave=False, start=STATUS)])
    with pytest.raises(MissingMetricResultError) as ei:
        apply_rolling_wave_window_check(None, sched)  # type: ignore[arg-type]
    assert ei.value.metric_id == "DCMA-8"
    assert ei.value.overlay_rule == "apply_rolling_wave_window_check"


# --------------------------------------------------------------------
# options passed through without effect
# --------------------------------------------------------------------


def test_options_accepted_for_signature_symmetry() -> None:
    near = STATUS + timedelta(days=30)
    tasks = [_task(1, is_rolling_wave=True, start=near)]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(
        original, sched, options=MetricOptions(high_duration_threshold_pct=7.0)
    )
    assert len(overlay.informational_notes) == 1


# --------------------------------------------------------------------
# early_start fallback when start is None
# --------------------------------------------------------------------


def test_early_start_fallback_when_start_missing() -> None:
    # Task has no .start but has .early_start — the rule uses that.
    near = STATUS + timedelta(days=30)
    task = Task(
        unique_id=1,
        task_id=1,
        name="T1",
        duration_minutes=480,
        is_rolling_wave=True,
        start=None,
        early_start=near,
    )
    sched = _schedule_with([task])

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert len(overlay.informational_notes) == 1
    assert overlay.informational_notes[0].note_kind is (
        OverlayNoteKind.ROLLING_WAVE_NEAR_TERM_WARNING
    )


# --------------------------------------------------------------------
# adjusted fields are None — note-emission rule
# --------------------------------------------------------------------


def test_adjusted_fields_all_none() -> None:
    near = STATUS + timedelta(days=30)
    tasks = [_task(1, is_rolling_wave=True, start=near)]
    sched = _schedule_with(tasks)

    original = run_high_duration(sched)
    overlay = apply_rolling_wave_window_check(original, sched)

    assert overlay.adjusted_numerator is None
    assert overlay.adjusted_denominator is None
    assert overlay.adjusted_ratio is None
    assert overlay.adjusted_severity is None
    assert overlay.tasks_excluded_from_denominator == ()
