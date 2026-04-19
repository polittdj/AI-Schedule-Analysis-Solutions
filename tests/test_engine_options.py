"""Tests for CPMOptions defaults, overrides, and validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.options import CPMOptions


def test_defaults_match_skill_driving_slack_paths_section_4() -> None:
    opts = CPMOptions()
    assert opts.near_critical_threshold_days == 10.0
    assert opts.project_finish_override is None
    assert opts.strict_cycles is False


def test_override_near_critical_threshold() -> None:
    opts = CPMOptions(near_critical_threshold_days=20.0)
    assert opts.near_critical_threshold_days == 20.0


def test_override_project_finish() -> None:
    override = datetime(2027, 1, 1, tzinfo=UTC)
    opts = CPMOptions(project_finish_override=override)
    assert opts.project_finish_override == override


def test_strict_cycles_toggle() -> None:
    opts = CPMOptions(strict_cycles=True)
    assert opts.strict_cycles is True


def test_negative_threshold_rejected() -> None:
    with pytest.raises(ValueError, match="near_critical_threshold"):
        CPMOptions(near_critical_threshold_days=-1.0)


def test_naive_override_rejected() -> None:
    naive = datetime(2027, 1, 1)  # no tzinfo
    with pytest.raises(ValueError, match="tz-aware"):
        CPMOptions(project_finish_override=naive)


def test_options_are_immutable() -> None:
    import dataclasses

    opts = CPMOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        opts.strict_cycles = True  # type: ignore[misc]
