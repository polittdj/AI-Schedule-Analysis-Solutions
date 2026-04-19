"""Synthetic :class:`Schedule` builders for the M5 DCMA metric tests.

Every builder is hand-crafted from synthetic numbers
(``cui-compliance-constraints §2e`` fixture-data quarantine) and
returns a fully validated :class:`~app.models.schedule.Schedule`.

Builders cover the per-metric pass / warn / fail bands and the
shared edge cases listed in the M5 prompt §5 gotcha tables.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.calendar import Calendar
from app.models.enums import RelationType
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
    # Chain T1 → T2 → … → T19 → Finish; leave T20 detached for the
    # Missing-Logic offender.
    for i in range(1, 19):
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
        Relation(predecessor_unique_id=19, successor_unique_id=200)
    )

    return Schedule(
        name="integration",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


__all__ = [
    "ANCHOR",
    "all_complete_schedule",
    "empty_schedule",
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
    "no_relations_schedule",
    "rel_types_all_fs_schedule",
    "rel_types_at_threshold_schedule",
    "rel_types_below_threshold_schedule",
    "rel_types_golden_fail_schedule",
]
