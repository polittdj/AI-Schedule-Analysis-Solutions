"""Synthetic :class:`Schedule` builders for the M5 DCMA metric tests.

Every builder is hand-crafted from synthetic numbers
(``cui-compliance-constraints §2e`` fixture-data quarantine) and
returns a fully validated :class:`~app.models.schedule.Schedule`.

Builders cover the per-metric pass / warn / fail bands and the
shared edge cases listed in the M5 prompt §5 gotcha tables.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.engine.result import CPMResult, TaskCPMResult
from app.models.calendar import Calendar
from app.models.enums import ConstraintType, RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


# ---------------------------------------------------------------------------
# Logic (DCMA-1) fixtures
# ---------------------------------------------------------------------------


def empty_schedule() -> Schedule:
    """Schedule with zero tasks (L5)."""
    return Schedule(name="empty", project_start=ANCHOR, calendars=[_std_cal()])


def all_complete_schedule() -> Schedule:
    """Three FS-chained tasks all 100% complete (L6)."""
    tasks = [
        Task(
            unique_id=i,
            task_id=i,
            name=f"T{i}",
            duration_minutes=480,
            percent_complete=100.0,
        )
        for i in range(1, 4)
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    return Schedule(
        name="all_complete",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def logic_pass_schedule() -> Schedule:
    """10-task FS chain bracketed by start/finish milestones — every
    interior task has both a predecessor and a successor, so Missing
    Logic = 0/10 = 0% PASS."""
    tasks: list[Task] = [
        Task(
            unique_id=100,
            task_id=100,
            name="Start",
            duration_minutes=0,
            is_milestone=True,
        )
    ]
    for i in range(1, 11):
        tasks.append(Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480))
    tasks.append(
        Task(
            unique_id=200,
            task_id=200,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        )
    )
    relations: list[Relation] = [
        Relation(predecessor_unique_id=100, successor_unique_id=1)
    ]
    for i in range(1, 10):
        relations.append(
            Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        )
    relations.append(Relation(predecessor_unique_id=10, successor_unique_id=200))
    return Schedule(
        name="logic_pass",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def logic_golden_fail_schedule() -> Schedule:
    """Hand-calculable Metric-1 golden (A6).

    10 working tasks bracketed by start/finish milestones.
    Tasks 1, 3-10 sit on the chain; task 2 is detached (missing
    predecessor + missing successor); task 11 is an extra unconnected
    task (also missing both). Endpoints (start/finish milestones)
    excluded. Numerator = 2, denominator = 10 → 20% FAIL.
    """
    tasks: list[Task] = [
        Task(
            unique_id=100,
            task_id=100,
            name="Start",
            duration_minutes=0,
            is_milestone=True,
        )
    ]
    for i in range(1, 11):
        tasks.append(
            Task(
                unique_id=i,
                task_id=i,
                name=f"T{i}",
                duration_minutes=480,
            )
        )
    tasks.append(
        Task(
            unique_id=200,
            task_id=200,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        )
    )
    # T1 and T2 are deliberately detached (missing both pred and succ);
    # the chain runs Start → T3 → T4 → … → T10 → Finish.
    # Numerator = 2 (T1, T2); denominator = 10 (T1..T10) → 20% FAIL.
    relations: list[Relation] = [
        Relation(predecessor_unique_id=100, successor_unique_id=3),
    ]
    for i in range(3, 10):
        relations.append(
            Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        )
    relations.append(Relation(predecessor_unique_id=10, successor_unique_id=200))
    return Schedule(
        name="logic_golden_fail",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def logic_summary_loe_completed_schedule() -> Schedule:
    """A schedule where the only "missing logic" tasks are summary,
    LOE, and 100%-complete tasks. With default exclusions, the
    metric must report 0% PASS (L2/L3/L4).

    The eligible chain (T4 → T5) is bracketed by Start / Finish
    milestones so neither end of the chain flags as missing logic.
    """
    tasks = [
        Task(
            unique_id=100,
            task_id=100,
            name="Start",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(
            unique_id=1,
            task_id=1,
            name="Summary phase",
            duration_minutes=2400,
            is_summary=True,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="Project mgmt LOE",
            duration_minutes=2400,
            is_loe=True,
        ),
        Task(
            unique_id=3,
            task_id=3,
            name="Closed",
            duration_minutes=480,
            percent_complete=100.0,
        ),
        Task(unique_id=4, task_id=4, name="Linked", duration_minutes=480),
        Task(unique_id=5, task_id=5, name="LinkedSucc", duration_minutes=480),
        Task(
            unique_id=200,
            task_id=200,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=100, successor_unique_id=4),
        Relation(predecessor_unique_id=4, successor_unique_id=5),
        Relation(predecessor_unique_id=5, successor_unique_id=200),
    ]
    return Schedule(
        name="logic_summary_loe_completed",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def logic_loe_by_name_schedule() -> Schedule:
    """A schedule where one task is LOE by name only (no
    ``is_loe`` flag). Used to test
    :attr:`MetricOptions.loe_name_patterns` opt-in fallback. The
    eligible chain is bracketed by Start / Finish milestones."""
    tasks = [
        Task(
            unique_id=100,
            task_id=100,
            name="Start",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(
            unique_id=1,
            task_id=1,
            name="Project Management LOE",
            duration_minutes=480,
        ),
        Task(unique_id=2, task_id=2, name="Real Work A", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="Real Work B", duration_minutes=480),
        Task(
            unique_id=200,
            task_id=200,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=100, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=200),
    ]
    return Schedule(
        name="logic_loe_by_name",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# Leads (DCMA-2) fixtures
# ---------------------------------------------------------------------------


def leads_pass_schedule() -> Schedule:
    """5-task FS chain with no negative lags. PASS."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 6)
    ]
    relations = [
        Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        for i in range(1, 5)
    ]
    return Schedule(
        name="leads_pass",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def leads_golden_fail_schedule() -> Schedule:
    """Hand-calculable Metric-2 golden (A6).

    20-task FS chain → 19 relationships. Replace one link's lag
    with –480 min (one full working day lead). Numerator = 1,
    denominator = 19. Threshold is 0% — any lead fails.
    Computed value 1/19 ≈ 5.263% → FAIL with offender row.
    Adjusted: build a 21-task chain so we get exactly 20
    relationships; one is a lead.
    """
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 22)
    ]
    relations: list[Relation] = []
    for i in range(1, 21):
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                lag_minutes=(-480 if i == 5 else 0),
            )
        )
    return Schedule(
        name="leads_golden_fail",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def leads_on_completed_task_schedule() -> Schedule:
    """A lead whose successor is a 100%-complete task. Per LD4 the
    lead is still flagged — completion does not erase the historical
    lead.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="Done A",
             duration_minutes=480, percent_complete=100.0),
        Task(unique_id=2, task_id=2, name="Done B",
             duration_minutes=480, percent_complete=100.0),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            lag_minutes=-240,
        ),
    ]
    return Schedule(
        name="leads_on_completed",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# Lags (DCMA-3) fixtures
# ---------------------------------------------------------------------------


def lags_pass_schedule() -> Schedule:
    """20 relations, no positive lags → PASS."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 22)
    ]
    relations = [
        Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        for i in range(1, 21)
    ]
    return Schedule(
        name="lags_pass",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def lags_golden_fail_schedule() -> Schedule:
    """Hand-calculable Metric-3 golden (A6).

    21-task chain → 20 relationships. Two relations carry +1440
    min lag (3 working days). Numerator = 2, denominator = 20 →
    10% > 5% → FAIL. Two offenders listed.
    """
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 22)
    ]
    relations: list[Relation] = []
    for i in range(1, 21):
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                lag_minutes=(1440 if i in (3, 7) else 0),
            )
        )
    return Schedule(
        name="lags_golden_fail",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def lags_below_threshold_schedule() -> Schedule:
    """20 relations, 1 positive lag → 5% exactly → PASS at the
    boundary (`<=` semantics).
    """
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 22)
    ]
    relations: list[Relation] = []
    for i in range(1, 21):
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                lag_minutes=(960 if i == 10 else 0),
            )
        )
    return Schedule(
        name="lags_below_threshold",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def lags_with_leads_schedule() -> Schedule:
    """Mix of positive lag and negative lag (lead). The Lags
    denominator excludes leads — leads are M2's job — so 1 positive
    lag against 19 non-lead relations yields 1/19 ≈ 5.263% → FAIL.
    """
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 22)
    ]
    relations: list[Relation] = []
    for i in range(1, 21):
        if i == 5:
            lag = -480  # lead, excluded from Lags denominator
        elif i == 10:
            lag = 960  # positive lag, in numerator
        else:
            lag = 0
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                lag_minutes=lag,
            )
        )
    return Schedule(
        name="lags_with_leads",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# Relationship Types (DCMA-4) fixtures
# ---------------------------------------------------------------------------


def rel_types_all_fs_schedule() -> Schedule:
    """11-task chain with 10 FS relations → 100% FS → PASS."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 12)
    ]
    relations = [
        Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        for i in range(1, 11)
    ]
    return Schedule(
        name="rel_types_all_fs",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def rel_types_at_threshold_schedule() -> Schedule:
    """10 relations: 9 FS, 1 SS → 90% FS exactly → PASS at boundary."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 12)
    ]
    relations: list[Relation] = []
    for i in range(1, 10):
        relations.append(
            Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        )
    relations.append(
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=11,
            relation_type=RelationType.SS,
        )
    )
    return Schedule(
        name="rel_types_at_threshold",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def rel_types_below_threshold_schedule() -> Schedule:
    """100 relations: 89 FS + 5 SS + 5 FF + 1 SF → 89% FS → FAIL."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 102)
    ]
    relations: list[Relation] = []
    # 89 FS
    for i in range(1, 90):
        relations.append(
            Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        )
    # 5 SS
    for i in range(91, 96):
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                relation_type=RelationType.SS,
            )
        )
    # 5 FF
    for i in range(96, 101):
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                relation_type=RelationType.FF,
            )
        )
    # 1 SF
    relations.append(
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=101,
            relation_type=RelationType.SF,
        )
    )
    return Schedule(
        name="rel_types_below_threshold",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def rel_types_golden_fail_schedule() -> Schedule:
    """Hand-calculable Metric-4 golden (A6).

    10 relations: 8 FS, 1 SS, 1 FF, 0 SF → 80% FS → FAIL.
    """
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 12)
    ]
    relations: list[Relation] = []
    for i in range(1, 9):
        relations.append(
            Relation(predecessor_unique_id=i, successor_unique_id=i + 1)
        )
    relations.append(
        Relation(
            predecessor_unique_id=9,
            successor_unique_id=10,
            relation_type=RelationType.SS,
        )
    )
    relations.append(
        Relation(
            predecessor_unique_id=10,
            successor_unique_id=11,
            relation_type=RelationType.FF,
        )
    )
    return Schedule(
        name="rel_types_golden_fail",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def no_relations_schedule() -> Schedule:
    """Five tasks, zero relations. Used by RT5 (division-by-zero
    guard for Metric 4) and by the Leads/Lags zero-relation paths."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 6)
    ]
    return Schedule(
        name="no_relations",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# Cross-metric integration fixture (A7)
# ---------------------------------------------------------------------------


def integration_schedule() -> Schedule:
    """Realistic schedule for the integration test (M5 AC7).

    20 incomplete working tasks bracketed by Start / Finish
    milestones. Includes:

    * 1 task missing both predecessor and successor (Logic FAIL)
    * 1 negative-lag relation (Leads FAIL)
    * 2 positive-lag relations (Lags 2/19 ≈ 10.5% FAIL)
    * 4 non-FS relations (16/20 = 80% FS → FAIL)
    """
    tasks: list[Task] = [
        Task(
            unique_id=100,
            task_id=100,
            name="Start",
            duration_minutes=0,
            is_milestone=True,
        )
    ]
    for i in range(1, 21):
        tasks.append(
            Task(
                unique_id=i,
                task_id=i,
                name=f"T{i}",
                duration_minutes=480,
            )
        )
    tasks.append(
        Task(
            unique_id=200,
            task_id=200,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
        )
    )

    relations: list[Relation] = [
        Relation(predecessor_unique_id=100, successor_unique_id=1),
    ]
    # Chain T1 → T2 → … → T18 → Finish; leave T19 and T20 detached
    # so the Missing-Logic numerator is 2/20 = 10% > 5% → FAIL.
    for i in range(1, 18):
        rt = RelationType.FS
        lag = 0
        if i == 4:
            rt = RelationType.SS
        elif i == 8:
            rt = RelationType.FF
        elif i == 12:
            rt = RelationType.SF
        elif i == 16:
            rt = RelationType.SS
        if i == 5:
            lag = -480  # lead
        if i in (10, 14):
            lag = 960  # positive lag (~2 WD)
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                relation_type=rt,
                lag_minutes=lag,
            )
        )
    relations.append(
        Relation(predecessor_unique_id=18, successor_unique_id=200)
    )

    return Schedule(
        name="integration",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# Hard Constraints (DCMA-5) fixtures
# ---------------------------------------------------------------------------


def hard_constraints_pass_schedule() -> Schedule:
    """20 tasks, no hard constraints. Denominator uses default §3
    exclusions (summary / LOE / 100%-complete), leaving 20 eligible
    tasks. Numerator = 0 → 0/20 = 0% → PASS."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 21)
    ]
    return Schedule(
        name="hard_constraints_pass",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def hard_constraints_golden_fail_schedule() -> Schedule:
    """Hand-calculable Metric-5 golden.

    20 tasks: 4 carry the 09NOV09 hard constraints (MSO, MFO, SNLT,
    FNLT), 2 carry soft / non-hard constraints (SNET, FNET) which
    must NOT count, and the remainder are ASAP (default). Numerator
    = 4 (the hard four), denominator = 20 → 20% → FAIL (>5%)."""
    cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    tasks: list[Task] = []
    # UID 1: MSO (hard)
    tasks.append(
        Task(
            unique_id=1,
            task_id=1,
            name="MSO task",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=cd,
        )
    )
    # UID 2: MFO (hard)
    tasks.append(
        Task(
            unique_id=2,
            task_id=2,
            name="MFO task",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=cd,
        )
    )
    # UID 3: SNLT (hard)
    tasks.append(
        Task(
            unique_id=3,
            task_id=3,
            name="SNLT task",
            duration_minutes=480,
            constraint_type=ConstraintType.START_NO_LATER_THAN,
            constraint_date=cd,
        )
    )
    # UID 4: FNLT (hard)
    tasks.append(
        Task(
            unique_id=4,
            task_id=4,
            name="FNLT task",
            duration_minutes=480,
            constraint_type=ConstraintType.FINISH_NO_LATER_THAN,
            constraint_date=cd,
        )
    )
    # UID 5: SNET (soft — does NOT count)
    tasks.append(
        Task(
            unique_id=5,
            task_id=5,
            name="SNET task",
            duration_minutes=480,
            constraint_type=ConstraintType.START_NO_EARLIER_THAN,
            constraint_date=cd,
        )
    )
    # UID 6: FNET (soft — does NOT count)
    tasks.append(
        Task(
            unique_id=6,
            task_id=6,
            name="FNET task",
            duration_minutes=480,
            constraint_type=ConstraintType.FINISH_NO_EARLIER_THAN,
            constraint_date=cd,
        )
    )
    # UID 7: ALAP (does NOT count here; detected by M11 per
    # forensic-manipulation-patterns §5.3).
    tasks.append(
        Task(
            unique_id=7,
            task_id=7,
            name="ALAP task",
            duration_minutes=480,
            constraint_type=ConstraintType.AS_LATE_AS_POSSIBLE,
        )
    )
    # UIDs 8..20: plain ASAP tasks to round out the denominator.
    for i in range(8, 21):
        tasks.append(
            Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        )
    return Schedule(
        name="hard_constraints_golden_fail",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def hard_constraints_excluded_population_schedule() -> Schedule:
    """A schedule where every hard-constrained task is summary, LOE,
    or 100%-complete — the default exclusions must drop them from
    the denominator. 3 excluded hard-constrained tasks + 2 eligible
    unconstrained tasks → 0/2 = 0% PASS."""
    cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Summary MSO",
            duration_minutes=480,
            is_summary=True,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=cd,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="LOE MFO",
            duration_minutes=480,
            is_loe=True,
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=cd,
        ),
        Task(
            unique_id=3,
            task_id=3,
            name="Closed SNLT",
            duration_minutes=480,
            percent_complete=100.0,
            constraint_type=ConstraintType.START_NO_LATER_THAN,
            constraint_date=cd,
        ),
        Task(unique_id=4, task_id=4, name="Plain A", duration_minutes=480),
        Task(unique_id=5, task_id=5, name="Plain B", duration_minutes=480),
    ]
    return Schedule(
        name="hard_constraints_excluded_population",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def hard_constraints_boundary_schedule() -> Schedule:
    """20-task schedule with exactly 1 hard-constrained task →
    1/20 = 5% exactly → PASS at the boundary (``<=`` semantics)."""
    cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    tasks: list[Task] = [
        Task(
            unique_id=1,
            task_id=1,
            name="MSO solo",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=cd,
        )
    ]
    for i in range(2, 21):
        tasks.append(
            Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        )
    return Schedule(
        name="hard_constraints_boundary",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# High Float (DCMA-6) fixtures — consume CPMResult
# ---------------------------------------------------------------------------
#
# Threshold: total_slack > 44 WD flags; 44.0 WD does not. On an 8h/day
# calendar, 44 WD = 44 * 8 * 60 = 21120 minutes exactly. 44.01 WD maps
# to 21125 min (rounded from 21124.8) via working_days_to_minutes.


def _schedule_with_n_tasks(n: int, name: str) -> Schedule:
    """Helper — n-task schedule, no relations, all incomplete,
    default ASAP. Used by several M6 CPM fixtures."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, n + 1)
    ]
    return Schedule(
        name=name,
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def _cpm_with_slack(tf_by_uid: dict[int, int]) -> CPMResult:
    """Helper — build a :class:`CPMResult` from a UID→TF-minutes map.

    Every UID present becomes a :class:`TaskCPMResult` carrying that
    total_slack_minutes. ``on_critical_path`` is set when TF <= 0 to
    match the engine's classification semantics — though the M6/M7
    metrics don't consume that flag, keeping it truthful makes the
    fixture safe to share with unrelated tests.
    """
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


def high_float_pass_with_cpm() -> tuple[Schedule, CPMResult]:
    """20 incomplete tasks, all with TF = 0 min (critical). 0/20 =
    0% → PASS."""
    sched = _schedule_with_n_tasks(20, "high_float_pass")
    cpm = _cpm_with_slack({i: 0 for i in range(1, 21)})
    return sched, cpm


def high_float_fail_with_cpm() -> tuple[Schedule, CPMResult]:
    """20 incomplete tasks; UIDs 5 and 15 carry TF = 21125 min
    (44.01 WD, just past threshold). 2/20 = 10% > 5% → FAIL."""
    sched = _schedule_with_n_tasks(20, "high_float_fail")
    tf_map = {i: 0 for i in range(1, 21)}
    tf_map[5] = 21125
    tf_map[15] = 21125
    cpm = _cpm_with_slack(tf_map)
    return sched, cpm


def high_float_boundary_with_cpm() -> tuple[Schedule, CPMResult]:
    """Boundary test — one task at 21120 min (44 WD exactly, must
    NOT flag) and one at 21121 min (44.00138... WD, must flag).
    Expected: 1/20 = 5% PASS."""
    sched = _schedule_with_n_tasks(20, "high_float_boundary")
    tf_map = {i: 0 for i in range(1, 21)}
    tf_map[5] = 21120  # 44.0 WD — does not flag per AC 2.
    tf_map[15] = 21121  # just above — flags.
    cpm = _cpm_with_slack(tf_map)
    return sched, cpm


def high_float_empty_with_cpm() -> tuple[Schedule, CPMResult]:
    """Zero-task schedule, empty CPMResult. Vacuous PASS."""
    sched = Schedule(
        name="high_float_empty",
        project_start=ANCHOR,
        tasks=[],
        relations=[],
        calendars=[_std_cal()],
    )
    return sched, CPMResult(tasks={})


def high_float_excluded_population_with_cpm() -> tuple[Schedule, CPMResult]:
    """Every high-float task is summary / LOE / 100%-complete, so
    the eligible denominator collapses. 3 excluded + 2 eligible with
    TF = 0 → 0/2 = 0% PASS."""
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Summary high-float",
            duration_minutes=480,
            is_summary=True,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="LOE high-float",
            duration_minutes=480,
            is_loe=True,
        ),
        Task(
            unique_id=3,
            task_id=3,
            name="Done high-float",
            duration_minutes=480,
            percent_complete=100.0,
        ),
        Task(unique_id=4, task_id=4, name="Live A", duration_minutes=480),
        Task(unique_id=5, task_id=5, name="Live B", duration_minutes=480),
    ]
    sched = Schedule(
        name="high_float_excluded_population",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )
    cpm = _cpm_with_slack({1: 30000, 2: 30000, 3: 30000, 4: 0, 5: 0})
    return sched, cpm


