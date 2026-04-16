"""Prompt construction from forensic engine output.

Takes a dict of engine results — any subset of comparison / DCMA /
manipulation / CPM / delay / earned value / float analysis — and
produces a compact, structured prompt suitable for a local 8K-context
Ollama model (`schedule-analyst`) or the cloud Claude API.

Design constraints
------------------
* **Hard token budget** (default 6000 tokens ≈ 24000 characters) so
  the narrative has room to breathe inside Ollama's 8K context.
* **Knowledge base injection** — exemplar findings, recent high-rated
  feedback, and DCMA threshold breach context are pulled from
  ``app/knowledge_base/`` on the first call (cached for the process
  lifetime) and slotted between SYSTEM_INTRO and the data sections.
  Missing files are tolerated silently — the prompt still builds.
* **Each section is optional** — the builder renders only what the
  caller provides, so the same function is used for single-schedule
  DCMA reports, comparison reports, or full-blown forensic reports.
* **Pydantic or dict input** — `_to_dict()` coerces either into a
  plain dict so the rest of the code doesn't care about the source.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Approximation: 1 token ≈ 4 characters of English text. This is close
# enough for a budget ceiling; the real tokenizer will be slightly off
# but never by more than ~15% for narrative text.
CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 6000

# How many rows to include in ranked tables before truncating.
TOP_SLIP_COUNT = 10
TOP_DURATION_CHANGES = 10
TOP_MANIPULATION_FINDINGS = 20

# Knowledge base injection limits
MAX_INJECTED_EXEMPLARS = 3
MAX_INJECTED_FEEDBACK = 2
MAX_INJECTED_BREACHES = 8
FEEDBACK_LOOKBACK_DAYS = 30
FEEDBACK_MIN_RATING = 4

# RAG injection hooks (kept as constants for backward compat with any
# tests that grep for them).
CONTEXT_START_TAG = "[CONTEXT_START]"
CONTEXT_END_TAG = "[CONTEXT_END]"

SYSTEM_INTRO = (
    "You are a forensic schedule analyst reviewing pre-computed metrics "
    "from a CPM schedule analysis tool. All numbers below are the output "
    "of deterministic Python analysis — treat them as ground truth and "
    "do not recompute them. Your job is to turn the metrics into a clear, "
    "professional narrative for a construction-claim audience."
)


# --------------------------------------------------------------------------- #
# Knowledge base — module-level cache, lazy-loaded on first build_prompt call
# --------------------------------------------------------------------------- #

# Resolve relative to this file so the loader works regardless of cwd.
_KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
_EXEMPLARS_PATH = _KB_DIR / "exemplar_findings.json"
_THRESHOLDS_PATH = _KB_DIR / "dcma_thresholds.json"
_FEEDBACK_PATH = _KB_DIR / "feedback.jsonl"

# Sentinel: True once we've attempted to load the static files. We never
# raise on missing files — the prompt builder must work in environments
# without a populated knowledge base.
_KB_LOADED: bool = False
_EXEMPLARS: List[Dict[str, Any]] = []
_THRESHOLDS: Dict[str, Any] = {}

# Map manipulation finding patterns → exemplar finding_type. Used to
# select the most relevant exemplars for the current analysis.
_PATTERN_TO_EXEMPLAR_TYPE: Dict[str, str] = {
    # Duration
    "critical_duration_reduction": "duration_compression",
    "selective_critical_compression": "duration_compression",
    # Logic
    "predecessors_removed": "logic_removal",
    "fs_type_downgrade": "logic_removal",
    "lag_change": "logic_removal",
    # Constraint / float
    "constraint_added": "constraint_addition",
    "single_file_hard_constraint": "constraint_addition",
    "unexplained_float_change": "float_reduction",
    "single_file_negative_float": "float_reduction",
    # Progress
    "out_of_sequence_progress": "progress_inflation",
    "percent_vs_remaining_mismatch": "progress_inflation",
    "actual_start_zero_progress": "progress_inflation",
    "single_file_complete_without_actuals": "progress_inflation",
    "progress_reversal": "progress_inflation",
}


def _load_knowledge_base() -> None:
    """Read exemplar_findings.json and dcma_thresholds.json once.

    Tolerates every flavor of failure (missing file, malformed JSON,
    permission error) by falling back to empty defaults — the prompt
    builder is never allowed to crash a forensic analysis just
    because the knowledge base is missing.
    """
    global _KB_LOADED, _EXEMPLARS, _THRESHOLDS
    if _KB_LOADED:
        return
    _KB_LOADED = True
    try:
        if _EXEMPLARS_PATH.is_file():
            with _EXEMPLARS_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                _EXEMPLARS = [d for d in data if isinstance(d, dict)]
    except (OSError, json.JSONDecodeError):
        _EXEMPLARS = []
    try:
        if _THRESHOLDS_PATH.is_file():
            with _THRESHOLDS_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                _THRESHOLDS = data
    except (OSError, json.JSONDecodeError):
        _THRESHOLDS = {}


def _load_recent_feedback() -> List[Dict[str, Any]]:
    """Read up to MAX_INJECTED_FEEDBACK high-rated, recent feedback entries.

    Filters: rating >= 4 and timestamp within the last 30 days.
    Returns most recent first, capped at MAX_INJECTED_FEEDBACK.
    Missing file or malformed lines are silently skipped — the
    feedback log is operator-managed and may not exist on a fresh
    install.
    """
    if not _FEEDBACK_PATH.is_file():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=FEEDBACK_LOOKBACK_DAYS)
    entries: List[Dict[str, Any]] = []
    try:
        with _FEEDBACK_PATH.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                rating = entry.get("rating")
                if not isinstance(rating, (int, float)) or rating < FEEDBACK_MIN_RATING:
                    continue
                ts_raw = entry.get("timestamp")
                if not isinstance(ts_raw, str):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                entries.append(entry)
    except OSError:
        return []
    # Most recent first.
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries[:MAX_INJECTED_FEEDBACK]


def _select_matching_exemplars(
    manipulation: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Pick up to MAX_INJECTED_EXEMPLARS exemplars matching current findings.

    The map :data:`_PATTERN_TO_EXEMPLAR_TYPE` translates manipulation
    pattern keys to exemplar ``finding_type`` slugs. We collect the
    distinct types in priority order (HIGH-confidence findings first,
    then MEDIUM, then LOW) and emit the first N matching exemplars,
    one per type, so the AI sees a *variety* of relevant examples
    rather than three of the same.
    """
    if not _EXEMPLARS or not manipulation:
        return []
    findings = manipulation.get("findings") or []
    if not isinstance(findings, list):
        return []

    # Order finding types by the highest-confidence finding observed.
    weight_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    type_priority: Dict[str, int] = {}
    for f in findings:
        if not isinstance(f, dict):
            continue
        ex_type = _PATTERN_TO_EXEMPLAR_TYPE.get(f.get("pattern", ""))
        if ex_type is None:
            continue
        weight = weight_order.get(f.get("confidence", ""), 0)
        if weight > type_priority.get(ex_type, 0):
            type_priority[ex_type] = weight

    if not type_priority:
        return []

    ordered_types = sorted(
        type_priority.keys(), key=lambda t: type_priority[t], reverse=True
    )
    by_type: Dict[str, Dict[str, Any]] = {
        e.get("finding_type", ""): e for e in _EXEMPLARS if isinstance(e, dict)
    }
    picked: List[Dict[str, Any]] = []
    for t in ordered_types:
        if t in by_type and len(picked) < MAX_INJECTED_EXEMPLARS:
            picked.append(by_type[t])
    return picked


