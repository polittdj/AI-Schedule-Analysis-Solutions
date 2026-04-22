"""Unit tests for ``app.metrics.logic`` — DCMA Metric 1 (Missing Logic).

Covers gotchas L1–L7 from the M5 spec, plus the cross-metric rules
CM1, CM3, CM4 that apply to every metric.

Threshold authority: ``dcma-14-point-assessment §4.1``;
DeltekDECMMetricsJan2022.xlsx row 06A204b (Guideline 6, row 32).
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.base import Severity
from app.metrics.logic import LogicMetric, run_logic
from app.metrics.options import MetricOptions
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.metric_schedules import (
    all_complete_schedule,
    empty_schedule,
    logic_golden_fail_schedule,
    logic_loe_by_name_schedule,
    logic_pass_schedule,
    logic_summary_loe_completed_schedule,
)


class TestEmptyAndAllComplete:
    """L5, L6 — vacuous PASS for empty / all-complete schedules."""

    def test_empty_schedule_passes_vacuously(self) -> None:
        result = run_logic(empty_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 0
        assert result.computed_value == 0.0
        assert "no eligible tasks" in result.notes

    def test_all_complete_passes_vacuously(self) -> None:
        result = run_logic(all_complete_schedule())
        assert result.severity is Severity.PASS
        assert result.denominator == 0


class TestEndpointExclusion:
    """L1 — project start/finish milestones are not flagged."""

    def test_endpoint_milestones_not_flagged(self) -> None:
        result = run_logic(logic_pass_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        # Eligible = T1..T10 (10). Endpoint UIDs (100, 200) are
        # milestones; the structural endpoint detector excludes them
        # from the population.
        assert result.denominator == 10

    def test_endpoint_detection_works_without_predecessors(self) -> None:
        """A milestone with no predecessor and no successor is also
        an endpoint pair (degenerate single-task project)."""
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            tasks=[
                Task(
                    unique_id=1,
                    task_id=1,
                    name="Solo",
                    duration_minutes=0,
                    is_milestone=True,
                ),
            ],
            relations=[],
        )
        result = run_logic(sched)
        # The single milestone is detected as an endpoint -> excluded.
        assert result.numerator == 0
        assert result.denominator == 0


class TestExclusions:
    """L2, L3, L4 — summary, LOE, and 100%-complete tasks excluded."""

    def test_summary_loe_completed_pass(self) -> None:
        result = run_logic(logic_summary_loe_completed_schedule())
        # Eligible: T4 + T5 (linked pair). Numerator: 0. PASS.
        assert result.severity is Severity.PASS
        assert result.denominator == 2
        assert result.numerator == 0

    def test_loe_name_pattern_opt_in(self) -> None:
        sched = logic_loe_by_name_schedule()
        # Without name opt-in: T1 (no flag, no link) flags as missing
        # both → 1 / 3 = 33% FAIL.
        baseline = run_logic(sched)
        assert baseline.severity is Severity.FAIL
        assert baseline.denominator == 3
        # Opt-in name pattern: T1 is excluded, eligible = 2, no
        # offenders → PASS.
        opts = MetricOptions(loe_name_patterns=("loe",))
        result = run_logic(sched, opts)
        assert result.severity is Severity.PASS
        assert result.denominator == 2

    def test_disabling_completed_exclusion_includes_them(self) -> None:
        opts = MetricOptions(exclude_completed=False)
        result = run_logic(all_complete_schedule(), opts)
        # T1 missing pred (it's the chain start, not a milestone, so
        # no endpoint exclusion); T3 missing succ; T2 OK.
        assert result.severity is Severity.FAIL
        assert result.denominator == 3
        assert result.numerator == 2


class TestThresholdOverride:
    """L7 — MetricOptions.logic_threshold_pct override."""

    def test_default_5pct_fails_at_20pct(self) -> None:
        result = run_logic(logic_golden_fail_schedule())
        assert result.severity is Severity.FAIL
        assert result.computed_value == 20.0

    def test_override_25pct_passes_at_20pct(self) -> None:
        opts = MetricOptions(logic_threshold_pct=25.0)
        result = run_logic(logic_golden_fail_schedule(), opts)
        assert result.severity is Severity.PASS
        assert result.threshold.value == 25.0
        assert result.threshold.is_overridden is True

    def test_default_threshold_not_marked_overridden(self) -> None:
        result = run_logic(logic_pass_schedule())
        assert result.threshold.is_overridden is False


class TestGoldenFail:
    """A6 golden — 10-task fixture, 2 missing predecessors → 20% FAIL.

    Hand-calc: detached T1 and T2 each contribute one offender. The
    chain runs Start → T3 → T4 → ... → T10 → Finish; Start and
    Finish are endpoint milestones, excluded by §4.1. Eligible
    population is T1..T10 = 10 tasks. 2 / 10 = 20% > 5% → FAIL.
    """

    def test_golden_fail_arithmetic(self) -> None:
        result = run_logic(logic_golden_fail_schedule())
        assert result.numerator == 2
        assert result.denominator == 10
        assert result.computed_value == 20.0
        assert result.severity is Severity.FAIL

    def test_golden_offenders_are_t1_and_t2(self) -> None:
        result = run_logic(logic_golden_fail_schedule())
        offender_uids = {o.unique_id for o in result.offenders}
        assert offender_uids == {1, 2}
        for o in result.offenders:
            assert "missing" in o.value


class TestCrossMetricInvariants:
    """CM1, CM3, CM4 applied to Logic."""

    def test_result_is_immutable(self) -> None:
        result = run_logic(logic_pass_schedule())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.severity = Severity.FAIL  # type: ignore[misc]

    def test_byte_equal_results_on_repeat(self) -> None:
        sched = logic_golden_fail_schedule()
        a = run_logic(sched)
        b = run_logic(sched)
        assert a == b

    def test_no_relations_does_not_crash(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            tasks=[
                Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
            ],
            relations=[],
        )
        result = run_logic(sched)
        # Single non-milestone task with no predecessors and no
        # successors → 1/1 = 100% FAIL but no crash.
        assert result.severity is Severity.FAIL
        assert result.computed_value == 100.0

    def test_carries_decm_citation(self) -> None:
        result = run_logic(logic_pass_schedule())
        assert "06A204b" in result.threshold.source_decm_row
        assert "§4.1" in result.threshold.source_skill_section


class TestLogicMetricClass:
    def test_class_wrapper_matches_function(self) -> None:
        sched = logic_golden_fail_schedule()
        f_result = run_logic(sched)
        c_result = LogicMetric().run(sched)
        assert f_result == c_result


class TestRelationDirectionality:
    """Ensure the metric counts predecessor and successor sides
    independently — a task with one outgoing FS but no incoming link
    should flag as missing-predecessor only, not both."""

    def test_one_sided_flags_correctly(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            tasks=[
                Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
                Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
            ],
            relations=[
                Relation(
                    predecessor_unique_id=1,
                    successor_unique_id=2,
                    relation_type=RelationType.FS,
                )
            ],
        )
        result = run_logic(sched)
        # T1 missing pred only; T2 missing succ only. Both flag.
        labels = {o.unique_id: o.value for o in result.offenders}
        assert labels[1] == "missing_predecessor"
        assert labels[2] == "missing_successor"
