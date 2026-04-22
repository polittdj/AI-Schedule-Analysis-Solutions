"""Task-specific driving-path tracer — Milestone 10.

Block 7 (2026-04-22) replaced the chain-based contract with an
adjacency map (BUILD-PLAN AM8, §2.18). The backward walk now visits
**every** zero-relationship-slack incoming edge at every node per
``driving-slack-and-paths §4`` ("No path is dropped.") and §5
("Walking every relationship-slack-zero link backward … walks
recursively until every driving predecessor is exhausted.").

.. note::

   Block 7.1 landed the new types (:mod:`app.engine.driving_path_types`)
   and the units helper (:mod:`app.engine.units`). The backward-walk
   implementation itself lands in Block 7.2; this module is a stub
   placeholder between 7.1 and 7.2 so downstream imports
   (``app.engine``, tests that import types) remain clean.

Authority:

* SSI driving-slack methodology — ``driving-slack-and-paths §2``.
* Per-link relationship-slack formulas —
  ``driving-slack-and-paths §3`` (reused via
  :func:`app.engine.relations.link_driving_slack_minutes`).
* Full-traversal backward walk —
  ``driving-slack-and-paths §§4, 5`` (verbatim quotes in
  :mod:`app.engine.driving_path_types` error messages).
* Period A slack rule — ``driving-slack-and-paths §9``.
* UniqueID-only matching — BUILD-PLAN §2.7;
  ``mpp-parsing-com-automation §5``.

Non-mutation invariant: neither ``Schedule`` nor ``CPMResult`` is
mutated by any function in this module.
"""

from __future__ import annotations

from app.engine.driving_path_types import (
    DrivingPathCrossVersionResult,
    DrivingPathResult,
    FocusPointAnchor,
)
from app.engine.exceptions import DrivingPathError
from app.engine.result import CPMResult
from app.models.schedule import Schedule


def trace_driving_path(
    schedule: Schedule,
    focus_spec: int | FocusPointAnchor,
    cpm_result: CPMResult | None = None,
) -> DrivingPathResult:
    """Trace the driving path to a nominated Focus Point — stub."""
    raise NotImplementedError(
        "trace_driving_path: Block 7.2 rewrite pending. Block 7.1 "
        "delivered the adjacency-map contract; the backward-walk "
        "implementation lands in Block 7.2."
    )


def trace_driving_path_cross_version(
    period_a: Schedule,
    period_b: Schedule,
    focus_spec: int | FocusPointAnchor,
    period_a_cpm_result: CPMResult,
    period_b_cpm_result: CPMResult,
) -> DrivingPathCrossVersionResult:
    """Trace driving paths in both periods from a shared Focus Point — stub."""
    raise NotImplementedError(
        "trace_driving_path_cross_version: Block 7.3 rewrite pending. "
        "Block 7.1 delivered the adjacency-map contract; the cross-"
        "version implementation lands in Block 7.3."
    )


__all__ = [
    "trace_driving_path",
    "trace_driving_path_cross_version",
]
