"""Schedule manipulation detection and scoring.

Takes the output of `compare_schedules` (plus the two original
`ScheduleData` objects) and surfaces forensic red flags — patterns
commonly associated with intentional or inadvertent schedule
manipulation. Each pattern yields a `ManipulationFinding` with a
confidence level (HIGH/MEDIUM/LOW) and a severity score; these
roll up into a single 0–100 `overall_score` that the AI narrative
layer can cite directly.

Scoring
-------
Confidence weights (per finding):
    HIGH    = 10
    MEDIUM  =  5
    LOW     =  2

The overall score is the sum of all finding weights, capped at 100.
A clean schedule scores 0; a score above 40 warrants an in-depth
human review.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.engine.comparator import ComparisonResults, TaskDelta
from app.parser.schema import Relationship, ScheduleData, TaskData


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

CONFIDENCE_WEIGHTS = {
    CONFIDENCE_HIGH: 10.0,
    CONFIDENCE_MEDIUM: 5.0,
    CONFIDENCE_LOW: 2.0,
}

# Significant-change thresholds
DURATION_REDUCTION_SIGNIFICANT = 0.25  # 25 %
DURATION_REDUCTION_EGREGIOUS = 0.50   # 50 %
FLOAT_DELTA_SIGNIFICANT = 1.0  # working days
PROGRESS_MISMATCH_TOLERANCE = 0.05  # 5 percentage points


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class ManipulationFinding(BaseModel):
    """A single detected manipulation pattern."""

    model_config = ConfigDict(extra="forbid")

    category: str  # "DURATION" | "LOGIC" | "BASELINE" | "FLOAT" | "PROGRESS"
    pattern: str  # machine-readable key, e.g. "critical_duration_reduction"
    confidence: str  # HIGH | MEDIUM | LOW
    severity_score: float
    task_uid: Optional[int] = None
    task_name: Optional[str] = None
    description: str
    evidence: Dict[str, float | int | str | bool] = Field(default_factory=dict)


class ManipulationResults(BaseModel):
    """Output of `detect_manipulations`."""

    model_config = ConfigDict(extra="forbid")

    findings: List[ManipulationFinding] = Field(default_factory=list)
    overall_score: float = 0.0
    confidence_summary: Dict[str, int] = Field(default_factory=dict)
    findings_by_category: Dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _finding(
    category: str,
    pattern: str,
    confidence: str,
    description: str,
    task_uid: Optional[int] = None,
    task_name: Optional[str] = None,
    evidence: Optional[Dict[str, float | int | str | bool]] = None,
) -> ManipulationFinding:
    return ManipulationFinding(
        category=category,
        pattern=pattern,
        confidence=confidence,
        severity_score=CONFIDENCE_WEIGHTS[confidence],
        task_uid=task_uid,
        task_name=task_name,
        description=description,
        evidence=evidence or {},
    )


def _task_map(schedule: ScheduleData) -> Dict[int, TaskData]:
    return {t.uid: t for t in schedule.tasks}


def _on_critical_path(uid: int, prior: Dict[int, TaskData], later: Dict[int, TaskData]) -> bool:
    """A task is 'on the critical path' if it was critical in either snapshot."""
    if uid in prior and prior[uid].critical:
        return True
    if uid in later and later[uid].critical:
        return True
    return False


# --------------------------------------------------------------------------- #
# Duration checks
# --------------------------------------------------------------------------- #


def _check_duration_reductions(
    comparison: ComparisonResults,
    prior_tasks: Dict[int, TaskData],
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        if delta.duration_change_days is None or delta.duration_change_days >= 0:
            continue
        prior_task = prior_tasks.get(delta.uid)
        later_task = later_tasks.get(delta.uid)
        if prior_task is None or later_task is None:
            continue
        prior_dur = prior_task.duration or 0.0
        if prior_dur <= 0:
            continue
        reduction_pct = abs(delta.duration_change_days) / prior_dur
        on_cp = _on_critical_path(delta.uid, prior_tasks, later_tasks)
        if not on_cp:
            continue  # non-CP compression is a normal optimization
        if reduction_pct >= DURATION_REDUCTION_EGREGIOUS:
            confidence = CONFIDENCE_HIGH
            pct_label = f"{reduction_pct * 100:.0f}%"
            desc = (
                f"Critical-path task duration reduced by {pct_label} "
                f"(prior {prior_dur:.1f}d → later {later_task.duration:.1f}d)."
            )
        elif reduction_pct >= DURATION_REDUCTION_SIGNIFICANT:
            confidence = CONFIDENCE_MEDIUM
            pct_label = f"{reduction_pct * 100:.0f}%"
            desc = (
                f"Critical-path task duration reduced by {pct_label} "
                f"(prior {prior_dur:.1f}d → later {later_task.duration:.1f}d)."
            )
        else:
            continue
        findings.append(
            _finding(
                category="DURATION",
                pattern="critical_duration_reduction",
                confidence=confidence,
                description=desc,
                task_uid=delta.uid,
                task_name=later_task.name or delta.name,
                evidence={
                    "prior_duration_days": round(prior_dur, 2),
                    "later_duration_days": round(later_task.duration or 0.0, 2),
                    "reduction_pct": round(reduction_pct * 100, 2),
                    "on_critical_path": True,
                },
            )
        )
    return findings


def _check_selective_compression(
    comparison: ComparisonResults,
    prior_tasks: Dict[int, TaskData],
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    """Flag when ONLY critical-path tasks were compressed."""
    critical_compressed = 0
    non_critical_compressed = 0
    for delta in comparison.task_deltas:
        if delta.duration_change_days is None or delta.duration_change_days >= 0:
            continue
        if _on_critical_path(delta.uid, prior_tasks, later_tasks):
            critical_compressed += 1
        else:
            non_critical_compressed += 1
    if critical_compressed >= 2 and non_critical_compressed == 0:
        return [
            _finding(
                category="DURATION",
                pattern="selective_critical_compression",
                confidence=CONFIDENCE_HIGH,
                description=(
                    f"Selective compression detected: {critical_compressed} "
                    "critical-path tasks were shortened while no non-critical "
                    "tasks were changed — suggests deliberate targeting of CP."
                ),
                evidence={
                    "critical_tasks_compressed": critical_compressed,
                    "non_critical_tasks_compressed": non_critical_compressed,
                },
            )
        ]
    return []


# --------------------------------------------------------------------------- #
# Logic checks
# --------------------------------------------------------------------------- #


def _check_predecessors_removed(
    comparison: ComparisonResults,
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        if not delta.predecessors_removed:
            continue
        later_task = later_tasks.get(delta.uid)
        findings.append(
            _finding(
                category="LOGIC",
                pattern="predecessors_removed",
                confidence=CONFIDENCE_HIGH,
                description=(
                    f"{len(delta.predecessors_removed)} predecessor(s) removed "
                    "without a corresponding scope change in the later update."
                ),
                task_uid=delta.uid,
                task_name=later_task.name if later_task else delta.name,
                evidence={
                    "removed_predecessor_uids": ",".join(
                        str(u) for u in delta.predecessors_removed
                    ),
                    "count": len(delta.predecessors_removed),
                },
            )
        )
    return findings


def _check_relationship_type_changes(
    comparison: ComparisonResults,
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        for change in delta.relationship_type_changes:
            if change.prior_type == "FS" and change.later_type in {"SS", "FF", "SF"}:
                later_task = later_tasks.get(delta.uid)
                findings.append(
                    _finding(
                        category="LOGIC",
                        pattern="fs_type_downgrade",
                        confidence=CONFIDENCE_MEDIUM,
                        description=(
                            f"Relationship {change.predecessor_uid}→"
                            f"{change.successor_uid} changed from FS to "
                            f"{change.later_type} — can hide sequencing issues."
                        ),
                        task_uid=delta.uid,
                        task_name=later_task.name if later_task else delta.name,
                        evidence={
                            "predecessor_uid": change.predecessor_uid,
                            "prior_type": change.prior_type or "",
                            "later_type": change.later_type or "",
                        },
                    )
                )
    return findings


def _check_lag_changes(
    comparison: ComparisonResults,
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        for change in delta.lag_changes:
            later_task = later_tasks.get(delta.uid)
            findings.append(
                _finding(
                    category="LOGIC",
                    pattern="lag_change",
                    confidence=CONFIDENCE_MEDIUM,
                    description=(
                        f"Lag on {change.predecessor_uid}→{change.successor_uid} "
                        f"changed from {change.prior_lag_days}d to "
                        f"{change.later_lag_days}d."
                    ),
                    task_uid=delta.uid,
                    task_name=later_task.name if later_task else delta.name,
                    evidence={
                        "predecessor_uid": change.predecessor_uid,
                        "prior_lag_days": change.prior_lag_days or 0.0,
                        "later_lag_days": change.later_lag_days or 0.0,
                    },
                )
            )
    return findings


def _check_out_of_sequence_progress(
    later: ScheduleData,
) -> List[ManipulationFinding]:
    """Any task with % complete > 0 whose FS predecessors are not done."""
    findings: List[ManipulationFinding] = []
    task_by_uid = _task_map(later)

    # Build FS predecessor map from relationships (fall back to .predecessors).
    preds_by_succ: Dict[int, List[Relationship]] = {}
    if later.relationships:
        for rel in later.relationships:
            preds_by_succ.setdefault(rel.successor_uid, []).append(rel)
    else:
        for task in later.tasks:
            for pred_uid in task.predecessors:
                preds_by_succ.setdefault(task.uid, []).append(
                    Relationship(
                        predecessor_uid=pred_uid,
                        successor_uid=task.uid,
                        type="FS",
                        lag_days=0.0,
                    )
                )

    for task in later.tasks:
        if task.summary:
            continue
        pct = task.percent_complete or 0.0
        if pct <= 0.0:
            continue
        violations: List[int] = []
        for rel in preds_by_succ.get(task.uid, []):
            if rel.type != "FS":
                continue  # SS/FF/SF don't require pred completion before start
            pred = task_by_uid.get(rel.predecessor_uid)
            if pred is None:
                continue
            pred_pct = pred.percent_complete or 0.0
            if pred_pct < 100.0:
                violations.append(pred.uid)
        if violations:
            findings.append(
                _finding(
                    category="LOGIC",
                    pattern="out_of_sequence_progress",
                    confidence=CONFIDENCE_HIGH,
                    description=(
                        f"Task shows {pct:.0f}% progress but {len(violations)} "
                        "FS predecessor(s) are still incomplete."
                    ),
                    task_uid=task.uid,
                    task_name=task.name,
                    evidence={
                        "percent_complete": pct,
                        "incomplete_predecessor_uids": ",".join(
                            str(u) for u in violations
                        ),
                    },
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Baseline checks
# --------------------------------------------------------------------------- #


def _check_baseline_changes(
    comparison: ComparisonResults,
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        bs_delta = delta.baseline_start_delta_days or 0.0
        bf_delta = delta.baseline_finish_delta_days or 0.0
        if abs(bs_delta) < 1e-6 and abs(bf_delta) < 1e-6:
            continue
        later_task = later_tasks.get(delta.uid)
        findings.append(
            _finding(
                category="BASELINE",
                pattern="baseline_date_change",
                confidence=CONFIDENCE_HIGH,
                description=(
                    "Baseline date changed between updates — baselines should "
                    "be frozen once set."
                ),
                task_uid=delta.uid,
                task_name=later_task.name if later_task else delta.name,
                evidence={
                    "baseline_start_delta_days": round(bs_delta, 2),
                    "baseline_finish_delta_days": round(bf_delta, 2),
                },
            )
        )
    return findings


def _check_selective_baseline_changes(
    comparison: ComparisonResults,
) -> List[ManipulationFinding]:
    """Flag when baselines were moved ONLY on tasks that also slipped."""
    baseline_moved: List[int] = []
    baseline_moved_and_slipped: List[int] = []
    for delta in comparison.task_deltas:
        bs = delta.baseline_start_delta_days or 0.0
        bf = delta.baseline_finish_delta_days or 0.0
        if abs(bs) < 1e-6 and abs(bf) < 1e-6:
            continue
        baseline_moved.append(delta.uid)
        if (delta.finish_slip_days or 0.0) > 0.5:
            baseline_moved_and_slipped.append(delta.uid)
    if not baseline_moved:
        return []
    ratio = len(baseline_moved_and_slipped) / len(baseline_moved)
    if len(baseline_moved) >= 2 and ratio >= 0.8:
        return [
            _finding(
                category="BASELINE",
                pattern="selective_baseline_correction",
                confidence=CONFIDENCE_HIGH,
                description=(
                    f"{len(baseline_moved_and_slipped)} of "
                    f"{len(baseline_moved)} baseline changes were on tasks "
                    "that also slipped — pattern of retroactive correction."
                ),
                evidence={
                    "total_baseline_changes": len(baseline_moved),
                    "changes_on_slipped_tasks": len(baseline_moved_and_slipped),
                    "ratio": round(ratio, 2),
                },
            )
        ]
    return []


def _check_retroactive_baseline(
    comparison: ComparisonResults,
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        if (delta.baseline_finish_delta_days or 0.0) == 0.0:
            continue
        later_task = later_tasks.get(delta.uid)
        if later_task is None:
            continue
        if later_task.baseline_finish is None or later_task.finish is None:
            continue
        if abs((later_task.baseline_finish - later_task.finish).total_seconds()) < 86400:
            findings.append(
                _finding(
                    category="BASELINE",
                    pattern="retroactive_baseline_equals_current",
                    confidence=CONFIDENCE_MEDIUM,
                    description=(
                        "Baseline finish was moved to match the current "
                        "finish date — appears to zero out the delay."
                    ),
                    task_uid=delta.uid,
                    task_name=later_task.name or delta.name,
                    evidence={
                        "baseline_finish": later_task.baseline_finish.isoformat(),
                        "current_finish": later_task.finish.isoformat(),
                    },
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Float checks
# --------------------------------------------------------------------------- #


def _check_added_constraints(
    prior_tasks: Dict[int, TaskData],
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for uid, later_task in later_tasks.items():
        if uid not in prior_tasks:
            continue
        prior_task = prior_tasks[uid]
        prior_ct = (prior_task.constraint_type or "").upper() or None
        later_ct = (later_task.constraint_type or "").upper() or None
        if later_ct and prior_ct != later_ct and later_ct not in {
            "AS_SOON_AS_POSSIBLE",
            "AS_LATE_AS_POSSIBLE",
            "ASAP",
            "ALAP",
        }:
            findings.append(
                _finding(
                    category="FLOAT",
                    pattern="constraint_added",
                    confidence=CONFIDENCE_MEDIUM,
                    description=(
                        f"Task constraint changed from "
                        f"{prior_ct or 'None'} → {later_ct}. Hard constraints "
                        "can artificially suppress float."
                    ),
                    task_uid=uid,
                    task_name=later_task.name,
                    evidence={
                        "prior_constraint": prior_ct or "",
                        "later_constraint": later_ct,
                    },
                )
            )
    return findings


def _check_unexplained_float_changes(
    comparison: ComparisonResults,
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for delta in comparison.task_deltas:
        ts_delta = delta.total_slack_delta
        if ts_delta is None or abs(ts_delta) < FLOAT_DELTA_SIGNIFICANT:
            continue
        # Check if there's an explanation locally (on this task)
        has_local_change = (
            (delta.duration_change_days or 0.0) != 0.0
            or bool(delta.predecessors_added)
            or bool(delta.predecessors_removed)
            or bool(delta.relationship_type_changes)
            or bool(delta.lag_changes)
        )
        if has_local_change:
            continue
        later_task = later_tasks.get(delta.uid)
        findings.append(
            _finding(
                category="FLOAT",
                pattern="unexplained_float_change",
                confidence=CONFIDENCE_HIGH,
                description=(
                    f"Total float changed by {ts_delta:+.1f}d with no "
                    "corresponding logic or duration change on this task."
                ),
                task_uid=delta.uid,
                task_name=later_task.name if later_task else delta.name,
                evidence={"total_slack_delta_days": round(ts_delta, 2)},
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Progress checks
# --------------------------------------------------------------------------- #


def _check_progress_vs_remaining(later: ScheduleData) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for task in later.tasks:
        if task.summary:
            continue
        pct = task.percent_complete
        dur = task.duration
        rem = task.remaining_duration
        if pct is None or dur is None or rem is None or dur <= 0:
            continue
        expected_rem = dur * (1.0 - pct / 100.0)
        if abs(expected_rem - rem) / max(dur, 1e-6) > PROGRESS_MISMATCH_TOLERANCE:
            findings.append(
                _finding(
                    category="PROGRESS",
                    pattern="percent_vs_remaining_mismatch",
                    confidence=CONFIDENCE_MEDIUM,
                    description=(
                        f"{pct:.0f}% complete implies {expected_rem:.1f}d "
                        f"remaining but task reports {rem:.1f}d."
                    ),
                    task_uid=task.uid,
                    task_name=task.name,
                    evidence={
                        "percent_complete": pct,
                        "duration_days": dur,
                        "remaining_duration_days": rem,
                        "expected_remaining_days": round(expected_rem, 2),
                    },
                )
            )
    return findings


def _check_actual_start_zero_progress(later: ScheduleData) -> List[ManipulationFinding]:
    findings: List[ManipulationFinding] = []
    for task in later.tasks:
        if task.summary:
            continue
        if task.actual_start is not None and (task.percent_complete or 0.0) == 0.0:
            findings.append(
                _finding(
                    category="PROGRESS",
                    pattern="actual_start_zero_progress",
                    confidence=CONFIDENCE_LOW,
                    description=(
                        "Task has an actual start recorded but 0% progress."
                    ),
                    task_uid=task.uid,
                    task_name=task.name,
                    evidence={
                        "actual_start": task.actual_start.isoformat(),
                    },
                )
            )
    return findings


def _check_status_date_misalignment(later: ScheduleData) -> List[ManipulationFinding]:
    status_date = later.project_info.status_date
    if status_date is None:
        return []
    latest_actual = None
    latest_uid: Optional[int] = None
    latest_name: Optional[str] = None
    for task in later.tasks:
        for dt_val in (task.actual_start, task.actual_finish):
            if dt_val is None:
                continue
            if latest_actual is None or dt_val > latest_actual:
                latest_actual = dt_val
                latest_uid = task.uid
                latest_name = task.name
    if latest_actual is None or latest_actual <= status_date:
        return []
    delta_days = (latest_actual - status_date).total_seconds() / 86400.0
    return [
        _finding(
            category="PROGRESS",
            pattern="status_date_lagging_actuals",
            confidence=CONFIDENCE_MEDIUM,
            description=(
                f"Status date is {delta_days:.1f}d older than the latest "
                "actual date in the schedule."
            ),
            task_uid=latest_uid,
            task_name=latest_name,
            evidence={
                "status_date": status_date.isoformat(),
                "latest_actual_date": latest_actual.isoformat(),
                "gap_days": round(delta_days, 2),
            },
        )
    ]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def detect_manipulations(
    comparison: ComparisonResults,
    prior: ScheduleData,
    later: ScheduleData,
) -> ManipulationResults:
    """Run every manipulation check and return a scored result."""
    prior_tasks = _task_map(prior)
    later_tasks = _task_map(later)

    findings: List[ManipulationFinding] = []

    # Duration
    findings.extend(_check_duration_reductions(comparison, prior_tasks, later_tasks))
    findings.extend(_check_selective_compression(comparison, prior_tasks, later_tasks))

    # Logic
    findings.extend(_check_predecessors_removed(comparison, later_tasks))
    findings.extend(_check_relationship_type_changes(comparison, later_tasks))
    findings.extend(_check_lag_changes(comparison, later_tasks))
    findings.extend(_check_out_of_sequence_progress(later))

    # Baseline
    findings.extend(_check_baseline_changes(comparison, later_tasks))
    findings.extend(_check_selective_baseline_changes(comparison))
    findings.extend(_check_retroactive_baseline(comparison, later_tasks))

    # Float
    findings.extend(_check_added_constraints(prior_tasks, later_tasks))
    findings.extend(_check_unexplained_float_changes(comparison, later_tasks))

    # Progress
    findings.extend(_check_progress_vs_remaining(later))
    findings.extend(_check_actual_start_zero_progress(later))
    findings.extend(_check_status_date_misalignment(later))

    overall_score = min(100.0, sum(f.severity_score for f in findings))
    confidence_summary: Dict[str, int] = {
        CONFIDENCE_HIGH: 0,
        CONFIDENCE_MEDIUM: 0,
        CONFIDENCE_LOW: 0,
    }
    category_summary: Dict[str, int] = {}
    for f in findings:
        confidence_summary[f.confidence] += 1
        category_summary[f.category] = category_summary.get(f.category, 0) + 1

    return ManipulationResults(
        findings=findings,
        overall_score=round(overall_score, 2),
        confidence_summary=confidence_summary,
        findings_by_category=category_summary,
    )
