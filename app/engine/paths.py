"""Longest-path extraction, driving slack, and near-critical bands.

The :class:`~app.engine.cpm.CPMEngine` computes per-task ES/EF/LS/LF/
TS/FS. This module derives the path-level structure forensic analysis
needs: critical-path chains (SSI ``driving-slack-and-paths §4`` multi-
critical-path handling), driving slack to an operator-nominated Focus
Point (``driving-slack-and-paths §2``), and near-critical banding
(``§4.2``).

Dispatch:

* :func:`critical_path_chains` — ordered lists of critical-path UIDs,
  one list per independent zero-slack chain terminating at the project
  finish. Multiple chains are emitted when two independent logic
  chains both end at the project finish with zero slack
  (``driving-slack-and-paths §4``).
* :func:`driving_slack_to_focus` — SSI Driving Slack computed for
  every UID upstream of the Focus Point, in working minutes.
* :func:`near_critical_chain` — ordered list of UIDs whose total slack
  falls in the ``(0, threshold]`` band.

All functions are read-only — neither :class:`Schedule` nor
:class:`CPMResult` is mutated.
"""

from __future__ import annotations

from collections import defaultdict

from app.engine.relations import link_driving_slack_minutes
from app.engine.result import CPMResult
from app.engine.topology import topological_order
from app.models.calendar import Calendar
from app.models.relation import Relation
from app.models.schedule import Schedule


def _schedule_calendar(schedule: Schedule) -> Calendar:
    for c in schedule.calendars:
        if c.name == schedule.default_calendar_name:
            return c
    if schedule.calendars:
        return schedule.calendars[0]
    return Calendar(name=schedule.default_calendar_name or "Standard")


def _succs(relations: list[Relation]) -> dict[int, list[Relation]]:
    out: dict[int, list[Relation]] = defaultdict(list)
    for r in relations:
        out[r.predecessor_unique_id].append(r)
    return out


def _preds(relations: list[Relation]) -> dict[int, list[Relation]]:
    out: dict[int, list[Relation]] = defaultdict(list)
    for r in relations:
        out[r.successor_unique_id].append(r)
    return out


def critical_path_chains(
    schedule: Schedule, cpm_result: CPMResult
) -> list[list[int]]:
    """Return ordered critical-path chains.

    Each returned list is a topological-order sequence of UIDs whose
    :attr:`TaskCPMResult.total_slack_minutes` is ``<= 0`` and that
    connects from a source (no critical predecessors) to a sink (no
    critical successors). Multiple chains surface when two
    independent paths both terminate at the project finish with zero
    slack (``driving-slack-and-paths §4``).

    Empty list is returned when no task is critical (rare, happens
    when :class:`CPMOptions.project_finish_override` pushes well past
    the computed finish — every task gets positive slack).
    """
    critical = {uid for uid, r in cpm_result.tasks.items() if r.on_critical_path}
    if not critical:
        return []

    succs = _succs(schedule.relations)
    preds = _preds(schedule.relations)
    topo = topological_order(schedule.tasks, schedule.relations).order

    sources = [
        uid
        for uid in critical
        if not any(
            r.predecessor_unique_id in critical
            for r in preds.get(uid, ())
        )
    ]

    chains: list[list[int]] = []
    topo_pos = {uid: i for i, uid in enumerate(topo)}

    def walk_from(start: int) -> list[list[int]]:
        results: list[list[int]] = []
        stack: list[tuple[int, list[int]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            crit_succs = [
                r.successor_unique_id
                for r in succs.get(node, ())
                if r.successor_unique_id in critical
            ]
            if not crit_succs:
                results.append(path)
                continue
            for s in sorted(
                crit_succs, key=lambda x: topo_pos.get(x, 0)
            ):
                stack.append((s, path + [s]))
        return results

    for src in sorted(sources, key=lambda x: topo_pos.get(x, 0)):
        chains.extend(walk_from(src))

    return chains


def driving_slack_to_focus(
    schedule: Schedule,
    cpm_result: CPMResult,
    focus_uid: int,
) -> dict[int, int]:
    """Working-minute Driving Slack to a nominated Focus Point.

    Implements SSI's DS definition (``driving-slack-and-paths §2``):

    * ``DS(F → F) = 0``.
    * ``DS(T → F) = min over all successor links (T→S) on a path to F
      of (link_DS(T→S) + DS(S → F))``.

    Tasks not on any forward path to ``focus_uid`` are absent from the
    result dict — the analyst sees them as "no DS to this focus",
    which matches SSI's "tasks off the forward-reachable subgraph of
    F have no defined Driving Slack to F".

    Args:
        schedule: source schedule (used for relations and calendar).
        cpm_result: output of the CPM engine.
        focus_uid: UniqueID of the Focus Point.

    Returns:
        Mapping ``{unique_id: driving_slack_minutes}``.
    """
    cal = _schedule_calendar(schedule)
    succs = _succs(schedule.relations)
    tasks_in_result = {
        uid for uid, r in cpm_result.tasks.items() if not r.skipped_due_to_cycle
    }
    if focus_uid not in tasks_in_result:
        return {}

    topo = topological_order(schedule.tasks, schedule.relations).order
    ds: dict[int, int] = {focus_uid: 0}

    # Walk in reverse topological order to propagate DS backward.
    for uid in reversed(topo):
        if uid == focus_uid or uid not in tasks_in_result:
            continue
        candidates: list[int] = []
        pred_result = cpm_result.tasks[uid]
        if pred_result.early_start is None or pred_result.early_finish is None:
            continue
        for rel in succs.get(uid, ()):
            succ_uid = rel.successor_unique_id
            if succ_uid not in ds:
                continue
            succ_result = cpm_result.tasks.get(succ_uid)
            if succ_result is None or succ_result.early_start is None:
                continue
            link_ds = link_driving_slack_minutes(
                rel.relation_type,
                pred_result.early_start,
                pred_result.early_finish,
                succ_result.early_start,
                succ_result.early_finish,  # type: ignore[arg-type]
                rel.lag_minutes,
                cal,
            )
            candidates.append(link_ds + ds[succ_uid])
        if candidates:
            ds[uid] = min(candidates)
    return ds


def near_critical_chain(
    cpm_result: CPMResult,
) -> list[int]:
    """Return UIDs flagged as near-critical, in ascending total slack.

    Ties broken by UniqueID for deterministic output. The
    threshold itself is owned by :class:`CPMOptions`; this helper just
    reads the ``on_near_critical`` flag already computed.
    """
    flagged = [
        (r.total_slack_minutes, uid)
        for uid, r in cpm_result.tasks.items()
        if r.on_near_critical
    ]
    flagged.sort()
    return [uid for _, uid in flagged]
