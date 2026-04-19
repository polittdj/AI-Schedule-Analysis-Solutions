"""Integration test for M5 — all four DCMA metrics on a single
realistic fixture (BUILD-PLAN §5 M5 AC7).

Also exercises the M4 ``complex_with_exceptions`` schedule to prove
the metric layer composes cleanly with the engine fixtures already
in the suite (no regression on the 472-test M4 baseline).
"""

from __future__ import annotations

from app.metrics import (
    MetricResult,
    Severity,
    run_lags,
    run_leads,
    run_logic,
    run_relationship_types,
)
from tests.fixtures.metric_schedules import integration_schedule
from tests.fixtures.schedules import complex_with_exceptions


def _run_all(schedule):
    return {
        "DCMA-1": run_logic(schedule),
        "DCMA-2": run_leads(schedule),
        "DCMA-3": run_lags(schedule),
        "DCMA-4": run_relationship_types(schedule),
    }


class TestIntegrationOnSyntheticSchedule:
    """A7 — all four metrics return MetricResult with expected severity
    against the integration fixture."""

    def test_all_four_metrics_run(self) -> None:
        results = _run_all(integration_schedule())
        assert set(results.keys()) == {"DCMA-1", "DCMA-2", "DCMA-3", "DCMA-4"}
        for r in results.values():
            assert isinstance(r, MetricResult)

    def test_logic_fail_with_detached_tasks(self) -> None:
        result = run_logic(integration_schedule())
        assert result.severity is Severity.FAIL
        offender_uids = {o.unique_id for o in result.offenders}
        # T19 and T20 are deliberately detached in the integration
        # fixture (missing both predecessor and successor) →
        # 2/20 = 10% → FAIL.
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
        # Two positive-lag relations in the integration fixture
        # against 18 non-lead relations (1 lead excluded per LG5).
        assert result.numerator == 2
        assert result.denominator == 18

    def test_relationship_types_fail_below_90pct(self) -> None:
        result = run_relationship_types(integration_schedule())
        assert result.severity is Severity.FAIL
        # 15 FS / 19 total ≈ 78.95% FS (4 non-FS: 2 SS + 1 FF + 1 SF).
        assert result.numerator == 15
        assert result.denominator == 19
        assert result.computed_value < 90.0

    def test_every_result_carries_provenance(self) -> None:
        results = _run_all(integration_schedule())
        for metric_id, r in results.items():
            assert r.metric_id == metric_id
            assert r.threshold.source_skill_section
            assert r.threshold.source_decm_row


class TestComposesWithEngineFixture:
    """Sanity check — running the metrics over an M4 fixture
    surfaces no exceptions and produces interpretable results."""

    def test_complex_engine_fixture_runs_clean(self) -> None:
        sched = complex_with_exceptions()
        results = _run_all(sched)
        for r in results.values():
            assert r.severity in (Severity.PASS, Severity.WARN, Severity.FAIL)
        # The complex fixture is 100% FS, so DCMA-4 should pass at 100%.
        assert results["DCMA-4"].severity is Severity.PASS
        assert results["DCMA-4"].computed_value == 100.0