# ---------------------------------------------------------------------------
# Negative Float (DCMA-7) fixtures — consume CPMResult
# ---------------------------------------------------------------------------
#
# Threshold is absolute 0% per AC 3 — any task with TF < 0 fails.


def negative_float_pass_with_cpm() -> tuple[Schedule, CPMResult]:
    """10-task schedule with every task at TF = 0 or positive.
    0/10 = 0% PASS."""
    sched = _schedule_with_n_tasks(10, "negative_float_pass")
    cpm = _cpm_with_slack({i: 480 * i for i in range(1, 11)})
    return sched, cpm


def negative_float_fail_with_cpm() -> tuple[Schedule, CPMResult]:
    """20-task schedule, UID 7 carries TF = -480 min (one full WD
    negative). 1/20 = 5% > 0% → FAIL (absolute threshold)."""
    sched = _schedule_with_n_tasks(20, "negative_float_fail")
    tf_map = {i: 0 for i in range(1, 21)}
    tf_map[7] = -480
    cpm = _cpm_with_slack(tf_map)
    return sched, cpm


def negative_float_multi_fail_with_cpm() -> tuple[Schedule, CPMResult]:
    """20-task schedule with 3 negative-float tasks carrying
    different TF magnitudes. Offender list must enumerate all three
    in deterministic UID order."""
    sched = _schedule_with_n_tasks(20, "negative_float_multi_fail")
    tf_map = {i: 0 for i in range(1, 21)}
    tf_map[3] = -240
    tf_map[8] = -960
    tf_map[17] = -2400
    cpm = _cpm_with_slack(tf_map)
    return sched, cpm


