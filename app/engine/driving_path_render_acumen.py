"""Default Acumen-style renderer for the driving-path sub-graph.

Block 7 (2026-04-22) default-view renderer. Consumes a
:class:`~app.engine.driving_path_types.DrivingPathResult` and produces
an activity-centric row list suitable for attorney / senior-reviewer
consumption — the same report shape Deltek Acumen Fuse emits for its
"Driving Logic" reports (``acumen-reference`` §2.2 driving-logic
reports).

Scope is intentionally minimal: return a plain ``list[dict]`` in the
Acumen report shape. HTML rendering, pagination, filtering, the SSI
gantt-style variant, and the multi-renderer view toggle are Block 8
work.
"""

from __future__ import annotations

from typing import Any

from app.engine.driving_path_types import DrivingPathResult


def render_acumen_table(result: DrivingPathResult) -> list[dict[str, Any]]:
    """Render a :class:`DrivingPathResult` as an activity-centric table.

    Each row represents ONE task in the driving sub-graph; driving-
    predecessor relationships are nested as a list on the row. Row
    count equals ``len(result.nodes)``.

    Args:
        result: The adjacency-map driving-path result to render.

    Returns:
        List of row dicts, one per node, sorted by ``early_start``
        ascending (a stable secondary sort on ``unique_id`` keeps the
        order deterministic when two nodes share an early-start).
        Each row carries:

        * ``unique_id``: ``Task.unique_id``.
        * ``name``: ``Task.name``.
        * ``early_start``: node's CPM early start (``datetime``).
        * ``early_finish``: node's CPM early finish (``datetime``).
        * ``total_float_days``: node's total float in days.
        * ``calendar_hours_per_day``: node's calendar factor
          (forensic audit trail per BUILD-PLAN §2.18).
        * ``driving_predecessor_count``: number of zero-slack
          incoming driving edges on this node.
        * ``driving_predecessors``: list of
          ``{predecessor_uid, predecessor_name, relation_type,
          lag_days, relationship_slack_days}`` dicts.
        * ``non_driving_predecessor_count``: number of positive-
          slack predecessor edges terminating on this node.
    """
    # Index incoming edges and non-driving predecessors by
    # successor UID so we can assemble each row in a single pass.
    edges_by_successor: dict[int, list[dict[str, Any]]] = {
        uid: [] for uid in result.nodes
    }
    for edge in result.edges:
        edges_by_successor.setdefault(edge.successor_uid, []).append(
            {
                "predecessor_uid": edge.predecessor_uid,
                "predecessor_name": edge.predecessor_name,
                "relation_type": edge.relation_type,
                "lag_days": edge.lag_days,
                "relationship_slack_days": edge.relationship_slack_days,
            }
        )

    non_driving_counts: dict[int, int] = {uid: 0 for uid in result.nodes}
    for ndp in result.non_driving_predecessors:
        non_driving_counts[ndp.successor_uid] = (
            non_driving_counts.get(ndp.successor_uid, 0) + 1
        )

    rows: list[dict[str, Any]] = []
    for uid, node in result.nodes.items():
        driving = edges_by_successor.get(uid, [])
        rows.append(
            {
                "unique_id": node.unique_id,
                "name": node.name,
                "early_start": node.early_start,
                "early_finish": node.early_finish,
                "total_float_days": node.total_float_days,
                "calendar_hours_per_day": node.calendar_hours_per_day,
                "driving_predecessor_count": len(driving),
                "driving_predecessors": driving,
                "non_driving_predecessor_count": non_driving_counts.get(uid, 0),
            }
        )

    rows.sort(key=lambda r: (r["early_start"], r["unique_id"]))
    return rows


__all__ = ["render_acumen_table"]
