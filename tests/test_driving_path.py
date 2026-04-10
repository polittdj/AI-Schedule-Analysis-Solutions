"""Unit tests for the tiered driving-path analysis engine.

The engine classifies every predecessor into one of four tiers based
on its relative float to the target task:

* **Primary**    — relative float == 0 (the actual driver chain)
* **Secondary**  — 0 < relative float <= 15 working days
* **Tertiary**   — 15 < relative float <= 30 working days
* **Non-critical** — relative float > 30 working days

Covers the original three required scenarios plus tier-specific
assertions and the UID-filter helper used by the task focus view.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pytest

from app.engine.driving_path import (
    SECONDARY_TIER_MAX_DAYS,
    TERTIARY_TIER_MAX_DAYS,
    TIER_NON_CRITICAL,
    TIER_PRIMARY,
    TIER_SECONDARY,
    TIER_TERTIARY,
    DrivingPathResults,
    analyze_driving_path,
    classify_tier,
    filter_engine_results_by_uids,
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
# classify_tier direct tests
# --------------------------------------------------------------------------- #


class TestClassifyTier:
    def test_zero_is_primary(self):
        assert classify_tier(0.0) == TIER_PRIMARY
        assert classify_tier(0.005) == TIER_PRIMARY

    def test_one_day_is_secondary(self):
        assert classify_tier(1.0) == TIER_SECONDARY

    def test_fifteen_days_is_secondary_boundary(self):
        assert classify_tier(15.0) == TIER_SECONDARY

    def test_sixteen_days_is_tertiary(self):
        assert classify_tier(16.0) == TIER_TERTIARY

    def test_thirty_days_is_tertiary_boundary(self):
        assert classify_tier(30.0) == TIER_TERTIARY

    def test_thirty_one_is_non_critical(self):
        assert classify_tier(31.0) == TIER_NON_CRITICAL

    def test_one_hundred_is_non_critical(self):
        assert classify_tier(100.0) == TIER_NON_CRITICAL


# --------------------------------------------------------------------------- #
# Linear chain: every predecessor is a primary driver
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

    def test_every_upstream_task_is_on_primary_critical_path(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        assert isinstance(result, DrivingPathResults)
        assert result.target_uid == 4
        primary_uids = {n.uid for n in result.primary_critical_path}
        # T3, T2, T1 all drive T4 in a linear chain.
        assert primary_uids == {1, 2, 3}
        for node in result.primary_critical_path:
            assert node.tier == TIER_PRIMARY
            assert node.driving is True
            assert node.relative_float_days == pytest.approx(0.0)

    def test_linear_chain_has_no_other_tiers(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        assert result.secondary_critical_path == []
        assert result.tertiary_critical_path == []
        assert result.non_critical_paths == []

    def test_relationship_metadata_preserved(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        for node in result.primary_critical_path:
            assert node.relationship_type == "FS"
            assert node.lag_days == pytest.approx(0.0)

    def test_depth_increases_walking_backward(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        depth_by_uid = {n.uid: n.depth for n in result.primary_critical_path}
        assert depth_by_uid[3] == 1
        assert depth_by_uid[2] == 2
        assert depth_by_uid[1] == 3

    def test_all_chain_uids_includes_target(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        assert 4 in result.all_chain_uids
        assert set(result.all_chain_uids) == {1, 2, 3, 4}


# --------------------------------------------------------------------------- #
# Parallel paths with secondary tier
# --------------------------------------------------------------------------- #


class TestSecondaryTier:
    def _build(self) -> ScheduleData:
        """
        Start(0d) ─┬─► LONG(10d) ───┐
                   │                ├─► TARGET(3d)
                   └─► SHORT(4d) ───┘

        LONG is 10 days, SHORT is 4 days, so SHORT has 6 working days
        of relative float to the target. 6 falls inside the secondary
        band (0 < rf ≤ 15).
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

    def test_long_path_is_on_primary(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        primary_uids = {n.uid for n in result.primary_critical_path}
        assert 2 in primary_uids
        assert 1 in primary_uids  # Start feeds LONG and is also primary

    def test_short_path_is_on_secondary_with_six_days_relative_float(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        secondary_uids = {n.uid for n in result.secondary_critical_path}
        assert 3 in secondary_uids
        short_node = next(n for n in result.secondary_critical_path if n.uid == 3)
        assert short_node.tier == TIER_SECONDARY
        assert short_node.relative_float_days == pytest.approx(6.0)

    def test_secondary_stays_within_band(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        for n in result.secondary_critical_path:
            assert 0 < n.relative_float_days <= SECONDARY_TIER_MAX_DAYS


# --------------------------------------------------------------------------- #
# Parallel paths with tertiary tier
# --------------------------------------------------------------------------- #


class TestTertiaryTier:
    def _build(self) -> ScheduleData:
        """
        Start ─┬─► LONG(30d) ───┐
               │                ├─► TARGET(3d)
               └─► MEDIUM(10d) ─┘

        MEDIUM has 20 working days of relative float to TARGET.
        20 falls inside the tertiary band (15 < rf ≤ 30).
        """
        tasks = [
            _task(1, "Start", duration=0.0, successors=[2, 3]),
            _task(2, "LONG", duration=30.0, predecessors=[1], successors=[4]),
            _task(3, "MEDIUM", duration=10.0, predecessors=[1], successors=[4]),
            _task(4, "TARGET", duration=3.0, predecessors=[2, 3]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=1, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=4),
            Relationship(predecessor_uid=3, successor_uid=4),
        ]
        return _schedule(tasks, rels)

    def test_medium_path_is_tertiary(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        tertiary_uids = {n.uid for n in result.tertiary_critical_path}
        assert 3 in tertiary_uids
        medium = next(n for n in result.tertiary_critical_path if n.uid == 3)
        assert medium.tier == TIER_TERTIARY
        assert medium.relative_float_days == pytest.approx(20.0)
        assert SECONDARY_TIER_MAX_DAYS < medium.relative_float_days <= TERTIARY_TIER_MAX_DAYS


# --------------------------------------------------------------------------- #
# Non-critical tier (> 30 days)
# --------------------------------------------------------------------------- #


class TestNonCriticalTier:
    def _build(self) -> ScheduleData:
        """
        Start ─┬─► LONG(50d) ───┐
               │                ├─► TARGET(3d)
               └─► BRIEF(2d) ───┘

        BRIEF has 48 working days of relative float to TARGET,
        which is beyond both the secondary (15) and tertiary (30)
        thresholds.
        """
        tasks = [
            _task(1, "Start", duration=0.0, successors=[2, 3]),
            _task(2, "LONG", duration=50.0, predecessors=[1], successors=[4]),
            _task(3, "BRIEF", duration=2.0, predecessors=[1], successors=[4]),
            _task(4, "TARGET", duration=3.0, predecessors=[2, 3]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=2),
            Relationship(predecessor_uid=1, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=4),
            Relationship(predecessor_uid=3, successor_uid=4),
        ]
        return _schedule(tasks, rels)

    def test_brief_path_is_non_critical(self):
        result = analyze_driving_path(self._build(), target_uid=4)
        nc_uids = {n.uid for n in result.non_critical_paths}
        assert 3 in nc_uids
        brief = next(n for n in result.non_critical_paths if n.uid == 3)
        assert brief.tier == TIER_NON_CRITICAL
        assert brief.relative_float_days > TERTIARY_TIER_MAX_DAYS


# --------------------------------------------------------------------------- #
# Forward trace
# --------------------------------------------------------------------------- #


class TestForwardTrace:
    def test_forward_trace_identifies_driven_successors(self):
        tasks = [
            _task(1, "SIDE", duration=12.0, successors=[3]),
            _task(2, "TARGET", duration=5.0, successors=[3, 4]),
            _task(3, "SUCC_A", duration=3.0, predecessors=[1, 2]),
            _task(4, "SUCC_B", duration=2.0, predecessors=[2]),
        ]
        rels = [
            Relationship(predecessor_uid=1, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=3),
            Relationship(predecessor_uid=2, successor_uid=4),
        ]
        result = analyze_driving_path(_schedule(tasks, rels), target_uid=2)

        succ_b = next(f for f in result.forward_driven_tasks if f.uid == 4)
        assert succ_b.is_driven is True

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
        tasks = [
            _task(1, "Done", duration=5.0, percent_complete=100.0, successors=[2]),
            _task(2, "Target", duration=3.0, predecessors=[1]),
        ]
        rels = [Relationship(predecessor_uid=1, successor_uid=2)]
        result = analyze_driving_path(_schedule(tasks, rels), target_uid=2)
        assert result.primary_critical_path == []
        assert result.secondary_critical_path == []

    def test_target_with_no_predecessors_returns_empty_chain(self):
        tasks = [_task(1, "Only", duration=5.0)]
        result = analyze_driving_path(_schedule(tasks, []), target_uid=1)
        assert result.primary_critical_path == []
        assert result.secondary_critical_path == []
        assert result.tertiary_critical_path == []
        assert result.non_critical_paths == []
        assert result.all_chain_uids == [1]

    def test_unknown_target_raises(self):
        tasks = [_task(1, "Only", duration=5.0)]
        with pytest.raises(ValueError):
            analyze_driving_path(_schedule(tasks, []), target_uid=999)


# --------------------------------------------------------------------------- #
# filter_engine_results_by_uids — UID-centric filter for the task view
# --------------------------------------------------------------------------- #


class TestFilterEngineResultsByUids:
    def test_filter_keeps_only_chain_task_deltas(self):
        from app.engine.comparator import compare_schedules

        def _full_task(uid, name, start, finish, pct=0.0):
            return TaskData(
                uid=uid,
                id=uid,
                name=name,
                duration=5.0,
                start=start,
                finish=finish,
                baseline_start=start,
                baseline_finish=finish,
                percent_complete=pct,
            )

        prior = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                _full_task(1, "A", datetime(2026, 1, 1), datetime(2026, 1, 6)),
                _full_task(2, "B", datetime(2026, 1, 7), datetime(2026, 1, 12)),
                _full_task(3, "C", datetime(2026, 1, 13), datetime(2026, 1, 18)),
            ],
        )
        later = ScheduleData(
            project_info=ProjectInfo(),
            tasks=[
                _full_task(1, "A", datetime(2026, 1, 1), datetime(2026, 1, 6)),
                _full_task(2, "B", datetime(2026, 1, 10), datetime(2026, 1, 15)),
                _full_task(3, "C", datetime(2026, 1, 16), datetime(2026, 1, 21)),
            ],
        )
        comparison = compare_schedules(prior, later)
        results = {"comparison": comparison}

        chain_uids = {2}  # only task B is in the chain
        filtered = filter_engine_results_by_uids(results, chain_uids)
        assert len(filtered["filtered_task_deltas"]) == 1
        assert filtered["filtered_task_deltas"][0].uid == 2

    def test_filter_returns_empty_when_no_comparison(self):
        filtered = filter_engine_results_by_uids({}, {1, 2, 3})
        assert filtered["filtered_task_deltas"] == []
        assert filtered["filtered_manipulation_findings"] == []
        assert filtered["filtered_float_changes"] == []
        assert filtered["filtered_dcma_metrics"] == []

    def test_filter_handles_empty_chain_gracefully(self):
        filtered = filter_engine_results_by_uids({"comparison": None}, set())
        # Empty chain → returns the input dict untouched (no filtering keys added)
        assert "filtered_task_deltas" not in filtered
