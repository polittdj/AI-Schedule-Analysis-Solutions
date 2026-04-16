"""Multi-schedule trend analysis.

Given N (≥2) chronologically-ordered `ScheduleData` snapshots, runs
N-1 pairwise comparisons and builds a time-series of key metrics so
the UI and AI narrative can show how the project evolved across
multiple updates — not just the delta between two of them.

Outputs a `TrendAnalysisResults` with:

* **data_points** — one `TrendDataPoint` per update, carrying
  project finish, task counts, critical-path length, float stats,
  SPI, BEI, manipulation score, and deltas-since-prior-update.
* **task_compressions** — top-20 tasks by cumulative duration
  change across every update (catches "death by a thousand cuts").
* **baseline_resets** — detected when a pairwise comparison shows
  two or more tasks with non-trivial baseline shifts.
* **completion_date_drift_days** — calendar-day change between the
  first and last updates' project finish dates.
* **float_trend / spi_trend / manipulation_trend** — classified as
  "eroding", "recovering", or "stable".
* **narrative** — a short plain-text summary the AI layer can pick up.

The function is pure: no I/O, no Flask, no JVM, trivially testable.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.engine.comparator import ComparisonResults, chain_compare
from app.engine.cpm import compute_cpm
from app.engine.dcma import compute_dcma
from app.engine.earned_value import compute_earned_value
from app.engine.manipulation import detect_manipulations
from app.parser.schema import ScheduleData

# Epsilons for the trend-direction classifier.
FLOAT_TREND_EPSILON = 0.5  # working days
SPI_TREND_EPSILON = 0.02
MANIPULATION_TREND_EPSILON = 1.0  # points out of 100

# A pairwise comparison is flagged as a baseline reset when this many tasks
# moved their baselines, or when this fraction did.
BASELINE_RESET_MIN_TASKS = 2
BASELINE_RESET_FRACTION = 0.10
BASELINE_SHIFT_THRESHOLD_DAYS = 0.5

TOP_COMPRESSION_COUNT = 20


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #


class TrendDataPoint(BaseModel):
    """One row in the time-series — one per schedule update."""

    model_config = ConfigDict(extra="forbid")

    update_index: int  # 0-indexed position in the chronological list
    update_label: str  # "Update 1", "Update 2", ...
    status_date: Optional[datetime] = None
    project_finish: Optional[datetime] = None

    task_count: int = 0
    tasks_complete: int = 0
    tasks_in_progress: int = 0
    tasks_not_started: int = 0
    critical_path_task_count: int = 0

    total_float_avg: float = 0.0
    total_float_min: float = 0.0

    spi: Optional[float] = None
    bei: Optional[float] = None

    # Deltas relative to the previous update (None / 0 for update_index 0)
    tasks_added_since_prior: int = 0
    tasks_removed_since_prior: int = 0
    tasks_completed_since_prior: int = 0
    manipulation_score: Optional[float] = None
    finish_slip_since_prior_days: Optional[float] = None


class TaskCompressionSummary(BaseModel):
    """Cumulative duration change for a single task across all updates."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    name: Optional[str] = None
    cumulative_duration_change_days: float
    compression_events: int
    first_duration: Optional[float] = None
    last_duration: Optional[float] = None


class BaselineResetEvent(BaseModel):
    """Detected baseline reset between two consecutive updates."""

    model_config = ConfigDict(extra="forbid")

    update_index: int  # The later index of the pair (1-based label in update_label)
    update_label: str
    affected_task_count: int
    max_baseline_shift_days: float


