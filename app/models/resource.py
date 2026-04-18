"""Resource and ResourceAssignment models.

Maps to MS Project's ``Resource`` COM object and the
``Task.Assignments`` / ``Resource.Assignments`` collections.

DCMA Metric 10 (``dcma-14-point-assessment §4.10``) reads
``Task.resource_count`` (computed from these assignments) to count
unresourced incomplete tasks. The forensic engine never resolves
``Resource`` instances by name (names are CUI per
``cui-compliance-constraints §2d``); cross-version matching is by
``unique_id`` only, mirroring the UniqueID rule for tasks
(``mpp-parsing-com-automation §5``).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceType


class ResourceAssignment(BaseModel):
    """A single (resource, task) assignment.

    Maps to ``Assignment`` in MS Project's COM object model. One
    ``Task`` carries zero or more assignments via
    ``Task.Assignments``; one ``Resource`` carries zero or more via
    ``Resource.Assignments``.

    The forensic data model stores assignments as facts of who-is-on-
    what; effort distributions, work contours, and overtime splits are
    not represented in Phase 1. EVA fields (BCWS, BCWP, ACWP) are
    Phase 3 and are not present here per BUILD-PLAN §1.5.
    """

    model_config = ConfigDict(extra="forbid")

    resource_unique_id: Annotated[int, Field(gt=0)]
    """COM property: ``Assignment.ResourceUniqueID``. Stable across
    schedule edits; the only safe key for cross-version matching.
    """

    task_unique_id: Annotated[int, Field(gt=0)]
    """COM property: ``Assignment.TaskUniqueID``. Cross-references
    the task ``unique_id`` on the schedule's ``Task`` list."""

    units: Annotated[float, Field(ge=0)] = 1.0
    """Allocation units (1.0 = 100%, 0.5 = half-time).

    COM property: ``Assignment.Units``. Pydantic stores it as a
    fraction; MS Project's UI renders it as a percentage.
    """

    work_minutes: Annotated[int, Field(ge=0)] = 0
    """Total assigned work in minutes (Gotcha 5 unit convention,
    ``mpp-parsing-com-automation §3.5``).

    COM property: ``Assignment.Work``. Always minutes internally;
    presentation conversion to working days happens elsewhere.
    """


class Resource(BaseModel):
    """A schedule resource (work, material, or cost).

    Maps to MS Project's ``Resource`` COM object. ``unique_id`` is
    stable across versions; ``id`` is the row number and changes when
    resources are inserted, deleted, or re-ordered (same UniqueID rule
    as ``Task``, ``mpp-parsing-com-automation §5``).
    """

    model_config = ConfigDict(extra="forbid")

    unique_id: Annotated[int, Field(gt=0)]
    """COM property: ``Resource.UniqueID``. Positive int. Stable
    cross-version key (G3 disallows zero and negatives)."""

    resource_id: Annotated[int, Field(ge=0)]
    """COM property: ``Resource.ID``. Display row number. Not stable
    across edits — never use for cross-version matching."""

    name: str
    """COM property: ``Resource.Name``. CUI-bearing
    (``cui-compliance-constraints §2d``); never logged. The
    Milestone 12 sanitizer replaces this with a label before any
    AI-prompt construction."""

    resource_type: ResourceType = ResourceType.WORK
    """COM property: ``Resource.Type``. Defaults to ``WORK``."""

    initials: str = ""
    """COM property: ``Resource.Initials``. Optional short label."""

    group: str = ""
    """COM property: ``Resource.Group``. Optional group/department
    label used for cost-pool roll-ups (Phase 3)."""

    max_units: Annotated[float, Field(ge=0)] = 1.0
    """COM property: ``Resource.MaxUnits``. Maximum simultaneous
    allocation (1.0 = single full-time equivalent)."""