def negative_float_empty_with_cpm() -> tuple[Schedule, CPMResult]:
    """Zero-task schedule. Vacuous PASS."""
    sched = Schedule(
        name="negative_float_empty",
        project_start=ANCHOR,
        tasks=[],
        relations=[],
        calendars=[_std_cal()],
    )
    return sched, CPMResult(tasks={})


def negative_float_with_cycle_skipped_with_cpm() -> tuple[Schedule, CPMResult]:
    """Task 5 is in a cycle and was skipped by the engine
    (skipped_due_to_cycle=True, TF defaults to 0). The metric must
    exclude skipped tasks from the denominator per the no-mutation
    CPM contract — evaluating slack on a skipped task is meaningless."""
    sched = _schedule_with_n_tasks(10, "negative_float_cycle_skipped")
    cpm = CPMResult(
        tasks={
            i: TaskCPMResult(
                unique_id=i,
                total_slack_minutes=0,
                skipped_due_to_cycle=(i == 5),
            )
            for i in range(1, 11)
        },
        cycles_detected=frozenset({5}),
    )
    return sched, cpm


# ---------------------------------------------------------------------------
# High Duration (DCMA-8) fixtures
# ---------------------------------------------------------------------------
#
# Threshold: remaining_duration > 44 WD flags; 44.0 WD does not.
# On an 8h/day calendar, 44 WD = 21120 minutes exactly.
# Rolling-wave-tagged tasks are exempt from the numerator per AC 4.


