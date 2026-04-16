"""MPP file reader: JPype1 + MPXJ bridge.

Starts a single JVM for the life of the process, loads MPXJ's
`UniversalProjectReader`, and walks the resulting `ProjectFile`
into our Pydantic `ScheduleData` container.

Usage:
    from app.parser.mpp_reader import parse_mpp
    schedule = parse_mpp("/path/to/schedule.mpp")

Notes
-----
* Uses the `org.mpxj` classpath (MPXJ >= 13), not the legacy `net.sf.mpxj`.
* Uses `rel.getPredecessorTask()` / `rel.getSuccessorTask()` — the modern
  relation accessors.
* Every MPXJ field can be null; `_safe_*` helpers handle that uniformly.
* Durations are normalized to working days (8-hour day) via `duration_to_days`.
"""
from __future__ import annotations

import glob
import os
from datetime import datetime
from typing import Any, List, Optional

import jpype

from app.parser.schema import (
    AssignmentData,
    ProjectInfo,
    Relationship,
    ResourceData,
    ScheduleData,
    TaskData,
)

# --------------------------------------------------------------------------- #
# JVM bootstrap
# --------------------------------------------------------------------------- #


def _mpxj_classpath() -> List[str]:
    """Return the list of JARs bundled with the `mpxj` pip package."""
    import mpxj  # local import so module can be imported without mpxj present

    jar_dir = getattr(mpxj, "mpxj_dir", None) or os.path.join(
        os.path.dirname(mpxj.__file__), "lib"
    )
    jars = glob.glob(os.path.join(jar_dir, "*.jar"))
    if not jars:
        raise RuntimeError(
            f"No MPXJ JARs found in {jar_dir}. "
            "Is the `mpxj` pip package installed correctly?"
        )
    return jars


def _ensure_jvm() -> None:
    """Start the JVM once with the MPXJ classpath. Idempotent."""
    if jpype.isJVMStarted():
        return
    jpype.startJVM(classpath=_mpxj_classpath(), convertStrings=True)


# --------------------------------------------------------------------------- #
# Conversion helpers (pure Python — safe to unit-test without a JVM)
# --------------------------------------------------------------------------- #

# Working-day conversion factors, keyed to MPXJ TimeUnit string representations.
# MPXJ `TimeUnit.toString()` returns short codes ("h", "d", "w", ...), while
# `.name()` returns "HOURS", "DAYS", etc. We accept both so tests and live
# parsing share one helper.
_WORKING_DAY_FACTORS = {
    # short codes (from TimeUnit.toString())
    "h": 1.0 / 8.0,
    "d": 1.0,
    "w": 5.0,
    "m": 20.0,   # months → ~20 working days
    "mo": 20.0,
    "min": 1.0 / (60.0 * 8.0),
    "y": 240.0,
    # elapsed variants
    "eh": 1.0 / 8.0,
    "ed": 1.0,
    "ew": 5.0,
    "emo": 20.0,
    "ey": 240.0,
    "emin": 1.0 / (60.0 * 8.0),
    # full names (from TimeUnit.name())
    "hours": 1.0 / 8.0,
    "days": 1.0,
    "weeks": 5.0,
    "months": 20.0,
    "minutes": 1.0 / (60.0 * 8.0),
    "years": 240.0,
    "elapsed_hours": 1.0 / 8.0,
    "elapsed_days": 1.0,
    "elapsed_weeks": 5.0,
    "elapsed_months": 20.0,
    "elapsed_minutes": 1.0 / (60.0 * 8.0),
    "elapsed_years": 240.0,
}


