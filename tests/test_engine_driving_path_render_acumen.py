"""Tests for the default Acumen-style driving-path renderer.

Block 7.4 (2026-04-22): minimal renderer on
:func:`app.engine.driving_path_render_acumen.render_acumen_table`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path
from app.engine.driving_path_render_acumen import render_acumen_table
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _sched(tasks: list[Task], relations: list[Relation], *, name: str) -> Schedule:
    return Schedule(
        name=name,
        project_start=ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def test_render_row_count_matches_node_count() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = _sched(tasks, relations, name="linear")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    rows = render_acumen_table(result)
    assert len(rows) == len(result.nodes) == 3


def test_rows_sorted_by_early_start_ascending() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="C", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
    ]
    s = _sched(tasks, relations, name="linear")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    rows = render_acumen_table(result)
    assert [r["unique_id"] for r in rows] == [1, 2, 3]
    for i in range(len(rows) - 1):
        assert rows[i]["early_start"] <= rows[i + 1]["early_start"]


def test_driving_predecessors_nested_per_row() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [Relation(predecessor_unique_id=1, successor_unique_id=2)]
    s = _sched(tasks, relations, name="linear")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 2, cpm)
    rows = render_acumen_table(result)
    # A has no driving predecessors in the sub-graph.
    row_a = next(r for r in rows if r["unique_id"] == 1)
    assert row_a["driving_predecessor_count"] == 0
    assert row_a["driving_predecessors"] == []
    # B has exactly one driving predecessor — A.
    row_b = next(r for r in rows if r["unique_id"] == 2)
    assert row_b["driving_predecessor_count"] == 1
    (pred,) = row_b["driving_predecessors"]
    assert pred["predecessor_uid"] == 1
    assert pred["predecessor_name"] == "A"
    assert pred["relation_type"] == RelationType.FS
    assert pred["lag_days"] == pytest.approx(0.0)
    assert pred["relationship_slack_days"] == pytest.approx(0.0)


def test_non_driving_predecessor_count_surfaces_on_successor_row() -> None:
    """Q feeds X with positive slack; Q's count lands on X's row."""
    tasks = [
        Task(unique_id=1, task_id=1, name="Y", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="X", duration_minutes=480),
        Task(
            unique_id=3,
            task_id=3,
            name="Focus",
            duration_minutes=0,
            is_milestone=True,
        ),
        Task(unique_id=5, task_id=5, name="Q", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=5, successor_unique_id=2),
    ]
    s = _sched(tasks, relations, name="q_feeds_x")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 3, cpm)
    rows = render_acumen_table(result)

    row_x = next(r for r in rows if r["unique_id"] == 2)
    assert row_x["non_driving_predecessor_count"] == 1
    # Other rows are unaffected.
    for r in rows:
        if r["unique_id"] != 2:
            assert r["non_driving_predecessor_count"] == 0


def test_calendar_hours_per_day_surfaces_on_row() -> None:
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
    ]
    s = _sched(tasks, [], name="lone")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 1, cpm)
    (row,) = render_acumen_table(result)
    assert row["calendar_hours_per_day"] == 8.0


def test_empty_driving_subgraph_single_node() -> None:
    """Focus task with no driving predecessors renders one row."""
    tasks = [Task(unique_id=42, task_id=1, name="Solo", duration_minutes=480)]
    s = _sched(tasks, [], name="solo")
    cpm = compute_cpm(s)
    result = trace_driving_path(s, 42, cpm)
    rows = render_acumen_table(result)
    assert len(rows) == 1
    assert rows[0]["unique_id"] == 42
    assert rows[0]["driving_predecessor_count"] == 0
    assert rows[0]["non_driving_predecessor_count"] == 0
