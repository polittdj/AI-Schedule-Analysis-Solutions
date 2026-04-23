"""Production-scenario tests for the Codex P1 three-bucket routing fix.

M10.1 Block 5. Block 2 (commit 666226b) added the
:class:`ConstraintDrivenPredecessor` routing to
:func:`app.engine.driving_path.trace_driving_path` so that negative-
relationship-slack edges no longer raise a Pydantic ``ValidationError``
when they fail the :class:`~app.engine.driving_path_types.DrivingPathEdge`
~0-slack validator or the :class:`~app.engine.driving_path_types.NonDrivingPredecessor`
strictly-positive-slack validator. These tests exercise the routing end-to-
end on synthetic schedules that drive the CPM engine through the four
DCMA Metric 5 hard constraints (``dcma-14-point-assessment §4.5``) plus
ASAP (the non-date-bearing reference case) and a three-bucket partition
where a single focus task simultaneously carries one driving, one non-
driving, and one constraint-driven predecessor (BUILD-PLAN §2.20).

Authority:

* Three-bucket partition — BUILD-PLAN §2.20 (AM10).
* DCMA Metric 5 hard constraints —
  ``dcma-14-point-assessment §4.5``; NASA SMH on "Improper use can cause
  negative float to be calculated throughout the schedule."
* DCMA-EA Metric #7 — Edwards 2016 pp. 9-10: "Negative float occurs
  when the project schedule is forecasting a missed deadline, or when
  a hard constraint is holding a task further to the left than it
  would otherwise be."
* Non-mutation invariant — BUILD-PLAN §2.13: ``Schedule`` and
  ``CPMResult`` are read-only.

Fixture rationale: every constraint-driven test pairs a predecessor A
with a successor B where ``ES(B)`` is pinned earlier than ``EF(A)``
by a B-side ``MUST_START_ON`` lock. That pairing yields a strictly
negative relationship slack on the ``A -> B`` FS edge regardless of
A's constraint type — which is exactly the condition Codex P1 was
written to route into the third bucket.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.cpm import compute_cpm
from app.engine.driving_path import trace_driving_path
from app.models.calendar import Calendar
from app.models.enums import ConstraintType, RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests._utils import cpm_result_snapshot

ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)

# Relationship-slack tolerance expressed in days — matches the one-
# second tolerance used by the DrivingPathEdge validator. A day value
# whose absolute magnitude is under this band is treated as driving.
_TOL_DAYS = 1.0 / 86_400.0


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


def _date_fragment(d: datetime) -> str:
    """Return the ``"/<day>/<year>"`` substring expected in the rationale.

    The rationale writer formats dates as ``M/D/YYYY`` with no zero-
    padding. A substring match on ``/<day>/<year>`` is stable under
    month-digit variation and confirms the date clause is present.
    """
    return f"/{d.day}/{d.year}"


# ----------------------------------------------------------------------
# 3.1–3.4: one-edge constraint-driven scenarios, one per constraint type
# ----------------------------------------------------------------------


def test_mso_predecessor_produces_negative_relationship_slack() -> None:
    """MSO on the predecessor forces it later than logic allows.

    A is locked to start Wed 4/22 by MSO (project anchor is Mon 4/20,
    so MSO pushes A two working days later than ASAP would). B is
    locked to start Mon 4/20 by its own MSO. The FS edge A -> B
    therefore carries three working days of negative relationship
    slack, routing through the constraint-driven bucket.
    """
    mso_a = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
    mso_b = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="A",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=mso_a,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="B",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=mso_b,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="mso_pred")
    cpm = compute_cpm(s)

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 2, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert len(result.constraint_driven_predecessors) == 1
    cdp = result.constraint_driven_predecessors[0]
    assert cdp.predecessor_uid == 1
    assert cdp.successor_uid == 2
    assert cdp.slack_days < 0
    assert cdp.predecessor_constraint_type == ConstraintType.MUST_START_ON
    assert cdp.predecessor_constraint_date == mso_a
    assert "MUST_START_ON" in cdp.rationale
    assert _date_fragment(mso_a) in cdp.rationale
    assert result.non_driving_predecessors == []


def test_mfo_predecessor_produces_negative_relationship_slack() -> None:
    """MFO on the predecessor pins its EF later than ASAP would.

    A's MFO locks EF to Wed 4/22 16:00; B's MSO locks ES to Mon 4/20
    08:00. Relationship slack on A -> B is negative.
    """
    mfo_a = datetime(2026, 4, 22, 16, 0, tzinfo=UTC)
    mso_b = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="A",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_FINISH_ON,
            constraint_date=mfo_a,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="B",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=mso_b,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="mfo_pred")
    cpm = compute_cpm(s)

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 2, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert len(result.constraint_driven_predecessors) == 1
    cdp = result.constraint_driven_predecessors[0]
    assert cdp.slack_days < 0
    assert cdp.predecessor_constraint_type == ConstraintType.MUST_FINISH_ON
    assert cdp.predecessor_constraint_date == mfo_a
    assert "MUST_FINISH_ON" in cdp.rationale
    assert _date_fragment(mfo_a) in cdp.rationale
    assert result.non_driving_predecessors == []


def test_snlt_predecessor_produces_negative_relationship_slack() -> None:
    """SNLT on the predecessor records the constraint on the edge.

    SNLT does not force the predecessor later in the forward pass —
    it caps the backward-pass LS. The negative edge slack on A -> B
    is produced by B's MSO pulling its ES earlier than A's EF.
    The tracer reports A's SNLT as the constraint-driven predecessor
    type because the bucket is indexed on the predecessor task.
    """
    snlt_a = datetime(2026, 4, 23, 8, 0, tzinfo=UTC)
    mso_b = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="A",
            duration_minutes=480,
            constraint_type=ConstraintType.START_NO_LATER_THAN,
            constraint_date=snlt_a,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="B",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=mso_b,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="snlt_pred")
    cpm = compute_cpm(s)

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 2, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert len(result.constraint_driven_predecessors) == 1
    cdp = result.constraint_driven_predecessors[0]
    assert cdp.slack_days < 0
    assert cdp.predecessor_constraint_type == ConstraintType.START_NO_LATER_THAN
    assert cdp.predecessor_constraint_date == snlt_a
    assert "START_NO_LATER_THAN" in cdp.rationale
    assert _date_fragment(snlt_a) in cdp.rationale
    assert result.non_driving_predecessors == []


def test_fnlt_predecessor_produces_negative_relationship_slack() -> None:
    """FNLT on the predecessor records the constraint on the edge.

    FNLT is a soft-backward constraint — it does not adjust the
    predecessor's forward-pass dates. B's MSO produces the negative
    slack on A -> B, and A's FNLT is recorded on the bucket entry.
    """
    fnlt_a = datetime(2026, 4, 23, 16, 0, tzinfo=UTC)
    mso_b = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    tasks = [
        Task(
            unique_id=1,
            task_id=1,
            name="A",
            duration_minutes=480,
            constraint_type=ConstraintType.FINISH_NO_LATER_THAN,
            constraint_date=fnlt_a,
        ),
        Task(
            unique_id=2,
            task_id=2,
            name="B",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=mso_b,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="fnlt_pred")
    cpm = compute_cpm(s)

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 2, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert len(result.constraint_driven_predecessors) == 1
    cdp = result.constraint_driven_predecessors[0]
    assert cdp.slack_days < 0
    assert cdp.predecessor_constraint_type == ConstraintType.FINISH_NO_LATER_THAN
    assert cdp.predecessor_constraint_date == fnlt_a
    assert "FINISH_NO_LATER_THAN" in cdp.rationale
    assert _date_fragment(fnlt_a) in cdp.rationale
    assert result.non_driving_predecessors == []


# ----------------------------------------------------------------------
# 3.5: non-date-bearing predecessor, negative-float-propagation channel
# ----------------------------------------------------------------------


def test_asap_predecessor_negative_slack_omits_date_clause() -> None:
    """ASAP predecessor + MSO successor → constraint-driven entry.

    A is ASAP (no constraint_date). B's MSO forces ES earlier than
    A's EF. The edge is constraint-driven by virtue of negative-float
    propagation from B's hard lock, and the rationale omits the
    date clause because ASAP is not in
    :data:`~app.models.enums.DATE_BEARING_CONSTRAINTS`.
    """
    mso_b = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=1440),
        Task(
            unique_id=2,
            task_id=2,
            name="B",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=mso_b,
        ),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    s = _sched(tasks, relations, name="asap_pred")
    cpm = compute_cpm(s)

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 2, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert len(result.constraint_driven_predecessors) == 1
    cdp = result.constraint_driven_predecessors[0]
    assert cdp.predecessor_constraint_type == ConstraintType.AS_SOON_AS_POSSIBLE
    assert cdp.predecessor_constraint_date is None
    # The date clause in the rationale writer is " of M/D/YYYY" —
    # check the constraint-name boundary ("constraint of " vs
    # "constraint,") to confirm the clause is omitted.
    assert "constraint of " not in cdp.rationale
    assert "AS_SOON_AS_POSSIBLE" in cdp.rationale


# ----------------------------------------------------------------------
# 3.6: three-bucket partition in a single trace
# ----------------------------------------------------------------------


def test_three_bucket_partition_on_single_focus() -> None:
    """A focus task with one driving, one non-driving, one constraint-driven pred.

    Focus F is MSO=Wed 4/22 08:00 (duration 1 day). Three ASAP
    predecessors span the three slack regimes cleanly:

    * P1 (2 working days → EF Wed 4/22 08:00) produces slack = 0
      (driving).
    * P2 (1 working day → EF Tue 4/21 08:00) produces slack = +1
      working day (non-driving).
    * P3 (4 working days → EF Fri 4/24 08:00) produces slack = -2
      working days (constraint-driven, negative-float propagation
      from F's MSO pulling ES back to 4/22).
    """
    f_mso = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
    tasks = [
        Task(unique_id=1, task_id=1, name="P1", duration_minutes=960),
        Task(unique_id=2, task_id=2, name="P2", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="P3", duration_minutes=1920),
        Task(
            unique_id=4,
            task_id=4,
            name="F",
            duration_minutes=480,
            constraint_type=ConstraintType.MUST_START_ON,
            constraint_date=f_mso,
        ),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=4),
        Relation(predecessor_unique_id=2, successor_unique_id=4),
        Relation(predecessor_unique_id=3, successor_unique_id=4),
    ]
    s = _sched(tasks, relations, name="three_bucket")
    cpm = compute_cpm(s)

    s_before = s.model_dump(mode="json")
    cpm_before = cpm_result_snapshot(cpm)

    result = trace_driving_path(s, 4, cpm)

    assert s.model_dump(mode="json") == s_before
    assert cpm_result_snapshot(cpm) == cpm_before

    assert len(result.edges) == 1
    assert len(result.non_driving_predecessors) == 1
    assert len(result.constraint_driven_predecessors) == 1

    edge = result.edges[0]
    ndp = result.non_driving_predecessors[0]
    cdp = result.constraint_driven_predecessors[0]

    assert edge.predecessor_uid == 1
    assert ndp.predecessor_uid == 2
    assert cdp.predecessor_uid == 3

    assert abs(edge.relationship_slack_days) < _TOL_DAYS
    assert ndp.slack_days > _TOL_DAYS
    assert cdp.slack_days < -_TOL_DAYS
    assert ndp.slack_days == pytest.approx(1.0)
    assert cdp.slack_days == pytest.approx(-2.0)
