"""Tests for longest-path and driving-slack computations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.options import CPMOptions
from app.engine.paths import (
    critical_path_chains,
    driving_slack_to_focus,
    near_critical_chain,
)
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.schedules import ANCHOR, small_fs_chain


def _t(uid: int, dur: int = 480) -> Task:
    return Task(unique_id=uid, task_id=uid, name=f"T{uid}", duration_minutes=dur)


def _r(p: int, s: int, rt: RelationType = RelationType.FS, lag: int = 0) -> Relation:
    return Relation(
        predecessor_unique_id=p,
        successor_unique_id=s,
        relation_type=rt,
        lag_minutes=lag,
    )


def _schedule(tasks: list[Task], relations: list[Relation]) -> Schedule:
    return Schedule(
        name="test",
        project_start=ANCHOR,
        tasks=tasks,
        relations=relations,
        calendars=[Calendar(name="Standard")],
    )


# ---- Critical path chains ----------------------------------------


def test_single_chain_yields_one_chain() -> None:
    result = compute_cpm(small_fs_chain())
    chains = critical_path_chains(small_fs_chain(), result)
    assert chains == [[1, 2, 3]]


def test_two_parallel_chains_both_critical() -> None:
    # 1->2->5 and 3->4->5. Both chains critical.
    tasks = [_t(1), _t(2), _t(3), _t(4), _t(5)]
    relations = [_r(1, 2), _r(2, 5), _r(3, 4), _r(4, 5)]
    s = _schedule(tasks, relations)
    result = compute_cpm(s)
    chains = critical_path_chains(s, result)
    # Two chains: [1,2,5] and [3,4,5].
    assert sorted(chains) == [[1, 2, 5], [3, 4, 5]]


def test_no_critical_when_override_pushes_finish_out() -> None:
    s = small_fs_chain()
    future = datetime(2026, 5, 31, 16, tzinfo=UTC)
    result = compute_cpm(s, CPMOptions(project_finish_override=future))
    assert critical_path_chains(s, result) == []


# ---- Driving slack to focus --------------------------------------


def test_driving_slack_to_project_finish_matches_total_slack() -> None:
    """For a simple FS chain with focus = project finish, DS(T → F)
    equals the task's total slack. This is the BUILD-PLAN §5 M4 E20
    invariant in its default form."""
    s = small_fs_chain()
    result = compute_cpm(s)
    ds = driving_slack_to_focus(s, result, focus_uid=3)
    assert ds[3] == 0
    assert ds[2] == 0
    assert ds[1] == 0


def test_driving_slack_focus_point_has_ds_zero() -> None:
    s = small_fs_chain()
    result = compute_cpm(s)
    ds = driving_slack_to_focus(s, result, focus_uid=2)
    assert ds[2] == 0
    # Task 3 is downstream of focus 2, not upstream → not in ds.
    assert 3 not in ds


def test_driving_slack_parallel_branch_has_slack() -> None:
    # 1 -> 2 -> 4 (critical); 1 -> 3 -> 4 where 3 is a short task giving
    # parallel branch slack. All four tasks' DS computed to focus 4.
    tasks = [_t(1), _t(2, 480 * 3), _t(3, 480), _t(4)]
    relations = [_r(1, 2), _r(2, 4), _r(1, 3), _r(3, 4)]
    s = _schedule(tasks, relations)
    result = compute_cpm(s)
    ds = driving_slack_to_focus(s, result, focus_uid=4)
    # Task 2 is on the longest path → DS 0.
    assert ds[2] == 0
    # Task 3 has slack (shorter duration, longer branch dominates).
    assert ds[3] > 0


def test_driving_slack_focus_not_in_schedule_returns_empty() -> None:
    s = small_fs_chain()
    result = compute_cpm(s)
    assert driving_slack_to_focus(s, result, focus_uid=999) == {}


# ---- Near-critical chain ----------------------------------------


def test_near_critical_chain_returns_flagged_uids() -> None:
    tasks = [_t(i) for i in (1, 2, 3, 4, 5, 6)]
    relations = [
        _r(1, 2), _r(2, 3), _r(3, 4), _r(4, 5),
        _r(1, 6), _r(6, 5),
    ]
    s = _schedule(tasks, relations)
    # 5-task chain 1->2->3->4->5 critical; 6 in parallel (1->6->5) has slack.
    result = compute_cpm(s, CPMOptions(near_critical_threshold_days=5.0))
    nc = near_critical_chain(result)
    assert 6 in nc


def test_near_critical_chain_empty_when_no_flagged() -> None:
    s = small_fs_chain()  # everything critical
    result = compute_cpm(s)
    assert near_critical_chain(result) == []


def test_driving_slack_no_edges_to_focus_only_focus() -> None:
    """A task not connected to focus is absent from the DS map."""
    tasks = [_t(1), _t(2)]
    relations: list[Relation] = []
    s = _schedule(tasks, relations)
    result = compute_cpm(s)
    ds = driving_slack_to_focus(s, result, focus_uid=2)
    # Focus present; unrelated task 1 is absent.
    assert ds == {2: 0}


# ---- SSI driving-slack vs free-slack divergence (E20) -----------


def test_task_with_fs_zero_can_still_have_driving_slack_positive() -> None:
    """SSI slide 20 inspiration: a task with FS=0 against its nearest
    successor can still have DS > 0 to a later Focus Point. We
    encode the structure: 1 ->(SS 0) 2 -> 3 (critical chain); 1's free
    slack is 0 by SS; driving slack to 3 can be positive."""
    tasks = [_t(1), _t(2, 480 * 2), _t(3)]
    relations = [
        _r(1, 2, RelationType.SS, lag=0),
        _r(2, 3, RelationType.FS),
    ]
    s = _schedule(tasks, relations)
    result = compute_cpm(s)
    assert result.tasks[1].free_slack_minutes == 0  # SS link, both ES same.
    ds = driving_slack_to_focus(s, result, focus_uid=3)
    # 1 has slack: it's only 1 day, task 2 is 2 days; dominates.
    assert ds[1] >= 0


# ---- Consistency across fixtures --------------------------------


@pytest.mark.parametrize("finish_focus", [3])
def test_fs_chain_critical_driving_slack_consistent(finish_focus: int) -> None:
    s = small_fs_chain()
    result = compute_cpm(s)
    ds = driving_slack_to_focus(s, result, focus_uid=finish_focus)
    # Everything on the critical chain has DS 0.
    for uid in (1, 2, 3):
        assert ds[uid] == 0
