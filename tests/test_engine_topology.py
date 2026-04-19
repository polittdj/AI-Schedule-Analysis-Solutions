"""Tests for topological sort and cycle detection (BUILD-PLAN §5 M4 E1)."""

from __future__ import annotations

import pytest

from app.engine.exceptions import CircularDependencyError
from app.engine.topology import detect_cycles, topological_order
from app.models.enums import RelationType
from app.models.relation import Relation
from app.models.task import Task


def _task(uid: int) -> Task:
    return Task(unique_id=uid, task_id=uid, name=f"T{uid}")


def _rel(p: int, s: int, rt: RelationType = RelationType.FS) -> Relation:
    return Relation(
        predecessor_unique_id=p, successor_unique_id=s, relation_type=rt
    )


# ---- Kahn topo sort ------------------------------------------------


def test_empty_schedule_topo() -> None:
    result = topological_order([], [])
    assert result.order == ()
    assert result.cycle_nodes == frozenset()


def test_single_task_topo() -> None:
    result = topological_order([_task(1)], [])
    assert result.order == (1,)


def test_linear_chain_topo() -> None:
    tasks = [_task(3), _task(1), _task(2)]
    relations = [_rel(1, 2), _rel(2, 3)]
    result = topological_order(tasks, relations)
    assert result.order == (1, 2, 3)


def test_diamond_topo() -> None:
    # 1 -> 2,3; 2,3 -> 4
    tasks = [_task(i) for i in (1, 2, 3, 4)]
    relations = [_rel(1, 2), _rel(1, 3), _rel(2, 4), _rel(3, 4)]
    result = topological_order(tasks, relations)
    assert result.order[0] == 1
    assert result.order[-1] == 4
    assert set(result.order) == {1, 2, 3, 4}


def test_independent_subgraphs_topo() -> None:
    tasks = [_task(i) for i in (1, 2, 3, 4)]
    relations = [_rel(1, 2), _rel(3, 4)]
    result = topological_order(tasks, relations)
    assert set(result.order) == {1, 2, 3, 4}
    # 1 precedes 2; 3 precedes 4.
    assert result.order.index(1) < result.order.index(2)
    assert result.order.index(3) < result.order.index(4)


def test_deterministic_tie_break_by_uid() -> None:
    # All four tasks are independent, ascending uid order expected.
    tasks = [_task(i) for i in (4, 2, 1, 3)]
    result = topological_order(tasks, [])
    assert result.order == (1, 2, 3, 4)


# ---- Cycle detection ----------------------------------------------


def test_two_node_cycle_detected() -> None:
    tasks = [_task(1), _task(2)]
    relations = [_rel(1, 2), _rel(2, 1)]
    cycles = detect_cycles(tasks, relations)
    assert cycles == frozenset({1, 2})


def test_three_node_cycle_detected() -> None:
    tasks = [_task(1), _task(2), _task(3)]
    relations = [_rel(1, 2), _rel(2, 3), _rel(3, 1)]
    cycles = detect_cycles(tasks, relations)
    assert cycles == frozenset({1, 2, 3})


def test_no_cycle_detected() -> None:
    tasks = [_task(1), _task(2), _task(3)]
    relations = [_rel(1, 2), _rel(2, 3)]
    assert detect_cycles(tasks, relations) == frozenset()


def test_strict_cycles_raises() -> None:
    tasks = [_task(1), _task(2), _task(3)]
    relations = [_rel(1, 2), _rel(2, 3), _rel(3, 1)]
    with pytest.raises(CircularDependencyError) as excinfo:
        topological_order(tasks, relations, strict_cycles=True)
    assert excinfo.value.nodes == {1, 2, 3}


def test_lenient_cycles_returns_acyclic_subgraph() -> None:
    # 1 and 2 form a cycle; 3 -> 4 is acyclic.
    tasks = [_task(i) for i in (1, 2, 3, 4)]
    relations = [_rel(1, 2), _rel(2, 1), _rel(3, 4)]
    result = topological_order(tasks, relations)
    assert result.cycle_nodes == frozenset({1, 2})
    assert result.order == (3, 4)


def test_self_loop_detected_via_direct_injection() -> None:
    """Model G4 guards self-loops, but dict-injection bypasses it (E22)."""
    # Construct a Relation that bypasses Pydantic validation by patching
    # the dict and then the test asserts Tarjan still reports the SCC.
    r = Relation.model_construct(
        predecessor_unique_id=1, successor_unique_id=1, relation_type=RelationType.FS,
        lag_minutes=0,
    )
    cycles = detect_cycles([_task(1)], [r])
    assert cycles == frozenset({1})


def test_acyclic_subgraph_rooted_at_cycle_successor_isolated() -> None:
    """A node downstream of only cyclic nodes must still be excluded
    from ``order`` when its predecessors never get scheduled."""
    # 1 <-> 2 cycle; 2 -> 3
    tasks = [_task(i) for i in (1, 2, 3)]
    relations = [_rel(1, 2), _rel(2, 1), _rel(2, 3)]
    result = topological_order(tasks, relations)
    assert 3 in result.order
    assert 1 not in result.order and 2 not in result.order


def test_cycle_with_dangling_predecessor() -> None:
    # 1 -> 2; 2 <-> 3; 4 independent.
    tasks = [_task(i) for i in (1, 2, 3, 4)]
    relations = [_rel(1, 2), _rel(2, 3), _rel(3, 2)]
    result = topological_order(tasks, relations)
    assert result.cycle_nodes == frozenset({2, 3})
    # 1 gets scheduled; 4 independent, also scheduled.
    assert 1 in result.order
    assert 4 in result.order
    assert 2 not in result.order and 3 not in result.order
