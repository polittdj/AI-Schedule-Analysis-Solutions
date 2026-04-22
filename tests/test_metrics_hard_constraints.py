"""Unit tests for ``app.metrics.hard_constraints`` — DCMA Metric 5.

Threshold authority: ``dcma-14-point-assessment §4.5``; DECM sheet
*Metrics*, Guideline 6 (Hard Constraints row). Boundary and gotcha
coverage traces back to BUILD-PLAN §5 M6 AC 1 (09NOV09 four-
constraint list) and AC 6 (offender provenance).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.metrics.base import Severity
from app.metrics.exceptions import InvalidThresholdError
from app.metrics.hard_constraints import (
    HardConstraintsMetric,
    run_hard_constraints,
)
from app.metrics.options import MetricOptions
from app.models.enums import HARD_CONSTRAINTS, ConstraintType
from app.models.schedule import Schedule
from app.models.task import Task
from tests.fixtures.metric_schedules import (
    empty_schedule,
    hard_constraints_boundary_schedule,
    hard_constraints_excluded_population_schedule,
    hard_constraints_golden_fail_schedule,
    hard_constraints_pass_schedule,
)


class TestEmptyAndExcluded:
    """Vacuous-PASS paths — empty schedule and all-excluded schedule."""

    def test_empty_schedule_passes_vacuously(self) -> None:
        result = run_hard_constraints(empty_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 0
        assert result.computed_value == 0.0
        assert "no eligible tasks" in result.notes

    def test_all_excluded_passes_vacuously(self) -> None:
        """A schedule where every task is summary / LOE / 100%
        complete collapses to denominator 0 → vacuous PASS."""
        cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="all-excluded",
            tasks=[
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
                    name="Done FNLT",
                    duration_minutes=480,
                    percent_complete=100.0,
                    constraint_type=ConstraintType.FINISH_NO_LATER_THAN,
                    constraint_date=cd,
                ),
            ],
        )
        result = run_hard_constraints(sched)
        assert result.severity is Severity.PASS
        assert result.denominator == 0


class TestHappyPath:
    """The metric passes when no hard constraints are present."""

    def test_pass_schedule(self) -> None:
        result = run_hard_constraints(hard_constraints_pass_schedule())
        assert result.severity is Severity.PASS
        assert result.numerator == 0
        assert result.denominator == 20
        assert result.computed_value == 0.0
        assert result.offenders == ()


class TestGoldenFail:
    """Hand-calculable fail — 4/20 = 20% > 5%."""

    def test_golden_fail_ratio(self) -> None:
        result = run_hard_constraints(hard_constraints_golden_fail_schedule())
        assert result.severity is Severity.FAIL
        assert result.numerator == 4
        assert result.denominator == 20
        assert result.computed_value == pytest.approx(20.0)

    def test_only_four_hard_types_counted(self) -> None:
        """SNET, FNET, ALAP, ASAP must NOT appear as offenders — only
        the 09NOV09 four (MSO, MFO, SNLT, FNLT). BUILD-PLAN AC 1."""
        result = run_hard_constraints(hard_constraints_golden_fail_schedule())
        flagged_kinds = {o.value for o in result.offenders}
        assert flagged_kinds == {"MUST_START_ON", "MUST_FINISH_ON",
                                 "START_NO_LATER_THAN",
                                 "FINISH_NO_LATER_THAN"}

    def test_offender_uids_are_deterministic(self) -> None:
        """Offender list is in UniqueID insertion order; UIDs 1..4
        carry the four hard constraints in the fixture."""
        result = run_hard_constraints(hard_constraints_golden_fail_schedule())
        offender_uids = [o.unique_id for o in result.offenders]
        assert offender_uids == [1, 2, 3, 4]

    def test_offenders_carry_name_and_kind(self) -> None:
        """Every offender row carries unique_id, name, and the
        constraint kind as the value (BUILD-PLAN AC 6 + §6 AC bar
        #3)."""
        result = run_hard_constraints(hard_constraints_golden_fail_schedule())
        for o in result.offenders:
            assert o.unique_id > 0
            assert o.name
            assert o.value in {
                ConstraintType.MUST_START_ON.name,
                ConstraintType.MUST_FINISH_ON.name,
                ConstraintType.START_NO_LATER_THAN.name,
                ConstraintType.FINISH_NO_LATER_THAN.name,
            }


class TestBoundary:
    """Threshold boundary — at exactly 5% the metric passes."""

    def test_boundary_exactly_five_percent_passes(self) -> None:
        result = run_hard_constraints(hard_constraints_boundary_schedule())
        assert result.numerator == 1
        assert result.denominator == 20
        assert result.computed_value == pytest.approx(5.0)
        # Threshold is <= 5%, so 5% exactly PASSES.
        assert result.severity is Severity.PASS

    def test_custom_threshold_stricter_flips_pass_to_fail(self) -> None:
        """A client whose acceptance criterion is 4% turns the 5%
        boundary case into FAIL."""
        result = run_hard_constraints(
            hard_constraints_boundary_schedule(),
            MetricOptions(hard_constraints_threshold_pct=4.0),
        )
        assert result.severity is Severity.FAIL
        assert result.threshold.is_overridden is True
        assert result.threshold.value == 4.0


class TestDefaultExclusions:
    """§3 exclusions (summary / LOE / completed) drop offenders from
    the numerator AND the denominator."""

    def test_excluded_hard_constrained_tasks_do_not_flag(self) -> None:
        result = run_hard_constraints(
            hard_constraints_excluded_population_schedule()
        )
        assert result.severity is Severity.PASS
        # 3 excluded hard-constrained tasks + 2 eligible plain tasks.
        assert result.denominator == 2
        assert result.numerator == 0

    def test_turning_off_exclude_summary_reintroduces_them(self) -> None:
        """With exclude_summary=False, the summary MSO task lands in
        both the numerator and the denominator."""
        result = run_hard_constraints(
            hard_constraints_excluded_population_schedule(),
            MetricOptions(exclude_summary=False),
        )
        assert result.denominator == 3  # 1 summary + 2 plain
        assert result.numerator == 1  # the summary-flagged MSO
        assert any(o.name == "Summary MSO" for o in result.offenders)


class TestAlapAndSoftConstraintsExcluded:
    """AC 1 — ALAP, SNET, and FNET never count toward the numerator."""

    @pytest.mark.parametrize(
        "constraint_type",
        [
            ConstraintType.AS_SOON_AS_POSSIBLE,
            ConstraintType.AS_LATE_AS_POSSIBLE,
            ConstraintType.START_NO_EARLIER_THAN,
            ConstraintType.FINISH_NO_EARLIER_THAN,
        ],
    )
    def test_non_hard_constraint_type_does_not_flag(
        self, constraint_type: ConstraintType
    ) -> None:
        needs_date = constraint_type in {
            ConstraintType.START_NO_EARLIER_THAN,
            ConstraintType.FINISH_NO_EARLIER_THAN,
        }
        cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC) if needs_date else None
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="single",
            tasks=[
                Task(
                    unique_id=1,
                    task_id=1,
                    name="Solo",
                    duration_minutes=480,
                    constraint_type=constraint_type,
                    constraint_date=cd,
                ),
            ],
        )
        result = run_hard_constraints(sched)
        assert result.numerator == 0
        assert result.offenders == ()


