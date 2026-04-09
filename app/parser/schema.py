"""Pydantic models for parsed Microsoft Project schedule data.

Every field that comes from MPXJ is Optional — MPP files are notoriously
inconsistent and any field can be null. The forensic engine is responsible
for flagging missing data; the parser just faithfully reports what it finds.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectInfo(BaseModel):
    """Top-level project properties (from ProjectProperties)."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    status_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    finish_date: Optional[datetime] = None
    current_date: Optional[datetime] = None
    calendar_name: Optional[str] = None


class Relationship(BaseModel):
    """A predecessor/successor logic relationship between two tasks."""

    model_config = ConfigDict(extra="forbid")

    predecessor_uid: int
    successor_uid: int
    type: str = "FS"  # FS, SS, FF, SF
    lag_days: float = 0.0


class TaskData(BaseModel):
    """A single task row from the MPP file.

    `duration` and the other duration-like fields are expressed in
    *working days* (8-hour days). The raw MPXJ values are normalized
    by `mpp_reader._duration_to_days`.
    """

    model_config = ConfigDict(extra="forbid")

    id: Optional[int] = None
    uid: int
    name: Optional[str] = None
    wbs: Optional[str] = None
    outline_level: Optional[int] = None
    start: Optional[datetime] = None
    finish: Optional[datetime] = None
    duration: Optional[float] = None
    actual_start: Optional[datetime] = None
    actual_finish: Optional[datetime] = None
    baseline_start: Optional[datetime] = None
    baseline_finish: Optional[datetime] = None
    baseline_duration: Optional[float] = None
    percent_complete: Optional[float] = None
    remaining_duration: Optional[float] = None
    total_slack: Optional[float] = None
    free_slack: Optional[float] = None
    critical: bool = False
    summary: bool = False
    milestone: bool = False
    constraint_type: Optional[str] = None
    constraint_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    priority: Optional[int] = None
    resource_names: Optional[str] = None
    predecessors: List[int] = Field(default_factory=list)
    successors: List[int] = Field(default_factory=list)


class ResourceData(BaseModel):
    """A resource assignable to one or more tasks."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    name: Optional[str] = None
    type: Optional[str] = None
    max_units: Optional[float] = None


class AssignmentData(BaseModel):
    """Resource assignment onto a task.

    `work`, `actual_work`, and `remaining_work` are in working days
    (consistent with TaskData.duration). `cost` and `actual_cost` are
    in whatever currency the MPP file uses — we do not attempt unit
    normalization.
    """

    model_config = ConfigDict(extra="forbid")

    task_uid: int
    resource_uid: int
    work: Optional[float] = None
    actual_work: Optional[float] = None
    remaining_work: Optional[float] = None
    cost: Optional[float] = None
    actual_cost: Optional[float] = None


class ScheduleData(BaseModel):
    """The master container returned by the MPP parser."""

    model_config = ConfigDict(extra="forbid")

    project_info: ProjectInfo
    tasks: List[TaskData] = Field(default_factory=list)
    resources: List[ResourceData] = Field(default_factory=list)
    assignments: List[AssignmentData] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
