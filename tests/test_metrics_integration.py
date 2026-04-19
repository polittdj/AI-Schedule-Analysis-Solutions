"""Integration test for M5 + M6 — all nine DCMA metrics on a single
realistic fixture (BUILD-PLAN §5 M5 AC7 extended by M6 Block 7).

Also exercises the M4 ``complex_with_exceptions`` schedule to prove
the metric layer composes cleanly with the engine fixtures already
in the suite (no regression on the 573-test M5 baseline).
"""

from __future__ import annotations

from app.engine.result import CPMResult
from app.metrics import (
    MetricResult,
    Severity,
    run_bei,
    run_cpli,
    run_critical_path_test,
    run_hard_constraints,
    run_high_duration,
    run_high_float,
    run_invalid_dates,
    run_lags,
    run_leads,
    run_logic,
    run_missed_tasks,
    run_negative_float,
    run_relationship_types,
    run_resources,
)
from app.models.schedule import Schedule
from tests._utils import cpm_result_snapshot
from tests.fixtures.metric_schedules import (
    integration_schedule,
    m6_integration_schedule,
    m7_integration_schedule,
)
from tests.fixtures.schedules import complex_with_exceptions

# ---------------------------------------------------------------------------
# M5 baseline — unchanged from the M5 PR (no regression)
# ---------------------------------------------------------------------------


def _run_m5(schedule: Schedule) -> dict[str, MetricResult]:
    return {
        "DCMA-1": run_logic(schedule),
        "DCMA-2": run_leads(schedule),
        "DCMA-3": run_lags(schedule),
        "DCMA-4": run_relationship_types(schedule),
    }


class TestIntegrationOnSyntheticSchedule:
    """A7 — all four M5 metrics still return MetricResult with
    expected severity against the M5 integration fixture."""

    def test_all_four_metrics_run(self) -> None:
        results = _run_m5(integration_schedule())
        assert set(results.keys()) == {"DCMA-1", "DCMA-2", "DCMA-3", "DCMA-4"}
        for r in results.values():
            assert isinstance(r, MetricResult)

    def test_logic_fail_with_detached_tasks(self) -> None:
        result = run_logic(integration_schedule())
        assert result.severity is Severity.FAIL
        offender_uids = {o.unique_id for o in result.offenders}
        assert {19, 20}.issubset(offender_uids)
        assert result.numerator == 2
        assert result.denominator == 20

    def test_leads_fail_with_negative_lag_offender(self) -> None:
        result = run_leads(integration_schedule())
        assert result.severity is Severity.FAIL
        assert any("-480" in o.value for o in result.offenders)

    def test_lags_fail(self) -> None:
        result = run_lags(integration_schedule())
        assert result.severity is Severity.FAIL
        assert result.numerator == 2
        assert result.denominator == 18

    def test_relationship_types_fail_below_90pct(self) -> None:
        result = run_relationship_types(integration_schedule())
        assert result.severity is Severity.FAIL
        assert result.numerator == 15
        assert result.denominator == 19
        assert result.computed_value < 90.0

    def test_every_result_carries_provenance(self) -> None:
        results = _run_m5(integration_schedule())
        for metric_id, r in results.items():
            assert r.metric_id == metric_id
            assert r.threshold.source_skill_section
            assert r.threshold.source_decm_row


class TestComposesWithEngineFixture:
    """Sanity check — running the M5 metrics over an M4 fixture
    surfaces no exceptions and produces interpretable results."""

    def test_complex_engine_fixture_runs_clean(self) -> None:
        sched = complex_with_exceptions()
        results = _run_m5(sched)
        for r in results.values():
            assert r.severity in (Severity.PASS, Severity.WARN, Severity.FAIL)
        assert results["DCMA-4"].severity is Severity.PASS
        assert results["DCMA-4"].computed_value == 100.0


# ---------------------------------------------------------------------------
# M6 — nine-metric end-to-end integration
# ---------------------------------------------------------------------------