class TrendAnalysisResults(BaseModel):
    """Output of `compute_trend_analysis`."""

    model_config = ConfigDict(extra="forbid")

    update_count: int
    data_points: List[TrendDataPoint] = Field(default_factory=list)
    task_compressions: List[TaskCompressionSummary] = Field(default_factory=list)
    baseline_resets: List[BaselineResetEvent] = Field(default_factory=list)
    completion_date_drift_days: Optional[float] = None
    float_trend: str = "stable"  # "eroding" | "recovering" | "stable"
    spi_trend: str = "stable"
    manipulation_trend: str = "stable"
    narrative: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fmt_date(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(dt)


def _trend_label(
    values: List[Optional[float]],
    erosion_direction: str = "decreasing",
    epsilon: float = 1e-6,
) -> str:
    """Classify a time-series as eroding / recovering / stable.

    ``erosion_direction="decreasing"`` means *lower values are worse*
    (e.g. float, SPI). ``"increasing"`` means higher values are worse
    (e.g. manipulation score).
    """
    real = [v for v in values if v is not None]
    if len(real) < 2:
        return "stable"
    delta = real[-1] - real[0]
    if abs(delta) < epsilon:
        return "stable"
    if erosion_direction == "decreasing":
        return "eroding" if delta < 0 else "recovering"
    return "eroding" if delta > 0 else "recovering"


def _detail_tasks(schedule: ScheduleData):
    return [t for t in schedule.tasks if not t.summary]


# --------------------------------------------------------------------------- #
# Per-update metric builder
# --------------------------------------------------------------------------- #


def _build_data_point(
    idx: int,
    schedule: ScheduleData,
    prior_schedule: Optional[ScheduleData],
    pairwise_comparison: Optional[ComparisonResults],
) -> TrendDataPoint:
    cpm = compute_cpm(schedule)
    dcma = compute_dcma(schedule, cpm)
    ev = compute_earned_value(schedule)

    bei: Optional[float] = None
    bei_metric = next((m for m in dcma.metrics if m.number == 14), None)
    if bei_metric is not None:
        bei = float(bei_metric.value)

    floats = [
        t.total_slack
        for t in schedule.tasks
        if t.total_slack is not None and not t.summary
    ]
    total_float_avg = (sum(floats) / len(floats)) if floats else 0.0
    total_float_min = min(floats) if floats else 0.0

    detail = _detail_tasks(schedule)
    tasks_complete = sum(1 for t in detail if (t.percent_complete or 0) >= 100)
    tasks_in_progress = sum(
        1 for t in detail if 0 < (t.percent_complete or 0) < 100
    )
    tasks_not_started = sum(
        1 for t in detail if (t.percent_complete or 0) == 0
    )

    manip_score: Optional[float] = None
    slip_since: Optional[float] = None
    tasks_added = 0
    tasks_removed = 0
    tasks_completed = 0
    if pairwise_comparison is not None and prior_schedule is not None:
        manip = detect_manipulations(pairwise_comparison, prior_schedule, schedule)
        manip_score = manip.overall_score
        slip_since = pairwise_comparison.completion_date_slip_days
        tasks_added = pairwise_comparison.tasks_added_count
        tasks_removed = pairwise_comparison.tasks_deleted_count
        tasks_completed = pairwise_comparison.tasks_completed_count

    return TrendDataPoint(
        update_index=idx,
        update_label=f"Update {idx + 1}",
        status_date=schedule.project_info.status_date,
        project_finish=schedule.project_info.finish_date,
        task_count=len(detail),
        tasks_complete=tasks_complete,
        tasks_in_progress=tasks_in_progress,
        tasks_not_started=tasks_not_started,
        critical_path_task_count=len(cpm.critical_path_uids),
        total_float_avg=round(total_float_avg, 2),
        total_float_min=round(total_float_min, 2),
        spi=round(ev.schedule_performance_index, 4),
        bei=round(bei, 4) if bei is not None else None,
        tasks_added_since_prior=tasks_added,
        tasks_removed_since_prior=tasks_removed,
        tasks_completed_since_prior=tasks_completed,
        manipulation_score=round(manip_score, 2) if manip_score is not None else None,
        finish_slip_since_prior_days=(
            round(slip_since, 2) if slip_since is not None else None
        ),
    )


# --------------------------------------------------------------------------- #
# Cumulative compressions
# --------------------------------------------------------------------------- #


def _compute_cumulative_compressions(
    schedules: List[ScheduleData],
    pairwise: List[ComparisonResults],
) -> List[TaskCompressionSummary]:
    """For each task, sum ``duration_change_days`` across every update."""
    cumulative: Dict[int, float] = defaultdict(float)
    events: Dict[int, int] = defaultdict(int)
    name_for: Dict[int, Optional[str]] = {}
    first_dur: Dict[int, Optional[float]] = {}
    last_dur: Dict[int, Optional[float]] = {}

    for t in schedules[0].tasks:
        first_dur[t.uid] = t.duration
        name_for.setdefault(t.uid, t.name)
    for t in schedules[-1].tasks:
        last_dur[t.uid] = t.duration
        name_for.setdefault(t.uid, t.name)

    for comparison in pairwise:
        for delta in comparison.task_deltas:
            dc = delta.duration_change_days
            if dc is None or dc == 0:
                continue
            cumulative[delta.uid] += dc
            events[delta.uid] += 1
            if delta.name:
                name_for.setdefault(delta.uid, delta.name)

    summaries = [
        TaskCompressionSummary(
            uid=uid,
            name=name_for.get(uid),
            cumulative_duration_change_days=round(change, 2),
            compression_events=events[uid],
            first_duration=first_dur.get(uid),
            last_duration=last_dur.get(uid),
        )
        for uid, change in cumulative.items()
    ]
    summaries.sort(
        key=lambda s: abs(s.cumulative_duration_change_days), reverse=True
    )
    return summaries[:TOP_COMPRESSION_COUNT]


# --------------------------------------------------------------------------- #
# Baseline reset detection
# --------------------------------------------------------------------------- #


def _detect_baseline_resets(
    pairwise: List[ComparisonResults],
    data_points: List[TrendDataPoint],
) -> List[BaselineResetEvent]:
    resets: List[BaselineResetEvent] = []
    for idx, comparison in enumerate(pairwise):
        affected = 0
        max_shift = 0.0
        for delta in comparison.task_deltas:
            shift = max(
                abs(delta.baseline_start_delta_days or 0.0),
                abs(delta.baseline_finish_delta_days or 0.0),
            )
            if shift > BASELINE_SHIFT_THRESHOLD_DAYS:
                affected += 1
                if shift > max_shift:
                    max_shift = shift
        total = max(1, len(comparison.task_deltas))
        fraction = affected / total
        if affected >= BASELINE_RESET_MIN_TASKS or (
            affected >= 1 and fraction >= BASELINE_RESET_FRACTION
        ):
            later_idx = idx + 1
            resets.append(
                BaselineResetEvent(
                    update_index=later_idx,
                    update_label=data_points[later_idx].update_label,
                    affected_task_count=affected,
                    max_baseline_shift_days=round(max_shift, 2),
                )
            )
    return resets


# --------------------------------------------------------------------------- #
# Narrative
# --------------------------------------------------------------------------- #


def _build_narrative(
    data_points: List[TrendDataPoint],
    drift_days: Optional[float],
    float_trend: str,
    spi_trend: str,
    manipulation_trend: str,
    baseline_resets: List[BaselineResetEvent],
) -> str:
    parts: List[str] = []
    parts.append(
        f"Trajectory covers {len(data_points)} schedule updates "
        f"from {_fmt_date(data_points[0].status_date)} "
        f"to {_fmt_date(data_points[-1].status_date)}."
    )
    if drift_days is not None:
        if drift_days > 0:
            direction = "later"
        elif drift_days < 0:
            direction = "earlier"
        else:
            direction = "unchanged"
        parts.append(
            f"Project completion has drifted {abs(drift_days):.1f} calendar days "
            f"{direction} across the span."
        )
    parts.append(f"Float is {float_trend}.")
    parts.append(f"SPI is {spi_trend}.")
    if manipulation_trend != "stable":
        parts.append(f"Manipulation signals are {manipulation_trend}.")
    if baseline_resets:
        updates = ", ".join(str(r.update_index + 1) for r in baseline_resets)
        parts.append(
            f"{len(baseline_resets)} baseline reset event(s) detected "
            f"(updates: {updates})."
        )
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compute_trend_analysis(
    schedules: List[ScheduleData],
) -> TrendAnalysisResults:
    """Run trend analysis over ≥2 chronologically-sorted schedules."""
    if len(schedules) < 2:
        raise ValueError(
            f"Trend analysis requires at least 2 schedules (got {len(schedules)})"
        )

    pairwise = chain_compare(schedules)

    data_points: List[TrendDataPoint] = []
    for idx, schedule in enumerate(schedules):
        prior = schedules[idx - 1] if idx > 0 else None
        pairwise_cmp = pairwise[idx - 1] if idx > 0 else None
        data_points.append(_build_data_point(idx, schedule, prior, pairwise_cmp))

    task_compressions = _compute_cumulative_compressions(schedules, pairwise)
    baseline_resets = _detect_baseline_resets(pairwise, data_points)

    first_finish = data_points[0].project_finish
    last_finish = data_points[-1].project_finish
    drift_days: Optional[float] = None
    if first_finish is not None and last_finish is not None:
        drift_days = (last_finish - first_finish).total_seconds() / 86400.0

    float_mins: List[Optional[float]] = [dp.total_float_min for dp in data_points]
    float_trend = _trend_label(
        float_mins, erosion_direction="decreasing", epsilon=FLOAT_TREND_EPSILON
    )

    spi_values: List[Optional[float]] = [dp.spi for dp in data_points]
    spi_trend = _trend_label(
        spi_values, erosion_direction="decreasing", epsilon=SPI_TREND_EPSILON
    )

    manip_values: List[Optional[float]] = [
        dp.manipulation_score for dp in data_points
    ]
    manipulation_trend = _trend_label(
        manip_values,
        erosion_direction="increasing",
        epsilon=MANIPULATION_TREND_EPSILON,
    )

    narrative = _build_narrative(
        data_points,
        drift_days,
        float_trend,
        spi_trend,
        manipulation_trend,
        baseline_resets,
    )

    return TrendAnalysisResults(
        update_count=len(schedules),
        data_points=data_points,
        task_compressions=task_compressions,
        baseline_resets=baseline_resets,
        completion_date_drift_days=(
            round(drift_days, 2) if drift_days is not None else None
        ),
        float_trend=float_trend,
        spi_trend=spi_trend,
        manipulation_trend=manipulation_trend,
        narrative=narrative,
    )
