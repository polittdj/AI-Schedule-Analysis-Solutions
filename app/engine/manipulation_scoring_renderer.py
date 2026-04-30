"""Jinja2-ready dict projection of the M11 manipulation-scoring summary.

Block 4b (2026-05-01) renderer helper. Consumes a frozen
:class:`~app.contracts.manipulation_scoring.ManipulationScoringSummary`
emitted by the M11 scoring engine
(:func:`app.engine.manipulation_scoring.score_manipulation`) and
produces a plain ``dict[str, Any]`` projection consumed downstream by
the M12 AI narrative layer and the M13 Flask UI templates. No HTML,
DOCX, XLSX, or PDF rendering happens here; M11 emits dict-only.

Scope is intentionally minimal per BUILD-PLAN §2.22(i): top-line
``total_score`` plus a derived ``severity_banner``; per-tier and
per-slack-state UID counts; and a flat list of per-UID rows. Detailed
column ordering, CSS classes, drill-down affordances, and AI-narrative
prompt templates are out of scope for this block and are fixed in M13.

Authority: BUILD-PLAN §2.22(i) (renderer signature, dict shape, row
columns, contract-sort preservation); §2.22(e) (per-UID weights and
[0, 100] aggregate clamp); ``acumen-reference §3.3`` / ``§3.6``
(indicator-not-verdict, weighting at scorecard assembly).
"""

from __future__ import annotations

from typing import Any

from app.contracts.manipulation_scoring import ManipulationScoringSummary

_BANNER_LOW_THRESHOLD = 25
_BANNER_MODERATE_THRESHOLD = 50
_BANNER_HIGH_THRESHOLD = 75


def _severity_banner(total_score: int) -> str:
    """Banner string for the top-line ``total_score``.

    Maps the [0, 100] clamped aggregate domain (BUILD-PLAN §2.22(e))
    onto five qualitative bands suitable for top-line display.

    Authority: BUILD-PLAN §2.22(i) (renderer scope mandates a "severity
    banner" alongside ``total_score`` but does not specify thresholds).
    Threshold table is a build-chat amendment to §2.22(i).
    ``forensic-manipulation-patterns §10`` confirms the aggregation
    rule is qualitative-only ("protocol-level, not quantitative");
    ``acumen-reference §3.3`` supplies the indicator-not-verdict
    posture under which any banding is a display convention rather
    than a verdict. Banding choice projects the §2.22(e) clamp
    domain onto a five-band Acumen-Fuse-style scorecard banner.

    Bands (left-closed, right-open except the top band):

    * ``"clean"``    — ``total_score == 0``
    * ``"low"``      — ``0 < total_score < 25``
    * ``"moderate"`` — ``25 <= total_score < 50``
    * ``"high"``     — ``50 <= total_score < 75``
    * ``"critical"`` — ``75 <= total_score <= 100``
    """
    if total_score == 0:
        return "clean"
    if total_score < _BANNER_LOW_THRESHOLD:
        return "low"
    if total_score < _BANNER_MODERATE_THRESHOLD:
        return "moderate"
    if total_score < _BANNER_HIGH_THRESHOLD:
        return "high"
    return "critical"


