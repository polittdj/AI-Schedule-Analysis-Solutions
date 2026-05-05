"""Regression test: verify no circular import between
app.contracts.manipulation_scoring and
app.engine.constraint_driven_cross_version.

Locks in the fix from PR landing on 2026-05-05. Any future PR that
re-adds an eager top-level import of ConstraintDrivenCrossVersionResult
in app/engine/constraint_driven_cross_version.py will resurrect the
cycle and fail this test.

The cycle, if reintroduced, fires at engine-package init time when
something forces app.engine.constraint_driven_cross_version to load
while app.contracts.manipulation_scoring is mid-load (e.g., M11
Block 5's BUILD-PLAN §2.22(h) public-API wiring in
app/engine/__init__.py).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run_in_fresh_interpreter(snippet: str) -> subprocess.CompletedProcess[str]:
    """Run ``snippet`` in a clean Python subprocess.

    Using a subprocess avoids polluting the in-process module cache, which
    would otherwise cause class-identity mismatches in unrelated tests
    (e.g. ``app.overlay.OverlayResult is OverlayResult``).
    """
    return subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
    )


def test_constraint_cross_version_imports_without_cycle() -> None:
    """Direct import of the engine module must succeed standalone."""
    result = _run_in_fresh_interpreter(textwrap.dedent("""
        from app.engine.constraint_driven_cross_version import (
            ConstraintDrivenCrossVersionComparator,
            compare_constraint_driven_cross_version,
        )
        assert ConstraintDrivenCrossVersionComparator is not None
        assert compare_constraint_driven_cross_version is not None
        print("OK")
    """))
    assert result.returncode == 0, (
        f"engine module import failed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_contracts_manipulation_scoring_imports_without_cycle() -> None:
    """Direct import of the contracts module must succeed standalone."""
    result = _run_in_fresh_interpreter(textwrap.dedent("""
        from app.contracts.manipulation_scoring import (
            ConstraintDrivenCrossVersionResult,
        )
        assert ConstraintDrivenCrossVersionResult is not None
        print("OK")
    """))
    assert result.returncode == 0, (
        f"contracts module import failed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_engine_init_can_eager_import_block_3_facade() -> None:
    """Block 5 prerequisite: app.engine.__init__ must be able to eagerly
    import ConstraintDrivenCrossVersionComparator and
    compare_constraint_driven_cross_version without triggering the
    cycle. This test simulates the exact import chain that BUILD-PLAN
    §2.22(h) Block 5 will execute, in a clean interpreter so the
    contracts package init runs from scratch."""
    result = _run_in_fresh_interpreter(textwrap.dedent("""
        # Trigger contracts package init first (the original failure path)
        from app.contracts import ConstraintDrivenCrossVersionResult
        # Then trigger an eager engine-side import of the Block 3 module
        from app.engine.constraint_driven_cross_version import (
            ConstraintDrivenCrossVersionComparator,
            compare_constraint_driven_cross_version,
        )
        assert ConstraintDrivenCrossVersionResult is not None
        assert ConstraintDrivenCrossVersionComparator is not None
        assert compare_constraint_driven_cross_version is not None
        print("OK")
    """))
    assert result.returncode == 0, (
        f"Block 5 import chain failed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout
