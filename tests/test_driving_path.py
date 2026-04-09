"""Unit tests for the driving-path analysis engine.

Covers the three required test cases plus a handful of supporting
cases to lock down the categorization logic (driving / near-driving /
non-driving) and the forward-trace behavior.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pytest

from app.engine.driving_path import (
    NEAR_DRIVING_MAX_DAYS,
    DrivingPathResults,
    analyze_driving_path,
)
from app.parser.schema import (
    ProjectInfo,
    Relationship,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _task(
    uid: int,
    name: str = "",
    duration: Optional[float] = None,
    percent_complete: Optional[float] = 0.0,
    predecessors: Optional[List[int]] = None,
    successors: Optional[List[int]] = None,
) -> TaskData:
    return TaskData(
        uid=uid,
        id=uid,
        name=name,
        duration=duration,
        percent_complete=percent_complete,
        predecessors=predecessors or [],
        successors=successors or [],
    )


def _schedule(tasks, rels) -> ScheduleData:
    return ScheduleData(
        project_info=ProjectInfo(name="Driving Path Test"),
        tasks=tasks,
        relationships=rels,
    )


# --------------------------------------------------------------------------- #
# Linear chain: every predecessor is the single driver
# --------------------------------------------------------------------------- #


class TestLinearChain:
    def _build(self) -> ScheduleData:
        # T1(5d) → T2(3d) → T3(7d) → T4(2d) [target]
        tasks = [
            _task(1, "Mobilize", duration=5.0, successors=[2]),
            _task(2, "Excavate", duration=3.0, predecessors=[1], successors=[3]),
            _task(3, "Pour", duration=7.0, predecessors=[2], successors=[4]),
            _task(4, "Cure", duration=2.0, predecessors=[3]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=2, successor_uid=3),
            Relationship(predecessor_uid=3, successor_uid=4),
        ]
        return _schedule(tasks, rels)

    def test_linear_chain_driving_path_has_every_upstream_task(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        assert isinstance(result, DrivingPathResults)
        assert result.target_uid == 4
        driving_uids = {n.uid for n in result.driving_chain}
        # T3, T2, T1 all drive T4 in a single linear chain.
        assert driving_uids == {1, 2, 3}
        # All driving nodes should have relative_float == 0 and driving == True.
        for node in result.driving_chain:
            assert node.driving is True
            assert node.relative_float_days == pytest.approx(0.0)

    def test_linear_chain_has_no_near_or_non_driving(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        assert result.near_driving_paths == []
        assert result.non_driving_paths == []

    def test_relationship_types_preserved_on_nodes(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        for node in result.driving_chain:
            assert node.relationship_type == "FS"
            assert node.lag_days == pytest.approx(0.0)

    def test_depth_increases_walking_backward(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        depth_by_uid = {n.uid: n.depth for n in result.driving_chain}
        # T3 is the direct predecessor of T4 → depth 1.
        # T2 is 2 hops back, T1 is 3 hops back.
        assert depth_by_uid[3] == 1
        assert depth_by_uid[2] == 2
        assert depth_by_uid[1] == 3


# --------------------------------------------------------------------------- #
# Parallel paths: one driver, one non-driver
# --------------------------------------------------------------------------- #


class TestParallelPaths:
    def _build(self) -> ScheduleData:
        """
        Start(0d) ─┬─► LONG(10d) ───┐
                   │                ├─► TARGET(3d)
                   └─► SHORT(4d) ───┘

        LONG takes 10 working days, SHORT takes 4, so LONG is the
        driver of TARGET and SHORT has 6 working days of relative float.
        """
        tasks = [
            _task(1, "Start", duration=0.0, successors=[2, 3]),
            _task(2, "LONG", duration=10.0, predecessors=[1], successors=[4]),
            _task(3, "SHORT", duration=4.0, predecessors=[1], successors=[4]),
            _task(4, "TARGET", duration=3.0, predecessors=[2, 3]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=1, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=4),
            Relationship(predecessor_uid=3, successor_uid=4),
        ]
        return _schedule(tasks, rels)

    def test_long_path_is_driving(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        driving_uids = {n.uid for n in result.driving_chain}
        assert 2 in driving_uids  # LONG drives
        assert 1 in driving_uids  # Start is upstream of LONG, so it drives too

    def test_short_path_is_non_driving_with_six_day_relative_float(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        non_driving_uids = {n.uid for n in result.non_driving_paths}
        assert 3 in non_driving_uids
        short_node = next(n for n in result.non_driving_paths if n.uid == 3)
        # LONG's EF = 10, SHORT's EF = 4 → relative float = 6 working days.
        assert short_node.relative_float_days == pytest.approx(6.0)

    def test_non_driving_tasks_exceed_threshold_get_non_driving_category(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        # 6 days > NEAR_DRIVING_MAX_DAYS (5), so SHORT goes to non_driving.
        assert any(n.uid == 3 for n in result.non_driving_paths)
        assert not any(n.uid == 3 for n in result.near_driving_paths)


# --------------------------------------------------------------------------- #
# Near-driving parallel path: slack within the threshold
# --------------------------------------------------------------------------- #


class TestNearDrivingPath:
    def _build(self) -> ScheduleData:
        """
        Start ─┬─► DRIVER(10d) ───┐
               │                  ├─► TARGET(3d)
               └─► NEAR(7d) ──────┘

        NEAR has relative float = 3 working days (10 - 7). That falls
        inside the 1..5 day near-driving band.
        """
        tasks = [
            _task(1, "Start", duration=0.0, successors=[2, 3]),
            _task(2, "DRIVER", duration=10.0, predecessors=[1], successors=[4]),
            _task(3, "NEAR", duration=7.0, predecessors=[1], successors=[4]),
            _task(4, "TARGET", duration=3.0, predecessors=[2, 3]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=1, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=4),
            Relationship(predecessor_uid=3, successor_uid=4),
        ]
        return _schedule(tasks, rels)

    def test_near_driving_task_classified_correctly(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        near_uids = {n.uid for n in result.near_driving_paths}
        assert 3 in near_uids
        near_node = next(n for n in result.near_driving_paths if n.uid == 3)
        assert near_node.relative_float_days == pytest.approx(3.0)
        assert near_node.relative_float_days <= NEAR_DRIVING_MAX_DAYS


# --------------------------------------------------------------------------- #
# Forward trace
# --------------------------------------------------------------------------- #


class TestForwardTrace:
    def test_forward_trace_identifies_driven_successors(self):
        # Target drives one successor; the other successor's date is
        # controlled by a separate longer path.
        #
        #   TARGET(5d) ─────────► DRIVEN(3d)
        #   SIDE(12d) ───────────┘          (DRIVEN's driver)
        #   TARGET(5d) ─────────► INDEPENDENT(2d)
        tasks = [
            _task(1, "SIDE", duration=12.0, successors=[2]),
            _task(2, "TARGET", duration=5.0, successors=[3, 4]),
            _task(3, "SUCC_A", duration=3.0, predecessors=[1, 2]),
            _task(4, "SUCC_B", duration=2.0, predecessors=[2]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=4),
        ]
        schedule = _schedule(tasks, rels)
        result = analyze_driving_path(schedule, target_uid=2)

        # SUCC_B has only the target as its predecessor → target drives it.
        succ_b = next(f for f in result.forward_driven_tasks if f.uid == 4)
        assert succ_b.is_driven is True

        # SUCC_A has SIDE (12d) as its actual driver, so target is NOT driving it.
        succ_a = next(f for f in result.forward_driven_tasks if f.uid == 3)
        assert succ_a.is_driven is False

    def test_forward_trace_preserves_relationship_metadata(self):
        tasks = [
            _task(1, "TARGET", duration=5.0, successors=[2]),
            _task(2, "NEXT", duration=2.0, predecessors=[1]),
        ]
        rels = [
            Relationship(
                predecessor_uid=1, successor_uid=2, type="FS", lag_days=3.0
            )
        ]
        result = analyze_driving_path(_schedule(tasks, rels), target_uid=1)
        assert len(result.forward_driven_tasks) == 1
        f = result.forward_driven_tasks[0]
        assert f.relationship_type == "FS"
        assert f.lag_days == pytest.approx(3.0)
        assert f.is_driven is True


# --------------------------------------------------------------------------- #
# Termination conditions
# --------------------------------------------------------------------------- #


class TestTerminationConditions:
    def test_completed_predecessor_stops_the_chain(self):
        # T1 is 100% complete → trace should not include T1 or anything
        # upstream of T1.
        tasks = [
            _task(1, "Done", duration=5.0, percent_complete=100.0, successors=[2]),
            _task(2, "Target", duration=3.0, predecessors=[1]),
        ]
        rels = [Relationship(predecessor_uid=1, successor_uid=2)]
        result = analyze_driving_path(_schedule(tasks, rels), target_uid=2)
        assert result.driving_chain == []

    def test_target_with_no_predecessors_returns_empty_chain(self):
        tasks = [_task(1, "Only", duration=5.0)]
        result = analyze_driving_path(_schedule(tasks, []), target_uid=1)
        assert result.driving_chain == []
        assert result.near_driving_paths == []
        assert result.non_driving_paths == []

    def test_unknown_target_raises(self):
        tasks = [_task(1, "Only", duration=5.0)]
        with pytest.raises(ValueError):
            analyze_driving_path(_schedule(tasks, []), target_uid=999)
