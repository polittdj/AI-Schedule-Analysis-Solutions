"""Schedule manipulation detection and scoring.

Takes the output of `compare_schedules` (plus the two original
`ScheduleData` objects) and surfaces forensic red flags — patterns
commonly associated with intentional or inadvertent schedule
manipulation. Each pattern yields a `ManipulationFinding` with a
confidence level (HIGH/MEDIUM/LOW); one finding per task is counted
toward a normalized composite score while every finding is still
displayed for analyst review.

Fuse alignment
--------------
Manipulation detection here mirrors the categories Acumen Fuse's
Forensic module reports: logic changes, duration changes, date
changes, progress reversals, out-of-sequence progress, constraint
changes, and scope changes (tasks added/deleted). Fuse does **not**
publish a single 0–100 manipulation score, so the one we compute
below is labeled "local composite indicator" in the UI. Schedule
Health (DCMA pass rate) comes from `app.engine.dcma` and is shown
alongside the composite as a Fuse-standard readout.

Scoring (local composite, not a Fuse metric)
--------------------------------------------
* Each finding carries a weight: HIGH = 3, MEDIUM = 2, LOW = 1.
* Findings are deduplicated by ``task_uid`` — only the single
  highest-weight finding per UID contributes to the score. The rest
  are shown in the UI with ``score_contribution = False``.
* Project-wide findings (no UID) always contribute to the score.
* ``max_theoretical_score = detail_task_count * 3`` — one HIGH
  finding per detail task is the worst realistic case.
* ``overall_score = round(weighted / max_theoretical * 100, 1)``
  floored at 0 and capped at 100.
* Single-file mode (no prior snapshot) still runs the static checks
  (hard constraints, negative float, 100%-complete-no-actuals) but
  sets ``overall_score = None`` — the normalized composite is a
  differential metric and requires a prior snapshot to interpret.
  Fuse Schedule Health still works in single-file mode, and the
  UI continues to display the change count and finding table.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.engine.comparator import ComparisonResults, TaskDelta
from app.parser.schema import Relationship, ScheduleData, TaskData


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

# Normalized scoring weights. One HIGH finding per detail task is the
# worst realistic case, so HIGH = 3 makes max_theoretical_score map
# cleanly to detail_task_count * 3.
CONFIDENCE_WEIGHTS = {
    CONFIDENCE_HIGH: 3.0,
    CONFIDENCE_MEDIUM: 2.0,
    CONFIDENCE_LOW: 1.0,
}

# Significant-change thresholds (comparative checks)
DURATION_REDUCTION_SIGNIFICANT = 0.25  # 25 %
DURATION_REDUCTION_EGREGIOUS = 0.50   # 50 %
FLOAT_DELTA_SIGNIFICANT = 5.0  # working days — ignore normal cascade jitter
PROGRESS_MISMATCH_TOLERANCE = 0.15  # 15 percentage points — MSP auto-calc noise
PROGRESS_REVERSAL_TOLERANCE = 1.0  # percent — MSP sometimes nudges by <1%

# Hard constraint types Fuse flags as non-ASAP/ALAP (single-file static check).
HARD_CONSTRAINT_TYPES = {
    "MUST_START_ON",
    "MUST_FINISH_ON",
    "START_NO_EARLIER_THAN",
    "START_NO_LATER_THAN",
    "FINISH_NO_EARLIER_THAN",
    "FINISH_NO_LATER_THAN",
    "MSO",
    "MFO",
    "SNET",
    "SNLT",
    "FNET",
    "FNLT",
}


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class ManipulationFinding(BaseModel):
    """A single detected manipulation pattern."""

    model_config = ConfigDict(extra="forbid")

    category: str  # "DURATION" | "LOGIC" | "BASELINE" | "FLOAT" | "PROGRESS" | "SCOPE"
    pattern: str  # machine-readable key, e.g. "critical_duration_reduction"
    confidence: str  # HIGH | MEDIUM | LOW
    severity_score: float
    task_uid: Optional[int] = None
    task_name: Optional[str] = None
    description: str
    evidence: Dict[str, float | int | str | bool] = Field(default_factory=dict)
    # True if this finding was counted toward ``overall_score``. When a
    # higher-weight finding for the same UID wins the dedup, losing
    # findings stay in the list (for audit) with score_contribution = False.
    # Project-wide findings (no task_uid) always contribute.
    score_contribution: bool = True


class ManipulationResults(BaseModel):
    """Output of `detect_manipulations`.

    ``overall_score`` is ``None`` when the normalized composite cannot
    be computed — either the schedule has no detail tasks (denominator
    is zero) or single-file mode offers no comparative basis. Callers
    should render "N/A — Comparative analysis required" in the
    single-file case and continue to show the findings table.
    """

    model_config = ConfigDict(extra="forbid")

    findings: List[ManipulationFinding] = Field(default_factory=list)
    overall_score: Optional[float] = 0.0
    confidence_summary: Dict[str, int] = Field(default_factory=dict)
    findings_by_category: Dict[str, int] = Field(default_factory=dict)
    applicable: bool = True  # False when run on single-file mode

    # Fuse-aligned readout fields (displayed in the UI alongside DCMA
    # Schedule Health, which comes from app.engine.dcma).
    change_count: int = 0  # total number of findings BEFORE dedup
    deduplicated_count: int = 0  # findings that contributed to overall_score
    detail_task_count: int = 0  # denominator basis for normalization
    max_theoretical_score: float = 0.0  # detail_task_count * HIGH weight
    weighted_score: float = 0.0  # sum of contributing weights
    single_file_mode: bool = False  # True when no prior was supplied


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
    """Any task with % complete > 0 whose FS predecessors are not done.

    Fuse treats OOS progress as a binary flag without a "chain depth"
    concept. Severity is modulated only by whether the task is on the
    critical path:

        * critical-path OOS → MEDIUM (forensically significant)
        * non-critical OOS  → LOW    (normal cascade churn in most
                                      schedules; still reported)

    A previous version classified every OOS hit as HIGH, which was
    the root cause of the "manipulation score = 100/100" bug on large
    schedules — any in-progress cascade would flood the score.
    """
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
        if not violations:
            continue
        on_critical_path = bool(task.critical) or (
            task.total_slack is not None and task.total_slack <= 0.0
        )
        confidence = CONFIDENCE_MEDIUM if on_critical_path else CONFIDENCE_LOW
        findings.append(
            _finding(
                category="LOGIC",
                pattern="out_of_sequence_progress",
                confidence=confidence,
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
                    "on_critical_path": on_critical_path,
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
        # Only flag tasks that are actually in progress (1-99% complete).
        # MSP auto-calculates remaining_duration for 0% and 100% tasks
        # and the math is never perfectly self-consistent. Also require
        # a significant discrepancy (>20%) to avoid false positives.
        if pct <= 0 or pct >= 100:
            continue
        expected_rem = dur * (1.0 - pct / 100.0)
        discrepancy = abs(expected_rem - rem) / max(dur, 1e-6)
        if discrepancy <= 0.20:
            continue
        if discrepancy > PROGRESS_MISMATCH_TOLERANCE:
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
# Scope checks (comparative) — Fuse forensic category
# --------------------------------------------------------------------------- #


def _check_progress_reversals(
    prior_tasks: Dict[int, TaskData],
    later_tasks: Dict[int, TaskData],
) -> List[ManipulationFinding]:
    """Flag tasks whose percent_complete went down between updates.

    Fuse reports progress reversals as a HIGH-severity forensic
    finding: a task legitimately cannot "uncomplete" work unless the
    prior update over-reported progress, actuals were reversed, or
    the baseline was re-pointed. A small (<1 %) tolerance absorbs
    float-formatting noise.
    """
    findings: List[ManipulationFinding] = []
    for uid, later_task in later_tasks.items():
        prior_task = prior_tasks.get(uid)
        if prior_task is None:
            continue
        prior_pct = prior_task.percent_complete
        later_pct = later_task.percent_complete
        if prior_pct is None or later_pct is None:
            continue
        delta = later_pct - prior_pct
        if delta < -PROGRESS_REVERSAL_TOLERANCE:
            findings.append(
                _finding(
                    category="PROGRESS",
                    pattern="progress_reversal",
                    confidence=CONFIDENCE_HIGH,
                    description=(
                        f"Task percent-complete went from {prior_pct:.0f}% "
                        f"down to {later_pct:.0f}% — a reversal of "
                        f"{abs(delta):.0f} points between updates."
                    ),
                    task_uid=uid,
                    task_name=later_task.name,
                    evidence={
                        "prior_percent_complete": round(prior_pct, 2),
                        "later_percent_complete": round(later_pct, 2),
                        "reversal_points": round(abs(delta), 2),
                    },
                )
            )
    return findings


def _check_added_deleted_tasks(
    comparison: ComparisonResults,
) -> List[ManipulationFinding]:
    """Emit LOW-severity informational findings for scope churn.

    Fuse's forensic report always lists tasks added or deleted
    between updates. They aren't automatically indicators of
    manipulation — scope changes are often legitimate — but analysts
    want to see them in the same place as everything else that moved.
    """
    findings: List[ManipulationFinding] = []
    for uid in getattr(comparison, "added_task_uids", []) or []:
        findings.append(
            _finding(
                category="SCOPE",
                pattern="task_added",
                confidence=CONFIDENCE_LOW,
                description=(
                    "Task was added to the later schedule and did not "
                    "exist in the prior snapshot."
                ),
                task_uid=uid,
                evidence={"change": "added"},
            )
        )
    for uid in getattr(comparison, "deleted_task_uids", []) or []:
        findings.append(
            _finding(
                category="SCOPE",
                pattern="task_deleted",
                confidence=CONFIDENCE_LOW,
                description=(
                    "Task existed in the prior schedule but is absent "
                    "from the later snapshot."
                ),
                task_uid=uid,
                evidence={"change": "deleted"},
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Single-file static checks — run even without a prior snapshot
# --------------------------------------------------------------------------- #


def _is_detail_task(task: TaskData) -> bool:
    """A detail task is non-summary. Milestones count as detail."""
    return not task.summary


def _check_single_file_hard_constraints(
    later: ScheduleData,
) -> List[ManipulationFinding]:
    """Fuse DCMA S5 intent: hard constraints on non-milestone detail tasks.

    Hard constraints (must-start/must-finish/start-no-later-than, etc.)
    override CPM float logic and are a classic manipulation vector —
    you can zero out float on a slipping path just by pinning the
    downstream task with a hard date. Reported as MEDIUM so a single
    constraint doesn't dominate the composite score.
    """
    findings: List[ManipulationFinding] = []
    for task in later.tasks:
        if not _is_detail_task(task):
            continue
        if task.milestone:
            continue
        ct = (task.constraint_type or "").upper().strip()
        if not ct:
            continue
        if ct not in HARD_CONSTRAINT_TYPES:
            continue
        findings.append(
            _finding(
                category="FLOAT",
                pattern="single_file_hard_constraint",
                confidence=CONFIDENCE_MEDIUM,
                description=(
                    f"Task carries a hard constraint ({ct}) which overrides "
                    "float calculations."
                ),
                task_uid=task.uid,
                task_name=task.name,
                evidence={"constraint_type": ct},
            )
        )
    return findings


def _check_single_file_negative_float(
    later: ScheduleData,
) -> List[ManipulationFinding]:
    """Fuse DCMA S7 intent: tasks with negative total float.

    Negative float means the task is already forecasted to miss its
    driving constraint — a strong signal that either the baseline is
    out of date or a hard constraint is masking a real slip. HIGH
    severity because it's a data-integrity signal, not just style.
    """
    findings: List[ManipulationFinding] = []
    for task in later.tasks:
        if not _is_detail_task(task):
            continue
        tf = task.total_slack
        if tf is None:
            continue
        if tf < -0.01:  # small tolerance for floating-point drift
            findings.append(
                _finding(
                    category="FLOAT",
                    pattern="single_file_negative_float",
                    confidence=CONFIDENCE_HIGH,
                    description=(
                        f"Task has negative total float ({tf:.1f}d) — the "
                        "schedule is forecasting a miss against its driving "
                        "constraint."
                    ),
                    task_uid=task.uid,
                    task_name=task.name,
                    evidence={"total_slack_days": round(tf, 2)},
                )
            )
    return findings


def _check_single_file_completed_without_actuals(
    later: ScheduleData,
) -> List[ManipulationFinding]:
    """100% complete but no actual_start or actual_finish recorded.

    Fuse flags this as a data-integrity / progress-inflation red
    flag: a task claiming full completion should carry actual dates,
    otherwise the update is just statusing on paper.
    """
    findings: List[ManipulationFinding] = []
    for task in later.tasks:
        if not _is_detail_task(task):
            continue
        pct = task.percent_complete or 0.0
        if pct < 100.0:
            continue
        if task.actual_start is not None and task.actual_finish is not None:
            continue
        missing: List[str] = []
        if task.actual_start is None:
            missing.append("actual_start")
        if task.actual_finish is None:
            missing.append("actual_finish")
        findings.append(
            _finding(
                category="PROGRESS",
                pattern="single_file_complete_without_actuals",
                confidence=CONFIDENCE_HIGH,
                description=(
                    "Task reports 100% complete but is missing "
                    f"{', '.join(missing)} — no contemporaneous record of "
                    "the work actually finishing."
                ),
                task_uid=task.uid,
                task_name=task.name,
                evidence={
                    "percent_complete": pct,
                    "missing_fields": ",".join(missing),
                },
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Deduplication & scoring
# --------------------------------------------------------------------------- #


def _dedupe_for_scoring(findings: List[ManipulationFinding]) -> None:
    """Mark the highest-weight finding per task_uid as the scorer.

    Mutates ``findings`` in place: sets ``score_contribution`` to
    True on exactly one finding per UID (the highest-weight one;
    ties resolved by order of appearance) and False on the rest.
    Findings with no ``task_uid`` (project-wide findings) are always
    scoring contributors — they can never collide with UID-keyed
    findings.
    """
    seen_by_uid: Dict[int, ManipulationFinding] = {}
    for finding in findings:
        if finding.task_uid is None:
            finding.score_contribution = True
            continue
        uid = finding.task_uid
        existing = seen_by_uid.get(uid)
        if existing is None:
            finding.score_contribution = True
            seen_by_uid[uid] = finding
            continue
        # A previous finding for this UID already claimed the slot.
        # Compare weights and keep the heavier one.
        if CONFIDENCE_WEIGHTS[finding.confidence] > CONFIDENCE_WEIGHTS[existing.confidence]:
            existing.score_contribution = False
            finding.score_contribution = True
            seen_by_uid[uid] = finding
        else:
            finding.score_contribution = False


def _normalize_score(
    findings: List[ManipulationFinding],
    detail_task_count: int,
) -> Dict[str, Any]:
    """Compute the normalized composite from deduplicated findings.

    Returns a dict with ``overall_score`` (float or None),
    ``weighted_score`` (float), ``max_theoretical_score`` (float),
    and ``deduplicated_count`` (int).
    """
    max_theoretical = float(detail_task_count) * CONFIDENCE_WEIGHTS[CONFIDENCE_HIGH]
    if detail_task_count == 0 or max_theoretical <= 0:
        return {
            "overall_score": None,
            "weighted_score": 0.0,
            "max_theoretical_score": 0.0,
            "deduplicated_count": 0,
        }
    weighted = 0.0
    dedup_count = 0
    for f in findings:
        if not f.score_contribution:
            continue
        weighted += CONFIDENCE_WEIGHTS.get(f.confidence, 0.0)
        dedup_count += 1
    raw = (weighted / max_theoretical) * 100.0
    clipped = max(0.0, min(100.0, raw))
    return {
        "overall_score": round(clipped, 1),
        "weighted_score": round(weighted, 2),
        "max_theoretical_score": round(max_theoretical, 2),
        "deduplicated_count": dedup_count,
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def detect_manipulations(
    comparison: Optional[ComparisonResults],
    prior: Optional[ScheduleData],
    later: ScheduleData,
) -> ManipulationResults:
    """Run every manipulation check and return a scored result.

    * When ``comparison`` and ``prior`` are both supplied, every
      comparative check runs AND the single-file static checks run.
      The normalized composite score is computed.
    * When ``comparison`` or ``prior`` is None (single-file mode),
      only the single-file static checks run. Findings populate but
      ``overall_score`` is set to None — the composite is a
      differential metric and cannot be interpreted without a prior
      snapshot. The UI renders "N/A — Comparative analysis required".
    """
    later_tasks = _task_map(later)
    detail_task_count = sum(1 for t in later.tasks if _is_detail_task(t))
    single_file_mode = comparison is None or prior is None

    findings: List[ManipulationFinding] = []

    if not single_file_mode:
        prior_tasks = _task_map(prior)  # type: ignore[arg-type]

        # Duration
        findings.extend(
            _check_duration_reductions(comparison, prior_tasks, later_tasks)  # type: ignore[arg-type]
        )
        findings.extend(
            _check_selective_compression(comparison, prior_tasks, later_tasks)  # type: ignore[arg-type]
        )

        # Logic
        findings.extend(_check_predecessors_removed(comparison, later_tasks))  # type: ignore[arg-type]
        findings.extend(_check_relationship_type_changes(comparison, later_tasks))  # type: ignore[arg-type]
        findings.extend(_check_lag_changes(comparison, later_tasks))  # type: ignore[arg-type]

        # Baseline
        findings.extend(_check_baseline_changes(comparison, later_tasks))  # type: ignore[arg-type]
        findings.extend(_check_selective_baseline_changes(comparison))  # type: ignore[arg-type]
        findings.extend(_check_retroactive_baseline(comparison, later_tasks))  # type: ignore[arg-type]

        # Float
        findings.extend(_check_added_constraints(prior_tasks, later_tasks))
        findings.extend(_check_unexplained_float_changes(comparison, later_tasks))  # type: ignore[arg-type]

        # Progress (comparative)
        findings.extend(_check_progress_vs_remaining(later))
        findings.extend(_check_actual_start_zero_progress(later))
        findings.extend(_check_status_date_misalignment(later))
        findings.extend(_check_progress_reversals(prior_tasks, later_tasks))

        # Scope (comparative)
        findings.extend(_check_added_deleted_tasks(comparison))  # type: ignore[arg-type]

    # Checks that fire in BOTH modes — Fuse forensic categories that
    # don't need a prior snapshot.
    findings.extend(_check_out_of_sequence_progress(later))
    findings.extend(_check_single_file_hard_constraints(later))
    findings.extend(_check_single_file_negative_float(later))
    findings.extend(_check_single_file_completed_without_actuals(later))

    # Dedupe by UID so a single task can't trigger HIGH + MEDIUM + LOW
    # and triple-count. All findings stay in the list for audit; only
    # ``score_contribution`` flags get flipped.
    _dedupe_for_scoring(findings)

    confidence_summary: Dict[str, int] = {
        CONFIDENCE_HIGH: 0,
        CONFIDENCE_MEDIUM: 0,
        CONFIDENCE_LOW: 0,
    }
    category_summary: Dict[str, int] = {}
    for f in findings:
        confidence_summary[f.confidence] = confidence_summary.get(f.confidence, 0) + 1
        category_summary[f.category] = category_summary.get(f.category, 0) + 1

    score_block = _normalize_score(findings, detail_task_count)
    overall_score: Optional[float] = score_block["overall_score"]

    # Single-file mode: findings populate but the composite is N/A.
    if single_file_mode:
        overall_score = None

    return ManipulationResults(
        findings=findings,
        overall_score=overall_score,
        confidence_summary=confidence_summary,
        findings_by_category=category_summary,
        applicable=not single_file_mode,
        change_count=len(findings),
        deduplicated_count=int(score_block["deduplicated_count"]),
        detail_task_count=detail_task_count,
        max_theoretical_score=float(score_block["max_theoretical_score"]),
        weighted_score=float(score_block["weighted_score"]),
        single_file_mode=single_file_mode,
    )