def render_manipulation_scoring_summary(
    summary: ManipulationScoringSummary,
) -> dict[str, Any]:
    """Project a :class:`ManipulationScoringSummary` into a Jinja2-ready dict.

    Pure helper. Deterministic: same input always yields the same dict
    structure. Empty-safe: an all-zero summary with no per-UID records
    produces a dict with every required key present, ``rows == []``,
    and ``severity_banner == "clean"``.

    StrEnum convention: ``severity_tier`` and ``slack_state`` are
    rendered as their ``.value`` strings (lowercase identity, e.g.
    ``"high"``, ``"joined_primary"``). The rendered dict carries no
    Pydantic models, no enum objects, and no datetimes — only str /
    int / list / dict primitives.

    Sort order: ``rows`` preserves ``summary.per_uid_results`` order
    verbatim. The contract docstring on
    :class:`ManipulationScoringSummary` specifies that
    ``per_uid_results`` is sorted by ``(severity_tier desc, unique_id
    asc)``; this renderer relies on that contract guarantee and does
    NOT re-sort. Re-sorting would mask any future contract-violation
    upstream.

    Args:
        summary: A frozen :class:`ManipulationScoringSummary` from the
            M11 scoring engine.

    Returns:
        A ``dict`` with the following keys (every key always present,
        regardless of summary content):

        * ``total_score`` (``int``) — ``summary.total_score``, clamped
          to [0, 100] by §2.22(e).
        * ``severity_banner`` (``str``) — one of ``"clean"``,
          ``"low"``, ``"moderate"``, ``"high"``, ``"critical"``.
        * ``uid_counts_by_severity`` (``dict[str, int]``) — keys
          ``"high"``, ``"medium"``, ``"low"``; values are
          ``summary.uid_count_high`` / ``_medium`` / ``_low``.
        * ``uid_counts_by_slack_state`` (``dict[str, int]``) — keys
          ``"joined_primary"``, ``"eroding_toward_primary"``,
          ``"stable"``, ``"recovering"``; values are the matching
          ``summary.uid_count_*`` integers.
        * ``rows`` (``list[dict[str, Any]]``) — one entry per
          :class:`ManipulationScoringResult` in
          ``summary.per_uid_results``, in contract-sorted order. Each
          row carries ``unique_id`` (``int``), ``name`` (``str``),
          ``score`` (``int``), ``severity_tier`` (``str``),
          ``slack_state`` (``str``), and ``rationale`` (``str``).

    Example:
        >>> from app.contracts.manipulation_scoring import (
        ...     ManipulationScoringResult,
        ...     ManipulationScoringSummary,
        ...     SeverityTier,
        ...     SlackState,
        ... )
        >>> result = ManipulationScoringResult(
        ...     unique_id=42,
        ...     name="Foundation pour",
        ...     score=10,
        ...     severity_tier=SeverityTier.HIGH,
        ...     slack_state=SlackState.JOINED_PRIMARY,
        ...     rationale="MSO predecessor newly bound primary",
        ... )
        >>> summary = ManipulationScoringSummary(
        ...     total_score=10,
        ...     uid_count_high=1,
        ...     uid_count_medium=0,
        ...     uid_count_low=0,
        ...     uid_count_joined_primary=1,
        ...     uid_count_eroding_toward_primary=0,
        ...     uid_count_stable=0,
        ...     uid_count_recovering=0,
        ...     per_uid_results=(result,),
        ... )
        >>> rendered = render_manipulation_scoring_summary(summary)
        >>> rendered["total_score"]
        10
        >>> rendered["severity_banner"]
        'low'
        >>> rendered["rows"][0]["severity_tier"]
        'high'
    """
    rows: list[dict[str, Any]] = [
        {
            "unique_id": result.unique_id,
            "name": result.name,
            "score": result.score,
            "severity_tier": result.severity_tier.value,
            "slack_state": result.slack_state.value,
            "rationale": result.rationale,
        }
        for result in summary.per_uid_results
    ]
    return {
        "total_score": summary.total_score,
        "severity_banner": _severity_banner(summary.total_score),
        "uid_counts_by_severity": {
            "high": summary.uid_count_high,
            "medium": summary.uid_count_medium,
            "low": summary.uid_count_low,
        },
        "uid_counts_by_slack_state": {
            "joined_primary": summary.uid_count_joined_primary,
            "eroding_toward_primary": summary.uid_count_eroding_toward_primary,
            "stable": summary.uid_count_stable,
            "recovering": summary.uid_count_recovering,
        },
        "rows": rows,
    }


__all__ = ["render_manipulation_scoring_summary"]
