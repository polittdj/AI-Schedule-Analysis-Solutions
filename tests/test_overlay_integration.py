"""Integration test for the three NASA SMH overlay rules against a
single synthetic schedule (Milestone 8 Block 6).

Exercises :func:`apply_schedule_margin_exclusion`,
:func:`apply_governance_milestone_triage`, and
:func:`apply_rolling_wave_window_check` end-to-end on one fixture
that simultaneously triggers:

* the High-Float schedule-margin exclusion (3 margin tasks in the
  eligible denominator, all over the 44 WD threshold — BUILD-PLAN
  §5 M8 AC #1);
* the governance-milestone triage note (a "CDR Review" task with
  an MFO constraint — AC #2);
* the rolling-wave near-term warning (a rolling-wave task whose
  forecast start is inside the SMH 6-month window).

All three rules run independently; none mutates the others' upstream
:class:`~app.metrics.base.MetricResult`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine.result import CPMResult, TaskCPMResult
from app.metrics.hard_constraints import run_hard_constraints
from app.metrics.high_duration import run_high_duration
from app.metrics.high_float import run_high_float
from app.models.calendar import Calendar
from app.models.enums import ConstraintType
from app.models.schedule import Schedule
from app.models.task import Task
from app.overlay import (
    OverlayNoteKind,
    apply_governance_milestone_triage,
    apply_rolling_wave_window_check,
    apply_schedule_margin_exclusion,
)

STATUS = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _cal() -> Calendar:
    return Calendar(name="Standard")


def _combined_fixture() -> tuple[Schedule, CPMResult]:
    """Build one schedule that exercises all three overlay rules.

    Task inventory:

    * UIDs 1, 2, 3 — schedule-margin, each with TF just above the
      High-Float threshold (AC #1 denominator = 7 after exclusion).
    * UIDs 4, 5, 6, 7 — ordinary incomplete tasks, TF = 0 (do not
      flag High Float).
    * UID 8 — "CDR Review" with MUST_FINISH_ON constraint.
      Triggers the governance-milestone triage note (AC #2).
    * UID 9 — rolling-wave task with forecast start 30 days into
      the future (near-term, inside SMH 6-month window). Triggers
      ROLLING_WAVE_NEAR_TERM_WARNING.
    * UID 10 — ordinary incomplete filler.
    """
    tasks = [
        Task(
            unique_id=1, task_id=1, name="SM-01",
            duration_minutes=480, is_schedule_margin=True,
        ),
        Task(
            unique_id=2, task_id=2, name="SM-02",
            duration_minutes=480, is_schedule_margin=True,
        ),
        Task(
            unique_id=3, task_id=3, name="SM-03",
            duration_minutes=480, is_schedule_margin=True,
        ),
        Task(unique_id=4, task_id=4, name="T04", duration_minutes=480),
        Task(unique_id=5, task_id=5, name="T05", duration_minutes=480),
        Task(unique_id=6, task_id=6, name="T06", duration_minutes=480),
        Task(unique_id=7, task_id=7, name="T07", duration_minutes=480),
        Task(
            unique_id=8, task_id=8, name="CDR Review",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=STATUS + timedelta(days=180),
        ),
        Task(
            unique_id=9, task_id=9, name="Early RW placeholder",
            duration_minutes=480, is_rolling_wave=True,
            start=STATUS + timedelta(days=30),  # 1 month out
        ),
        Task(unique_id=10, task_id=10, name="T10", duration_minutes=480),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="m8_integration",
        status_date=STATUS,
        project_start=STATUS,
        tasks=tasks,
        relations=[],
        calendars=[_cal()],
    )
    # CPM: 44.01 WD in minutes is 21125; set that on the three
    # schedule-margin UIDs so they land in the High-Float numerator.
    tf_map = {i: 0 for i in range(1, 11)}
    for uid in (1, 2, 3):
        tf_map[uid] = 21125
    cpm = CPMResult(
        tasks={
            uid: TaskCPMResult(
                unique_id=uid,
                total_slack_minutes=tf,
                on_critical_path=tf <= 0,
            )
            for uid, tf in tf_map.items()
        }
    )
    return sched, cpm


def test_all_three_rules_on_combined_fixture() -> None:
    sched, cpm = _combined_fixture()

    # Upstream DCMA results.
    m5 = run_hard_constraints(sched)
    m6 = run_high_float(sched, cpm)
    m8 = run_high_duration(sched)

    # Snapshot the Schedule before any overlay call — the overlay
    # reads Schedule read-only, so status_date, project_start, and
    # every task field must be byte-equal after the three rules run.
    schedule_snapshot_before = sched.model_dump()

    # Rule 1 — schedule-margin exclusion (AC #1).
    m6_overlay = apply_schedule_margin_exclusion(m6, sched)
    assert m6.denominator == 10
    assert m6_overlay.adjusted_denominator == 7
    assert m6_overlay.adjusted_numerator == 0
    assert m6_overlay.adjusted_ratio == 0.0
    # 3 schedule-margin exclusions.
    assert {e.unique_id for e in m6_overlay.tasks_excluded_from_denominator} \
        == {1, 2, 3}

    # Rule 2 — governance-milestone triage (AC #2).
    m5_overlay = apply_governance_milestone_triage(m5, sched)
    assert any(
        n.note_kind is OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE
        and n.unique_id == 8
        for n in m5_overlay.informational_notes
    )

    # Rule 3 — rolling-wave near-term warning.
    m8_overlay = apply_rolling_wave_window_check(m8, sched)
    assert any(
        n.note_kind is OverlayNoteKind.ROLLING_WAVE_NEAR_TERM_WARNING
        and n.unique_id == 9
        for n in m8_overlay.informational_notes
    )

    # All three rules preserve the original_result identity —
    # consumers can rely on a stable upstream pointer.
    assert m6_overlay.original_result is m6
    assert m5_overlay.original_result is m5
    assert m8_overlay.original_result is m8

    # Schedule mutation-invariance: none of the three overlay rules
    # may edit status_date, project_start, or any task / relation
    # field on the source Schedule. Pydantic v2 model_dump() equality
    # catches every field-level mutation at the root.
    assert sched.model_dump() == schedule_snapshot_before, (
        "Overlay mutated Schedule; non-mutation contract broken"
    )


def test_rules_are_independent_no_cross_contamination() -> None:
    sched, cpm = _combined_fixture()

    m5 = run_hard_constraints(sched)
    m6 = run_high_float(sched, cpm)
    m8 = run_high_duration(sched)

    # Call rules in different orders; results are deterministic.
    order_a_m6 = apply_schedule_margin_exclusion(m6, sched)
    order_a_m5 = apply_governance_milestone_triage(m5, sched)
    order_a_m8 = apply_rolling_wave_window_check(m8, sched)

    order_b_m8 = apply_rolling_wave_window_check(m8, sched)
    order_b_m5 = apply_governance_milestone_triage(m5, sched)
    order_b_m6 = apply_schedule_margin_exclusion(m6, sched)

    # Each rule's output should equal regardless of call order —
    # frozen dataclasses with slots provide structural equality.
    assert order_a_m6 == order_b_m6
    assert order_a_m5 == order_b_m5
    assert order_a_m8 == order_b_m8
