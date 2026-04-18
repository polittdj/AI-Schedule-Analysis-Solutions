"""Task model.

Maps to MS Project's ``Task`` COM object. Field names mirror the COM
property where possible (``mpp-parsing-com-automation §4 / Appendix
B``); units follow the Gotcha 5 convention — durations, slack, lag
all in **minutes** (``mpp-parsing-com-automation §3.5``).

The ``unique_id`` field is the **only** stable cross-version
identifier (``mpp-parsing-com-automation §5``). ``task_id`` is the
display row number captured for UI rendering and **must not** be used
for matching across versions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models._validators import require_tz_aware
from app.models.enums import (
    DATE_BEARING_CONSTRAINTS,
    ConstraintType,
    TaskType,
)


class Task(BaseModel):
    """A single schedule task.

    Field-to-COM mapping follows ``mpp-parsing-com-automation
    Appendix B``. Date fields are timezone-aware (G1); duration / slack
    fields are **minutes** (G5). ``unique_id`` must be a positive
    integer (G3).
    """

    model_config = ConfigDict(extra="forbid")

    # ---- Identification ------------------------------------------------

    unique_id: Annotated[int, Field(gt=0)]
    """COM property: ``Task.UniqueID``. Stable across schedule edits.
    The **only** identifier used for cross-version matching per
    ``mpp-parsing-com-automation §5`` and BUILD-PLAN §2.7."""

    task_id: Annotated[int, Field(ge=0)]
    """COM property: ``Task.ID``. Display row number. Changes when
    tasks are inserted, deleted, or re-ordered. Captured for
    rendering only — never for cross-version matching."""

    name: str
    """COM property: ``Task.Name``. CUI-bearing
    (``cui-compliance-constraints §2d``); the Milestone 12 sanitizer
    replaces it with a label before any AI prompt is built."""

    wbs: str = ""
    """COM property: ``Task.WBS``. Outline code; CUI-bearing."""

    outline_level: Annotated[int, Field(ge=0)] = 0
    """COM property: ``Task.OutlineLevel``."""

    # ---- Dates (all tz-aware per G1) ----------------------------------

    start: datetime | None = None
    """COM property: ``Task.Start``. Forecast start. tz-aware."""

    finish: datetime | None = None
    """COM property: ``Task.Finish``. Forecast finish. tz-aware."""

    early_start: datetime | None = None
    """COM property: ``Task.EarlyStart``. Output of CPM forward pass."""

    early_finish: datetime | None = None
    """COM property: ``Task.EarlyFinish``."""

    late_start: datetime | None = None
    """COM property: ``Task.LateStart``. Output of CPM backward pass."""

    late_finish: datetime | None = None
    """COM property: ``Task.LateFinish``."""

    baseline_start: datetime | None = None
    """COM property: ``Task.BaselineStart``."""

    baseline_finish: datetime | None = None
    """COM property: ``Task.BaselineFinish``."""

    actual_start: datetime | None = None
    """COM property: ``Task.ActualStart``."""

    actual_finish: datetime | None = None
    """COM property: ``Task.ActualFinish``."""

    deadline: datetime | None = None
    """COM property: ``Task.Deadline``. Soft date target distinct
    from constraint date."""

    # ---- Durations and slack (minutes per G5) -------------------------

    duration_minutes: Annotated[int, Field(ge=0)] = 0
    """COM property: ``Task.Duration``. Minutes (G5)."""

    remaining_duration_minutes: Annotated[int, Field(ge=0)] = 0
    """COM property: ``Task.RemainingDuration``. Minutes."""

    actual_duration_minutes: Annotated[int, Field(ge=0)] = 0
    """COM property: ``Task.ActualDuration``. Minutes."""

    baseline_duration_minutes: Annotated[int, Field(ge=0)] = 0
    """COM property: ``Task.BaselineDuration``. Minutes."""

    total_slack_minutes: int = 0
    """COM property: ``Task.TotalSlack``. Minutes. May be **negative**
    (DCMA Metric 7 ``dcma-14-point-assessment §4.7``)."""

    free_slack_minutes: int = 0
    """COM property: ``Task.FreeSlack``. Minutes. May be negative."""

    # ---- Constraint --------------------------------------------------

    constraint_type: ConstraintType = ConstraintType.AS_SOON_AS_POSSIBLE
    """COM property: ``Task.ConstraintType``. Validators enforce G6
    (ASAP/ALAP carry no date) and G7 (date-bearing constraints
    require ``constraint_date``)."""

    constraint_date: datetime | None = None
    """COM property: ``Task.ConstraintDate``. tz-aware when present."""

    # ---- Status / completion ----------------------------------------

    percent_complete: Annotated[float, Field(ge=0, le=100)] = 0.0
    """COM property: ``Task.PercentComplete``. Range [0, 100] enforced
    per G8."""

    task_type: TaskType = TaskType.FIXED_UNITS
    """COM property: ``Task.Type``."""

    # ---- Boolean flags (forensic relevance) -------------------------

    is_milestone: bool = False
    """COM property: ``Task.Milestone``. DCMA Metric 1a excludes
    milestones from the missing-logic numerator boundary; DCMA Metric
    3 (``dcma-14-point-assessment §3``) excludes them from
    ``Total Tasks``."""

    is_summary: bool = False
    """COM property: ``Task.Summary``. Excluded from ``Total Tasks``
    per ``dcma-14-point-assessment §3``."""

    is_critical_from_msp: bool = False
    """COM property: ``Task.Critical``. The MS-Project-computed
    critical flag, captured as MSP's own answer for the M4 validation
    step (``driving-slack-and-paths §4`` MSP-validation requirement)."""

    is_loe: bool = False
    """Level-of-Effort flag (typically a custom MS Project field).
    Excluded from ``Total Tasks`` per DCMA §3."""

    is_rolling_wave: bool = False
    """Rolling-wave-planning placeholder flag (typically a custom MS
    Project field). DCMA Metric 8 (``§4.8``) exempts rolling-wave
    tasks from the high-duration numerator."""

    is_schedule_margin: bool = False
    """NASA SMH schedule-margin flag (``nasa-schedule-management §3``).
    Excluded from the High-Float denominator by the NASA overlay
    (Milestone 8 ``§4.6`` overlay rule)."""

    # ---- Resource roll-up -------------------------------------------

    resource_count: Annotated[int, Field(ge=0)] = 0
    """COM derivation: ``len(Task.Assignments)`` filtered to work
    resources. DCMA Metric 10 (``§4.10``) flags incomplete tasks
    where this is zero."""

    # ---- Validators --------------------------------------------------

    @field_validator(
        "start",
        "finish",
        "early_start",
        "early_finish",
        "late_start",
        "late_finish",
        "baseline_start",
        "baseline_finish",
        "actual_start",
        "actual_finish",
        "deadline",
        "constraint_date",
    )
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        """G1: every date field, when present, must be timezone-aware."""
        return require_tz_aware(v)

    @model_validator(mode="after")
    def _check_constraint_date_rules(self) -> Task:
        """G6 / G7: constraint type and constraint date must agree.

        * ASAP / ALAP MUST NOT carry a constraint date (G6).
        * MSO / MFO / SNET / SNLT / FNET / FNLT MUST carry one (G7).
        """
        ct = self.constraint_type
        cd = self.constraint_date
        if ct in (
            ConstraintType.AS_SOON_AS_POSSIBLE,
            ConstraintType.AS_LATE_AS_POSSIBLE,
        ):
            if cd is not None:
                raise ValueError(
                    f"constraint_type {ct.name} must not carry a constraint_date (G6)"
                )
        elif ct in DATE_BEARING_CONSTRAINTS:
            if cd is None:
                raise ValueError(
                    f"constraint_type {ct.name} requires a constraint_date (G7)"
                )
        return self