def high_duration_pass_schedule() -> Schedule:
    """20 incomplete tasks, all 1 WD (480 min). 0/20 = 0% → PASS."""
    tasks = [
        Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        for i in range(1, 21)
    ]
    return Schedule(
        name="high_duration_pass",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def high_duration_golden_fail_schedule() -> Schedule:
    """Hand-calculable Metric-8 golden.

    20 incomplete tasks; 3 carry duration = 50 WD (24000 min) which
    exceeds the 44 WD threshold. Numerator = 3, denominator = 20 →
    15% > 5% → FAIL."""
    tasks: list[Task] = []
    long_minutes = 24000  # 50 WD
    for i in range(1, 21):
        if i in (4, 10, 16):
            tasks.append(
                Task(
                    unique_id=i,
                    task_id=i,
                    name=f"LongT{i}",
                    duration_minutes=long_minutes,
                )
            )
        else:
            tasks.append(
                Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
            )
    return Schedule(
        name="high_duration_golden_fail",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def high_duration_boundary_schedule() -> Schedule:
    """Boundary test — one task at 21120 min (44 WD exactly, must
    NOT flag) and one at 21121 min (just past threshold, must flag).
    Other 18 tasks at 1 WD. Expected: 1/20 = 5% PASS (boundary)."""
    tasks: list[Task] = [
        Task(unique_id=1, task_id=1, name="Boundary=44", duration_minutes=21120),
        Task(unique_id=2, task_id=2, name="JustOver", duration_minutes=21121),
    ]
    for i in range(3, 21):
        tasks.append(
            Task(unique_id=i, task_id=i, name=f"T{i}", duration_minutes=480)
        )
    return Schedule(
        name="high_duration_boundary",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def high_duration_rolling_wave_schedule() -> Schedule:
    """AC 4 — ``is_rolling_wave=True`` exempts a task from the
    high-duration numerator.

    20 incomplete tasks; UID 5 carries 28800 min (60 WD) AND
    ``is_rolling_wave=True`` — exempt from the numerator; UID 6
    carries the same duration WITHOUT the flag — counted. Expected
    numerator = 1, denominator = 20 → 5% PASS (at boundary). Pair
    tests the exemption mechanics directly."""
    tasks: list[Task] = []
    big_minutes = 28800  # 60 WD
    for i in range(1, 21):
        if i == 5:
            tasks.append(
                Task(
                    unique_id=i,
                    task_id=i,
                    name="RollingWave",
                    duration_minutes=big_minutes,
                    is_rolling_wave=True,
                )
            )
        elif i == 6:
            tasks.append(
                Task(
                    unique_id=i,
                    task_id=i,
                    name="PlainLong",
                    duration_minutes=big_minutes,
                )
            )
        else:
            tasks.append(
                Task(
                    unique_id=i,
                    task_id=i,
                    name=f"T{i}",
                    duration_minutes=480,
                )
            )
    return Schedule(
        name="high_duration_rolling_wave",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def high_duration_excluded_population_schedule() -> Schedule:
    """Every long-duration task is summary / LOE / 100%-complete.
    Default §3 exclusions drop them from the denominator. 3 excluded
    + 2 eligible (each 1 WD) → 0/2 = 0% PASS."""
    big_minutes = 24000  # 50 WD
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Summary long",
            duration_minutes=big_minutes,
            is_summary=True,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="LOE long",
            duration_minutes=big_minutes,
            is_loe=True,
        ),
        Task(
            unique_id=3,
            task_id=3,
            name="Done long",
            duration_minutes=big_minutes,
            percent_complete=100.0,
        ),
        Task(unique_id=4, task_id=4, name="Live A", duration_minutes=480),
        Task(unique_id=5, task_id=5, name="Live B", duration_minutes=480),
    ]
    return Schedule(
        name="high_duration_excluded_population",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# Resources (DCMA-10) fixtures
# ---------------------------------------------------------------------------
#
# Metric 10 returns a ratio only — AC 5 pins pass_flag=None. The fixtures
# exercise the numerator (resource_count == 0) and the default §3
# exclusions on the denominator.


def resources_all_assigned_schedule() -> Schedule:
    """10 incomplete tasks, each with resource_count = 2.
    Numerator = 0, denominator = 10 → 0.0 ratio."""
    tasks = [
        Task(
            unique_id=i,
            task_id=i,
            name=f"T{i}",
            duration_minutes=480,
            resource_count=2,
        )
        for i in range(1, 11)
    ]
    return Schedule(
        name="resources_all_assigned",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def resources_half_missing_schedule() -> Schedule:
    """20 incomplete tasks, even UIDs have resource_count=0 and odd
    UIDs have resource_count=1. Numerator = 10, denominator = 20 →
    50% ratio."""
    tasks: list[Task] = []
    for i in range(1, 21):
        tasks.append(
            Task(
                unique_id=i,
                task_id=i,
                name=f"T{i}",
                duration_minutes=480,
                resource_count=(0 if i % 2 == 0 else 1),
            )
        )
    return Schedule(
        name="resources_half_missing",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def resources_all_missing_schedule() -> Schedule:
    """10 incomplete tasks, all with resource_count=0. Numerator = 10,
    denominator = 10 → 100% ratio. Still returns pass_flag=None per
    AC 5."""
    tasks = [
        Task(
            unique_id=i,
            task_id=i,
            name=f"T{i}",
            duration_minutes=480,
            resource_count=0,
        )
        for i in range(1, 11)
    ]
    return Schedule(
        name="resources_all_missing",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def resources_excluded_population_schedule() -> Schedule:
    """Zero-resource tasks are all summary / LOE / 100%-complete →
    dropped from denominator. 3 excluded + 2 eligible (with 1
    resource each) → 0/2 = 0% ratio."""
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="Summary no-rsrc",
            duration_minutes=480,
            is_summary=True,
            resource_count=0,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="LOE no-rsrc",
            duration_minutes=480,
            is_loe=True,
            resource_count=0,
        ),
        Task(
            unique_id=3,
            task_id=3,
            name="Done no-rsrc",
            duration_minutes=480,
            percent_complete=100.0,
            resource_count=0,
        ),
        Task(
            unique_id=4,
            task_id=4,
            name="Live A",
            duration_minutes=480,
            resource_count=1,
        ),
        Task(
            unique_id=5,
            task_id=5,
            name="Live B",
            duration_minutes=480,
            resource_count=1,
        ),
    ]
    return Schedule(
        name="resources_excluded_population",
        project_start=ANCHOR,
        tasks=tasks,
        relations=[],
        calendars=[_std_cal()],
    )


def resources_empty_schedule() -> Schedule:
    """Zero tasks. Denominator = 0; ratio reported as 0.0 with the
    vacuous-note convention."""
    return Schedule(
        name="resources_empty",
        project_start=ANCHOR,
        tasks=[],
        relations=[],
        calendars=[_std_cal()],
    )


# ---------------------------------------------------------------------------
# M6 9-metric integration fixture (extends M5's integration_schedule)
# ---------------------------------------------------------------------------


def m6_integration_schedule() -> tuple[Schedule, CPMResult]:
    """Realistic fixture exercising all nine metrics (M5 1-4 + M6 5-8, 10).

    20 incomplete working tasks bracketed by Start / Finish milestones.

    Failure vectors baked in:

    * Metric 1 (Logic): T19 and T20 detached → 2/20 = 10% FAIL.
    * Metric 2 (Leads): one relation carrying -480 min lag → FAIL.
    * Metric 3 (Lags): two relations carrying +960 min → 2/18 ≈
      11.1% FAIL (19 non-lead relations minus the 1 lead = 18).
    * Metric 4 (Relationship Types): 4 non-FS relations / 19 total
      → 15/19 ≈ 78.9% FS FAIL.
    * Metric 5 (Hard Constraints): UID 3 MSO + UID 11 FNLT →
      2/22 ≈ 9.09% FAIL (denominator includes the two milestones
      because §3 exclusions don't drop them for Metric 5).
    * Metric 6 (High Float): UIDs 17 and 18 carry TF = 21125 min
      (44.01 WD) → 2/22 ≈ 9.09% FAIL.
    * Metric 7 (Negative Float): UID 9 carries TF = -480 min →
      1/22 ≈ 4.55% > 0% FAIL (absolute threshold).
    * Metric 8 (High Duration): UID 13 carries 24000 min (50 WD);
      milestones have duration=0 so they don't flag → 1/22 ≈
      4.55% PASS (below the 5% ceiling).
    * Metric 10 (Resources): UIDs 19 and 20 have resource_count=0;
      milestones get resource_count=1 so they don't spuriously
      flag → 2/22 ≈ 9.09% ratio (indicator-only).
    """
    cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    # Start milestone — resource_count=1 so Metric 10's seeded
    # offender set stays pinned to {19, 20} (milestones with the
    # default resource_count=0 would otherwise flag as indicator
    # offenders and dilute the seeded signal).
    tasks: list[Task] = [
        Task(
            unique_id=100,
            task_id=100,
            name="Start",
            duration_minutes=0,
            is_milestone=True,
            resource_count=1,
        )
    ]
    for i in range(1, 21):
        ct = ConstraintType.AS_SOON_AS_POSSIBLE
        cd_i: datetime | None = None
        if i == 3:
            ct = ConstraintType.MUST_START_ON
            cd_i = cd
        elif i == 11:
            ct = ConstraintType.FINISH_NO_LATER_THAN
            cd_i = cd
        duration = 24000 if i == 13 else 480
        tasks.append(
            Task(
                unique_id=i,
                task_id=i,
                name=f"T{i}",
                duration_minutes=duration,
                constraint_type=ct,
                constraint_date=cd_i,
                resource_count=(0 if i in (19, 20) else 1),
            )
        )
    tasks.append(
        Task(
            unique_id=200,
            task_id=200,
            name="Finish",
            duration_minutes=0,
            is_milestone=True,
            resource_count=1,
        )
    )

    relations: list[Relation] = [
        Relation(predecessor_unique_id=100, successor_unique_id=1),
    ]
    for i in range(1, 18):
        rt = RelationType.FS
        lag = 0
        if i == 4:
            rt = RelationType.SS
        elif i == 8:
            rt = RelationType.FF
        elif i == 12:
            rt = RelationType.SF
        elif i == 16:
            rt = RelationType.SS
        if i == 5:
            lag = -480  # lead
        if i in (10, 14):
            lag = 960  # positive lag
        relations.append(
            Relation(
                predecessor_unique_id=i,
                successor_unique_id=i + 1,
                relation_type=rt,
                lag_minutes=lag,
            )
        )
    relations.append(Relation(predecessor_unique_id=18, successor_unique_id=200))

    sched = Schedule(
        name="m6_integration",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )

    # CPMResult — hand-built so the M6/M7 expectations are
    # deterministic regardless of CPM engine evolution.
    cpm_tasks: dict[int, TaskCPMResult] = {}
    for i in range(1, 21):
        if i in (17, 18):
            tf = 21125  # 44.01 WD — High Float flag
        elif i == 9:
            tf = -480  # Negative Float flag
        else:
            tf = 0
        cpm_tasks[i] = TaskCPMResult(
            unique_id=i,
            total_slack_minutes=tf,
            on_critical_path=tf <= 0,
        )
    # Endpoint milestones also carry a CPM record (TF=0).
    cpm_tasks[100] = TaskCPMResult(unique_id=100, total_slack_minutes=0)
    cpm_tasks[200] = TaskCPMResult(unique_id=200, total_slack_minutes=0)
    cpm = CPMResult(tasks=cpm_tasks)
    return sched, cpm


__all__ = [
    "ANCHOR",
    "all_complete_schedule",
    "empty_schedule",
    "hard_constraints_boundary_schedule",
    "hard_constraints_excluded_population_schedule",
    "hard_constraints_golden_fail_schedule",
    "hard_constraints_pass_schedule",
    "high_duration_boundary_schedule",
    "high_duration_excluded_population_schedule",
    "high_duration_golden_fail_schedule",
    "high_duration_pass_schedule",
    "high_duration_rolling_wave_schedule",
    "high_float_boundary_with_cpm",
    "high_float_empty_with_cpm",
    "high_float_excluded_population_with_cpm",
    "high_float_fail_with_cpm",
    "high_float_pass_with_cpm",
    "integration_schedule",
    "lags_below_threshold_schedule",
    "lags_golden_fail_schedule",
    "lags_pass_schedule",
    "lags_with_leads_schedule",
    "leads_golden_fail_schedule",
    "leads_on_completed_task_schedule",
    "leads_pass_schedule",
    "logic_golden_fail_schedule",
    "logic_loe_by_name_schedule",
    "logic_pass_schedule",
    "logic_summary_loe_completed_schedule",
    "m6_integration_schedule",
    "negative_float_empty_with_cpm",
    "negative_float_fail_with_cpm",
    "negative_float_multi_fail_with_cpm",
    "negative_float_pass_with_cpm",
    "negative_float_with_cycle_skipped_with_cpm",
    "no_relations_schedule",
    "rel_types_all_fs_schedule",
    "rel_types_at_threshold_schedule",
    "rel_types_below_threshold_schedule",
    "rel_types_golden_fail_schedule",
    "resources_all_assigned_schedule",
    "resources_all_missing_schedule",
    "resources_empty_schedule",
    "resources_excluded_population_schedule",
    "resources_half_missing_schedule",
]
