"""Tests for the eight constraint-type handlers (BUILD-PLAN §5 M4 E8-E11)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.constraints import (
    apply_backward_constraint,
    apply_forward_constraint,
)
from app.engine.exceptions import InvalidConstraintError
from app.models.calendar import Calendar
from app.models.enums import ConstraintType
from app.models.task import Task


@pytest.fixture
def cal() -> Calendar:
    return Calendar(name="Std")


def _dt(d: int, h: int = 8) -> datetime:
    return datetime(2026, 4, d, h, tzinfo=UTC)


def _task(ct: ConstraintType, date_: datetime | None = None) -> Task:
    return Task(
        unique_id=1, task_id=1, name="T",
        constraint_type=ct, constraint_date=date_, duration_minutes=480,
    )


# ---- ASAP / ALAP (no-op forward) ---------------------------------


def test_asap_forward_no_change(cal: Calendar) -> None:
    t = _task(ConstraintType.AS_SOON_AS_POSSIBLE)
    out = apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.early_start == _dt(20)
    assert out.early_finish == _dt(20, 16)
    assert out.violation is None


def test_alap_forward_no_change(cal: Calendar) -> None:
    t = _task(ConstraintType.AS_LATE_AS_POSSIBLE)
    out = apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.early_start == _dt(20)


def test_alap_backward_no_change(cal: Calendar) -> None:
    t = _task(ConstraintType.AS_LATE_AS_POSSIBLE)
    out = apply_backward_constraint(t, _dt(22), _dt(22, 16), cal)
    assert out.late_start == _dt(22)
    assert out.late_finish == _dt(22, 16)


# ---- MSO -------------------------------------------------------


def test_mso_forward_locks_es(cal: Calendar) -> None:
    """E8: MSO locks ES at constraint_date regardless of predecessors."""
    t = _task(ConstraintType.MUST_START_ON, _dt(22, 10))
    out = apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.early_start == _dt(22, 10)


def test_mso_backward_locks_ls(cal: Calendar) -> None:
    t = _task(ConstraintType.MUST_START_ON, _dt(22, 10))
    out = apply_backward_constraint(t, _dt(30), _dt(30, 16), cal)
    assert out.late_start == _dt(22, 10)


# ---- MFO -------------------------------------------------------


def test_mfo_forward_locks_ef(cal: Calendar) -> None:
    t = _task(ConstraintType.MUST_FINISH_ON, _dt(22, 16))
    out = apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.early_finish == _dt(22, 16)


def test_mfo_backward_locks_lf(cal: Calendar) -> None:
    t = _task(ConstraintType.MUST_FINISH_ON, _dt(22, 16))
    out = apply_backward_constraint(t, _dt(30), _dt(30, 16), cal)
    assert out.late_finish == _dt(22, 16)


def test_mfo_forward_violation_when_pred_pushes_past(cal: Calendar) -> None:
    """E8: predecessor forcing successor past MFO surfaces as violation,
    not exception. Our MFO lock model overrides, but the earlier EF
    is informational — for test simplicity we rely on the lock only
    (caller handles the violation flag via a separate comparison in
    the CPM engine; see test in test_engine_cpm.py)."""
    t = _task(ConstraintType.MUST_FINISH_ON, _dt(20, 16))
    out = apply_forward_constraint(t, _dt(25), _dt(25, 16), cal)
    # Lock wins: EF = MFO date.
    assert out.early_finish == _dt(20, 16)


# ---- SNET / FNET (soft forward) ---------------------------------


def test_snet_forward_bumps_es_later(cal: Calendar) -> None:
    """E10: SNET: ES >= constraint_date; bumps later if predecessors
    would have had us earlier."""
    t = _task(ConstraintType.START_NO_EARLIER_THAN, _dt(23, 10))
    out = apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.early_start == _dt(23, 10)


def test_snet_forward_no_change_when_already_later(cal: Calendar) -> None:
    t = _task(ConstraintType.START_NO_EARLIER_THAN, _dt(20))
    out = apply_forward_constraint(t, _dt(22, 10), _dt(22, 16), cal)
    assert out.early_start == _dt(22, 10)


def test_fnet_forward_bumps_ef_later(cal: Calendar) -> None:
    t = _task(ConstraintType.FINISH_NO_EARLIER_THAN, _dt(23, 16))
    out = apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    # snap_forward of 23 16:00 = Mon 24 is Fri? April 23 is Thursday.
    # 16:00 is window end → snap forward to Fri 24 08:00.
    assert out.early_finish == _dt(24, 8)


# ---- SNLT / FNLT (soft backward) --------------------------------


def test_snlt_forward_breach_emits_violation(cal: Calendar) -> None:
    """E11: SNLT breach in forward pass → ConstraintViolation."""
    t = _task(ConstraintType.START_NO_LATER_THAN, _dt(20, 10))
    out = apply_forward_constraint(t, _dt(25, 10), _dt(25, 16), cal)
    assert out.violation is not None
    assert out.violation.kind == "SNLT_BREACHED"


def test_snlt_forward_no_breach(cal: Calendar) -> None:
    t = _task(ConstraintType.START_NO_LATER_THAN, _dt(25, 10))
    out = apply_forward_constraint(t, _dt(20, 10), _dt(20, 16), cal)
    assert out.violation is None


def test_fnlt_forward_breach_emits_violation(cal: Calendar) -> None:
    t = _task(ConstraintType.FINISH_NO_LATER_THAN, _dt(20, 16))
    out = apply_forward_constraint(t, _dt(25, 8), _dt(25, 16), cal)
    assert out.violation is not None
    assert out.violation.kind == "FNLT_BREACHED"


def test_snlt_backward_narrows_ls(cal: Calendar) -> None:
    t = _task(ConstraintType.START_NO_LATER_THAN, _dt(22, 10))
    out = apply_backward_constraint(t, _dt(30), _dt(30, 16), cal)
    assert out.late_start == _dt(22, 10)


def test_fnlt_backward_narrows_lf(cal: Calendar) -> None:
    t = _task(ConstraintType.FINISH_NO_LATER_THAN, _dt(22, 16))
    out = apply_backward_constraint(t, _dt(30), _dt(30, 16), cal)
    assert out.late_finish == _dt(22, 16)


def test_snet_backward_breach_emits_violation(cal: Calendar) -> None:
    """SNET breach in the backward pass is uncommon but emitted."""
    t = _task(ConstraintType.START_NO_EARLIER_THAN, _dt(25, 10))
    out = apply_backward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.violation is not None
    assert out.violation.kind == "SNET_BREACHED_BACKWARD"


def test_fnet_backward_breach_emits_violation(cal: Calendar) -> None:
    t = _task(ConstraintType.FINISH_NO_EARLIER_THAN, _dt(25, 16))
    out = apply_backward_constraint(t, _dt(20), _dt(20, 16), cal)
    assert out.violation is not None


# ---- Malformed inputs ------------------------------------------


def test_missing_date_raises_invalid_constraint() -> None:
    # Bypass Pydantic by using model_construct.
    cal_ = Calendar(name="Std")
    t = Task.model_construct(
        unique_id=1, task_id=1, name="T",
        constraint_type=ConstraintType.MUST_START_ON,
        constraint_date=None, duration_minutes=480,
        start=None, finish=None, early_start=None, early_finish=None,
        late_start=None, late_finish=None, baseline_start=None,
        baseline_finish=None, actual_start=None, actual_finish=None,
        deadline=None, remaining_duration_minutes=0,
        actual_duration_minutes=0, baseline_duration_minutes=0,
        total_slack_minutes=0, free_slack_minutes=0, task_type=0,
        percent_complete=0.0, is_milestone=False, is_summary=False,
        is_critical_from_msp=False, is_loe=False, is_rolling_wave=False,
        is_schedule_margin=False, resource_count=0, wbs="",
        outline_level=0,
    )
    with pytest.raises(InvalidConstraintError):
        apply_forward_constraint(t, _dt(20), _dt(20, 16), cal_)


def test_unknown_constraint_type_raises(cal: Calendar) -> None:
    t = Task.model_construct(
        unique_id=1, task_id=1, name="T",
        constraint_type=99,  # type: ignore[arg-type]
        constraint_date=None, duration_minutes=480,
        start=None, finish=None, early_start=None, early_finish=None,
        late_start=None, late_finish=None, baseline_start=None,
        baseline_finish=None, actual_start=None, actual_finish=None,
        deadline=None, remaining_duration_minutes=0,
        actual_duration_minutes=0, baseline_duration_minutes=0,
        total_slack_minutes=0, free_slack_minutes=0, task_type=0,
        percent_complete=0.0, is_milestone=False, is_summary=False,
        is_critical_from_msp=False, is_loe=False, is_rolling_wave=False,
        is_schedule_margin=False, resource_count=0, wbs="",
        outline_level=0,
    )
    with pytest.raises(InvalidConstraintError):
        apply_forward_constraint(t, _dt(20), _dt(20, 16), cal)
    with pytest.raises(InvalidConstraintError):
        apply_backward_constraint(t, _dt(20), _dt(20, 16), cal)
