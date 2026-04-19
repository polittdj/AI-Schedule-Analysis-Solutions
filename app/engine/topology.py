"""Topological sort and cycle detection over the schedule logic graph.

The CPM forward pass needs a linearization of tasks such that every
predecessor precedes its successors. For acyclic networks the answer
is a Kahn topological sort (``driving-slack-and-paths §8`` invariant:
forward/backward pass must be deterministic). For cyclic networks the
engine's behavior is governed by :attr:`CPMOptions.strict_cycles`:

* ``strict_cycles=True`` → raise
  :class:`~app.engine.exceptions.CircularDependencyError` listing every
  UniqueID that participates in at least one cycle (BUILD-PLAN §5 M4
  E1).
* ``strict_cycles=False`` → return the topological order of the
  acyclic subgraph together with the set of cyclic UniqueIDs so the
  engine can surface them on :class:`CPMResult.cycles_detected` and
  still compute float for the rest of the network (BUILD-PLAN §5 M4
  AC5).

Cycles are identified by Tarjan's strongly-connected-components
algorithm: any SCC with more than one node, or a single-node SCC with
a self-loop, is a cycle. Self-loops are guarded upstream by
:class:`~app.models.relation.Relation`'s G4 validator, but the
algorithm still handles them for dict-injected pathological inputs
(BUILD-PLAN §5 M4 E22).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.engine.exceptions import CircularDependencyError
from app.models.relation import Relation
from app.models.task import Task


@dataclass(frozen=True, slots=True)
class TopoResult:
    """Output of :func:`topological_order`.

    Attributes:
        order: ``Task.unique_id`` values in an order where every
            predecessor precedes its successors. Cyclic UIDs are
            excluded.
        cycle_nodes: UIDs that participate in at least one cycle.
            Empty when the network is acyclic.
    """

    order: tuple[int, ...]
    cycle_nodes: frozenset[int] = field(default_factory=frozenset)


def _build_adjacency(
    tasks: list[Task], relations: list[Relation]
) -> tuple[dict[int, list[int]], dict[int, int]]:
    """Build forward adjacency ``pred_uid → [succ_uid, ...]`` plus
    an in-degree map keyed by successor UID.

    Only relations whose endpoints appear in ``tasks`` contribute. The
    model's G11 validator guarantees this at Schedule level; the extra
    guard here lets the topology module be called on hand-built inputs
    during unit testing.
    """
    known = {t.unique_id for t in tasks}
    adj: dict[int, list[int]] = defaultdict(list)
    indeg: dict[int, int] = {uid: 0 for uid in known}
    for r in relations:
        p, s = r.predecessor_unique_id, r.successor_unique_id
        if p not in known or s not in known:
            continue
        adj[p].append(s)
        indeg[s] = indeg.get(s, 0) + 1
    return adj, indeg


def _find_cycle_nodes(
    tasks: list[Task], relations: list[Relation]
) -> frozenset[int]:
    """Return the set of UIDs that sit inside any cycle.

    Iterative Tarjan's SCC — recursion depth could blow the stack on
    very large schedules (defensive on the HP ZBook corporate
    workstation per CLAUDE.md §7 environment constraints).
    """
    known = [t.unique_id for t in tasks]
    adj, _ = _build_adjacency(tasks, relations)

    index_counter = [0]
    stack: list[int] = []
    on_stack: set[int] = set()
    indices: dict[int, int] = {}
    lowlinks: dict[int, int] = {}
    cycles: set[int] = set()
    # Explicit stack: (node, iterator_over_successors)
    for start in known:
        if start in indices:
            continue
        work: list[tuple[int, list[int]]] = [(start, list(adj.get(start, [])))]
        indices[start] = index_counter[0]
        lowlinks[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, succs = work[-1]
            if succs:
                w = succs.pop()
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, list(adj.get(w, []))))
                elif w in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[w])
            else:
                if lowlinks[node] == indices[node]:
                    component: list[int] = []
                    while True:
                        top = stack.pop()
                        on_stack.remove(top)
                        component.append(top)
                        if top == node:
                            break
                    if len(component) > 1:
                        cycles.update(component)
                    else:
                        sole = component[0]
                        # Self-loop detection (dict-injected — G4
                        # validator normally guards this).
                        if sole in adj.get(sole, ()):
                            cycles.add(sole)
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlinks[parent] = min(lowlinks[parent], lowlinks[node])
    return frozenset(cycles)


def topological_order(
    tasks: list[Task],
    relations: list[Relation],
    *,
    strict_cycles: bool = False,
) -> TopoResult:
    """Return topological order of ``tasks`` with cycles excluded.

    Uses Kahn's algorithm on the acyclic subgraph; cyclic nodes are
    identified via Tarjan's SCC and omitted from ``order``. Tie-
    breaking when multiple zero-in-degree nodes are available uses
    ascending ``unique_id`` — deterministic output is a forensic
    defensibility requirement (BUILD-PLAN §6 AC bar).

    Args:
        tasks: schedule tasks.
        relations: schedule relations.
        strict_cycles: when True, any cycle raises
            :class:`CircularDependencyError`.

    Returns:
        :class:`TopoResult` with the order and (if any) cycle UIDs.
    """
    cycle_nodes = _find_cycle_nodes(tasks, relations)
    if cycle_nodes and strict_cycles:
        raise CircularDependencyError(set(cycle_nodes))

    adj, indeg = _build_adjacency(tasks, relations)

    # Remove cyclic nodes from consideration entirely; their edges to
    # acyclic nodes still count toward the acyclic in-degree — but that
    # would leave acyclic successors perpetually blocked. A task that
    # depends on a cyclic predecessor cannot be scheduled without a
    # forward-pass value for that predecessor. Drop their outgoing
    # edges for the Kahn queue so the acyclic subgraph finishes.
    effective_indeg = dict(indeg)
    for cy in cycle_nodes:
        for succ in adj.get(cy, ()):
            if succ not in cycle_nodes:
                effective_indeg[succ] -= 1

    # Initial queue: zero in-degree and not in a cycle.
    ready: deque[int] = deque(
        sorted(
            uid for uid, d in effective_indeg.items()
            if d == 0 and uid not in cycle_nodes
        )
    )

    order: list[int] = []
    while ready:
        uid = ready.popleft()
        order.append(uid)
        for succ in sorted(adj.get(uid, ())):
            if succ in cycle_nodes:
                continue
            effective_indeg[succ] -= 1
            if effective_indeg[succ] == 0:
                ready.append(succ)

    return TopoResult(order=tuple(order), cycle_nodes=cycle_nodes)


def detect_cycles(
    tasks: list[Task], relations: list[Relation]
) -> frozenset[int]:
    """Public cycle-detection entry point — alias for internal SCC.

    Useful in tests and in consumers that want cycle UIDs without
    triggering a full topological sort.
    """
    return _find_cycle_nodes(tasks, relations)