class TestFrozenContractAndProvenance:
    """CM3 / CM4 / M5 CM5 — determinism, no mutation, citation."""

    def test_result_carries_skill_and_decm_citation(self) -> None:
        result = run_hard_constraints(hard_constraints_golden_fail_schedule())
        assert result.threshold.source_skill_section == (
            "dcma-14-point-assessment §4.5"
        )
        assert "Hard Constraints" in result.threshold.source_decm_row

    def test_two_invocations_produce_equal_results(self) -> None:
        s1 = hard_constraints_golden_fail_schedule()
        s2 = hard_constraints_golden_fail_schedule()
        r1 = run_hard_constraints(s1)
        r2 = run_hard_constraints(s2)
        assert r1 == r2

    def test_schedule_not_mutated(self) -> None:
        sched = hard_constraints_golden_fail_schedule()
        before = sched.model_dump_json()
        run_hard_constraints(sched)
        assert sched.model_dump_json() == before

    def test_class_wrapper_matches_function(self) -> None:
        sched = hard_constraints_golden_fail_schedule()
        assert HardConstraintsMetric().run(sched) == run_hard_constraints(sched)


class TestLoeByNameFallback:
    """Closes the LOE name-pattern fallback branch in
    :func:`app.metrics.hard_constraints._is_loe` (lines 74-75)."""

    def test_loe_name_pattern_fallback_excludes_task(self) -> None:
        cd = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
        sched = Schedule(
            project_calendar_hours_per_day=8.0,
            name="loe-name",
            tasks=[
                Task(
                    unique_id=1, task_id=1,
                    name="Project Management LOE",
                    duration_minutes=480,
                    constraint_type=ConstraintType.MUST_START_ON,
                    constraint_date=cd,
                ),
                Task(unique_id=2, task_id=2, name="Live", duration_minutes=480),
            ],
        )
        result = run_hard_constraints(
            sched, MetricOptions(loe_name_patterns=("loe",)),
        )
        # The LOE-by-name task (MSO) is excluded → denominator=1,
        # numerator=0, PASS.
        assert result.denominator == 1
        assert result.numerator == 0
        assert result.severity is Severity.PASS


class TestInvalidOptions:
    """A structurally invalid override raises InvalidThresholdError."""

    def test_negative_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(hard_constraints_threshold_pct=-1.0)

    def test_over_100_threshold_rejected(self) -> None:
        with pytest.raises(InvalidThresholdError):
            MetricOptions(hard_constraints_threshold_pct=150.0)


def test_hard_constraints_enum_frozen_to_four() -> None:
    """Belt-and-suspenders: HARD_CONSTRAINTS must be exactly the four
    09NOV09 types. If someone edits enums.py to add SNET, the metric
    test fleet catches it."""
    assert HARD_CONSTRAINTS == frozenset(
        {
            ConstraintType.MUST_START_ON,
            ConstraintType.MUST_FINISH_ON,
            ConstraintType.START_NO_LATER_THAN,
            ConstraintType.FINISH_NO_LATER_THAN,
        }
    )
