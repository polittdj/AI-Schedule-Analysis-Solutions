"""Unit tests for ``app.metrics.baseline`` plumbing (M7 Block 1).

These helpers are consumed by Metric 11 (Missed Tasks), Metric 13
(CPLI), and Metric 14 (BEI). Every test is synthetic per
``cui-compliance-constraints §2e``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine.result import CPMResult, TaskCPMResult
from app.metrics.baseline import (
    BaselineComparison,
    baseline_critical_path_length_minutes,
    baseline_slip_minutes,
    has_baseline,
    has_baseline_coverage,
    tasks_with_baseline_finish_by,
)
from app.models.calendar import Calendar
from app.models.schedule import Schedule
from app.models.task import Task

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _task(
    uid: int,
    *,
    baseline_start: datetime | None = None,
    baseline_finish: datetime | None = None,
    baseline_duration: int = 0,
    finish: datetime | None = None,
    actual_finish: datetime | None = None,
    is_milestone: bool = False,
    is_summary: bool = False,
    name: str | None = None,
) -> Task:
    return Task(
        unique_id=uid,
        task_id=uid,
        name=name or f"T{uid}",
        duration_minutes=480,
        baseline_start=baseline_start,
        baseline_finish=baseline_finish,
        baseline_duration_minutes=baseline_duration,
        finish=finish,
        actual_finish=actual_finish,
        is_milestone=is_milestone,
        is_summary=is_summary,
    )


# ---------------------------------------------------------------------------
# has_baseline
# ---------------------------------------------------------------------------


class TestHasBaseline:
    def test_true_when_baseline_finish_populated(self) -> None:
        t = _task(1, baseline_finish=ANCHOR)
        assert has_baseline(t) is True

    def test_false_when_baseline_finish_missing(self) -> None:
        t = _task(1, baseline_finish=None)
        assert has_baseline(t) is False

    def test_false_when_only_baseline_start_populated(self) -> None:
        # baseline_start alone is not enough — baseline_finish is the
        # anchor M11/M14 compare against status_date.
        t = _task(1, baseline_start=ANCHOR, baseline_finish=None)
        assert has_baseline(t) is False


# ---------------------------------------------------------------------------
# baseline_slip_minutes
# ---------------------------------------------------------------------------


class TestBaselineSlipMinutes:
    def test_positive_slip_when_current_later_than_baseline(self) -> None:
        baseline = ANCHOR
        current = ANCHOR + timedelta(days=2)
        t = _task(1, baseline_finish=baseline, finish=current)
        # 2 calendar days × 24 × 60 = 2880 minutes
        assert baseline_slip_minutes(t) == 2880

    def test_negative_slip_when_current_earlier_than_baseline(self) -> None:
        baseline = ANCHOR + timedelta(days=2)
        current = ANCHOR
        t = _task(1, baseline_finish=baseline, finish=current)
        assert baseline_slip_minutes(t) == -2880

    def test_zero_slip_when_current_matches_baseline(self) -> None:
        t = _task(1, baseline_finish=ANCHOR, finish=ANCHOR)
        assert baseline_slip_minutes(t) == 0

    def test_uses_actual_finish_when_present(self) -> None:
        # Actual finish takes precedence over forecast finish —
        # baseline_slip for a completed task is the realized slip,
        # not the forecast.
        baseline = ANCHOR
        forecast = ANCHOR + timedelta(days=4)
        actual = ANCHOR + timedelta(days=1)
        t = _task(
            1,
            baseline_finish=baseline,
            finish=forecast,
            actual_finish=actual,
        )
        assert baseline_slip_minutes(t) == 1440  # 1 day

    def test_none_when_no_baseline(self) -> None:
        t = _task(1, baseline_finish=None, finish=ANCHOR)
        assert baseline_slip_minutes(t) is None

    def test_none_when_no_current_or_actual_finish(self) -> None:
        t = _task(1, baseline_finish=ANCHOR)
        assert baseline_slip_minutes(t) is None

    def test_hand_calculated_slip_matches_across_calendars(self) -> None:
        # Sanity check: regardless of the schedule's calendar, slip is
        # calendar minutes (documented Phase 1 behaviour).
        baseline = ANCHOR
        current = ANCHOR + timedelta(hours=30)  # 1 day 6 hours
        t = _task(1, baseline_finish=baseline, finish=current)
        assert baseline_slip_minutes(t) == 30 * 60


# ---------------------------------------------------------------------------
# tasks_with_baseline_finish_by
# ---------------------------------------------------------------------------


class TestTasksWithBaselineFinishBy:
    def test_filters_to_tasks_at_or_before_cutoff(self) -> None:
        cutoff = ANCHOR + timedelta(days=10)
        t_on = _task(1, baseline_finish=ANCHOR + timedelta(days=5))
        t_at = _task(2, baseline_finish=cutoff)
        t_after = _task(3, baseline_finish=ANCHOR + timedelta(days=11))
        t_nobl = _task(4, baseline_finish=None)
        sched = Schedule(
            name="test",
            project_start=ANCHOR,
            tasks=[t_on, t_at, t_after, t_nobl],
            calendars=[_std_cal()],
        )
        result = tasks_with_baseline_finish_by(sched, cutoff)
        uids = {t.unique_id for t in result}
        assert uids == {1, 2}

    def test_empty_schedule_returns_empty_list(self) -> None:
        sched = Schedule(
            name="empty", project_start=ANCHOR, calendars=[_std_cal()]
        )
        assert tasks_with_baseline_finish_by(sched, ANCHOR) == []

    def test_none_baseline_tasks_excluded(self) -> None:
        t_nobl = _task(1, baseline_finish=None)
        sched = Schedule(
            name="nobl",
            project_start=ANCHOR,
            tasks=[t_nobl],
            calendars=[_std_cal()],
        )
        assert (
            tasks_with_baseline_finish_by(sched, ANCHOR + timedelta(days=1))
            == []
        )


# ---------------------------------------------------------------------------
# has_baseline_coverage
# ---------------------------------------------------------------------------


class TestHasBaselineCoverage:
    def test_true_when_every_task_baselined(self) -> None:
        tasks = [
            _task(i, baseline_finish=ANCHOR + timedelta(days=i))
            for i in range(1, 4)
        ]
        sched = Schedule(
            name="covered",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        assert has_baseline_coverage(sched) is True

    def test_false_when_one_task_missing_baseline(self) -> None:
        tasks = [
            _task(1, baseline_finish=ANCHOR + timedelta(days=1)),
            _task(2, baseline_finish=None),
            _task(3, baseline_finish=ANCHOR + timedelta(days=3)),
        ]
        sched = Schedule(
            name="partial",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        assert has_baseline_coverage(sched) is False

    def test_milestones_exempt_from_coverage_requirement(self) -> None:
        tasks = [
            _task(
                100,
                baseline_finish=None,
                is_milestone=True,
                name="Start",
            ),
            _task(1, baseline_finish=ANCHOR + timedelta(days=1)),
            _task(
                200,
                baseline_finish=None,
                is_milestone=True,
                name="Finish",
            ),
        ]
        sched = Schedule(
            name="milestones_exempt",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        assert has_baseline_coverage(sched) is True

    def test_summary_tasks_exempt_from_coverage_requirement(self) -> None:
        tasks = [
            _task(1, baseline_finish=None, is_summary=True, name="Phase"),
            _task(2, baseline_finish=ANCHOR + timedelta(days=2)),
        ]
        sched = Schedule(
            name="summary_exempt",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        assert has_baseline_coverage(sched) is True

    def test_empty_schedule_has_vacuous_coverage(self) -> None:
        sched = Schedule(
            name="empty", project_start=ANCHOR, calendars=[_std_cal()]
        )
        assert has_baseline_coverage(sched) is True


# ---------------------------------------------------------------------------
# baseline_critical_path_length_minutes
# ---------------------------------------------------------------------------


class TestBaselineCriticalPathLengthMinutes:
    def test_span_is_max_finish_minus_min_start(self) -> None:
        # Three critical-path tasks with baselines that span 10 days.
        tasks = [
            _task(
                1,
                baseline_start=ANCHOR,
                baseline_finish=ANCHOR + timedelta(days=3),
            ),
            _task(
                2,
                baseline_start=ANCHOR + timedelta(days=3),
                baseline_finish=ANCHOR + timedelta(days=6),
            ),
            _task(
                3,
                baseline_start=ANCHOR + timedelta(days=6),
                baseline_finish=ANCHOR + timedelta(days=10),
            ),
        ]
        sched = Schedule(
            name="cpl",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        cpm = CPMResult(
            tasks={
                uid: TaskCPMResult(unique_id=uid, total_slack_minutes=0)
                for uid in (1, 2, 3)
            },
            critical_path_uids=frozenset({1, 2, 3}),
        )
        minutes = baseline_critical_path_length_minutes(sched, cpm)
        assert minutes == 10 * 24 * 60

    def test_none_when_no_critical_path_uids(self) -> None:
        sched = Schedule(
            name="empty_cp", project_start=ANCHOR, calendars=[_std_cal()]
        )
        cpm = CPMResult(tasks={}, critical_path_uids=frozenset())
        assert baseline_critical_path_length_minutes(sched, cpm) is None

    def test_none_when_critical_task_lacks_baseline(self) -> None:
        tasks = [
            _task(
                1,
                baseline_start=ANCHOR,
                baseline_finish=ANCHOR + timedelta(days=2),
            ),
            _task(2, baseline_start=None, baseline_finish=None),
        ]
        sched = Schedule(
            name="no_bl_on_cp",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        cpm = CPMResult(
            tasks={
                1: TaskCPMResult(unique_id=1, total_slack_minutes=0),
                2: TaskCPMResult(unique_id=2, total_slack_minutes=0),
            },
            critical_path_uids=frozenset({1, 2}),
        )
        assert baseline_critical_path_length_minutes(sched, cpm) is None

    def test_none_when_span_is_non_positive(self) -> None:
        # Pathological: baseline_finish < baseline_start on the only
        # critical task — reject with None, don't paper over it.
        tasks = [
            _task(
                1,
                baseline_start=ANCHOR + timedelta(days=5),
                baseline_finish=ANCHOR + timedelta(days=3),
            )
        ]
        sched = Schedule(
            name="negative",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        cpm = CPMResult(
            tasks={1: TaskCPMResult(unique_id=1, total_slack_minutes=0)},
            critical_path_uids=frozenset({1}),
        )
        assert baseline_critical_path_length_minutes(sched, cpm) is None


# ---------------------------------------------------------------------------
# BaselineComparison snapshot
# ---------------------------------------------------------------------------


class TestBaselineComparison:
    def test_from_schedule_captures_every_task(self) -> None:
        tasks = [
            _task(1, baseline_finish=ANCHOR + timedelta(days=1)),
            _task(2, baseline_finish=None),
        ]
        sched = Schedule(
            name="cmp",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        snap = BaselineComparison.from_schedule(sched)
        assert set(snap.baselines.keys()) == {1, 2}
        assert snap.has(1) is True
        assert snap.has(2) is False

    def test_snapshot_is_immutable(self) -> None:
        tasks = [_task(1, baseline_finish=ANCHOR + timedelta(days=1))]
        sched = Schedule(
            name="imm",
            project_start=ANCHOR,
            tasks=tasks,
            calendars=[_std_cal()],
        )
        snap = BaselineComparison.from_schedule(sched)
        # MappingProxyType raises TypeError on mutation attempts.
        import pytest

        with pytest.raises(TypeError):
            snap.baselines[99] = (ANCHOR, ANCHOR, 0)  # type: ignore[index]
