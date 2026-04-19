"""Tests for the engine exception hierarchy (BUILD-PLAN §5 M4)."""

from __future__ import annotations

import pytest

from app.engine.exceptions import (
    CircularDependencyError,
    ConstraintViolation,
    EngineError,
    InvalidConstraintError,
    MissingCalendarError,
)


def test_all_engine_errors_subclass_engine_error() -> None:
    """Every engine error is catchable via the EngineError base."""
    assert issubclass(CircularDependencyError, EngineError)
    assert issubclass(MissingCalendarError, EngineError)
    assert issubclass(InvalidConstraintError, EngineError)


def test_circular_dependency_carries_nodes_as_set() -> None:
    err = CircularDependencyError({1, 2, 3})
    assert err.nodes == {1, 2, 3}
    # Message lists UIDs in sorted order for deterministic test asserts.
    assert "[1, 2, 3]" in str(err)


def test_circular_dependency_accepts_custom_message() -> None:
    err = CircularDependencyError({7, 8}, message="custom")
    assert str(err) == "custom"
    assert err.nodes == {7, 8}


def test_missing_calendar_names_calendar() -> None:
    err = MissingCalendarError("Standard")
    assert err.calendar_name == "Standard"
    assert "'Standard'" in str(err)


def test_invalid_constraint_carries_context() -> None:
    err = InvalidConstraintError(42, "date-bearing constraint missing date")
    assert err.unique_id == 42
    assert "UniqueID 42" in str(err)
    assert "date-bearing" in str(err)


def test_constraint_violation_is_data_only_not_raised() -> None:
    """Soft violations are records; raising would abort analysis (E8/E11)."""
    v = ConstraintViolation(unique_id=5, kind="FNLT_BREACHED", detail="pushed 3d late")
    assert v.unique_id == 5
    assert v.kind == "FNLT_BREACHED"
    assert v.detail == "pushed 3d late"
    # frozen dataclass — attempting to mutate raises.
    with pytest.raises(Exception):
        v.unique_id = 99  # type: ignore[misc]


def test_engine_error_base_is_catchable() -> None:
    with pytest.raises(EngineError):
        raise CircularDependencyError({1})
    with pytest.raises(EngineError):
        raise MissingCalendarError("X")
    with pytest.raises(EngineError):
        raise InvalidConstraintError(1, "bad")
