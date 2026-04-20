"""Tests for the High-Float NASA SMH overlay rule (Milestone 8
Block 3).

Exercises :func:`apply_schedule_margin_exclusion`: denominator /
numerator accounting, ratio and severity recomputation against
``MetricOptions`` (not hardcoded), exclusion-record emission, the
all-margin zero-denominator case, and mutation-invariance of the
upstream :class:`~app.metrics.base.MetricResult`.

Authority — ``nasa-schedule-management §3`` (schedule margin is not
CPM total float); ``nasa-schedule-management §6`` and ``dcma-14-
point-assessment §8`` (overlay placement); BUILD-PLAN §5 M8 AC #1
(denominator = 7 after 3 margin tasks excluded from 10).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.result import CPMResult, TaskCPMResult
from app.metrics.base import (
    MetricResult,
    Severity,
    ThresholdConfig,
)
from app.metrics.high_float import run_high_float
from app.metrics.options import MetricOptions
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task
from app.overlay import (
    ExclusionRecord,
    MissingMetricResultError,
    OverlayResult,
    apply_schedule_margin_exclusion,
)

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)

# 44.01 WD in minutes (8 hours/day): 44.01 * 8 * 60 = 21124.8 →
# 21125 minutes in the existing high_float fixtures; keep the value
# stable across tests.
_JUST_OVER_44_WD_MIN = 21125


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _make_task(uid: int, *, is_schedule_margin: bool = False,
               name: str | None = None) -> Task:
    return Task(
        unique_id=uid,
        task_id=uid,
        name=name or f"T{uid}",
        duration_minutes=480,
        is_schedule_margin=is_schedule_margin,
    )


def _build_schedule(margin_uids: set[int], total: int = 10) -> Schedule:
    """Build a schedule with ``total`` incomplete non-summary non-LOE
    tasks, ``margin_uids`` marked as schedule margin."""
    tasks = [
        _make_task(i, is_schedule_margin=(i in margin_uids))
        for i in range(1, total + 1)
    ]
    return Schedule(
        name="margin_overlay_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def _cpm_with_tf(tf_by_uid: dict[int, int]) -> CPMResult:
    return CPMResult(
        tasks={
            uid: TaskCPMResult(
                unique_id=uid,
                total_slack_minutes=tf,
                on_critical_path=tf <= 0,
            )
            for uid, tf in tf_by_uid.items()
        }
    )


# --------------------------------------------------------------------
# AC #1 — 10 incomplete tasks, 3 schedule-margin, all 3 over threshold
# --------------------------------------------------------------------


def test_ac1_ten_tasks_three_margin_all_flagged() -> None:
    # UIDs 2, 5, 8 are schedule-margin and all three carry TF above
    # the High-Float threshold. Expected: original denominator=10,
    # adjusted denominator=7; tasks_excluded length=3.
    sched = _build_schedule(margin_uids={2, 5, 8})
    tf_map = {i: 0 for i in range(1, 11)}
    for uid in (2, 5, 8):
        tf_map[uid] = _JUST_OVER_44_WD_MIN
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)
    assert original.denominator == 10
    assert original.numerator == 3

    overlay = apply_schedule_margin_exclusion(original, sched)
    assert isinstance(overlay, OverlayResult)
    assert overlay.metric_id == "DCMA-6"
    assert overlay.adjusted_denominator == 7
    assert overlay.adjusted_numerator == 0
    assert overlay.adjusted_ratio == 0.0
    assert overlay.adjusted_severity is Severity.PASS
    assert len(overlay.tasks_excluded_from_denominator) == 3
    assert {e.unique_id for e in overlay.tasks_excluded_from_denominator} == {
        2, 5, 8
    }
    assert all(
        isinstance(e, ExclusionRecord)
        for e in overlay.tasks_excluded_from_denominator
    )
    # Exclusion reason carries the SMH §3 citation.
    for e in overlay.tasks_excluded_from_denominator:
        assert "is_schedule_margin" in e.exclusion_reason
        assert "§3" in e.exclusion_reason
    # Informational notes are empty for this rule (it is a
    # denominator correction, not a note emission).
    assert overlay.informational_notes == ()


# --------------------------------------------------------------------
# Zero schedule-margin tasks — overlay is a no-op
# --------------------------------------------------------------------


def test_zero_margin_tasks_adjusted_equals_original() -> None:
    sched = _build_schedule(margin_uids=set())
    tf_map = {i: 0 for i in range(1, 11)}
    tf_map[5] = _JUST_OVER_44_WD_MIN
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)
    overlay = apply_schedule_margin_exclusion(original, sched)

    assert overlay.adjusted_denominator == original.denominator
    assert overlay.adjusted_numerator == original.numerator
    assert overlay.adjusted_ratio == pytest.approx(original.computed_value)
    assert overlay.adjusted_severity is original.severity
    assert overlay.tasks_excluded_from_denominator == ()
    assert overlay.informational_notes == ()


# --------------------------------------------------------------------
# All tasks are schedule-margin — denominator collapses to zero
# --------------------------------------------------------------------


def test_all_tasks_schedule_margin_zero_denominator() -> None:
    sched = _build_schedule(margin_uids={i for i in range(1, 11)})
    tf_map = {i: _JUST_OVER_44_WD_MIN for i in range(1, 11)}
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)
    overlay = apply_schedule_margin_exclusion(original, sched)

    assert overlay.adjusted_denominator == 0
    assert overlay.adjusted_numerator == 0  # 10 - 10 = 0
    assert overlay.adjusted_ratio is None
    assert overlay.adjusted_severity is None
    assert len(overlay.tasks_excluded_from_denominator) == 10


# --------------------------------------------------------------------
# Margin tasks in denominator but NOT numerator — adjust denom only
# --------------------------------------------------------------------


def test_margin_in_denominator_not_numerator() -> None:
    # UIDs 2 and 5 are schedule-margin with TF = 0 (below threshold —
    # not offenders). UIDs 7 and 9 are non-margin with TF above the
    # threshold. Expected: adjusted numerator = original numerator
    # (unchanged, 2), adjusted denominator = 8 (10 - 2 margin).
    sched = _build_schedule(margin_uids={2, 5})
    tf_map = {i: 0 for i in range(1, 11)}
    tf_map[7] = _JUST_OVER_44_WD_MIN
    tf_map[9] = _JUST_OVER_44_WD_MIN
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)
    assert original.numerator == 2
    assert original.denominator == 10

    overlay = apply_schedule_margin_exclusion(original, sched)
    assert overlay.adjusted_numerator == 2
    assert overlay.adjusted_denominator == 8
    assert overlay.adjusted_ratio == pytest.approx(25.0)
    # 25% > 5% default threshold — FAIL.
    assert overlay.adjusted_severity is Severity.FAIL
    assert {e.unique_id for e in overlay.tasks_excluded_from_denominator} == {
        2, 5
    }


# --------------------------------------------------------------------
# Threshold consumption — reads from MetricOptions, not hardcoded
# --------------------------------------------------------------------


def test_threshold_read_from_metric_options_not_hardcoded() -> None:
    # With the default 5% threshold, 2/8 = 25% FAILS. With a
    # client-configured 30% threshold, the same ratio PASSES. The
    # overlay must honour whichever MetricOptions the caller passes.
    sched = _build_schedule(margin_uids={2, 5})
    tf_map = {i: 0 for i in range(1, 11)}
    tf_map[7] = _JUST_OVER_44_WD_MIN
    tf_map[9] = _JUST_OVER_44_WD_MIN
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)

    # Client-specific 30% acceptance threshold.
    overlay = apply_schedule_margin_exclusion(
        original, sched, options=MetricOptions(high_float_threshold_pct=30.0)
    )
    assert overlay.adjusted_severity is Severity.PASS


# --------------------------------------------------------------------
# Mutation invariance — original_result is the exact upstream instance
# --------------------------------------------------------------------


def test_original_result_reference_preserved() -> None:
    sched = _build_schedule(margin_uids={2, 5, 8})
    tf_map = {i: 0 for i in range(1, 11)}
    for uid in (2, 5, 8):
        tf_map[uid] = _JUST_OVER_44_WD_MIN
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)
    overlay = apply_schedule_margin_exclusion(original, sched)

    # original_result carries the exact upstream instance — not a
    # copy.
    assert overlay.original_result is original


def test_upstream_metric_result_unchanged_after_overlay() -> None:
    sched = _build_schedule(margin_uids={2, 5, 8})
    tf_map = {i: 0 for i in range(1, 11)}
    for uid in (2, 5, 8):
        tf_map[uid] = _JUST_OVER_44_WD_MIN
    cpm = _cpm_with_tf(tf_map)

    original = run_high_float(sched, cpm)
    # Snapshot every public field before the overlay call; dataclass
    # equality covers offenders (tuple of frozen Offender) and
    # threshold (frozen ThresholdConfig).
    before = (
        original.metric_id,
        original.metric_name,
        original.severity,
        original.numerator,
        original.denominator,
        original.offenders,
        original.computed_value,
        original.threshold,
        original.notes,
    )

    _ = apply_schedule_margin_exclusion(original, sched)

    after = (
        original.metric_id,
        original.metric_name,
        original.severity,
        original.numerator,
        original.denominator,
        original.offenders,
        original.computed_value,
        original.threshold,
        original.notes,
    )
    assert before == after


# --------------------------------------------------------------------
# MissingMetricResultError on None input
# --------------------------------------------------------------------


def test_missing_metric_result_raises() -> None:
    sched = _build_schedule(margin_uids=set())
    with pytest.raises(MissingMetricResultError) as ei:
        apply_schedule_margin_exclusion(None, sched)  # type: ignore[arg-type]
    assert ei.value.metric_id == "DCMA-6"
    assert ei.value.overlay_rule == "apply_schedule_margin_exclusion"


# --------------------------------------------------------------------
# Eligibility — a schedule_margin task that's also summary is dropped
# by DCMA §3 first, so it does NOT count toward the exclusion.
# --------------------------------------------------------------------


def test_summary_margin_task_not_double_counted() -> None:
    # UID 1 is summary AND is_schedule_margin=True. DCMA §3 drops it
    # from the eligible set first; the overlay does not double-count
    # by additionally removing it as "schedule margin."
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Summary margin",
            duration_minutes=480,
            is_summary=True,
            is_schedule_margin=True,
        ),
    ] + [
        _make_task(i, is_schedule_margin=(i in {3, 7}))
        for i in range(2, 11)
    ]
    sched = Schedule(
        name="summary_margin_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )
    cpm = _cpm_with_tf({i: 0 for i in range(1, 11)})

    original = run_high_float(sched, cpm)
    # Eligible: UIDs 2..10 (9 tasks); UID 1 summary-dropped.
    assert original.denominator == 9

    overlay = apply_schedule_margin_exclusion(original, sched)
    # 2 schedule-margin tasks (UIDs 3, 7) are in the eligible set;
    # denominator drops from 9 to 7.
    assert overlay.adjusted_denominator == 7
    assert {e.unique_id for e in overlay.tasks_excluded_from_denominator} == {
        3, 7
    }


# --------------------------------------------------------------------
# Returned type guarantees
# --------------------------------------------------------------------


def test_returned_value_is_overlay_result_frozen() -> None:
    sched = _build_schedule(margin_uids={2})
    cpm = _cpm_with_tf({i: 0 for i in range(1, 11)})

    original = run_high_float(sched, cpm)
    overlay = apply_schedule_margin_exclusion(original, sched)

    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        overlay.adjusted_numerator = 42  # type: ignore[misc]


# --------------------------------------------------------------------
# MetricResult-shaped regression: overlay echoes the upstream
# metric_id verbatim (so consumers key on the exact string).
# --------------------------------------------------------------------


def test_overlay_echoes_metric_id_verbatim() -> None:
    # Build a synthetic MetricResult whose metric_id is non-standard
    # (e.g. "DCMA-06") — the overlay should not rewrite it.
    threshold = ThresholdConfig(
        value=5.0,
        direction="<=",
        source_skill_section="dcma-14-point-assessment §4.6",
        source_decm_row="DECM sheet Metrics, Guideline 6 — High Float",
    )
    synth = MetricResult(
        metric_id="DCMA-06",
        metric_name="High Float",
        severity=Severity.PASS,
        threshold=threshold,
        numerator=0,
        denominator=5,
        offenders=(),
        computed_value=0.0,
    )
    sched = _build_schedule(margin_uids=set(), total=5)
    overlay = apply_schedule_margin_exclusion(synth, sched)
    assert overlay.metric_id == "DCMA-06"


# --------------------------------------------------------------------
# DCMA §3 eligibility — a schedule-margin task that is also LOE
# (via Task.is_loe flag) is dropped by §3 first, so it does NOT count
# toward the margin-exclusion set (same no-double-count guarantee as
# the summary case; covers the explicit is_loe branch in _is_loe and
# the exclude_loe branch in _is_dcma_eligible).
# --------------------------------------------------------------------


def test_is_loe_flag_margin_task_not_double_counted() -> None:
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="LOE margin",
            duration_minutes=480,
            is_loe=True,
            is_schedule_margin=True,
        ),
    ] + [
        _make_task(i, is_schedule_margin=(i in {3, 7}))
        for i in range(2, 11)
    ]
    sched = Schedule(
        name="loe_flag_margin_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )
    cpm = _cpm_with_tf({i: 0 for i in range(1, 11)})

    original = run_high_float(sched, cpm)
    # Eligible: UIDs 2..10 (9 tasks); UID 1 dropped as LOE by §3.
    assert original.denominator == 9

    overlay = apply_schedule_margin_exclusion(original, sched)
    # 2 schedule-margin tasks (UIDs 3, 7) survive §3 filtering;
    # UID 1 is not counted a second time as margin-excluded.
    assert overlay.adjusted_denominator == 7
    assert {e.unique_id for e in overlay.tasks_excluded_from_denominator} == {
        3, 7
    }


# --------------------------------------------------------------------
# DCMA §3 eligibility — LOE detection via MetricOptions.
# loe_name_patterns fallback. Task has is_loe=False but a name that
# matches an opt-in pattern; the overlay must apply the same
# name-pattern fallback the upstream metric does so the exclusion
# accounting lines up (covers the name-pattern branch in _is_loe).
# --------------------------------------------------------------------


def test_loe_name_pattern_margin_task_not_double_counted() -> None:
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Level of Effort support",
            duration_minutes=480,
            is_loe=False,
            is_schedule_margin=True,
        ),
    ] + [
        _make_task(i, is_schedule_margin=(i in {3, 7}))
        for i in range(2, 11)
    ]
    sched = Schedule(
        name="loe_pattern_margin_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )
    cpm = _cpm_with_tf({i: 0 for i in range(1, 11)})

    opts = MetricOptions(loe_name_patterns=("Level of Effort",))
    original = run_high_float(sched, cpm, options=opts)
    # Eligible: UIDs 2..10 (9 tasks); UID 1 dropped as LOE by §3
    # via the name-pattern fallback.
    assert original.denominator == 9

    overlay = apply_schedule_margin_exclusion(original, sched, options=opts)
    # UID 1 is not counted a second time as margin-excluded; only
    # UIDs 3 and 7 appear in the exclusion set.
    assert overlay.adjusted_denominator == 7
    assert {e.unique_id for e in overlay.tasks_excluded_from_denominator} == {
        3, 7
    }


# --------------------------------------------------------------------
# DCMA §3 eligibility — a 100%-complete schedule-margin task is
# dropped by §3 (exclude_completed) before the overlay sees it, so it
# does NOT count toward the margin-exclusion set (covers the
# exclude_completed branch in _is_dcma_eligible).
# --------------------------------------------------------------------


def test_completed_margin_task_not_double_counted() -> None:
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Completed margin",
            duration_minutes=480,
            percent_complete=100.0,
            is_schedule_margin=True,
        ),
    ] + [
        _make_task(i, is_schedule_margin=(i in {3, 7}))
        for i in range(2, 11)
    ]
    sched = Schedule(
        name="completed_margin_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )
    cpm = _cpm_with_tf({i: 0 for i in range(1, 11)})

    original = run_high_float(sched, cpm)
    # Eligible: UIDs 2..10 (9 tasks); UID 1 dropped as completed by §3.
    assert original.denominator == 9

    overlay = apply_schedule_margin_exclusion(original, sched)
    # UID 1 is not counted a second time; only UIDs 3 and 7 appear
    # in the exclusion set.
    assert overlay.adjusted_denominator == 7
    assert {e.unique_id for e in overlay.tasks_excluded_from_denominator} == {
        3, 7
    }
