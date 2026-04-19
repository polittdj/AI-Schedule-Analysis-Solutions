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
    run_hard_constraints,
    run_high_duration,
    run_high_float,
    run_lags,
    run_leads,
    run_logic,
    run_negative_float,
    run_relationship_types,
    run_resources,
)
from app.models.schedule import Schedule
from tests.fixtures.metric_schedules import (
    integration_schedule,
    m6_integration_schedule,
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
