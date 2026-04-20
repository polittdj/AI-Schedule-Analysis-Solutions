"""Tests for the NASA SMH overlay frozen contract (Milestone 8).

Block 1 covers only scaffolding: module imports, frozen-dataclass
mutation behaviour, enum values, and well-formed construction of
the four contract types (:class:`OverlayResult`,
:class:`OverlayNote`, :class:`OverlayNoteKind`,
:class:`ExclusionRecord`). Rule-logic tests land in Blocks 3–5.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.metrics.base import (
    MetricResult,
    Severity,
    ThresholdConfig,
)
from app.overlay import (
    ExclusionRecord,
    MissingMetricResultError,
    OverlayError,
    OverlayNote,
    OverlayNoteKind,
    OverlayResult,
)


def _sample_metric_result() -> MetricResult:
    """Build a trivial upstream :class:`MetricResult` for use as the
    overlay's ``original_result`` input in scaffolding tests."""
    threshold = ThresholdConfig(
        value=5.0,
        direction="<=",
        source_skill_section="dcma-14-point-assessment §4.6",
        source_decm_row="DECM sheet Metrics, Guideline 6 — High Float",
    )
    return MetricResult(
        metric_id="DCMA-6",
        metric_name="High Float",
        severity=Severity.PASS,
        threshold=threshold,
        numerator=0,
        denominator=5,
        offenders=(),
        computed_value=0.0,
    )


# ----- imports work -----------------------------------------------


def test_overlay_package_imports_cleanly() -> None:
    # Re-import through the package surface; failure here means
    # __init__.py's __all__ is out of sync with the modules.
    from app.overlay import (
        ExclusionRecord as _ER,
    )
    from app.overlay import (
        OverlayNote as _ON,
    )
    from app.overlay import (
        OverlayNoteKind as _ONK,
    )
    from app.overlay import (
        OverlayResult as _OR,
    )

    assert _OR is OverlayResult
    assert _ON is OverlayNote
    assert _ONK is OverlayNoteKind
    assert _ER is ExclusionRecord


# ----- StrEnum values --------------------------------------------


def test_overlay_note_kind_values() -> None:
    # Stringly-typed values must match the BUILD-PLAN spec exactly —
    # M11 consumer routes on the exact values.
    assert OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE.value == (
        "GOVERNANCE_MILESTONE_TRIAGE"
    )
    assert OverlayNoteKind.ROLLING_WAVE_NEAR_TERM_WARNING.value == (
        "ROLLING_WAVE_NEAR_TERM_WARNING"
    )
    assert OverlayNoteKind.ROLLING_WAVE_OUT_OF_WINDOW.value == (
        "ROLLING_WAVE_OUT_OF_WINDOW"
    )
    # StrEnum shall also be a str (JSON / JSONLines export path).
    assert isinstance(OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE, str)


def test_overlay_note_kind_membership() -> None:
    # Exactly three note kinds in M8 scope.
    assert len(list(OverlayNoteKind)) == 3


# ----- frozen dataclass behaviour --------------------------------


def test_overlay_note_is_frozen() -> None:
    note = OverlayNote(
        note_kind=OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE,
        unique_id=1001,
        task_name="CDR Review",
        detail="MFO constraint on governance milestone CDR",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        note.detail = "mutated"  # type: ignore[misc]


def test_exclusion_record_is_frozen() -> None:
    row = ExclusionRecord(
        unique_id=42,
        task_name="SM-01",
        exclusion_reason="is_schedule_margin = True (SMH §3)",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.exclusion_reason = "mutated"  # type: ignore[misc]


def test_overlay_result_is_frozen() -> None:
    result = OverlayResult(
        metric_id="DCMA-6",
        original_result=_sample_metric_result(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.metric_id = "DCMA-7"  # type: ignore[misc]


def test_overlay_result_has_slots() -> None:
    # slots=True — no stray __dict__ attribute (prevents accidental
    # attribute bleed in downstream consumers).
    result = OverlayResult(
        metric_id="DCMA-6",
        original_result=_sample_metric_result(),
    )
    assert not hasattr(result, "__dict__")
    # Setting any attribute (slotted or not) on a frozen dataclass
    # raises — covered by test_overlay_result_is_frozen; here we
    # verify slots excludes __dict__ specifically.


# ----- well-formed construction ----------------------------------


def test_overlay_result_default_adjusted_fields_are_none() -> None:
    result = OverlayResult(
        metric_id="DCMA-5",
        original_result=_sample_metric_result(),
    )
    assert result.adjusted_numerator is None
    assert result.adjusted_denominator is None
    assert result.adjusted_ratio is None
    assert result.adjusted_severity is None
    assert result.informational_notes == ()
    assert result.tasks_excluded_from_denominator == ()


def test_overlay_result_carries_notes_and_exclusions() -> None:
    note = OverlayNote(
        note_kind=OverlayNoteKind.GOVERNANCE_MILESTONE_TRIAGE,
        unique_id=1,
        task_name="CDR",
        detail="detail",
    )
    row = ExclusionRecord(
        unique_id=2,
        task_name="SM-01",
        exclusion_reason="schedule margin",
    )
    result = OverlayResult(
        metric_id="DCMA-6",
        original_result=_sample_metric_result(),
        adjusted_numerator=1,
        adjusted_denominator=4,
        adjusted_ratio=25.0,
        adjusted_severity=Severity.FAIL,
        informational_notes=(note,),
        tasks_excluded_from_denominator=(row,),
    )
    assert result.informational_notes == (note,)
    assert result.tasks_excluded_from_denominator == (row,)
    assert result.adjusted_ratio == 25.0
    assert result.adjusted_severity is Severity.FAIL


# ----- exception hierarchy ---------------------------------------


def test_missing_metric_result_error_is_overlay_error() -> None:
    err = MissingMetricResultError("apply_schedule_margin_exclusion", "DCMA-6")
    assert isinstance(err, OverlayError)
    assert err.overlay_rule == "apply_schedule_margin_exclusion"
    assert err.metric_id == "DCMA-6"
    assert "DCMA-6" in str(err)
    assert "nasa-schedule-management §6" in str(err)