def _select_dcma_breaches(
    dcma: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build threshold-breach context for failed DCMA metrics.

    Each entry pairs the failed metric (from the analysis) with its
    canonical threshold + rationale (from the knowledge base) so the
    AI can cite the standard alongside the observed value.
    """
    if not dcma or not _THRESHOLDS:
        return []
    metrics = dcma.get("metrics")
    if not isinstance(metrics, list):
        return []
    threshold_by_name = {}
    for key, defn in _THRESHOLDS.get("metrics", {}).items():
        if isinstance(defn, dict):
            name = defn.get("name", "").strip().lower()
            threshold_by_name[name] = (key, defn)

    breaches: List[Dict[str, Any]] = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        if m.get("passed") is True:
            continue
        m_name = (m.get("name") or "").strip().lower()
        # Try exact name match, then fuzzy contains.
        match = threshold_by_name.get(m_name)
        if match is None:
            for n, val in threshold_by_name.items():
                if n and (n in m_name or m_name in n):
                    match = val
                    break
        if match is None:
            continue
        kb_key, kb_defn = match
        breaches.append(
            {
                "kb_key": kb_key,
                "metric_name": m.get("name"),
                "observed_value": m.get("value"),
                "observed_unit": m.get("unit"),
                "threshold": kb_defn.get("threshold"),
                "comparison": kb_defn.get("comparison"),
                "rationale": kb_defn.get("rationale"),
            }
        )
        if len(breaches) >= MAX_INJECTED_BREACHES:
            break
    return breaches


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _to_dict(obj: Any) -> Any:
    """Coerce a Pydantic model (or any nested structure) into plain Python."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="python")
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    return obj


def estimate_tokens(text: str) -> int:
    """Rough token count using the 4-chars-per-token heuristic."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def summarize_for_prompt(
    rows: List[Dict[str, Any]],
    sort_key: str,
    max_items: int,
    reverse: bool = True,
) -> List[Dict[str, Any]]:
    """Return the top `max_items` rows of `rows` ordered by `sort_key`.

    Missing values are treated as 0. Used by every ranked section so
    we never blow past the token budget on pathological inputs.
    """
    def _key(row: Dict[str, Any]) -> float:
        v = row.get(sort_key)
        return float(v) if isinstance(v, (int, float)) else 0.0

    return sorted(rows, key=_key, reverse=reverse)[:max_items]


def _fmt_date(val: Any) -> str:
    if val is None:
        return "—"
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _fmt_num(val: Any, suffix: str = "", precision: int = 2) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.{precision}f}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _fmt_pct(val: Any) -> str:
    return _fmt_num(val, suffix="%", precision=2)


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #


def _section_project_overview(comparison: Dict[str, Any]) -> str:
    lines = ["## PROJECT OVERVIEW"]
    prior = comparison.get("prior_project_name") or "—"
    later = comparison.get("later_project_name") or "—"
    lines.append(f"- Prior update:  {prior}")
    lines.append(f"- Later update:  {later}")
    lines.append(
        f"- Prior status date: {_fmt_date(comparison.get('prior_status_date'))}"
    )
    lines.append(
        f"- Later status date: {_fmt_date(comparison.get('later_status_date'))}"
    )
    lines.append(
        f"- Tasks added / deleted / completed: "
        f"{comparison.get('tasks_added_count', 0)} / "
        f"{comparison.get('tasks_deleted_count', 0)} / "
        f"{comparison.get('tasks_completed_count', 0)}"
    )
    lines.append(
        f"- Tasks slipped / pulled in: "
        f"{comparison.get('tasks_slipped_count', 0)} / "
        f"{comparison.get('tasks_pulled_in_count', 0)}"
    )
    slip = comparison.get("completion_date_slip_days")
    if slip is not None:
        lines.append(f"- Project completion slip: {_fmt_num(slip, ' days')}")
    net_float = comparison.get("net_float_change_days")
    if net_float is not None:
        lines.append(f"- Net float change: {_fmt_num(net_float, ' days')}")
    return "\n".join(lines)


def _section_schedule_health(dcma: Dict[str, Any]) -> str:
    lines = ["## SCHEDULE HEALTH (DCMA 14-Point)"]
    passed = dcma.get("passed_count", 0)
    failed = dcma.get("failed_count", 0)
    score = dcma.get("overall_score_pct", 0.0)
    lines.append(f"Overall: {passed} passed / {failed} failed ({score:.1f}%).")
    lines.append("")
    lines.append("| # | Metric | Value | Threshold | Status |")
    lines.append("|---|--------|-------|-----------|--------|")
    for m in dcma.get("metrics", []):
        value = m.get("value")
        threshold = m.get("threshold")
        unit = m.get("unit", "")
        comparison_op = m.get("comparison", "")
        status = "PASS" if m.get("passed") else "FAIL"
        value_str = (
            f"{value:.2f}{unit}" if isinstance(value, (int, float)) else str(value)
        )
        thresh_str = (
            f"{comparison_op}{threshold}{unit}"
            if isinstance(threshold, (int, float))
            else str(threshold)
        )
        lines.append(
            f"| {m.get('number')} | {m.get('name')} | {value_str} | "
            f"{thresh_str} | {status} |"
        )
    return "\n".join(lines)


def _section_critical_path(
    cpm: Dict[str, Any], task_name_lookup: Dict[int, str]
) -> str:
    lines = ["## CRITICAL PATH"]
    dur = cpm.get("project_duration_days")
    if dur is not None:
        lines.append(f"Project duration: {_fmt_num(dur, ' working days')}")
    critical_uids = cpm.get("critical_path_uids") or []
    task_floats = cpm.get("task_floats") or {}
    lines.append(f"Critical path length: {len(critical_uids)} task(s).")
    if critical_uids:
        lines.append("")
        lines.append("Driving sequence:")
        for idx, uid in enumerate(critical_uids[:30], start=1):
            name = task_name_lookup.get(uid, f"Task {uid}")
            tf = task_floats.get(uid) if isinstance(task_floats, dict) else None
            if tf is None and isinstance(task_floats, dict):
                # task_floats may be keyed by str after JSON round-trip
                tf = task_floats.get(str(uid))
            if tf:
                ef = tf.get("early_finish")
                lines.append(
                    f"{idx:3d}. {name}  (EF {_fmt_num(ef, ' d', precision=1)})"
                )
            else:
                lines.append(f"{idx:3d}. {name}")
        if len(critical_uids) > 30:
            lines.append(f"... and {len(critical_uids) - 30} more on the CP")
    return "\n".join(lines)


def _section_slippage_summary(comparison: Dict[str, Any]) -> str:
    lines = ["## SLIPPAGE SUMMARY (top 10 by finish slip)"]
    deltas = comparison.get("task_deltas") or []
    top = summarize_for_prompt(deltas, "finish_slip_days", TOP_SLIP_COUNT)
    if not top:
        lines.append("No task-level slippage detected.")
        return "\n".join(lines)
    lines.append("| UID | Task | Finish Slip (d) | Start Slip (d) | Δ Dur (d) |")
    lines.append("|-----|------|-----------------|----------------|-----------|")
    for d in top:
        lines.append(
            f"| {d.get('uid')} | "
            f"{(d.get('name') or '—')[:40]} | "
            f"{_fmt_num(d.get('finish_slip_days'))} | "
            f"{_fmt_num(d.get('start_slip_days'))} | "
            f"{_fmt_num(d.get('duration_change_days'))} |"
        )
    return "\n".join(lines)


def _section_duration_changes(comparison: Dict[str, Any]) -> str:
    lines = ["## DURATION CHANGES (top 10 by absolute change)"]
    deltas = comparison.get("task_deltas") or []
    with_changes = [
        d
        for d in deltas
        if isinstance(d.get("duration_change_days"), (int, float))
        and d.get("duration_change_days") != 0
    ]
    top = sorted(
        with_changes,
        key=lambda d: abs(float(d.get("duration_change_days") or 0.0)),
        reverse=True,
    )[:TOP_DURATION_CHANGES]
    if not top:
        lines.append("No duration changes detected.")
        return "\n".join(lines)
    lines.append("| UID | Task | Δ Duration (d) |")
    lines.append("|-----|------|----------------|")
    for d in top:
        lines.append(
            f"| {d.get('uid')} | {(d.get('name') or '—')[:40]} | "
            f"{_fmt_num(d.get('duration_change_days'))} |"
        )
    return "\n".join(lines)


def _section_manipulation_findings(manipulation: Dict[str, Any]) -> str:
    lines = ["## MANIPULATION FINDINGS"]
    score = manipulation.get("overall_score", 0.0)
    summary = manipulation.get("confidence_summary", {}) or {}
    lines.append(
        f"Overall manipulation score: {score:.1f}/100  "
        f"(HIGH={summary.get('HIGH', 0)}, "
        f"MEDIUM={summary.get('MEDIUM', 0)}, "
        f"LOW={summary.get('LOW', 0)})"
    )
    findings = manipulation.get("findings") or []
    if not findings:
        lines.append("No manipulation patterns detected.")
        return "\n".join(lines)
    # Order: HIGH → MEDIUM → LOW, then by severity desc
    confidence_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ordered = sorted(
        findings,
        key=lambda f: (
            confidence_rank.get(f.get("confidence", "LOW"), 9),
            -float(f.get("severity_score") or 0.0),
        ),
    )[:TOP_MANIPULATION_FINDINGS]
    for f in ordered:
        task_label = ""
        if f.get("task_uid") is not None:
            task_label = f" [{f.get('task_name') or f.get('task_uid')}]"
        lines.append(
            f"- **{f.get('confidence')}** [{f.get('category')}] "
            f"{f.get('pattern')}{task_label}: {f.get('description')}"
        )
    if len(findings) > TOP_MANIPULATION_FINDINGS:
        lines.append(
            f"... and {len(findings) - TOP_MANIPULATION_FINDINGS} more findings "
            "(truncated for prompt length)"
        )
    return "\n".join(lines)


def _section_float_analysis(float_analysis: Dict[str, Any]) -> str:
    lines = ["## FLOAT ANALYSIS"]
    lines.append(f"Trend: {float_analysis.get('trend', 'stable')}")
    lines.append(
        f"Net float delta: {_fmt_num(float_analysis.get('net_float_delta'), ' days')}"
    )
    lines.append(
        f"Average float delta per task: "
        f"{_fmt_num(float_analysis.get('avg_float_delta'), ' days')}"
    )
    bc = float_analysis.get("became_critical_uids") or []
    dc = float_analysis.get("dropped_off_critical_uids") or []
    lines.append(f"Tasks that became critical: {len(bc)}")
    lines.append(f"Tasks that dropped off the critical path: {len(dc)}")
    wbs = float_analysis.get("wbs_summaries") or []
    if wbs:
        lines.append("")
        lines.append("WBS float consumption:")
        for w in sorted(
            wbs, key=lambda x: float(x.get("total_float_consumed") or 0), reverse=True
        )[:10]:
            lines.append(
                f"- {w.get('wbs_prefix')}: "
                f"{_fmt_num(w.get('total_float_consumed'), ' days consumed')} "
                f"across {w.get('task_count')} task(s)"
            )
    return "\n".join(lines)


def _section_earned_value(ev: Dict[str, Any]) -> str:
    lines = ["## EARNED VALUE"]
    units = ev.get("units", "working_days")
    unit_label = "d" if units == "working_days" else " $"
    lines.append(f"Units: {units}")
    lines.append(f"BAC:  {_fmt_num(ev.get('budget_at_completion'), unit_label)}")
    lines.append(f"PV:   {_fmt_num(ev.get('planned_value'), unit_label)}")
    lines.append(f"EV:   {_fmt_num(ev.get('earned_value'), unit_label)}")
    if ev.get("actual_cost") is not None:
        lines.append(f"AC:   {_fmt_num(ev.get('actual_cost'), unit_label)}")
    lines.append(f"SV:   {_fmt_num(ev.get('schedule_variance'), unit_label)}")
    if ev.get("cost_variance") is not None:
        lines.append(f"CV:   {_fmt_num(ev.get('cost_variance'), unit_label)}")
    lines.append(f"SPI:  {_fmt_num(ev.get('schedule_performance_index'))}")
    if ev.get("cost_performance_index") is not None:
        lines.append(f"CPI:  {_fmt_num(ev.get('cost_performance_index'))}")
    if ev.get("to_complete_performance_index") is not None:
        lines.append(
            f"TCPI: {_fmt_num(ev.get('to_complete_performance_index'))}"
        )
    if ev.get("estimate_at_completion") is not None:
        lines.append(
            f"EAC:  {_fmt_num(ev.get('estimate_at_completion'), unit_label)}"
        )
    if ev.get("notes"):
        lines.append(f"Note: {ev.get('notes')}")
    return "\n".join(lines)


def _section_delay_analysis(delay: Dict[str, Any]) -> str:
    lines = ["## DELAY ROOT-CAUSE ANALYSIS"]
    fmu = delay.get("first_mover_uid")
    if fmu is not None:
        lines.append(
            f"First mover: {delay.get('first_mover_name') or f'Task {fmu}'} "
            f"(slipped {_fmt_num(delay.get('first_mover_slip_days'), ' days')})"
        )
    causes = delay.get("root_causes") or []
    if causes:
        lines.append("")
        lines.append("Top delay drivers:")
        ordered = sorted(
            causes, key=lambda c: float(c.get("slip_days") or 0), reverse=True
        )[:10]
        for c in ordered:
            cp_flag = " (CP)" if c.get("on_critical_path") else ""
            label = c.get("task_name") or f"Task {c.get('task_uid')}"
            lines.append(
                f"- {label}{cp_flag}: "
                f"{_fmt_num(c.get('slip_days'), ' days')} "
                f"[{c.get('category')}]"
            )
    cascades = delay.get("cascade_chains") or []
    if cascades:
        lines.append("")
        lines.append(f"Cascade chains: {len(cascades)}")
    return "\n".join(lines)


def _section_trend_analysis(trend: Dict[str, Any]) -> str:
    lines = ["## TREND ANALYSIS (multi-update time-series)"]
    lines.append(f"Updates analyzed: {trend.get('update_count', 0)}")
    lines.append(f"Float trend: {trend.get('float_trend', 'stable')}")
    lines.append(f"SPI trend: {trend.get('spi_trend', 'stable')}")
    lines.append(
        f"Manipulation trend: {trend.get('manipulation_trend', 'stable')}"
    )
    drift = trend.get("completion_date_drift_days")
    if drift is not None:
        lines.append(
            f"Completion drift (first → last): {_fmt_num(drift, suffix=' calendar days')}"
        )
    narrative = trend.get("narrative")
    if narrative:
        lines.append("")
        lines.append(f"Summary: {narrative}")

    data_points = trend.get("data_points") or []
    if data_points:
        lines.append("")
        lines.append("| Update | Status Date | Project Finish | SPI | Manip | Slip (d) |")
        lines.append("|--------|-------------|----------------|-----|-------|----------|")
        for dp in data_points[:20]:
            lines.append(
                f"| {dp.get('update_label')} | "
                f"{_fmt_date(dp.get('status_date'))} | "
                f"{_fmt_date(dp.get('project_finish'))} | "
                f"{_fmt_num(dp.get('spi'))} | "
                f"{_fmt_num(dp.get('manipulation_score'))} | "
                f"{_fmt_num(dp.get('finish_slip_since_prior_days'))} |"
            )

    compressions = trend.get("task_compressions") or []
    if compressions:
        lines.append("")
        lines.append("Top cumulative task compressions:")
        for tc in compressions[:10]:
            task_label = tc.get("name") or f"Task {tc.get('uid')}"
            delta = tc.get("cumulative_duration_change_days")
            events = tc.get("compression_events", 0)
            lines.append(
                f"- {task_label}: {_fmt_num(delta)}d cumulative over "
                f"{events} update(s)"
            )

    resets = trend.get("baseline_resets") or []
    if resets:
        lines.append("")
        lines.append("Baseline reset events:")
        for ev in resets:
            lines.append(
                f"- {ev.get('update_label')}: {ev.get('affected_task_count')} "
                f"task(s) affected, max shift "
                f"{_fmt_num(ev.get('max_baseline_shift_days'), suffix=' d')}"
            )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Task-name lookup helper
# --------------------------------------------------------------------------- #


def _build_task_name_lookup(engine_results: Dict[str, Any]) -> Dict[int, str]:
    lookup: Dict[int, str] = {}
    later_schedule = _to_dict(engine_results.get("later_schedule"))
    prior_schedule = _to_dict(engine_results.get("prior_schedule"))
    for schedule in (later_schedule, prior_schedule):
        if not schedule:
            continue
        for task in schedule.get("tasks", []) or []:
            uid = task.get("uid")
            if uid is not None and uid not in lookup:
                lookup[int(uid)] = task.get("name") or f"Task {uid}"
    # Fall back to names from comparison.task_deltas
    comparison = _to_dict(engine_results.get("comparison"))
    if comparison:
        for d in comparison.get("task_deltas", []) or []:
            uid = d.get("uid")
            if uid is not None and int(uid) not in lookup:
                lookup[int(uid)] = d.get("name") or f"Task {uid}"
    return lookup


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _section_knowledge_base_context(
    manipulation: Optional[Dict[str, Any]],
    dcma: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Render the REFERENCE EXAMPLES / SUCCESSFUL ANALYSIS PATTERNS /
    DCMA BREACH CONTEXT block.

    Returns ``None`` when nothing applies — the prompt builder will
    drop the section entirely instead of emitting empty headers.
    """
    _load_knowledge_base()

    exemplars = _select_matching_exemplars(manipulation)
    feedback = _load_recent_feedback()
    breaches = _select_dcma_breaches(dcma)

    if not exemplars and not feedback and not breaches:
        return None

    blocks: List[str] = [CONTEXT_START_TAG]

    if exemplars:
        blocks.append("## REFERENCE EXAMPLES")
        blocks.append(
            "The following are canonical forensic-finding write-ups for "
            "the manipulation patterns present in this analysis. Use them "
            "to calibrate tone, depth, and citation style — do NOT copy "
            "the placeholder tokens like [TASK_NAME] verbatim; substitute "
            "the actual task identifiers from the data sections below."
        )
        for ex in exemplars:
            blocks.append(
                f"### EXAMPLE — {ex.get('finding_type', '?')} "
                f"(severity {ex.get('severity', '?')}, "
                f"confidence {ex.get('confidence', '?')})"
            )
            ctx = ex.get("context")
            if ctx:
                blocks.append(f"Context: {ctx}")
            narrative = ex.get("narrative")
            if narrative:
                blocks.append(f"Narrative: {narrative}")
            implication = ex.get("forensic_implication")
            if implication:
                blocks.append(f"Forensic implication: {implication}")

    if feedback:
        blocks.append("## SUCCESSFUL ANALYSIS PATTERNS")
        blocks.append(
            "Recent operator feedback rated 4 stars or higher in the "
            "last 30 days. These are previously generated narratives "
            "an operator marked as forensically defensible — calibrate "
            "your output toward this style."
        )
        for fb in feedback:
            ts = fb.get("timestamp", "?")
            rating = fb.get("rating", "?")
            comment = (fb.get("comment") or "").strip()
            excerpt = (fb.get("analysis_excerpt") or "").strip()
            blocks.append(f"### FEEDBACK ({ts}, {rating}/5)")
            if excerpt:
                blocks.append(f"Excerpt: {excerpt}")
            if comment:
                blocks.append(f"Operator comment: {comment}")

    if breaches:
        blocks.append("## DCMA BREACH CONTEXT")
        blocks.append(
            "These are the failed DCMA 14-Point metrics in the current "
            "analysis, paired with the canonical Fuse-standard threshold "
            "and the forensic rationale for each. Cite the threshold "
            "value and rationale when discussing the corresponding "
            "metric in your narrative."
        )
        for br in breaches:
            metric = br.get("metric_name", "?")
            value = br.get("observed_value")
            unit = br.get("observed_unit") or ""
            threshold = br.get("threshold")
            comparison = br.get("comparison", "")
            rationale = br.get("rationale", "")
            value_str = (
                f"{value}{unit}" if value is not None else "(no value)"
            )
            blocks.append(
                f"- **{metric}** observed = {value_str}; "
                f"threshold {comparison} {threshold}. "
                f"Rationale: {rationale}"
            )

    blocks.append(CONTEXT_END_TAG)
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def build_prompt(
    engine_results: Dict[str, Any],
    user_request: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Build a full forensic-analysis prompt from engine results.

    Parameters
    ----------
    engine_results
        Dict containing any subset of keys: ``comparison``, ``dcma``,
        ``manipulation``, ``cpm``, ``delay``, ``earned_value``,
        ``float_analysis``, ``prior_schedule``, ``later_schedule``.
        Values may be Pydantic models or plain dicts.
    user_request
        Optional user-supplied instruction (e.g. "focus on weather delays").
    max_tokens
        Hard ceiling on the prompt length. Default 6000.
    """
    comparison = _to_dict(engine_results.get("comparison"))
    dcma = _to_dict(engine_results.get("dcma"))
    manipulation = _to_dict(engine_results.get("manipulation"))
    cpm = _to_dict(engine_results.get("cpm"))
    delay = _to_dict(engine_results.get("delay"))
    earned_value = _to_dict(engine_results.get("earned_value"))
    float_analysis = _to_dict(engine_results.get("float_analysis"))
    trend = _to_dict(engine_results.get("trend"))
    task_name_lookup = _build_task_name_lookup(engine_results)

    parts: List[str] = [SYSTEM_INTRO]

    kb_block = _section_knowledge_base_context(manipulation, dcma)
    if kb_block:
        parts.append(kb_block)
    else:
        # Keep the bracketing tags so any downstream tooling that
        # greps for them still finds a (deliberately empty) RAG slot.
        parts.append(
            f"{CONTEXT_START_TAG}\n(no knowledge-base context applied)\n{CONTEXT_END_TAG}"
        )

    if comparison:
        parts.append(_section_project_overview(comparison))
    if dcma:
        parts.append(_section_schedule_health(dcma))
    if cpm:
        parts.append(_section_critical_path(cpm, task_name_lookup))
    if comparison:
        parts.append(_section_slippage_summary(comparison))
        parts.append(_section_duration_changes(comparison))
    if manipulation:
        parts.append(_section_manipulation_findings(manipulation))
    if float_analysis:
        parts.append(_section_float_analysis(float_analysis))
    if earned_value:
        parts.append(_section_earned_value(earned_value))
    if delay:
        parts.append(_section_delay_analysis(delay))
    if trend:
        parts.append(_section_trend_analysis(trend))

    if user_request:
        parts.append("## REQUEST")
        parts.append(user_request.strip())

    parts.append("")
    parts.append(
        "Please produce:\n"
        "1. A 2–3 sentence executive summary.\n"
        "2. Top findings grouped by severity.\n"
        "3. Recommended next steps for the reviewer."
    )

    prompt = "\n\n".join(p for p in parts if p is not None)

    # Enforce budget.
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(prompt) > max_chars:
        marker = "\n\n[...remaining sections truncated for prompt token budget...]"
        prompt = prompt[: max_chars - len(marker)] + marker
    return prompt
