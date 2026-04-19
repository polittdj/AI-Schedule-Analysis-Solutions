"""Shared test-utility helpers (M6 cleanup C3).

The metric layer consumes :class:`app.engine.result.CPMResult`
read-only (mutation-vs-wrap invariant, BUILD-PLAN §5 M4 AC10;
cross-referenced by the M6 High Float / Negative Float modules in
their CPM-cycle-skip docstrings). ``CPMResult`` is a ``frozen=True``
dataclass so rebinding its attributes raises, but its ``tasks``
field is a ``dict`` — the frozen-ness does not propagate into the
container. :func:`cpm_result_snapshot` captures a deep-enough tuple
snapshot (one tuple per ``TaskCPMResult``'s field vector, plus the
surrounding frozen fields) so a test can assert equality before and
after a metric invocation and catch any in-place mutation of the
tasks map or the per-task records.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from app.engine.result import CPMResult, TaskCPMResult


def _task_cpm_tuple(tc: TaskCPMResult) -> tuple[Any, ...]:
    return tuple(getattr(tc, f.name) for f in fields(tc))


def cpm_result_snapshot(cpm: CPMResult) -> tuple[Any, ...]:
    """Return a hashable snapshot of ``cpm`` suitable for before/after
    equality checks in mutation-invariance assertions.

    The ``tasks`` dict is captured as a sorted tuple of
    ``(unique_id, field_vector)`` pairs so dict-key reordering or
    per-task field edits both surface as inequality.
    """
    tasks_snapshot = tuple(
        (uid, _task_cpm_tuple(cpm.tasks[uid]))
        for uid in sorted(cpm.tasks)
    )
    other = tuple(
        getattr(cpm, f.name) for f in fields(cpm) if f.name != "tasks"
    )
    return (tasks_snapshot, other)
