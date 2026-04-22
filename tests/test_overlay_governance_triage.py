"""Tests for the governance-milestone constraint triage overlay rule
(Milestone 8 Block 4).

Exercises :func:`apply_governance_milestone_triage`: note emission
for DCMA Metric 5 offenders whose task name matches a NASA
governance-milestone pattern, non-emission for tasks whose names do
not match, mutation-invariance of the upstream Metric 5
:class:`~app.metrics.base.MetricResult`, and the M11-consumer
contract (structured note kind + unique_id + name + detail).

Authority — ``nasa-schedule-management §6``; ``nasa-program-project-
governance §§4, 5``; ``dcma-14-point-assessment §4.5``; BUILD-PLAN
§5 M8 AC #2 (CDR Review task with MFO → triage note emitted; M11
reads the note and does not raise the constraint as manipulation).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.metrics.hard_constraints import run_hard_constraints
from app.metrics.options import MetricOptions
from app.models.calendar import Calendar
from app.models.enums import ConstraintType
from app.models.schedule import Schedule
from app.models.task import Task
from app.overlay import (
    MissingMetricResultError,
    OverlayNoteKind,
    OverlayResult,
    apply_governance_milestone_triage,
)

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _make_task(
    uid: int,
    name: str,
    *,
    constraint_type: ConstraintType = ConstraintType.AS_SOON_AS_POSSIBLE,
    constraint_date: datetime | None = None,
) -> Task:
    return Task(
        unique_id=uid,
        task_id=uid,
        name=name,
        duration_minutes=480,
        constraint_type=constraint_type,
        constraint_date=constraint_date,
    )


# --------------------------------------------------------------------
# AC #2 — CDR Review with MFO produces a governance-triage note
# --------------------------------------------------------------------


def test_ac2_cdr_review_with_mfo_emits_triage_note() -> None:
    tasks = [
        _make_task(
            100,
            "CDR Review",
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        # filler non-governance, non-constrained tasks so the
        # Metric 5 denominator is sensible.
        *(_make_task(i, f"Ordinary task {i}") for i in range(1, 20)),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="governance_triage_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )

    original = run_hard_constraints(sched)
    # UID 100 is the only offender.
    assert original.numerator == 1
    assert any(o.unique_id == 100 for o in original.offenders)

    overlay = apply_governance_milestone_triage(original, sched)
    assert isinstance(overlay, OverlayResult)
    assert overlay.metric_id == original.metric_id

    # Exactly one governance-triage note, pointing at UID 100.
    assert len(overlay.informational_notes) == 1
    note = overlay.informational_notes[0]
    assert note.note_kind is OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE
    assert note.unique_id == 100
    assert note.task_name == "CDR Review"
    # Detail carries the constraint label, the matched acronym, the
    # task name, and a skill-section citation the narrative layer
    # can render verbatim.
    assert "MUST_FINISH_ON" in note.detail
    assert "CDR" in note.detail
    assert "SMH §6" in note.detail

    # Rule is note-emission only — no adjusted fields, no exclusions.
    assert overlay.adjusted_numerator is None
    assert overlay.adjusted_denominator is None
    assert overlay.adjusted_ratio is None
    assert overlay.adjusted_severity is None
    assert overlay.tasks_excluded_from_denominator == ()


# --------------------------------------------------------------------
# Non-governance offender does NOT emit a triage note
# --------------------------------------------------------------------


def test_non_governance_constrained_task_does_not_emit_note() -> None:
    tasks = [
        _make_task(
            1,
            "Procurement Pin",  # no governance acronym in the name
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        *(_make_task(i, f"T{i}") for i in range(2, 12)),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="no_governance_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )

    original = run_hard_constraints(sched)
    overlay = apply_governance_milestone_triage(original, sched)

    # No governance-milestone match → no triage note.
    assert overlay.informational_notes == ()


# --------------------------------------------------------------------
# Multiple governance offenders → one note per match
# --------------------------------------------------------------------


def test_multiple_governance_offenders_emit_one_note_each() -> None:
    tasks = [
        _make_task(
            10, "CDR Review",
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        _make_task(
            20, "KDP-C approval",
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=ANCHOR,
        ),
        _make_task(
            30, "Preliminary Design Review (PDR)",
            constraint_type=ConstraintType.FINISH_NO_LATER_THAN,
            constraint_date=ANCHOR,
        ),
        *(_make_task(i, f"T{i}") for i in range(1, 10)),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="multi_governance_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )

    original = run_hard_constraints(sched)
    overlay = apply_governance_milestone_triage(original, sched)

    assert len(overlay.informational_notes) == 3
    note_uids = {n.unique_id for n in overlay.informational_notes}
    assert note_uids == {10, 20, 30}
    # Every note carries the GOVERNANCE_MILESTONE_TRIAGE kind.
    assert all(
        n.note_kind is OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE
        for n in overlay.informational_notes
    )


# --------------------------------------------------------------------
# Mixed offender list — only governance-named ones get notes
# --------------------------------------------------------------------


def test_mixed_offenders_filter_by_name_match() -> None:
    tasks = [
        _make_task(
            10, "CDR Review",
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        _make_task(
            20, "Pin launch date",  # non-governance offender
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        *(_make_task(i, f"T{i}") for i in range(1, 10)),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="mixed_fixture",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )

    original = run_hard_constraints(sched)
    assert original.numerator == 2

    overlay = apply_governance_milestone_triage(original, sched)
    assert len(overlay.informational_notes) == 1
    assert overlay.informational_notes[0].unique_id == 10


# --------------------------------------------------------------------
# Mutation invariance — original_result is untouched
# --------------------------------------------------------------------


def test_original_result_preserved_after_triage() -> None:
    tasks = [
        _make_task(
            10, "CDR Review",
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        *(_make_task(i, f"T{i}") for i in range(1, 10)),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="mutation_check",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )

    original = run_hard_constraints(sched)
    before = (
        original.numerator,
        original.denominator,
        original.severity,
        original.offenders,
        original.computed_value,
        original.threshold,
    )
    overlay = apply_governance_milestone_triage(original, sched)
    after = (
        original.numerator,
        original.denominator,
        original.severity,
        original.offenders,
        original.computed_value,
        original.threshold,
    )
    assert before == after
    # original_result is the exact upstream instance.
    assert overlay.original_result is original


# --------------------------------------------------------------------
# MissingMetricResultError on None input
# --------------------------------------------------------------------


def test_missing_metric_result_raises() -> None:
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="empty",
        project_start=ANCHOR,
        tasks=[_make_task(1, "T1")],
        relations=[],
        calendars=[_std_cal()],
    )
    with pytest.raises(MissingMetricResultError) as ei:
        apply_governance_milestone_triage(None, sched)  # type: ignore[arg-type]
    assert ei.value.metric_id == "DCMA-5"
    assert ei.value.overlay_rule == "apply_governance_milestone_triage"


# --------------------------------------------------------------------
# options parameter is accepted for signature symmetry
# --------------------------------------------------------------------


def test_accepts_metric_options_without_using_them() -> None:
    tasks = [
        _make_task(
            10, "CDR Review",
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=ANCHOR,
        ),
        *(_make_task(i, f"T{i}") for i in range(1, 10)),
    ]
    sched = Schedule(
        project_calendar_hours_per_day=8.0,
        name="options_symmetry",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )

    original = run_hard_constraints(sched)
    # Custom threshold override — rule signature symmetry; no
    # observable effect because the rule is note-emission only.
    overlay = apply_governance_milestone_triage(
        original, sched,
        options=MetricOptions(hard_constraints_threshold_pct=7.0),
    )
    assert len(overlay.informational_notes) == 1