def duration_to_days(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    """Normalize a duration to working days (8-hour day).

    Returns None when `value` is None so that Pydantic Optional fields
    stay None instead of collapsing to 0.0.
    """
    if value is None:
        return None
    if unit is None:
        return float(value)
    key = str(unit).strip().lower()
    factor = _WORKING_DAY_FACTORS.get(key)
    if factor is None:
        # Unknown unit — assume already in days rather than silently dropping.
        return float(value)
    return float(value) * factor


def _extract_duration(jdur: Any) -> Optional[float]:
    """Pull a float (working days) out of an MPXJ `Duration` object."""
    if jdur is None:
        return None
    try:
        raw = float(jdur.getDuration())
    except Exception:
        return None
    units = jdur.getUnits()
    unit_str = str(units.toString()) if units is not None else None
    return duration_to_days(raw, unit_str)


def _to_py_datetime(jdt: Any) -> Optional[datetime]:
    """Convert any MPXJ date/time value (Date, LocalDateTime, ...) to Python."""
    if jdt is None:
        return None
    # jpype converts java.util.Date automatically if we access .getTime() (ms since epoch)
    try:
        if hasattr(jdt, "getTime") and not hasattr(jdt, "getYear"):
            ms = int(jdt.getTime())
            return datetime.fromtimestamp(ms / 1000.0)
    except Exception:
        pass
    # Fallback: parse ISO string (works for java.time.LocalDateTime.toString()
    # which looks like "2024-03-15T08:00" or "2024-03-15T08:00:00").
    try:
        s = str(jdt)
        # LocalDateTime has no zone; add seconds if missing for fromisoformat.
        if "T" in s and s.count(":") == 1:
            s = s + ":00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _to_py_str(jval: Any) -> Optional[str]:
    if jval is None:
        return None
    s = str(jval)
    return s if s else None


def _to_py_int(jval: Any) -> Optional[int]:
    if jval is None:
        return None
    try:
        return int(jval)
    except Exception:
        return None


def _to_py_float(jval: Any) -> Optional[float]:
    if jval is None:
        return None
    try:
        return float(jval)
    except Exception:
        return None


_RELATION_TYPE_MAP = {
    "FINISH_START": "FS",
    "START_START": "SS",
    "FINISH_FINISH": "FF",
    "START_FINISH": "SF",
}


def _relation_type(jtype: Any) -> str:
    if jtype is None:
        return "FS"
    try:
        name = str(jtype.name())
    except Exception:
        name = str(jtype)
    return _RELATION_TYPE_MAP.get(name.upper(), name)


# --------------------------------------------------------------------------- #
# Extractors
# --------------------------------------------------------------------------- #


def _extract_project_info(project_file: Any) -> ProjectInfo:
    props = project_file.getProjectProperties()
    calendar_name: Optional[str] = None
    try:
        default_cal = project_file.getDefaultCalendar()
        if default_cal is not None:
            calendar_name = _to_py_str(default_cal.getName())
    except Exception:
        calendar_name = None

    return ProjectInfo(
        name=_to_py_str(props.getName()) if props is not None else None,
        status_date=_to_py_datetime(props.getStatusDate()) if props is not None else None,
        start_date=_to_py_datetime(props.getStartDate()) if props is not None else None,
        finish_date=_to_py_datetime(props.getFinishDate()) if props is not None else None,
        current_date=_to_py_datetime(props.getCurrentDate()) if props is not None else None,
        calendar_name=calendar_name,
    )


def _extract_task(jtask: Any) -> TaskData:
    uid = _to_py_int(jtask.getUniqueID()) or 0

    constraint_type = None
    try:
        ct = jtask.getConstraintType()
        constraint_type = str(ct.name()) if ct is not None else None
    except Exception:
        constraint_type = None

    predecessors: List[int] = []
    successors: List[int] = []
    try:
        preds = jtask.getPredecessors()
        if preds is not None:
            for rel in preds:
                other = rel.getPredecessorTask()
                if other is not None:
                    pid = _to_py_int(other.getUniqueID())
                    if pid is not None:
                        predecessors.append(pid)
    except Exception:
        pass
    try:
        succs = jtask.getSuccessors()
        if succs is not None:
            for rel in succs:
                other = rel.getSuccessorTask()
                if other is not None:
                    sid = _to_py_int(other.getUniqueID())
                    if sid is not None:
                        successors.append(sid)
    except Exception:
        pass

    # Baselines: MPP stores "baseline 0" (current baseline) plus up to 10
    # additional. For Phase 1 we extract baseline 0.
    baseline_start = None
    baseline_finish = None
    baseline_duration = None
    try:
        baseline_start = _to_py_datetime(jtask.getBaselineStart())
        baseline_finish = _to_py_datetime(jtask.getBaselineFinish())
        baseline_duration = _extract_duration(jtask.getBaselineDuration())
    except Exception:
        pass

    return TaskData(
        id=_to_py_int(jtask.getID()),
        uid=uid,
        name=_to_py_str(jtask.getName()),
        wbs=_to_py_str(jtask.getWBS()),
        outline_level=_to_py_int(jtask.getOutlineLevel()),
        start=_to_py_datetime(jtask.getStart()),
        finish=_to_py_datetime(jtask.getFinish()),
        duration=_extract_duration(jtask.getDuration()),
        actual_start=_to_py_datetime(jtask.getActualStart()),
        actual_finish=_to_py_datetime(jtask.getActualFinish()),
        baseline_start=baseline_start,
        baseline_finish=baseline_finish,
        baseline_duration=baseline_duration,
        percent_complete=_to_py_float(jtask.getPercentageComplete()),
        remaining_duration=_extract_duration(jtask.getRemainingDuration()),
        total_slack=_extract_duration(jtask.getTotalSlack()),
        free_slack=_extract_duration(jtask.getFreeSlack()),
        critical=bool(jtask.getCritical()) if jtask.getCritical() is not None else False,
        summary=bool(jtask.getSummary()) if jtask.getSummary() is not None else False,
        milestone=bool(jtask.getMilestone()) if jtask.getMilestone() is not None else False,
        constraint_type=constraint_type,
        constraint_date=_to_py_datetime(jtask.getConstraintDate()),
        deadline=_to_py_datetime(jtask.getDeadline()),
        notes=_to_py_str(jtask.getNotes()),
        priority=(
            _to_py_int(jtask.getPriority().getValue())
            if jtask.getPriority() is not None
            else None
        ),
        resource_names=_to_py_str(jtask.getResourceNames()),
        predecessors=predecessors,
        successors=successors,
    )


def _extract_relationships(project_file: Any) -> List[Relationship]:
    relationships: List[Relationship] = []
    for jtask in project_file.getTasks():
        try:
            preds = jtask.getPredecessors()
        except Exception:
            preds = None
        if preds is None:
            continue
        for rel in preds:
            pred_task = rel.getPredecessorTask()
            succ_task = rel.getSuccessorTask()
            if pred_task is None or succ_task is None:
                continue
            pred_uid = _to_py_int(pred_task.getUniqueID())
            succ_uid = _to_py_int(succ_task.getUniqueID())
            if pred_uid is None or succ_uid is None:
                continue
            lag_days = _extract_duration(rel.getLag()) or 0.0
            relationships.append(
                Relationship(
                    predecessor_uid=pred_uid,
                    successor_uid=succ_uid,
                    type=_relation_type(rel.getType()),
                    lag_days=lag_days,
                )
            )
    return relationships


def _extract_resource(jres: Any) -> ResourceData:
    res_type = None
    try:
        rt = jres.getType()
        res_type = str(rt.name()) if rt is not None else None
    except Exception:
        res_type = None
    return ResourceData(
        uid=_to_py_int(jres.getUniqueID()) or 0,
        name=_to_py_str(jres.getName()),
        type=res_type,
        max_units=_to_py_float(jres.getMaxUnits()),
    )


def _extract_assignment(jasn: Any) -> Optional[AssignmentData]:
    task = jasn.getTask()
    resource = jasn.getResource()
    if task is None or resource is None:
        return None
    task_uid = _to_py_int(task.getUniqueID())
    res_uid = _to_py_int(resource.getUniqueID())
    if task_uid is None or res_uid is None:
        return None
    return AssignmentData(
        task_uid=task_uid,
        resource_uid=res_uid,
        work=_extract_duration(jasn.getWork()),
        actual_work=_extract_duration(jasn.getActualWork()),
        remaining_work=_extract_duration(jasn.getRemainingWork()),
        cost=_to_py_float(jasn.getCost()),
        actual_cost=_to_py_float(jasn.getActualCost()),
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def parse_mpp(filepath: str) -> ScheduleData:
    """Parse an MPP file into a `ScheduleData` model.

    Raises
    ------
    FileNotFoundError
        If `filepath` does not exist. Checked before the JVM is touched
        so missing-file tests don't need MPXJ available.
    RuntimeError
        If MPXJ fails to read the file.
    """
    if not filepath or not os.path.isfile(filepath):
        raise FileNotFoundError(f"MPP file not found: {filepath}")

    _ensure_jvm()

    UniversalProjectReader = jpype.JClass("org.mpxj.reader.UniversalProjectReader")
    reader = UniversalProjectReader()
    try:
        project_file = reader.read(filepath)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"MPXJ failed to read {filepath}: {exc}") from exc
    if project_file is None:
        raise RuntimeError(f"MPXJ returned no project for {filepath}")

    project_info = _extract_project_info(project_file)

    tasks: List[TaskData] = []
    for jtask in project_file.getTasks():
        # MPXJ sometimes includes a synthetic root task with uid 0 — keep it,
        # the engine can filter on summary/outline_level.
        tasks.append(_extract_task(jtask))

    resources: List[ResourceData] = []
    for jres in project_file.getResources():
        resources.append(_extract_resource(jres))

    assignments: List[AssignmentData] = []
    for jasn in project_file.getResourceAssignments():
        a = _extract_assignment(jasn)
        if a is not None:
            assignments.append(a)

    relationships = _extract_relationships(project_file)

    return ScheduleData(
        project_info=project_info,
        tasks=tasks,
        resources=resources,
        assignments=assignments,
        relationships=relationships,
    )
