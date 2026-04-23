"""Schema invariant — no ``_minutes`` / ``_hours`` / ``_seconds`` fields
on any public Pydantic model in :mod:`app.engine`.

Authority: BUILD-PLAN §2.19 (AM9, 4/23/2026). All user-visible durations
— Pydantic contract field names, renderer output, README examples,
Word/Excel/HTML report bodies, and CLI output — are denominated in
DAYS. Minutes and hours are internal CPM currency (§2.16) and must
never surface in the public engine contract.

This test enforces §2.19 structurally: it walks
:data:`app.engine.__all__`, filters to :class:`pydantic.BaseModel`
subclasses, and asserts that no ``model_fields`` key matches the
regex ``/_(minutes|hours|seconds)$/``.

Remediation path on failure: rename the offending field to the
``*_days`` convention and convert at construction time via
:func:`app.engine.units.minutes_to_days`. Do not add an escape
hatch; the invariant is forensic-grade per NASA Schedule Management
Handbook §5.5.9.1 ("task durations should generally be assigned in
workdays") and Papicito's forensic-tool standard dated 4/23/2026.

Note on regex scope: the pattern only matches fields ending in
``_minutes``, ``_hours``, or ``_seconds``. Fields whose suffix happens
to contain one of those tokens as a non-terminal component — e.g.
``calendar_hours_per_day`` (ends in ``_day``) — do NOT match and pass
the invariant.
"""

from __future__ import annotations

import inspect
import re

import pytest
from pydantic import BaseModel

import app.engine as engine

_FORBIDDEN_SUFFIX = re.compile(r"_(minutes|hours|seconds)$")


def _collect_public_models() -> list[type[BaseModel]]:
    """Return every public Pydantic model exported by :mod:`app.engine`.

    Walks ``app.engine.__all__`` and filters to class objects that are
    proper subclasses of :class:`pydantic.BaseModel`. Non-class exports
    (functions, enums, exception types) are skipped.
    """

    models: list[type[BaseModel]] = []
    for name in engine.__all__:
        obj = getattr(engine, name)
        if inspect.isclass(obj) and issubclass(obj, BaseModel):
            models.append(obj)
    return models


def test_at_least_one_public_model_scanned() -> None:
    """Guardrail — the parameterized invariant cannot be vacuous.

    If ``app.engine.__all__`` is ever emptied or loses every Pydantic
    model, the schema-invariant test below would pass trivially with
    zero parameter sets. This sentinel asserts the scan has non-empty
    input.
    """

    assert len(_collect_public_models()) > 0, (
        "No public Pydantic models were collected from app.engine.__all__. "
        "The schema invariant (BUILD-PLAN §2.19, AM9) would be vacuous. "
        "Verify that app.engine.__all__ still exports the engine's "
        "public Pydantic contract."
    )


@pytest.mark.parametrize(
    "model_cls",
    _collect_public_models(),
    ids=lambda cls: cls.__name__,
)
def test_public_model_has_no_minute_hour_or_second_fields(
    model_cls: type[BaseModel],
) -> None:
    """No public model field may end in ``_minutes``/``_hours``/``_seconds``.

    Enforces BUILD-PLAN §2.19 (AM9): user-visible durations are
    denominated in DAYS. Minutes and hours are internal CPM currency
    only.
    """

    violations = [
        field_name
        for field_name in model_cls.model_fields
        if _FORBIDDEN_SUFFIX.search(field_name)
    ]
    assert not violations, (
        f"Public engine model {model_cls.__name__} has field(s) with a "
        f"forbidden _minutes/_hours/_seconds suffix: {sorted(violations)}. "
        "This violates BUILD-PLAN §2.19 (AM9, 4/23/2026): user-visible "
        "durations must be denominated in DAYS. Remediation: rename the "
        "offending field(s) to the *_days convention and convert at "
        "construction via app.engine.units.minutes_to_days."
    )
