"""Task-dependency (relationship) model.

Maps to MS Project's ``TaskDependency`` COM object exposed via
``Task.TaskDependencies`` (``mpp-parsing-com-automation §5``). The
predecessor and successor are recorded as **UniqueIDs** — never as
``ID`` and never as ``Name`` — per BUILD-PLAN §2.7 and the
``mpp-parsing-com-automation §5`` UniqueID rule.

Lag is stored in **minutes** (G5, ``mpp-parsing-com-automation §3.5``)
and may be negative (a "lead").
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import RelationType


class Relation(BaseModel):
    """A logic link between two tasks.

    Maps to a single ``TaskDependency`` element of
    ``Task.TaskDependencies``. The predecessor and successor are keyed
    by UniqueID so the link survives row inserts, deletes, and
    re-orders across versions.
    """

    model_config = ConfigDict(extra="forbid")

    predecessor_unique_id: Annotated[int, Field(gt=0)]
    """COM property: ``TaskDependency.From.UniqueID``. Positive int
    (G3); cross-version-stable per ``mpp-parsing-com-automation §5``."""

    successor_unique_id: Annotated[int, Field(gt=0)]
    """COM property: enclosing ``Task.UniqueID`` (the dependency is
    discovered while iterating the successor's
    ``TaskDependencies``)."""

    relation_type: RelationType = RelationType.FS
    """COM property: ``TaskDependency.Type``. COM enum 0=FF, 1=FS,
    2=SF, 3=SS — distinct from MPXJ's enum
    (``mpp-parsing-com-automation §5``)."""

    lag_minutes: int = 0
    """COM property: ``TaskDependency.Lag``. Minutes (G5). May be
    negative (a "lead") — DCMA Metric 2 (``§4.2``) flags any negative
    lag, and DCMA Metric 3 (``§4.3``) flags positive lags above the
    09NOV09 5-day MSP/OpenPlan carve-out."""

    @model_validator(mode="after")
    def _no_self_loop(self) -> "Relation":
        """G4: a task cannot be its own predecessor."""
        if self.predecessor_unique_id == self.successor_unique_id:
            raise ValueError(
                "predecessor_unique_id and successor_unique_id must differ (G4)"
            )
        return self
