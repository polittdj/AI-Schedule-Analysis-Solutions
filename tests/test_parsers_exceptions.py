"""Unit tests for the parser exception hierarchy.

Validates that every concrete parser exception inherits from the
:class:`ParserError` root so callers can catch broadly without
depending on win32com being importable on the test runner's
platform (covers parser gotcha P1's CI-skip strategy).
"""

from __future__ import annotations

import pytest

from app.parsers.exceptions import (
    COMUnavailableError,
    CorruptScheduleError,
    MPOpenError,
    ParserError,
    UnsupportedVersionError,
)


class TestParserErrorHierarchy:
    """All four concrete errors descend from ParserError."""

    @pytest.mark.parametrize(
        "exc_cls",
        [
            COMUnavailableError,
            MPOpenError,
            CorruptScheduleError,
            UnsupportedVersionError,
        ],
    )
    def test_subclass_of_parser_error(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, ParserError)

    @pytest.mark.parametrize(
        "exc_cls",
        [
            COMUnavailableError,
            MPOpenError,
            CorruptScheduleError,
            UnsupportedVersionError,
        ],
    )
    def test_message_round_trips(self, exc_cls: type[Exception]) -> None:
        msg = "diagnostic detail"
        err = exc_cls(msg)
        assert str(err) == msg

    def test_root_is_exception(self) -> None:
        assert issubclass(ParserError, Exception)

    def test_cause_chain_preserved(self) -> None:
        """CorruptScheduleError must preserve the originating COM error."""
        original = RuntimeError("MS Project COM error 0x80004005")
        try:
            try:
                raise original
            except RuntimeError as e:
                raise CorruptScheduleError("schedule unreadable") from e
        except CorruptScheduleError as e:
            assert e.__cause__ is original

    def test_catch_broad_at_root(self) -> None:
        """Callers can catch on ParserError without importing win32com."""
        with pytest.raises(ParserError):
            raise COMUnavailableError("MS Project not installed")
