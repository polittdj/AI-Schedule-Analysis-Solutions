"""Status-date windowing predicate tests (Block 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.engine.windowing import is_legitimate_actual
from app.models.task import Task


def _task(
    unique_id: int = 1,
    *,
    name: str = "T",
    finish: datetime | None = None,
) -> Task:
    return Task(unique_id=unique_id, task_id=unique_id, name=name, finish=finish)


STATUS_A = datetime(2026, 3, 1, 16, 0, tzinfo=UTC)
STATUS_B = datetime(2026, 3, 31, 16, 0, tzinfo=UTC)


# -----------------------------------------------------------------------
# AC #2 skill-example fixture
# -----------------------------------------------------------------------


def test_ac2_skill_example_period_a_finish_le_status_b_is_legitimate() -> None:
    # BUILD-PLAN §5 M9 AC #2 worked example:
    # Period A finish = 2026-03-15, Period B status_date = 2026-03-31
    # → is_legitimate_actual = True.
    a_task = _task(finish=datetime(2026, 3, 15, 17, 0, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(
        a_task, b_task, STATUS_A, datetime(2026, 3, 31, 16, 0, tzinfo=UTC)
    )


# -----------------------------------------------------------------------
# Core predicate cases
# -----------------------------------------------------------------------


def test_period_a_finish_before_status_b_is_legitimate() -> None:
    a_task = _task(finish=datetime(2026, 3, 14, 16, 0, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, STATUS_B) is True


def test_period_a_finish_equal_to_status_b_is_legitimate() -> None:
    # Predicate is ≤, not <.
    a_task = _task(finish=STATUS_B)
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, STATUS_B) is True


def test_period_a_finish_after_status_b_is_not_legitimate() -> None:
    a_task = _task(finish=datetime(2026, 4, 15, 16, 0, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, STATUS_B) is False


def test_period_a_finish_before_status_a_still_legitimate() -> None:
    # Task already completed in Period A. Per the skill predicate
    # (Period A finish ≤ Period B status_date), this still qualifies
    # as legitimate — it was completed inside the cumulative window
    # A-status → B-status. M11 is the layer that further distinguishes
    # retro-statusing edits vs. tampering on already-completed tasks
    # (DECM 06A504a/b); the skill §3.2 predicate as written does not
    # exclude this case.
    a_task = _task(finish=datetime(2026, 2, 15, 16, 0, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, STATUS_B) is True


# -----------------------------------------------------------------------
# Structural change cases
# -----------------------------------------------------------------------


def test_task_added_in_b_is_not_legitimate() -> None:
    assert is_legitimate_actual(None, _task(), STATUS_A, STATUS_B) is False


def test_task_deleted_from_a_is_not_legitimate() -> None:
    assert is_legitimate_actual(_task(), None, STATUS_A, STATUS_B) is False


def test_both_missing_is_not_legitimate() -> None:
    assert is_legitimate_actual(None, None, STATUS_A, STATUS_B) is False


# -----------------------------------------------------------------------
# Status-date absence
# -----------------------------------------------------------------------


def test_period_a_status_date_none_is_not_legitimate() -> None:
    a_task = _task(finish=datetime(2026, 3, 15, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, None, STATUS_B) is False


def test_period_b_status_date_none_is_not_legitimate() -> None:
    a_task = _task(finish=datetime(2026, 3, 15, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, None) is False


def test_both_status_dates_none_is_not_legitimate() -> None:
    a_task = _task(finish=datetime(2026, 3, 15, tzinfo=UTC))
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, None, None) is False


# -----------------------------------------------------------------------
# Period A finish missing
# -----------------------------------------------------------------------


def test_period_a_task_no_finish_is_not_legitimate() -> None:
    a_task = _task(finish=None)
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, STATUS_B) is False


# -----------------------------------------------------------------------
# Tz-aware discipline
# -----------------------------------------------------------------------


def test_tz_aware_comparison_across_timezones() -> None:
    # UTC+0 finish and UTC+0 status date, but instantiated via a
    # different tz object: the predicate must resolve the comparison
    # via tz-aware semantics, not raise.
    tz_plus2 = timezone(timedelta(hours=2))
    a_task = _task(finish=datetime(2026, 3, 31, 18, 0, tzinfo=tz_plus2))
    # That is 2026-03-31 16:00 UTC — equal to STATUS_B.
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, STATUS_B) is True


def test_tz_aware_status_dates_on_mixed_offsets_honor_absolute_time() -> None:
    tz_minus5 = timezone(timedelta(hours=-5))
    status_b_local = datetime(2026, 3, 31, 11, 0, tzinfo=tz_minus5)  # == 16:00 UTC
    a_task = _task(finish=datetime(2026, 3, 31, 17, 0, tzinfo=UTC))
    # 17:00 UTC > status_b_local == 16:00 UTC, so NOT legitimate.
    b_task = _task()
    assert is_legitimate_actual(a_task, b_task, STATUS_A, status_b_local) is False
