"""End-to-end integration tests for the M11 public-API surface.

Authority: BUILD-PLAN §2.22(h) public-API surface; §2.22(k) Block 5
directive — "Public-API wiring + integration test combining M10.1 /
M10.2 output with M11 scoring end-to-end." Closes M11.

Scope:

* Verifies the six §2.22(h) top-level facade exports on ``app``.
* Verifies the three §2.22(h) engine-level exports on ``app.engine``
  (``ConstraintDrivenCrossVersionComparator``,
  ``compare_constraint_driven_cross_version``,
  ``render_manipulation_scoring_summary``).
* Enforces the §2.22(h) "canonical entry point rule" — the function
  ``score_manipulation`` is only reachable via ``app`` and via the
  underlying module ``app.engine.manipulation_scoring``; it is NOT
  re-exported from ``app.engine``.
* Exercises the e2e flow: build two minimal :class:`Schedule`
  fixtures, run :func:`app.engine.compute_cpm` and
  :func:`app.engine.trace_driving_path` (the M10.1 surface), call
  :func:`app.score_manipulation` (the top-level facade), and project
  the resulting :class:`ManipulationScoringSummary` through
  :func:`app.engine.render_manipulation_scoring_summary` (the
  Block 4b renderer dict per §2.22(i)).
* Cross-checks the M10.2 ``skipped_cycle_participants`` field
  presence on :class:`DrivingPathResult` (§2.21 / AM11) — this is
  the M10.2 surface that Block 5's e2e test must combine with M11
  per §2.22(k).
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from enum import StrEnum

import pytest
from pydantic import BaseModel, ValidationError

from app import (
    ConstraintDrivenCrossVersionResult,
    ManipulationScoringResult,
    ManipulationScoringSummary,
    SeverityTier,
    SlackState,
    score_manipulation,
)
from app.engine import (
    ConstraintDrivenCrossVersionComparator,
    FocusPointAnchor,
    compare_constraint_driven_cross_version,
    compute_cpm,
    render_manipulation_scoring_summary,
    trace_driving_path,
)
from app.engine.exceptions import FocusPointError
from app.models.calendar import Calendar
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task

_ANCHOR = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)


def _std_cal() -> Calendar:
    return Calendar(name="Standard")


def _two_task_chain(name: str) -> Schedule:
    """Two-task FS chain — the smallest non-degenerate schedule.

    Both tasks ASAP, no constraints, no actuals. compute_cpm produces
    a clean CPMResult with the second task as project finish.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="A", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="B", duration_minutes=480),
    ]
    relations = [
        Relation(
            predecessor_unique_id=1,
            successor_unique_id=2,
            relation_type=RelationType.FS,
        ),
    ]
    return Schedule(
        name=name,
        project_start=_ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


def _cyclic_three_task_schedule() -> Schedule:
    """Three-task schedule with a deliberate UID 2 ↔ 3 cycle.

    UID 1 is a clean ancestor; UIDs 2 and 3 form the cycle. The CPM
    engine flags 2 and 3 in ``cycles_detected`` and marks them
    ``skipped_due_to_cycle=True``. The driving-path tracer consults
    this state via ``DrivingPathResult.skipped_cycle_participants``
    (M10.2 / §2.21 / AM11). Mirrors the cycle pattern in
    ``tests/test_engine_driving_path_focus_exclusion.py``.
    """
    tasks = [
        Task(unique_id=1, task_id=1, name="Clean", duration_minutes=480),
        Task(unique_id=2, task_id=2, name="CycleA", duration_minutes=480),
        Task(unique_id=3, task_id=3, name="CycleB", duration_minutes=480),
    ]
    relations = [
        Relation(predecessor_unique_id=1, successor_unique_id=2),
        Relation(predecessor_unique_id=2, successor_unique_id=3),
        Relation(predecessor_unique_id=3, successor_unique_id=2),
    ]
    return Schedule(
        name="cyclic_e2e_fixture",
        project_start=_ANCHOR,
        project_calendar_hours_per_day=8.0,
        tasks=tasks,
        relations=relations,
        calendars=[_std_cal()],
    )


# ----------------------------------------------------------------------
# T1 — top-level facade
# ----------------------------------------------------------------------


def test_top_level_facade_exports_all_six_m11_symbols() -> None:
    """All six §2.22(h) top-level symbols are present and well-typed.

    Three Pydantic models (BaseModel subclasses with ``frozen=True``),
    two ``StrEnum`` classes, and one callable function. The seventh
    symbol on ``app.__all__`` (``create_app``) is verified by the
    Flask conftest fixture and is intentionally not re-tested here.
    """
    assert issubclass(ConstraintDrivenCrossVersionResult, BaseModel)
    assert issubclass(ManipulationScoringResult, BaseModel)
    assert issubclass(ManipulationScoringSummary, BaseModel)

    assert issubclass(SlackState, StrEnum)
    assert issubclass(SeverityTier, StrEnum)

    assert callable(score_manipulation)


# ----------------------------------------------------------------------
# T2 — engine-level facade (Block 5 additions)
# ----------------------------------------------------------------------


def test_engine_level_facade_exports_block_5_additions() -> None:
    """The three Block 5 engine-level symbols are present and callable.

    ``ConstraintDrivenCrossVersionComparator`` is a class;
    ``compare_constraint_driven_cross_version`` and
    ``render_manipulation_scoring_summary`` are module-level
    functions. All three appear on ``app.engine.__all__``.
    """
    import app.engine

    assert isinstance(ConstraintDrivenCrossVersionComparator, type)
    assert callable(compare_constraint_driven_cross_version)
    assert callable(render_manipulation_scoring_summary)

    assert "ConstraintDrivenCrossVersionComparator" in app.engine.__all__
    assert "compare_constraint_driven_cross_version" in app.engine.__all__
    assert "render_manipulation_scoring_summary" in app.engine.__all__


# ----------------------------------------------------------------------
# T3 — canonical entry point rule
# ----------------------------------------------------------------------


def test_score_manipulation_NOT_exported_from_engine_facade() -> None:
    """``score_manipulation`` must not be reachable from ``app.engine``.

    Authority: §2.22(h) "canonical entry point rule". The function is
    re-exported by the top-level ``app`` facade only; engine-level
    consumers must reach into ``app.engine.manipulation_scoring``
    directly. Keeps a single deposition-grade entry point.
    """
    with pytest.raises(ImportError):
        from app.engine import score_manipulation  # noqa: F401


# ----------------------------------------------------------------------
# T4 — score_manipulation happy path (M10.1 inputs end-to-end)
# ----------------------------------------------------------------------


def test_e2e_score_manipulation_happy_path_with_m10_1_dpr_inputs() -> None:
    """Run :func:`score_manipulation` on a clean schedule pair.

    Builds Period A and Period B as two-task FS chains (no
    constraints, no manipulation), then calls the top-level facade.
    The facade computes DPRs via :func:`trace_driving_path` (M10.1
    surface) for both periods, runs the constraint-driven cross-
    version comparator (M11 Block 3), and aggregates the result into
    a :class:`ManipulationScoringSummary`.

    Because both fixtures are clean (no
    ``ConstraintDrivenPredecessor`` rows), the summary's
    ``total_score`` is ``0`` and ``per_uid_results`` is empty — the
    "always-zero on clean inputs" regression bar from BUILD-PLAN
    §2.22(g). The summary is also frozen per
    ``ConfigDict(frozen=True)``.
    """
    period_a = _two_task_chain("period_a")
    period_b = _two_task_chain("period_b")
    cpm_a = compute_cpm(period_a)
    cpm_b = compute_cpm(period_b)

    summary = score_manipulation(
        period_a, period_b, cpm_a, cpm_b, FocusPointAnchor.PROJECT_FINISH
    )

    assert isinstance(summary, ManipulationScoringSummary)
    assert 0 <= summary.total_score <= 100
    assert summary.total_score == 0
    assert summary.per_uid_results == ()

    # SeverityTier annotation surfaces only on per-UID rows; a clean
    # schedule pair produces no rows. The contract still requires that
    # any row's ``severity_tier`` be a SeverityTier member.
    for row in summary.per_uid_results:
        assert isinstance(row, ManipulationScoringResult)
        assert isinstance(row.severity_tier, SeverityTier)
        assert isinstance(row.slack_state, SlackState)

    # ConfigDict(frozen=True) is enforced by Pydantic v2's __setattr__,
    # which raises ValidationError on assignment.
    with pytest.raises(ValidationError):
        summary.total_score = 99  # type: ignore[misc]


# ----------------------------------------------------------------------
# T5 — renderer dict shape (Block 4b §2.22(i))
# ----------------------------------------------------------------------


def test_e2e_render_manipulation_scoring_summary_dict_shape() -> None:
    """The renderer projects a summary into a plain Jinja2-ready dict.

    Authority: BUILD-PLAN §2.22(i) — renderer scope and dict shape.
    Block 4b decision (frozen at handoff): StrEnum fields are
    rendered as their ``.value`` strings, NOT as enum objects. The
    dict carries only ``str`` / ``int`` / ``list`` / ``dict``
    primitives — no Pydantic models, no enums, no datetimes.
    """
    row = ManipulationScoringResult(
        unique_id=42,
        name="Foundation pour",
        score=10,
        severity_tier=SeverityTier.HIGH,
        slack_state=SlackState.JOINED_PRIMARY,
        rationale="MSO predecessor newly bound primary",
    )
    summary = ManipulationScoringSummary(
        total_score=10,
        uid_count_high=1,
        uid_count_medium=0,
        uid_count_low=0,
        uid_count_joined_primary=1,
        uid_count_eroding_toward_primary=0,
        uid_count_stable=0,
        uid_count_recovering=0,
        per_uid_results=(row,),
    )

    rendered = render_manipulation_scoring_summary(summary)

    assert rendered["total_score"] == 10
    assert rendered["severity_banner"] == "low"
    assert rendered["uid_counts_by_severity"] == {
        "high": 1,
        "medium": 0,
        "low": 0,
    }
    assert rendered["uid_counts_by_slack_state"] == {
        "joined_primary": 1,
        "eroding_toward_primary": 0,
        "stable": 0,
        "recovering": 0,
    }

    # StrEnum -> .value rendering on the row.
    rendered_row = rendered["rows"][0]
    assert rendered_row["severity_tier"] == "high"
    assert rendered_row["slack_state"] == "joined_primary"
    # Belt-and-braces: NOT enum objects.
    assert not isinstance(rendered_row["severity_tier"], SeverityTier)
    assert not isinstance(rendered_row["slack_state"], SlackState)
    assert isinstance(rendered_row["severity_tier"], str)
    assert isinstance(rendered_row["slack_state"], str)


# ----------------------------------------------------------------------
# T6 — comparator engine-facade call returns the contract type
# ----------------------------------------------------------------------


def test_e2e_compare_constraint_driven_cross_version_via_engine_facade() -> None:
    """The Block 3 comparator facade is reachable via ``app.engine``.

    Pre-builds DPRs via the M10.1 :func:`trace_driving_path` surface
    rather than relying on the comparator's lazy DPR-construction
    path — that path requires a non-default trace_driving_path
    invocation that the existing test suite only exercises under
    mocking (see
    ``tests/engine/test_constraint_driven_cross_version.py
    test_facade_computes_dprs_when_none_supplied``). For an honest
    e2e test, construct the DPRs in the realistic call pattern.

    The result type is imported via the top-level facade for
    symmetry with §2.22(h).
    """
    period_a = _two_task_chain("e2e_compare_a")
    period_b = _two_task_chain("e2e_compare_b")
    cpm_a = compute_cpm(period_a)
    cpm_b = compute_cpm(period_b)
    dpr_a = trace_driving_path(period_a, FocusPointAnchor.PROJECT_FINISH, cpm_a)
    dpr_b = trace_driving_path(period_b, FocusPointAnchor.PROJECT_FINISH, cpm_b)

    result = compare_constraint_driven_cross_version(
        schedule_a=period_a,
        schedule_b=period_b,
        dpr_a=dpr_a,
        dpr_b=dpr_b,
        focus_uid=dpr_a.focus_point_uid,
    )

    assert isinstance(result, ConstraintDrivenCrossVersionResult)
    # Clean fixture pair => empty set algebra.
    assert result.added_constraint_driven_uids == set()
    assert result.removed_constraint_driven_uids == set()
    assert result.retained_constraint_driven_uids == set()


# ----------------------------------------------------------------------
# T7 — M10.2 skipped_cycle_participants field presence
# ----------------------------------------------------------------------


def test_e2e_m10_2_skipped_cycle_participants_field_propagates() -> None:
    """``DrivingPathResult.skipped_cycle_participants`` is a list of UIDs.

    Authority: BUILD-PLAN §2.21 (AM11). Builds a schedule with a
    deliberate predecessor cycle (UIDs 2 ↔ 3), runs the M10.1
    :func:`trace_driving_path` from the clean ancestor (UID 1), and
    asserts the M10.2 forensic-visibility field is present and is a
    list of integer UIDs. Per the focus-exclusion test suite,
    natural lenient-mode CPM populates ``cycles_detected`` while the
    tracer silently drops cycle-participant edges; this test only
    covers field presence and type, not the surgical-override defensive
    path documented in
    ``tests/test_engine_driving_path_focus_exclusion.py``.
    """
    schedule = _cyclic_three_task_schedule()
    cpm = compute_cpm(schedule)

    # Confirm CPM detected the cycle as expected.
    assert 2 in cpm.cycles_detected
    assert 3 in cpm.cycles_detected

    dpr = trace_driving_path(schedule, 1, cpm)

    # Field is present, is a list, and members are ints when populated.
    assert hasattr(dpr, "skipped_cycle_participants")
    assert isinstance(dpr.skipped_cycle_participants, list)
    for uid in dpr.skipped_cycle_participants:
        assert isinstance(uid, int)


# ----------------------------------------------------------------------
# T8 — score_manipulation focus_spec narrower contract
# ----------------------------------------------------------------------


def test_focus_spec_strenum_only_score_manipulation_rejects_int() -> None:
    """``score_manipulation`` documents a narrower focus_spec contract.

    Authority: §2.22(h). Where :func:`trace_driving_path` accepts
    ``int | FocusPointAnchor``, :func:`score_manipulation` narrows to
    ``FocusPointAnchor`` only. Verified two ways:

    1. Type-annotation introspection — the function signature names
       ``FocusPointAnchor`` and not ``int``. Documents the contract.
    2. Runtime delegation — passing an integer that is not a
       resolvable ``Task.unique_id`` surfaces a
       :class:`~app.engine.exceptions.FocusPointError` (the actual
       exception class — narrower than ``TypeError`` /
       ``ValueError`` but informative). The error message names the
       offending UID.
    """
    sig = inspect.signature(score_manipulation)
    focus_annotation = str(sig.parameters["focus_spec"].annotation)
    assert "FocusPointAnchor" in focus_annotation
    assert focus_annotation.strip() == "FocusPointAnchor"

    period_a = _two_task_chain("e2e_focus_a")
    period_b = _two_task_chain("e2e_focus_b")
    cpm_a = compute_cpm(period_a)
    cpm_b = compute_cpm(period_b)

    bogus_uid = 99999
    with pytest.raises(FocusPointError) as exc_info:
        # type: ignore[arg-type]  -- intentional contract violation
        score_manipulation(period_a, period_b, cpm_a, cpm_b, bogus_uid)  # type: ignore[arg-type]

    assert str(bogus_uid) in str(exc_info.value)
