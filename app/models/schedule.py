"""Schedule model — top-level container.

Maps to MS Project's ``Project`` COM object plus its ``Tasks``,
``TaskDependencies`` (across all tasks), ``Resources``, and
``Calendars`` collections.

Cross-model invariants enforced here:

* G9  — ``status_date`` is timezone-aware when present.
* G10 — every ``Task.unique_id`` is unique within the schedule.
* G11 — every ``Relation`` refers to tasks that exist.
* G12 — a schedule with zero tasks is legal (a fresh / empty file).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models._validators import require_tz_aware
from app.models.calendar import Calendar
from app.models.relation import Relation
from app.models.resource import Resource, ResourceAssignment
from app.models.task import Task


class Schedule(BaseModel):
    """A parsed, validated schedule file.

    Produced by the Milestone 3 COM adapter (``parse_mpp``) and
    consumed read-only by the CPM engine (M4), the DCMA metric modules
    (M5–M7), the NASA overlay (M8), the comparator (M9), the driving-
    path tracer (M10), and the manipulation engine (M11). Any
    downstream mutation is performed via ``model_copy(update=...)``
    per BUILD-PLAN §5 M7 AC1 (CPT no-mutation invariant).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    """COM property: ``Project.Name`` (usually the file stem).
    CUI-bearing — never logged."""

    status_date: datetime | None = None
    """COM property: ``Project.StatusDate``. tz-aware when present.

    ``None`` here means the project has no status date set; the
    Milestone 3 adapter converts the ``"NA"`` / OLE-zero /
    MSP-epoch sentinels per ``mpp-parsing-com-automation §3.6``
    (Gotcha 6) to ``None`` before populating this model.
    """

    project_start: datetime | None = None
    """COM property: ``Project.ProjectStart``. tz-aware."""

    project_finish: datetime | None = None
    """COM property: ``Project.ProjectFinish``. tz-aware."""

    default_calendar_name: str = "Standard"
    """COM property: ``Project.Calendar.Name``. The project's default
    working-time calendar; its ``hours_per_day`` drives the minutes →
    working-days conversion (G5,
    ``mpp-parsing-com-automation §3.5``)."""

    tasks: list[Task] = Field(default_factory=list)
    """All detail and summary tasks, keyed internally by
    ``Task.unique_id``."""

    relations: list[Relation] = Field(default_factory=list)
    """All logic links, each keyed by
    ``(predecessor_unique_id, successor_unique_id, relation_type)``.
    A single task pair may carry multiple links of different types."""

    resources: list[Resource] = Field(default_factory=list)
    """All resources defined on the project."""

    assignments: list[ResourceAssignment] = Field(default_factory=list)
    """All (resource, task) assignments."""

    calendars: list[Calendar] = Field(default_factory=list)
    """All calendars defined on the project, including ``Standard``
    and any base / task calendars."""

    @field_validator("status_date", "project_start", "project_finish")
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        """G9 (status_date) plus the two project-level dates."""
        return require_tz_aware(v)

    @model_validator(mode="after")
    def _cross_model_checks(self) -> Schedule:
        """G10, G11 — schedule-level referential integrity.

        * G10 — every ``Task.unique_id`` must be unique.
        * G11 — every ``Relation`` must reference ``unique_id`` values
          that exist in ``tasks``.

        G12 is implicit: ``tasks == []`` passes every check.
        """
        # G10 — Task UniqueID uniqueness.
        uid_counts: dict[int, int] = {}
        for t in self.tasks:
            uid_counts[t.unique_id] = uid_counts.get(t.unique_id, 0) + 1
        duplicates = sorted(uid for uid, c in uid_counts.items() if c > 1)
        if duplicates:
            raise ValueError(f"duplicate Task.unique_id values: {duplicates} (G10)")

        # G11 — Relation predecessor / successor must resolve.
        known_uids = set(uid_counts.keys())
        dangling: list[tuple[int, int]] = []
        for r in self.relations:
            if (
                r.predecessor_unique_id not in known_uids
                or r.successor_unique_id not in known_uids
            ):
                dangling.append((r.predecessor_unique_id, r.successor_unique_id))
        if dangling:
            raise ValueError(
                f"Relation references {dangling} not in tasks (G11)"
            )

        # Assignment task UIDs must also resolve (cross-model hygiene).
        resource_uids = {res.unique_id for res in self.resources}
        for a in self.assignments:
            if a.task_unique_id not in known_uids:
                raise ValueError(
                    f"ResourceAssignment task_unique_id {a.task_unique_id} not in tasks"
                )
            if resource_uids and a.resource_unique_id not in resource_uids:
                raise ValueError(
                    "ResourceAssignment resource_unique_id "
                    f"{a.resource_unique_id} not in resources"
                )

        return self
