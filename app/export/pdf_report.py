"""PDF report generator (reportlab).

Mirrors the structure of ``docx_report.generate_docx_report`` but
produces a paginated PDF suitable for email or claim-package
attachment. Uses platypus for layout so tables split cleanly across
page breaks.

Design notes
------------
* Palette matches the web UI dark-theme navy `#1B2432` for headers
  with pastel fills for PASS / FAIL / manipulation confidence rows.
* Every table has `repeatRows=1` so headers show on every page.
* Story elements use ``KeepTogether`` for sub-sections that shouldn't
  split mid-list (e.g. the executive summary paragraphs).
* Returns ``bytes`` so the Flask route can wrap it in a BytesIO.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


HDR_BG = colors.HexColor("#1B2432")
HDR_FG = colors.whitesmoke
PASS_BG = colors.HexColor("#D4F5E3")
FAIL_BG = colors.HexColor("#FBD7DB")
HIGH_BG = colors.HexColor("#FBD7DB")
MEDIUM_BG = colors.HexColor("#FCEBC8")
LOW_BG = colors.HexColor("#D6E9FC")
ACCENT = colors.HexColor("#4A9EFF")
GRID = colors.HexColor("#8690A3")


# --------------------------------------------------------------------------- #
# Style builders
# --------------------------------------------------------------------------- #


def _make_styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: Dict[str, ParagraphStyle] = {}
    styles["title"] = ParagraphStyle(
        "title",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=HDR_BG,
        spaceAfter=16,
        alignment=TA_LEFT,
    )
    styles["h1"] = ParagraphStyle(
        "h1",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=HDR_BG,
        spaceBefore=14,
        spaceAfter=10,
    )
    styles["h2"] = ParagraphStyle(
        "h2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=HDR_BG,
        spaceBefore=10,
        spaceAfter=6,
    )
    styles["body"] = ParagraphStyle(
        "body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    styles["meta"] = ParagraphStyle(
        "meta",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#5A6578"),
        spaceAfter=4,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        leftIndent=14,
        bulletIndent=4,
        spaceAfter=4,
    )
    return styles


BASE_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), HDR_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), HDR_FG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def generate_pdf_report(
    results: Dict[str, Any],
    ai_narrative: Optional[str] = None,
    analyst_name: Optional[str] = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Schedule Forensics Report",
        author=analyst_name or "Schedule Forensics Local Tool",
    )
    styles = _make_styles()
    story: List[Any] = []

    has_comparison = results.get("comparison") is not None
    schedule = _primary_schedule(results)
    title = (
        "Comparative Schedule Analysis"
        if has_comparison
        else "Schedule Analysis"
    )

    _add_title_page(story, styles, title, schedule, analyst_name)
    story.append(PageBreak())

    _add_executive_summary(story, styles, ai_narrative)

    if results.get("dcma") is not None:
        _add_dcma(story, styles, results["dcma"])

    if results.get("cpm") is not None:
        _add_critical_path(story, styles, results["cpm"], schedule)

    if has_comparison:
        _add_slippage(
            story, styles, results["comparison"], results.get("delay")
        )

    if results.get("manipulation") is not None:
        _add_manipulation(story, styles, results["manipulation"])

    if results.get("float_analysis") is not None:
        _add_float(story, styles, results["float_analysis"])

    if results.get("earned_value") is not None:
        _add_earned_value(story, styles, results["earned_value"])

    _add_recommendations(story, styles, results)
    _add_conclusion(story, styles, results, has_comparison)

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _primary_schedule(results: Dict[str, Any]):
    return results.get("later_schedule") or results.get("prior_schedule")


def _fmt_date(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(value)


def _fmt_signed(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}"


def _fmt_num(value: Optional[float], decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}"


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#8690A3"))
    canvas.drawCentredString(
        letter[0] / 2,
        0.4 * inch,
        f"Page {doc.page} · Schedule Forensics Local Tool",
    )
    canvas.restoreState()


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _add_title_page(
    story: List[Any],
    styles: Dict[str, ParagraphStyle],
    title: str,
    schedule,
    analyst_name: Optional[str],
) -> None:
    story.append(Paragraph(title, styles["title"]))

    if schedule is not None:
        info = schedule.project_info
        story.append(
            Paragraph(f"<b>{info.name or 'Unnamed Project'}</b>", styles["h2"])
        )
        story.append(
            Paragraph(
                f"Start: {_fmt_date(info.start_date)}", styles["meta"]
            )
        )
        story.append(
            Paragraph(
                f"Finish: {_fmt_date(info.finish_date)}", styles["meta"]
            )
        )
        story.append(
            Paragraph(
                f"Status date: {_fmt_date(info.status_date)}", styles["meta"]
            )
        )

    if analyst_name:
        story.append(
            Paragraph(f"<b>Analyst:</b> {analyst_name}", styles["meta"])
        )
    story.append(
        Paragraph(
            f"Generated: {datetime.utcnow().isoformat(timespec='seconds')} UTC",
            styles["meta"],
        )
    )


def _add_executive_summary(
    story: List[Any],
    styles: Dict[str, ParagraphStyle],
    ai_narrative: Optional[str],
) -> None:
    story.append(Paragraph("Executive Summary", styles["h1"]))
    if ai_narrative and ai_narrative.strip():
        for para in ai_narrative.strip().split("\n\n"):
            text = para.strip()
            if not text:
                continue
            # Escape simple HTML-significant chars that break Paragraph parser.
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(text, styles["body"]))
    else:
        story.append(
            Paragraph(
                "<i>AI narrative not yet generated. Open the Analysis tab in "
                "the web UI and click 'Generate AI Analysis' to produce a "
                "narrative, then re-export this report to include it.</i>",
                styles["body"],
            )
        )


def _add_dcma(
    story: List[Any], styles: Dict[str, ParagraphStyle], dcma
) -> None:
    story.append(
        Paragraph("Schedule Health Assessment — DCMA 14-Point", styles["h1"])
    )
    story.append(
        Paragraph(
            f"<b>Overall:</b> {dcma.passed_count} passed / {dcma.failed_count} "
            f"failed ({dcma.overall_score_pct:.1f}%).",
            styles["body"],
        )
    )

    data: List[List[Any]] = [["#", "Metric", "Value", "Threshold", "Status"]]
    status_row_colors: List[tuple] = []
    for row_idx, m in enumerate(dcma.metrics, start=1):
        if m.unit == "%":
            value_str = f"{m.value:.2f}%"
        elif m.unit == "index":
            value_str = f"{m.value:.3f}"
        else:
            value_str = str(m.value)
        data.append(
            [
                str(m.number),
                m.name,
                value_str,
                f"{m.comparison}{m.threshold}",
                "PASS" if m.passed else "FAIL",
            ]
        )
        status_row_colors.append(
            (row_idx, PASS_BG if m.passed else FAIL_BG)
        )

    table = Table(
        data,
        repeatRows=1,
        colWidths=[0.4 * inch, 2.2 * inch, 1.1 * inch, 1.1 * inch, 0.8 * inch],
    )
    style = TableStyle(BASE_TABLE_STYLE.getCommands())
    for row_idx, bg in status_row_colors:
        style.add("BACKGROUND", (4, row_idx), (4, row_idx), bg)
        style.add("FONTNAME", (4, row_idx), (4, row_idx), "Helvetica-Bold")
    table.setStyle(style)
    story.append(table)
    story.append(Spacer(1, 6))


def _add_critical_path(
    story: List[Any], styles: Dict[str, ParagraphStyle], cpm, schedule
) -> None:
    story.append(Paragraph("Critical Path Analysis", styles["h1"]))
    story.append(
        Paragraph(
            f"Project duration: {cpm.project_duration_days:.1f} working days — "
            f"{len(cpm.critical_path_uids)} task(s) on the critical path.",
            styles["body"],
        )
    )
    if not cpm.critical_path_uids or schedule is None:
        return

    task_by_uid = {t.uid: t for t in schedule.tasks}
    float_lookup = cpm.task_floats or {}
    data: List[List[Any]] = [
        ["Seq", "Task", "Finish", "Dur (d)", "Total Float (d)"]
    ]
    for idx, uid in enumerate(cpm.critical_path_uids[:30], start=1):
        task = task_by_uid.get(uid)
        if task is None:
            continue
        tf = float_lookup.get(uid)
        total_float = getattr(tf, "total_float", None) if tf else None
        data.append(
            [
                str(idx),
                (task.name or f"Task {uid}")[:60],
                _fmt_date(task.finish),
                _fmt_num(task.duration),
                _fmt_num(total_float),
            ]
        )
    table = Table(
        data,
        repeatRows=1,
        colWidths=[0.5 * inch, 3.0 * inch, 1.0 * inch, 0.9 * inch, 1.2 * inch],
    )
    table.setStyle(BASE_TABLE_STYLE)
    story.append(table)


def _add_slippage(
    story: List[Any],
    styles: Dict[str, ParagraphStyle],
    comparison,
    delay,
) -> None:
    story.append(Paragraph("Delay and Slippage Analysis", styles["h1"]))

    story.append(
        Paragraph(
            f"<b>Tasks slipped:</b> {comparison.tasks_slipped_count}   "
            f"<b>Pulled in:</b> {comparison.tasks_pulled_in_count}   "
            f"<b>Completed:</b> {comparison.tasks_completed_count}   "
            f"<b>Added:</b> {comparison.tasks_added_count}   "
            f"<b>Deleted:</b> {comparison.tasks_deleted_count}",
            styles["body"],
        )
    )
    if comparison.completion_date_slip_days is not None:
        story.append(
            Paragraph(
                f"<b>Project completion slip:</b> "
                f"{comparison.completion_date_slip_days:+.1f} calendar days.",
                styles["body"],
            )
        )

    slipped = [
        d
        for d in comparison.task_deltas
        if d.finish_slip_days and d.finish_slip_days > 0
    ]
    slipped.sort(key=lambda d: d.finish_slip_days or 0, reverse=True)

    if slipped:
        story.append(Paragraph("Top 10 Slipped Tasks", styles["h2"]))
        data: List[List[Any]] = [
            ["UID", "Task", "Start Slip (d)", "Finish Slip (d)", "Δ Dur (d)"]
        ]
        for d in slipped[:10]:
            data.append(
                [
                    str(d.uid),
                    (d.name or "—")[:60],
                    _fmt_signed(d.start_slip_days),
                    _fmt_signed(d.finish_slip_days),
                    _fmt_signed(d.duration_change_days),
                ]
            )
        table = Table(
            data,
            repeatRows=1,
            colWidths=[0.5 * inch, 3.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch],
        )
        table.setStyle(BASE_TABLE_STYLE)
        story.append(table)

    duration_changes = [
        d
        for d in comparison.task_deltas
        if d.duration_change_days and d.duration_change_days != 0
    ]
    if duration_changes:
        story.append(Paragraph("Duration Changes", styles["h2"]))
        top = sorted(
            duration_changes,
            key=lambda d: abs(d.duration_change_days or 0),
            reverse=True,
        )[:10]
        data = [["UID", "Task", "Δ Duration (d)"]]
        for d in top:
            data.append(
                [
                    str(d.uid),
                    (d.name or "—")[:60],
                    _fmt_signed(d.duration_change_days),
                ]
            )
        table = Table(
            data,
            repeatRows=1,
            colWidths=[0.6 * inch, 4.0 * inch, 1.4 * inch],
        )
        table.setStyle(BASE_TABLE_STYLE)
        story.append(table)

    if delay is not None:
        story.append(Paragraph("Root Cause Analysis", styles["h2"]))
        if delay.first_mover_uid is not None:
            name = delay.first_mover_name or f"Task {delay.first_mover_uid}"
            story.append(
                Paragraph(
                    f"<b>First mover:</b> {name} — slipped "
                    f"{delay.first_mover_slip_days:.1f} days.",
                    styles["body"],
                )
            )
        for cause in (delay.root_causes or [])[:10]:
            task_label = cause.task_name or f"Task {cause.task_uid}"
            cp = " (critical path)" if cause.on_critical_path else ""
            story.append(
                Paragraph(
                    f"• <b>[{cause.category}]</b> {task_label} — "
                    f"{cause.slip_days:.1f} days{cp}",
                    styles["bullet"],
                )
            )


def _add_manipulation(
    story: List[Any], styles: Dict[str, ParagraphStyle], manip
) -> None:
    story.append(Paragraph("Manipulation Findings", styles["h1"]))
    story.append(
        Paragraph(
            f"<b>Overall score:</b> {manip.overall_score:.0f}/100   "
            f"(HIGH: {manip.confidence_summary.get('HIGH', 0)}, "
            f"MEDIUM: {manip.confidence_summary.get('MEDIUM', 0)}, "
            f"LOW: {manip.confidence_summary.get('LOW', 0)})",
            styles["body"],
        )
    )
    if not manip.findings:
        story.append(Paragraph("No manipulation patterns detected.", styles["body"]))
        return

    conf_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ordered = sorted(
        manip.findings,
        key=lambda f: (conf_rank.get(f.confidence, 9), -f.severity_score),
    )
    data: List[List[Any]] = [["Conf.", "Category", "Finding"]]
    row_confs: List[str] = []
    for f in ordered:
        task_suffix = (
            f" <font color='#5A6578'>— {f.task_name}</font>"
            if f.task_name
            else ""
        )
        desc = f.description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        data.append(
            [
                f.confidence,
                f.category,
                Paragraph(f"{desc}{task_suffix}", styles["body"]),
            ]
        )
        row_confs.append(f.confidence)

    table = Table(
        data,
        repeatRows=1,
        colWidths=[0.7 * inch, 1.0 * inch, 5.3 * inch],
    )
    style = TableStyle(BASE_TABLE_STYLE.getCommands())
    for row_idx, conf in enumerate(row_confs, start=1):
        if conf == "HIGH":
            bg = HIGH_BG
        elif conf == "MEDIUM":
            bg = MEDIUM_BG
        else:
            bg = LOW_BG
        style.add("BACKGROUND", (0, row_idx), (0, row_idx), bg)
        style.add("FONTNAME", (0, row_idx), (0, row_idx), "Helvetica-Bold")
    table.setStyle(style)
    story.append(table)


def _add_float(
    story: List[Any], styles: Dict[str, ParagraphStyle], fa
) -> None:
    story.append(Paragraph("Float Analysis", styles["h1"]))
    story.append(
        Paragraph(f"<b>Trend:</b> {fa.trend}", styles["body"])
    )
    story.append(
        Paragraph(
            f"Net float delta: <b>{fa.net_float_delta:+.1f}</b> days across "
            f"{len(fa.task_changes)} compared tasks.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            f"Became critical: <b>{len(fa.became_critical_uids)}</b> · "
            f"Dropped off critical: <b>{len(fa.dropped_off_critical_uids)}</b>",
            styles["body"],
        )
    )


def _add_earned_value(
    story: List[Any], styles: Dict[str, ParagraphStyle], ev
) -> None:
    story.append(Paragraph("Earned Value Summary", styles["h1"]))
    story.append(Paragraph(f"Units: {ev.units}", styles["meta"]))

    rows: List[List[Any]] = [["Metric", "Value"]]
    rows.append(["BAC — Budget at Completion", _fmt_num(ev.budget_at_completion)])
    rows.append(["PV — Planned Value", _fmt_num(ev.planned_value)])
    rows.append(["EV — Earned Value", _fmt_num(ev.earned_value)])
    rows.append(["SV — Schedule Variance", _fmt_signed(ev.schedule_variance)])
    rows.append(
        [
            "SPI — Schedule Performance Index",
            _fmt_num(ev.schedule_performance_index, decimals=3),
        ]
    )
    if ev.actual_cost is not None:
        rows.append(["AC — Actual Cost", _fmt_num(ev.actual_cost)])
    if ev.cost_variance is not None:
        rows.append(["CV — Cost Variance", _fmt_signed(ev.cost_variance)])
    if ev.cost_performance_index is not None:
        rows.append(
            [
                "CPI — Cost Performance Index",
                _fmt_num(ev.cost_performance_index, decimals=3),
            ]
        )
    if ev.estimate_at_completion is not None:
        rows.append(
            ["EAC — Estimate at Completion", _fmt_num(ev.estimate_at_completion)]
        )

    table = Table(
        rows,
        repeatRows=1,
        colWidths=[3.5 * inch, 2.0 * inch],
    )
    table.setStyle(BASE_TABLE_STYLE)
    story.append(table)


def _add_recommendations(
    story: List[Any],
    styles: Dict[str, ParagraphStyle],
    results: Dict[str, Any],
) -> None:
    story.append(Paragraph("Opportunities and Recommendations", styles["h1"]))
    for rec in _build_recommendations(results):
        story.append(Paragraph(f"• {rec}", styles["bullet"]))


def _add_conclusion(
    story: List[Any],
    styles: Dict[str, ParagraphStyle],
    results: Dict[str, Any],
    has_comparison: bool,
) -> None:
    story.append(Paragraph("Conclusion", styles["h1"]))
    story.append(
        Paragraph(_build_conclusion_text(results, has_comparison), styles["body"])
    )


def _build_recommendations(results: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    dcma = results.get("dcma")
    if dcma is not None:
        failed = [m for m in dcma.metrics if not m.passed]
        for m in failed[:5]:
            recs.append(
                f"DCMA #{m.number} ({m.name}) is failing at {m.value}{m.unit}. "
                f"Target: {m.comparison}{m.threshold}."
            )
    manip = results.get("manipulation")
    if manip is not None and manip.overall_score >= 20:
        recs.append(
            f"Manipulation score of {manip.overall_score:.0f}/100 warrants "
            "independent review."
        )
    fa = results.get("float_analysis")
    if fa is not None and fa.trend == "consuming":
        recs.append(
            f"Float consumption trend is negative ({fa.net_float_delta:+.1f}d). "
            f"Review mitigation for {len(fa.became_critical_uids)} newly "
            "critical task(s)."
        )
    ev = results.get("earned_value")
    if ev is not None and ev.schedule_performance_index < 0.95:
        recs.append(
            f"SPI of {ev.schedule_performance_index:.2f} indicates schedule "
            "performance below plan."
        )
    if not recs:
        recs.append(
            "No critical issues detected. Continue weekly schedule updates."
        )
    return recs


def _build_conclusion_text(
    results: Dict[str, Any], has_comparison: bool
) -> str:
    parts: List[str] = []
    dcma = results.get("dcma")
    if dcma is not None:
        parts.append(
            f"The schedule passes {dcma.passed_count} of "
            f"{len(dcma.metrics)} DCMA metrics "
            f"({dcma.overall_score_pct:.0f}% overall health)."
        )
    if has_comparison:
        comparison = results.get("comparison")
        if comparison is not None:
            parts.append(
                f"Between updates, {comparison.tasks_slipped_count} task(s) "
                f"slipped, {comparison.tasks_completed_count} completed, and "
                f"{comparison.tasks_added_count} were added."
            )
        manip = results.get("manipulation")
        if manip is not None:
            parts.append(
                f"Manipulation indicators scored {manip.overall_score:.0f}/100 "
                f"with {manip.confidence_summary.get('HIGH', 0)} HIGH-confidence "
                "finding(s)."
            )
    else:
        parts.append(
            "This is a single-schedule snapshot; run a comparative analysis "
            "against a prior update to assess slippage and manipulation."
        )
    if not parts:
        parts.append("Report generated with no engine findings available.")
    return " ".join(parts)
