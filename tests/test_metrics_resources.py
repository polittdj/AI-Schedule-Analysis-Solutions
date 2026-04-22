"""Unit tests for ``app.metrics.resources`` — DCMA Metric 10.

Threshold authority: ``dcma-14-point-assessment §4.10``; DECM sheet
*Metrics*, Guideline 6 (Resources row — no published pass/fail
threshold). BUILD-PLAN §5 M6 AC 5 pins ``pass_flag``/severity to
the indicator state (``Severity.WARN``).
"""

from __future__ import annotations

from app.metrics.base import Severity
from app.metrics.options import MetricOptions
from app.metrics.resources import ResourcesMetric, run_resources
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.metric_schedules import (
    resources_all_assigned_schedule,
    resources_all_missing_schedule,
    resources_empty_schedule,
    resources_excluded_population_schedule,
    resources_half_missing_schedule,
)


class TestIndicatorStateAlwaysWarn:
    """AC 5 — severity is ``Severity.WARN`` regardless of the ratio.
    There is no pass/fail bar for Metric 10."""

    def test_all_assigned_is_warn_not_pass(self) -> None:
        result = run_resources(resources_all_assigned_schedule())
        assert result.severity is Severity.WARN
        assert result.numerator == 0
        assert result.denominator == 10

    def test_all_missing_is_warn_not_fail(self) -> None:
        result = run_resources(resources_all_missing_schedule())
        assert result.severity is Severity.WARN
        assert result.numerator == 10
        assert result.denominator == 10
        assert result.computed_value == 100.0

    def test_half_missing_reports_50_percent_warn(self) -> None:
        result = run_resources(resources_half_missing_schedule())
        assert result.severity is Severity.WARN
        assert result.numerator == 10
        assert result.denominator == 20
        assert result.computed_value == 50.0

    def test_empty_schedule_reports_warn_with_note(self) -> None:
        result = run_resources(resources_empty_schedule())
        assert result.severity is Severity.WARN
        assert result.denominator == 0
        assert "indicator-only" in result.notes


class TestThresholdCarrierIsIndicatorOnly:
    """The ThresholdConfig stays schema-stable but is annotated as
    an indicator-only carrier so downstream renderers don't
    misrepresent the metric as "passed at 0%" or similar."""

    def test_threshold_direction_is_indicator_only(self) -> None:
        result = run_resources(resources_all_missing_schedule())
        assert result.threshold.direction == "indicator-only"
        assert result.threshold.value == 0.0
        assert result.threshold.is_overridden is False

    def test_threshold_carries_skill_and_decm_citation(self) -> None:
        result = run_resources(resources_all_assigned_schedule())
        assert result.threshold.source_skill_section == (
            "dcma-14-point-assessment §4.10"
        )
        assert "Resources" in result.threshold.source_decm_row
        assert "no pass/fail threshold" in result.threshold.source_decm_row


class TestExclusionProtocol:
    """§3 exclusions drop summary / LOE / 100%-complete tasks from
    both the numerator and the denominator."""

    def test_excluded_zero_resource_tasks_do_not_flag(self) -> None:
        result = run_resources(
            resources_excluded_population_schedule()
        )
        # 3 excluded (each with resource_count=0) + 2 eligible (each
        # with resource_count=1) → 0/2 = 0% ratio.
        assert result.denominator == 2
        assert result.numerator == 0
        assert result.computed_value == 0.0

    def test_disabling_exclude_completed_reintroduces_done_task(self) -> None:
        result = run_resources(
            resources_excluded_population_schedule(),
            MetricOptions(exclude_completed=False),
        )
        # The completed zero-resource task is now in the pool.
        assert result.denominator == 3  # +1 done task
        assert result.numerator == 1


class TestOffenderListDetails:
    """AC 6 — every offender carries unique_id + name + a
    metric-specific evidence field."""

    def test_every_offender_carries_name_and_evidence(self) -> None:
        result = run_resources(resources_half_missing_schedule())
        for o in result.offenders:
            assert o.unique_id > 0
            assert o.name
            assert o.value == "resource_count=0"

    def test_offender_uids_are_the_zero_resource_tasks(self) -> None:
        result = run_resources(resources_half_missing_schedule())
        offender_uids = sorted(o.unique_id for o in result.offenders)
        # Even UIDs carry resource_count=0 in the half-missing fixture.
        assert offender_uids == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]


class TestLoeByNameFallback:
    def test_loe_name_pattern_fallback_excludes_task(self) -> None:
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="loe-name",
            tasks=[
                Task(
                    unique_id=1, task_id=1,
                    name="Level of Effort — task",
                    duration_minutes=480, resource_count=0,
                ),
                Task(
                    unique_id=2, task_id=2, name="Live",
                    duration_minutes=480, resource_count=1,
                ),
            ],
        )
        result = run_resources(
            sched, MetricOptions(loe_name_patterns=("level of effort",))
        )
        assert result.denominator == 1
        assert result.numerator == 0


class TestFrozenContract:
    def test_two_invocations_produce_equal_results(self) -> None:
        s1 = resources_half_missing_schedule()
        s2 = resources_half_missing_schedule()
        assert run_resources(s1) == run_resources(s2)

    def test_schedule_not_mutated(self) -> None:
        sched = resources_half_missing_schedule()
        before = sched.model_dump_json()
        run_resources(sched)
        assert sched.model_dump_json() == before

    def test_class_wrapper_matches_function(self) -> None:
        sched = resources_half_missing_schedule()
        assert ResourcesMetric().run(sched) == run_resources(sched)


def test_notes_cite_skill_section_for_narrative_layer() -> None:
    result = run_resources(resources_half_missing_schedule())
    assert "dcma-14-point-assessment §4.10" in result.notes
