"""Critical Path Method engine — forward pass, backward pass, slack.

High-level algorithm:

1. Locate the project calendar by
   :attr:`~app.models.schedule.Schedule.default_calendar_name`.
2. Topologically order tasks (Kahn on the acyclic subgraph;
   :mod:`app.engine.topology`).
3. **Forward pass** over the topological order, deriving each task's
   early start (ES) and early finish (EF) from predecessor links
   (:mod:`app.engine.relations`) and its constraint
   (:mod:`app.engine.constraints`). Tasks with no predecessors anchor
   on their existing ``start``/``early_start`` if set, else on
   :attr:`Schedule.project_start`, else on the earliest date across
   already-computed tasks.
4. Derive project start/finish from the forward-pass results.
5. **Backward pass** over the reversed topological order, deriving
   late finish (LF) and late start (LS) from successor links. Tasks
   with no successors anchor on
   :attr:`CPMOptions.project_finish_override` if set, else on the
   project finish.
6. Compute total slack ``TS = LS - ES`` in working minutes
   (``driving-slack-and-paths §1``) and free slack
   ``FS = min(succ_link_ds)`` per task.
7. Classify tasks as on-critical (TS ≤ 0) or near-critical
   (0 < TS ≤ threshold).
8. Cyclic tasks are skipped entirely (lenient) or cause
   :class:`CircularDependencyError` (strict,
   :attr:`CPMOptions.strict_cycles`).

The class exposes a single ``compute()`` method returning an
immutable :class:`CPMResult`; a module-level ``compute_cpm()`` helper
wraps the common one-shot call.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.engine.calendar_math import (
    add_working_minutes,
    snap_forward,
    subtract_working_minutes,
    working_minutes_between,
)
from app.engine.constraints import (
    apply_backward_constraint,
    apply_forward_constraint,
)
from app.engine.exceptions import (
    ConstraintViolation,
)
from app.engine.options import CPMOptions
from app.engine.relations import (
    backward_link_bound,
    forward_link_bound,
)
from app.engine.result import CPMResult, TaskCPMResult
from app.engine.topology import topological_order
from app.models.calendar import Calendar
from app.models.enums import ConstraintType
from app.models.relation import Relation
from app.models.schedule import Schedule
from app.models.task import Task


class CPMEngine:
    """Forward/backward pass runner for a single :class:`Schedule`.

    Usage::

        engine = CPMEngine(schedule, CPMOptions(...))
        result = engine.compute()

    The engine never mutates ``schedule``; every computed value lives
    on :class:`CPMResult`. That contract is the M4 mutation-vs-wrap
    decision documented in ``app/engine/README.md``.
    """

    def __init__(
        self, schedule: Schedule, options: CPMOptions | None = None
    ) -> None:
        self._schedule = schedule
        self._options = options or CPMOptions()

    # ---- entry point ------------------------------------------------

    def compute(self) -> CPMResult:
        schedule = self._schedule
        if not schedule.tasks:
            # E2 — empty schedule is a valid no-op.
            return CPMResult(tasks={})

        cal = _find_calendar(schedule)
        topo = topological_order(
            schedule.tasks,
            schedule.relations,
            strict_cycles=self._options.strict_cycles,
        )
        acyclic_uids = set(topo.order)
        tasks_by_uid: dict[int, Task] = {t.unique_id: t for t in schedule.tasks}

        preds_of, succs_of = _index_relations(
            schedule.relations, acyclic_uids
        )

        violations: list[ConstraintViolation] = []

        early_start, early_finish = self._forward_pass(
            topo.order, tasks_by_uid, preds_of, cal, schedule, violations
        )

        project_start = _min_or_none(early_start.values())
        project_finish = _max_or_none(early_finish.values())

        anchor_finish = self._options.project_finish_override or project_finish

        late_start, late_finish = self._backward_pass(
            topo.order,
            tasks_by_uid,
            succs_of,
            cal,
            anchor_finish,
            violations,
        )

        task_results = _build_task_results(
            schedule.tasks,
            acyclic_uids,
            early_start,
            early_finish,
            late_start,
            late_finish,
            succs_of,
            schedule.relations,
            tasks_by_uid,
            cal,
            self._options,
        )

        critical = frozenset(
            uid for uid, r in task_results.items() if r.on_critical_path
        )
        near_critical = frozenset(
            uid for uid, r in task_results.items() if r.on_near_critical
        )

        return CPMResult(
            tasks=task_results,
            project_start=project_start,
            project_finish=project_finish,
            cycles_detected=topo.cycle_nodes,
            critical_path_uids=critical,
            near_critical_uids=near_critical,
            violations=tuple(violations),
        )

    # ---- forward pass ----------------------------------------------

    def _forward_pass(
        self,
        order: tuple[int, ...],
        tasks_by_uid: dict[int, Task],
        preds_of: dict[int, list[Relation]],
        cal: Calendar,
        schedule: Schedule,
        violations: list[ConstraintViolation],
    ) -> tuple[dict[int, datetime], dict[int, datetime]]:
        es: dict[int, datetime] = {}
        ef: dict[int, datetime] = {}
        anchor = schedule.project_start or _earliest_task_start(schedule)
        if anchor is None:
            anchor = datetime(2000, 1, 1, 8, 0, tzinfo=UTC)
        anchor = snap_forward(anchor, cal)

        for uid in order:
            task = tasks_by_uid[uid]
            es_candidate = anchor
            ef_candidate: datetime | None = None

            for rel in preds_of.get(uid, ()):
                pred_es = es.get(rel.predecessor_unique_id)
                pred_ef = ef.get(rel.predecessor_unique_id)
                if pred_es is None or pred_ef is None:
                    continue
                field_, bound = forward_link_bound(
                    rel.relation_type, pred_es, pred_ef, rel.lag_minutes, cal
                )
                bound = snap_forward(bound, cal)
                if field_ == "ES":
                    if bound > es_candidate:
                        es_candidate = bound
                else:  # "EF"
                    if ef_candidate is None or bound > ef_candidate:
                        ef_candidate = bound

            if ef_candidate is not None:
                # EF-bound links drive EF first, then ES back-derives.
                es_from_ef = subtract_working_minutes(
                    ef_candidate, task.duration_minutes, cal
                )
                if es_from_ef > es_candidate:
                    es_candidate = es_from_ef
            ef_from_es = add_working_minutes(
                es_candidate, task.duration_minutes, cal
            )
            ef_final = ef_candidate if ef_candidate and ef_candidate > ef_from_es else ef_from_es

            outcome = apply_forward_constraint(task, es_candidate, ef_final, cal)
            es_final = outcome.early_start
            ef_final = outcome.early_finish

            if task.constraint_type == ConstraintType.MUST_START_ON:
                # Re-derive EF from the locked ES.
                ef_final = add_working_minutes(
                    es_final, task.duration_minutes, cal
                )
            elif task.constraint_type == ConstraintType.MUST_FINISH_ON:
                # Re-derive ES from the locked EF.
                es_final = subtract_working_minutes(
                    ef_final, task.duration_minutes, cal
                )

            if outcome.violation is not None:
                violations.append(outcome.violation)

            es[uid] = es_final
            ef[uid] = ef_final

        return es, ef

    # ---- backward pass ---------------------------------------------

    def _backward_pass(
        self,
        order: tuple[int, ...],
        tasks_by_uid: dict[int, Task],
        succs_of: dict[int, list[Relation]],
        cal: Calendar,
        anchor_finish: datetime | None,
        violations: list[ConstraintViolation],
    ) -> tuple[dict[int, datetime], dict[int, datetime]]:
        ls: dict[int, datetime] = {}
        lf: dict[int, datetime] = {}
        if anchor_finish is None:
            anchor_finish = datetime(2000, 1, 1, 16, 0, tzinfo=UTC)

        for uid in reversed(order):
            task = tasks_by_uid[uid]
            lf_candidate = anchor_finish
            ls_candidate: datetime | None = None

            for rel in succs_of.get(uid, ()):
                succ_ls = ls.get(rel.successor_unique_id)
                succ_lf = lf.get(rel.successor_unique_id)
                if succ_ls is None or succ_lf is None:
                    continue
                field_, bound = backward_link_bound(
                    rel.relation_type, succ_ls, succ_lf, rel.lag_minutes, cal
                )
                if field_ == "LF":
                    if bound < lf_candidate:
                        lf_candidate = bound
                else:  # "LS"
                    if ls_candidate is None or bound < ls_candidate:
                        ls_candidate = bound

            # Derive the missing boundary from duration.
            if ls_candidate is None:
                ls_from_lf = subtract_working_minutes(
                    lf_candidate, task.duration_minutes, cal
                )
                ls_final_guess = ls_from_lf
            else:
                lf_from_ls = add_working_minutes(
                    ls_candidate, task.duration_minutes, cal
                )
                if lf_from_ls < lf_candidate:
                    lf_candidate = lf_from_ls
                ls_final_guess = ls_candidate

            outcome = apply_backward_constraint(
                task, ls_final_guess, lf_candidate, cal
            )
            ls_final = outcome.late_start
            lf_final = outcome.late_finish

            if task.constraint_type == ConstraintType.MUST_START_ON:
                lf_final = add_working_minutes(
                    ls_final, task.duration_minutes, cal
                )
            elif task.constraint_type == ConstraintType.MUST_FINISH_ON:
                ls_final = subtract_working_minutes(
                    lf_final, task.duration_minutes, cal
                )
            else:
                # Keep LS = LF - duration consistent.
                ls_final = subtract_working_minutes(
                    lf_final, task.duration_minutes, cal
                )

            if outcome.violation is not None:
                violations.append(outcome.violation)

            ls[uid] = ls_final
            lf[uid] = lf_final

        return ls, lf


# ---- helpers --------------------------------------------------------


def _find_calendar(schedule: Schedule) -> Calendar:
    for c in schedule.calendars:
        if c.name == schedule.default_calendar_name:
            return c
    if schedule.calendars:
        return schedule.calendars[0]
    # Synthesize a default calendar on empty lists — a schedule can
    # arrive with no calendars if constructed from a minimal fixture.
    # The CPM engine requires *some* calendar; this is the forensic-
    # defensibility knob (M4 guardrail: flag if model change seems
    # needed).
    return Calendar(name=schedule.default_calendar_name or "Standard")


def _index_relations(
    relations: list[Relation], acyclic_uids: set[int]
) -> tuple[dict[int, list[Relation]], dict[int, list[Relation]]]:
    preds: dict[int, list[Relation]] = {}
    succs: dict[int, list[Relation]] = {}
    for r in relations:
        if (
            r.predecessor_unique_id not in acyclic_uids
            or r.successor_unique_id not in acyclic_uids
        ):
            continue
        preds.setdefault(r.successor_unique_id, []).append(r)
        succs.setdefault(r.predecessor_unique_id, []).append(r)
    return preds, succs


def _earliest_task_start(schedule: Schedule) -> datetime | None:
    starts = [t.start for t in schedule.tasks if t.start is not None]
    return min(starts) if starts else None


def _min_or_none(values) -> datetime | None:  # type: ignore[no-untyped-def]
    vals = [v for v in values if v is not None]
    return min(vals) if vals else None


def _max_or_none(values) -> datetime | None:  # type: ignore[no-untyped-def]
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def _build_task_results(
    all_tasks: list[Task],
    acyclic_uids: set[int],
    es_map: dict[int, datetime],
    ef_map: dict[int, datetime],
    ls_map: dict[int, datetime],
    lf_map: dict[int, datetime],
    succs_of: dict[int, list[Relation]],
    relations: list[Relation],
    tasks_by_uid: dict[int, Task],
    cal: Calendar,
    opts: CPMOptions,
) -> dict[int, TaskCPMResult]:
    # Near-critical threshold in working minutes (hours_per_day * 60).
    near_crit_min = int(round(opts.near_critical_threshold_days * cal.hours_per_day * 60))

    out: dict[int, TaskCPMResult] = {}
    for t in all_tasks:
        uid = t.unique_id
        if uid not in acyclic_uids:
            out[uid] = TaskCPMResult(unique_id=uid, skipped_due_to_cycle=True)
            continue

        es = es_map.get(uid)
        ef = ef_map.get(uid)
        ls = ls_map.get(uid)
        lf = lf_map.get(uid)
        if es is None or ef is None or ls is None or lf is None:
            out[uid] = TaskCPMResult(unique_id=uid, skipped_due_to_cycle=True)
            continue

        ts_min = working_minutes_between(es, ls, cal)

        # Free slack = min over successor links of the per-link DS.
        succ_rels = succs_of.get(uid, [])
        if succ_rels:
            fs_candidates: list[int] = []
            for rel in succ_rels:
                s_es = es_map.get(rel.successor_unique_id)
                s_ef = ef_map.get(rel.successor_unique_id)
                if s_es is None or s_ef is None:
                    continue
                fs_candidates.append(
                    _link_free_slack(rel, es, ef, s_es, s_ef, cal)
                )
            fs_min = min(fs_candidates) if fs_candidates else ts_min
        else:
            fs_min = ts_min

        on_critical = ts_min <= 0
        on_near = (not on_critical) and (0 < ts_min <= near_crit_min)

        out[uid] = TaskCPMResult(
            unique_id=uid,
            early_start=es,
            early_finish=ef,
            late_start=ls,
            late_finish=lf,
            total_slack_minutes=ts_min,
            free_slack_minutes=fs_min,
            on_critical_path=on_critical,
            on_near_critical=on_near,
        )
    return out


def _link_free_slack(
    rel: Relation,
    pred_es: datetime,
    pred_ef: datetime,
    succ_es: datetime,
    succ_ef: datetime,
    cal: Calendar,
) -> int:
    """Per-link driving slack — value used for free-slack aggregation.

    Mirrors :func:`app.engine.relations.link_driving_slack_minutes` but
    accepts a :class:`Relation` directly.
    """
    from app.engine.relations import link_driving_slack_minutes

    return link_driving_slack_minutes(
        rel.relation_type,
        pred_es,
        pred_ef,
        succ_es,
        succ_ef,
        rel.lag_minutes,
        cal,
    )


def compute_cpm(
    schedule: Schedule, options: CPMOptions | None = None
) -> CPMResult:
    """One-shot helper — equivalent to ``CPMEngine(s, o).compute()``."""
    return CPMEngine(schedule, options).compute()