def _run_all_nine(schedule: Schedule, cpm: CPMResult) -> dict[str, MetricResult]:
    """Run every metric in M5 + M6 scope on a shared schedule+CPM
    pair. Metric 9 and Metrics 11-14 are M7 scope and excluded here."""
    return {
        "DCMA-1": run_logic(schedule),
        "DCMA-2": run_leads(schedule),
        "DCMA-3": run_lags(schedule),
        "DCMA-4": run_relationship_types(schedule),
        "DCMA-5": run_hard_constraints(schedule),
        "DCMA-6": run_high_float(schedule, cpm),
        "DCMA-7": run_negative_float(schedule, cpm),
        "DCMA-8": run_high_duration(schedule),
        "DCMA-10": run_resources(schedule),
    }


class TestNineMetricIntegration:
    """BUILD-PLAN §5 M6 Block 7 — all nine metrics run end-to-end
    on a single realistic (Schedule, CPMResult) pair."""

    def test_every_metric_returns_a_result(self) -> None:
        sched, cpm = m6_integration_schedule()
        results = _run_all_nine(sched, cpm)
        assert set(results.keys()) == {
            "DCMA-1", "DCMA-2", "DCMA-3", "DCMA-4",
            "DCMA-5", "DCMA-6", "DCMA-7", "DCMA-8", "DCMA-10",
        }
        for r in results.values():
            assert isinstance(r, MetricResult)
            assert r.severity in (Severity.PASS, Severity.WARN, Severity.FAIL)

    def test_hard_constraints_flags_mso_and_fnlt(self) -> None:
        sched, _ = m6_integration_schedule()
        r = run_hard_constraints(sched)
        assert r.severity is Severity.FAIL
        assert r.numerator == 2
        # 22 total = 20 working tasks + 2 milestones; §3 exclusions
        # don't drop milestones for Metric 5.
        assert r.denominator == 22
        kinds = {o.value for o in r.offenders}
        assert kinds == {"MUST_START_ON", "FINISH_NO_LATER_THAN"}

    def test_high_float_flags_the_two_seeded_tasks(self) -> None:
        sched, cpm = m6_integration_schedule()
        r = run_high_float(sched, cpm)
        assert r.severity is Severity.FAIL
        assert {o.unique_id for o in r.offenders} == {17, 18}
        assert r.numerator == 2
        assert r.denominator == 22

    def test_negative_float_flags_single_offender(self) -> None:
        sched, cpm = m6_integration_schedule()
        r = run_negative_float(sched, cpm)
        assert r.severity is Severity.FAIL
        assert {o.unique_id for o in r.offenders} == {9}

    def test_high_duration_is_below_boundary_pass(self) -> None:
        sched, _ = m6_integration_schedule()
        r = run_high_duration(sched)
        # UID 13 carries 50 WD; milestones have duration 0 so they
        # don't flag → 1/22 ≈ 4.55% PASS (under the 5% ceiling).
        assert r.severity is Severity.PASS
        assert r.numerator == 1
        assert r.denominator == 22

    def test_resources_reports_ratio_only(self) -> None:
        sched, _ = m6_integration_schedule()
        r = run_resources(sched)
        assert r.severity is Severity.WARN
        # UIDs 19 and 20 have resource_count=0; milestones and every
        # other working task carry resource_count=1.
        assert r.numerator == 2
        assert r.denominator == 22
        assert r.threshold.direction == "indicator-only"

    def test_every_result_carries_provenance(self) -> None:
        sched, cpm = m6_integration_schedule()
        results = _run_all_nine(sched, cpm)
        for metric_id, r in results.items():
            assert r.metric_id == metric_id
            assert r.threshold.source_skill_section
            assert r.threshold.source_decm_row

    def test_no_metric_mutates_the_schedule(self) -> None:
        sched, cpm = m6_integration_schedule()
        before = sched.model_dump_json()
        _run_all_nine(sched, cpm)
        assert sched.model_dump_json() == before

    def test_no_metric_mutates_the_cpm_result(self) -> None:
        """Mutation-vs-wrap invariant (BUILD-PLAN §5 M4 AC10): the
        CPM-consuming metrics must read ``cpm_result.tasks[...]``
        without mutating the CPMResult or its tasks dict."""
        sched, cpm = m6_integration_schedule()
        before = cpm_result_snapshot(cpm)
        _run_all_nine(sched, cpm)
        assert cpm_result_snapshot(cpm) == before

    def test_determinism_across_two_invocations(self) -> None:
        sched, cpm = m6_integration_schedule()
        r1 = _run_all_nine(sched, cpm)
        r2 = _run_all_nine(sched, cpm)
        assert r1 == r2


