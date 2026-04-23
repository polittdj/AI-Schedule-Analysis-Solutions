"""Production-scenario tests for the Codex P2 focus-exclusion raise.

M10.1 Block 5. Block 2 (commit 666226b) reshaped the behavior of
:func:`app.engine.driving_path.trace_driving_path` for tasks the CPM
pass could not materialize:

* The FOCUS Point itself — cycle participant, missing from the
  :class:`~app.engine.result.CPMResult`, or with ``None`` early/late
  dates — now raises :class:`~app.engine.exceptions.DrivingPathError`.
  Returning an empty-nodes result was silently hiding a CPM-engine
  problem; Codex P2 flipped that to a loud failure.
* NON-focus tasks that hit the same conditions are recorded on
  :attr:`~app.engine.driving_path_types.DrivingPathResult.skipped_cycle_participants`
  for forensic visibility, preserving the rest of the walk.

Non-mutation invariant (BUILD-PLAN §2.13): every trace call is
wrapped in a :meth:`~pydantic.BaseModel.model_dump` snapshot equality
check. ``CPMResult`` is snapshotted via
:func:`tests._utils.cpm_result_snapshot`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path
from app.engine.exceptions import DrivingPathError
from app.engine.result import CPMResult, TaskCPMResult
from app.models.calendar import Calendar
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot

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


# ----------------------------------------------------------------------
# 4.1: focus is a cycle participant
# ----------------------------------------------------------------------


def test_focus_in_cycle_raises_driving_path_error() -> None:
    """Focus task skipped by CPM lenient cycle handling raises.

    Two-node cycle A <-> B. CPM lenient mode flags both UIDs in
    :attr:`~app.engine.result.CPMResult.cycles_detected` and sets
    ``skipped_due_to_cycle=True`` on both tasks. Tracing from the
    cycle's UID 2 cannot materialize a focus node; the tracer
    refuses to return a silent empty-nodes result and raises
    instead.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=1),
    ]
    s = _sched(tasks, relations, name="focus_cycle")
    cpm = compute_cpm(s)

    assert cpm.tasks[2].skipped_due_to_cycle is True

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    with pytest.raises(DrivingPathError, match=r"UniqueID 2.*missing"):
        trace_driving_path(s, 2, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before


# ----------------------------------------------------------------------
# 4.2: focus is missing from cpm_result.tasks
# ----------------------------------------------------------------------


def test_focus_missing_from_cpm_result_raises_driving_path_error() -> None:
    """Focus UID absent from ``cpm_result.tasks`` raises.

    A hand-built :class:`~app.engine.result.CPMResult` with an empty
    tasks dict simulates a CPMResult the M4 engine would never
    produce but a malformed caller could hand in. The tracer
    detects ``current_cpm is None`` for the focus UID and raises
    rather than silently walking nothing.
    """
    tasks = [Task(unique_id=1, task_id=1, name="A", duration_minutes=480)]
    s = _sched(tasks, [], name="focus_missing")
    empty_cpm = CPMResult(tasks={})

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(empty_cpm)

    with pytest.raises(DrivingPathError, match=r"UniqueID 1.*missing"):
        trace_driving_path(s, 1, empty_cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(empty_cpm) == cpm_before


# ----------------------------------------------------------------------
# 4.3: non-focus cycle participant recorded on skipped_cycle_participants
# ----------------------------------------------------------------------


def test_non_focus_cycle_ancestor_recorded_on_skipped_list() -> None:
    """Cycle-participant ancestor lands on ``skipped_cycle_participants``.

    Schedule carries a real two-node cycle (UIDs 2 <-> 3) plus a
    clean ancestor (UID 1) and a clean focus (UID 4). Fixture
    rationale: a natural lenient-mode CPMResult marks cycle
    participants with ``skipped_due_to_cycle=True``, which causes
    :func:`app.engine.driving_path._link_slack_minutes` to return
    ``None`` and the tracer to drop the edge silently (no record on
    ``skipped_cycle_participants``). To exercise the defensive
    non-focus skip-recording branch — the forensic visibility
    channel for inconsistent CPMResult inputs — we surgically
    override the cycle participant's entry with
    ``skipped_due_to_cycle=False`` plus valid early dates (so the
    edge traverses as a zero-slack driving link and the predecessor
    is enqueued) but ``None`` late dates (so visit-time detects the
    partial state and records the UID on
    :attr:`~app.engine.driving_path_types.DrivingPathResult.skipped_cycle_participants`).

    Asserts:

    * No :class:`DrivingPathError` raised — the focus itself is
      clean, so the walk completes.
    * ``skipped_cycle_participants`` contains the cycle-participant
      UID 2.
    * ``nodes`` contains the focus UID 4 and the clean ancestor
      UID 1 (non-cycle ancestors are materialized as normal).
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="Clean", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="CycleA", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="CycleB", duration_minutes=480),
        Task(unique_id=4, task_id=4, name="Focus", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=4),
        Relation(predecessor_unique_id=2, successor_unique_id=4),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=2),
    ]
    s = _sched(tasks, relations, name="non_focus_cycle")
    real_cpm = compute_cpm(s)

    # Sanity check — the real CPM flagged the cycle as expected.
    assert 2 in real_cpm.cycles_detected
    assert 3 in real_cpm.cycles_detected
    assert real_cpm.tasks[2].skipped_due_to_cycle is True

    # Surgical override: give UID 2 valid early dates + missing late
    # dates with skipped=False so the edge 2 -> 4 traverses as
    # zero-slack driving (early-date check in _link_slack_minutes
    # passes) but the visit-time check (all four dates required)
    # catches the partial state and records UID 2 on
    # skipped_cycle_participants.
    end = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
    modified_tasks = dict(real_cpm.tasks)
    modified_tasks[2] = TaskCPMResult(
        unique_id=2,
        early_start=ANCHOR,
        early_finish=end,
        late_start=None,
        late_finish=None,
        skipped_due_to_cycle=False,
    )
    cpm = CPMResult(
        tasks=modified_tasks,
        project_start=real_cpm.project_start,
        project_finish=real_cpm.project_finish,
        cycles_detected=real_cpm.cycles_detected,
        critical_path_uids=real_cpm.critical_path_uids,
        near_critical_uids=real_cpm.near_critical_uids,
        violations=real_cpm.violations,
    )

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 4, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert 2 in result.skipped_cycle_participants
    assert 4 in result.nodes
    assert 1 in result.nodes
