"""Unit tests for ``app.parsers.zombie_cleanup``.

Covers skill §6 ordering invariant #1 — the orphan ``MSPROJECT.EXE``
startup sweep. Three branches:

1. Windows path: ``subprocess.run`` is invoked with the correct
   ``taskkill`` command and ``check=False`` semantics.
2. Non-Windows path: no subprocess is invoked.
3. Failure tolerance: an unexpected exception from ``subprocess.run``
   does not propagate (secondary defense must not abort a parse).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.parsers import zombie_cleanup


class TestSweepOrphanMsproject:
    def test_windows_invokes_taskkill(self) -> None:
        """On Windows, subprocess.run is called with the taskkill cmd."""
        with patch.object(zombie_cleanup.sys, "platform", "win32"), patch.object(
            zombie_cleanup.subprocess, "run"
        ) as mock_run:
            zombie_cleanup.sweep_orphan_msproject()
        assert mock_run.called
        args, kwargs = mock_run.call_args
        assert args[0] == ["taskkill", "/F", "/IM", "MSPROJECT.EXE"]
        # check=False so a clean workstation (no orphans) does not raise.
        assert kwargs.get("check") is False
        # Output is suppressed so taskkill lines do not leak into the log.
        assert kwargs.get("capture_output") is True

    def test_non_windows_is_noop(self) -> None:
        """On Linux / macOS, no subprocess is invoked."""
        with patch.object(zombie_cleanup.sys, "platform", "linux"), patch.object(
            zombie_cleanup.subprocess, "run"
        ) as mock_run:
            zombie_cleanup.sweep_orphan_msproject()
        assert mock_run.called is False

    def test_subprocess_exception_swallowed(self) -> None:
        """An unexpected subprocess exception must not propagate."""
        raising = MagicMock(side_effect=OSError("taskkill not on PATH"))
        with patch.object(zombie_cleanup.sys, "platform", "win32"), patch.object(
            zombie_cleanup.subprocess, "run", raising
        ):
            # Must not raise — startup sweep is the secondary defense.
            zombie_cleanup.sweep_orphan_msproject()
        assert raising.called


class TestParserInvokesSweep:
    """The parser calls the sweep before COM dispatch (skill §6 inv #1)."""

    def test_sweep_called_before_dispatch(self, tmp_path) -> None:
        from app.parsers.com_parser import MPProjectParser
        from tests.fixtures import FakeMSProjectApp, make_minimal_project

        call_log: list[str] = []

        def dispatch(prog_id: str) -> FakeMSProjectApp:
            call_log.append("dispatch")
            assert prog_id == "MSProject.Application"
            return FakeMSProjectApp(make_minimal_project())

        def sweep() -> None:
            call_log.append("sweep")

        parser = MPProjectParser(
            dispatch=dispatch,
            co_initialize=lambda: None,
            co_uninitialize=lambda: None,
            sweep=sweep,
        )
        mpp = tmp_path / "x.mpp"
        mpp.write_bytes(b"")
        with parser:
            parser.parse(mpp)

        # Sweep must precede every dispatch call.
        assert call_log.index("sweep") < call_log.index("dispatch")