class TestCoveragesEngineFixtureForM6:
    """Metric 8 and Metric 10 run end-to-end on an M4 engine fixture
    — the 50-task ``complex_with_exceptions`` schedule has one MFO
    milestone and no rolling-wave flags, so Metric 5 flags the MFO
    (1/50 = 2% PASS) and Metric 8 PASSes (all 1 WD durations)."""

    def test_metric_5_on_complex_engine_fixture(self) -> None:
        r = run_hard_constraints(complex_with_exceptions())
        assert r.severity is Severity.PASS  # 1/50 = 2% <= 5%
        assert r.numerator == 1
        assert {o.unique_id for o in r.offenders} == {30}

    def test_metric_8_on_complex_engine_fixture_is_pass(self) -> None:
        r = run_high_duration(complex_with_exceptions())
        assert r.severity is Severity.PASS
        assert r.numerator == 0

    def test_metric_10_on_complex_engine_fixture_all_missing(self) -> None:
        r = run_resources(complex_with_exceptions())
        assert r.severity is Severity.WARN
        # resource_count defaults to 0 in this fixture.
        assert r.computed_value == 100.0


# ---------------------------------------------------------------------------
# M7 — full fourteen-metric end-to-end integration
# ---------------------------------------------------------------------------


def _run_all_fourteen(schedule: Schedule, cpm: CPMResult) -> dict[str, MetricResult]:
    """Run every Phase 1 DCMA metric (1-14) on a shared schedule +
    CPMResult pair. Metric 1b (Dangling Logic) remains deferred per
    §9.1 ledger; everything else is in M7 scope."""
    return {
        "DCMA-1": run_logic(schedule),
        "DCMA-2": run_leads(schedule),
        "DCMA-3": run_lags(schedule),
        "DCMA-4": run_relationship_types(schedule),
        "DCMA-5": run_hard_constraints(schedule),
        "DCMA-6": run_high_float(schedule, cpm),
        "DCMA-7": run_negative_float(schedule, cpm),
        "DCMA-8": run_high_duration(schedule),
        "DCMA-9": run_invalid_dates(schedule),
        "DCMA-10": run_resources(schedule),
        "DCMA-11": run_missed_tasks(schedule),
        "DCMA-12": run_critical_path_test(schedule, cpm),
        "DCMA-13": run_cpli(schedule, cpm),
        "DCMA-14": run_bei(schedule),
    }


