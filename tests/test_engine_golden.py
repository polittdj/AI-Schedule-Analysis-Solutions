"""Golden hand-calculable CPM test (BUILD-PLAN §5 M4 AC6).

A 5-task FS chain on the Standard calendar (8h/day, Mon-Fri) anchored
at 2026-04-20 08:00 UTC (a Monday). Every ES/EF/LS/LF/TS is derived
by hand in the arithmetic block below; the test asserts the engine's
output byte-for-byte.

Calendar convention: a 1-working-day task starting Mon 08:00 finishes
at Tue 08:00 (the E12 boundary-roll convention — Mon 16:00 and
Tue 08:00 denote the same working-time instant; the engine reports
the next-window-start canonical form). Durations below are all 480
minutes (1 working day).

Hand arithmetic
===============

Tasks: A(480), B(480), C(480), D(480), E(480), FS chain A → B → C → D → E.

Forward pass (ES / EF)::

    A: ES = Mon 2026-04-20 08:00    EF = ES + 1wd = Tue 04-21 08:00
    B: ES = Tue 04-21 08:00          EF = Wed 04-22 08:00
    C: ES = Wed 04-22 08:00          EF = Thu 04-23 08:00
    D: ES = Thu 04-23 08:00          EF = Fri 04-24 08:00
    E: ES = Fri 04-24 08:00          EF = Mon 04-27 08:00
       (Fri + 1wd crosses the weekend → E12.)

Project finish = E's EF = Mon 04-27 08:00.

Backward pass (anchor on project finish; no override):

    E: LF = Mon 04-27 08:00          LS = Fri 04-24 08:00
    D: LF = Fri 04-24 08:00          LS = Thu 04-23 08:00
    C: LF = Thu 04-23 08:00          LS = Wed 04-22 08:00
    B: LF = Wed 04-22 08:00          LS = Tue 04-21 08:00
    A: LF = Tue 04-21 08:00          LS = Mon 04-20 08:00

Total slack (TS = LS - ES in working minutes):

    All five tasks: TS = 0 → every task is on the critical path.

Near-critical (default 10wd threshold): nobody qualifies because
TS = 0 → already critical; bucket is exclusive (E19 classification).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.engine import compute_cpm, critical_path_chains
from app.engine.duration import minutes_to_working_days
from app.models.calendar import Calendar
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _task(uid: int) -> Task:
    return Task(unique_id=uid, task_id=uid, name=f"T{uid}", duration_minutes=480)


def _rel(p: int, s: int) -> Relation:
    return Relation(predecessor_unique_id=p, successor_unique_id=s)


def _schedule() -> Schedule:
    return Schedule(
        project_calendar_hours_per_day=8.0,
        name="golden",
        project_start=ANCHOR,
        tasks=[_task(i) for i in (1, 2, 3, 4, 5)],
        relations=[_rel(1, 2), _rel(2, 3), _rel(3, 4), _rel(4, 5)],
        calendars=[Calendar(name="Standard")],
    )


def test_golden_forward_pass_dates_byte_for_byte() -> None:
    result = compute_cpm(_schedule())

    expected = {
        1: (datetime(2026, 4, 20, 8, tzinfo=UTC),
            datetime(2026, 4, 21, 8, tzinfo=UTC)),
        2: (datetime(2026, 4, 21, 8, tzinfo=UTC),
            datetime(2026, 4, 22, 8, tzinfo=UTC)),
        3: (datetime(2026, 4, 22, 8, tzinfo=UTC),
            datetime(2026, 4, 23, 8, tzinfo=UTC)),
        4: (datetime(2026, 4, 23, 8, tzinfo=UTC),
            datetime(2026, 4, 24, 8, tzinfo=UTC)),
        5: (datetime(2026, 4, 24, 8, tzinfo=UTC),
            datetime(2026, 4, 27, 8, tzinfo=UTC)),
    }
    for uid, (es, ef) in expected.items():
        r = result.tasks[uid]
        assert r.early_start == es, f"T{uid} ES"
        assert r.early_finish == ef, f"T{uid} EF"


def test_golden_backward_pass_dates_byte_for_byte() -> None:
    result = compute_cpm(_schedule())
    expected = {
        1: (datetime(2026, 4, 20, 8, tzinfo=UTC),
            datetime(2026, 4, 21, 8, tzinfo=UTC)),
        2: (datetime(2026, 4, 21, 8, tzinfo=UTC),
            datetime(2026, 4, 22, 8, tzinfo=UTC)),
        3: (datetime(2026, 4, 22, 8, tzinfo=UTC),
            datetime(2026, 4, 23, 8, tzinfo=UTC)),
        4: (datetime(2026, 4, 23, 8, tzinfo=UTC),
            datetime(2026, 4, 24, 8, tzinfo=UTC)),
        5: (datetime(2026, 4, 24, 8, tzinfo=UTC),
            datetime(2026, 4, 27, 8, tzinfo=UTC)),
    }
    for uid, (ls, lf) in expected.items():
        r = result.tasks[uid]
        assert r.late_start == ls, f"T{uid} LS"
        assert r.late_finish == lf, f"T{uid} LF"


def test_golden_total_slack_zero_for_all_tasks() -> None:
    result = compute_cpm(_schedule())
    for uid in (1, 2, 3, 4, 5):
        assert result.tasks[uid].total_slack_minutes == 0, f"T{uid}"
        assert minutes_to_working_days(result.tasks[uid].total_slack_minutes) == 0


def test_golden_critical_path_is_the_full_chain() -> None:
    s = _schedule()
    result = compute_cpm(s)
    chains = critical_path_chains(s, result)
    assert chains == [[1, 2, 3, 4, 5]]


def test_golden_project_finish_matches_task_e_ef() -> None:
    result = compute_cpm(_schedule())
    assert result.project_finish == datetime(2026, 4, 27, 8, tzinfo=UTC)


def test_golden_near_critical_empty_when_everything_critical() -> None:
    result = compute_cpm(_schedule())
    assert result.near_critical_uids == frozenset()