class TestFourteenMetricIntegration:
    """M7 Block 7 AC — every Phase 1 DCMA metric runs end-to-end on
    a single realistic (Schedule, CPMResult) pair."""

    def test_every_metric_returns_a_result(self) -> None:
        sched, cpm = m7_integration_schedule()
        results = _run_all_fourteen(sched, cpm)
        expected_ids = {f"DCMA-{i}" for i in range(1, 15) if i != 10} | {"DCMA-10"}
        # Metric 1b deferred; Metrics 1-14 otherwise all present.
        assert set(results.keys()) == expected_ids
        for r in results.values():
            assert isinstance(r, MetricResult)
            assert r.severity in (Severity.PASS, Severity.WARN, Severity.FAIL)

    def test_every_result_carries_provenance(self) -> None:
        sched, cpm = m7_integration_schedule()
        results = _run_all_fourteen(sched, cpm)
        for metric_id, r in results.items():
            assert r.metric_id == metric_id
            assert r.threshold.source_skill_section
            assert r.threshold.source_decm_row

    def test_invalid_dates_flags_seeded_actual_after_status(self) -> None:
        sched, _ = m7_integration_schedule()
        r = run_invalid_dates(sched)
        assert r.severity is Severity.FAIL
        # UID 5 is seeded with actual_finish > status_date.
        assert 5 in {o.unique_id for o in r.offenders}

    def test_missed_tasks_denominator_is_hand_calculable(self) -> None:
        sched, _ = m7_integration_schedule()
        r = run_missed_tasks(sched)
        # Baseline-due (≤ status): UIDs 1, 2, 3, 4, 5 — five tasks.
        # Summary/milestone excluded from denominator (none in this
        # set); LOE/rolling-wave exempt from numerator only.
        assert r.denominator == 5
        # Numerator: not-completed, not rolling-wave, not LOE → UID 3.
        # UID 1, 2, 5 have actual_finish; UID 4 is rolling-wave.
        assert r.numerator == 1
        assert {o.unique_id for o in r.offenders} == {3}

    def test_critical_path_test_passes_on_linear_chain(self) -> None:
        sched, cpm = m7_integration_schedule()
        r = run_critical_path_test(sched, cpm)
        assert r.severity is Severity.PASS

    def test_cpli_reports_valid_ratio(self) -> None:
        sched, cpm = m7_integration_schedule()
        r = run_cpli(sched, cpm)
        assert r.computed_value is not None
        # project_finish matches baseline's max → CPLI ≈ 1.0.
        assert r.severity is Severity.PASS

    def test_bei_denominator_excludes_early_finisher(self) -> None:
        sched, _ = m7_integration_schedule()
        r = run_bei(sched)
        # Baseline-due ≤ status: UIDs 1, 2, 3, 4, 5 → denominator 5.
        assert r.denominator == 5
        # Numerator: completed-by-status, excl. rolling-wave (UID 4) and
        # LOE → UID 1, 2 (on-time), UID 5 (actual after status, so NOT
        # counted in numerator because actual_finish > status_date).
        # UID 3 incomplete. → numerator = 2.
        assert r.numerator == 2
        # UID 6 (early-finisher with later baseline) is out of window.

    def test_no_metric_mutates_the_schedule(self) -> None:
        sched, cpm = m7_integration_schedule()
        before = sched.model_dump_json()
        _run_all_fourteen(sched, cpm)
        assert sched.model_dump_json() == before

    def test_no_metric_mutates_the_cpm_result(self) -> None:
        sched, cpm = m7_integration_schedule()
        before = cpm_result_snapshot(cpm)
        _run_all_fourteen(sched, cpm)
        assert cpm_result_snapshot(cpm) == before

    def test_determinism_across_two_invocations(self) -> None:
        sched, cpm = m7_integration_schedule()
        r1 = _run_all_fourteen(sched, cpm)
        r2 = _run_all_fourteen(sched, cpm)
        assert r1 == r2


class TestPublicApiCompleteness:
    """Every M7 metric is importable from the top-level
    ``app.metrics`` namespace — smoke test for Block 7 exports."""

    def test_all_fourteen_metrics_importable(self) -> None:
        from app.metrics import (
            BEIMetric,
            CPLIMetric,
            CriticalPathTestMetric,
            HardConstraintsMetric,
            HighDurationMetric,
            HighFloatMetric,
            InvalidDatesMetric,
            LagsMetric,
            LeadsMetric,
            LogicMetric,
            MissedTasksMetric,
            NegativeFloatMetric,
            RelationshipTypesMetric,
            ResourcesMetric,
        )

        expected_ids = {
            LogicMetric.metric_id,
            LeadsMetric.metric_id,
            LagsMetric.metric_id,
            RelationshipTypesMetric.metric_id,
            HardConstraintsMetric.metric_id,
            HighFloatMetric.metric_id,
            NegativeFloatMetric.metric_id,
            HighDurationMetric.metric_id,
            InvalidDatesMetric.metric_id,
            ResourcesMetric.metric_id,
            MissedTasksMetric.metric_id,
            CriticalPathTestMetric.metric_id,
            CPLIMetric.metric_id,
            BEIMetric.metric_id,
        }
        # 14 distinct metric IDs (Metric 1b deferred).
        assert len(expected_ids) == 14

    def test_baseline_plumbing_importable(self) -> None:
        from app.metrics import (
            BaselineComparison,
            baseline_critical_path_length_minutes,
            baseline_slip_minutes,
            has_baseline,
            has_baseline_coverage,
            tasks_with_baseline_finish_by,
        )

        assert callable(has_baseline)
        assert callable(has_baseline_coverage)
        assert callable(baseline_slip_minutes)
        assert callable(tasks_with_baseline_finish_by)
        assert callable(baseline_critical_path_length_minutes)
        assert BaselineComparison.__name__ == "BaselineComparison"
