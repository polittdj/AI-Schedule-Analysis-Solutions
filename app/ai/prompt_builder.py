"""Build narrative prompts from pre-computed AnalysisResult payloads.

Per cui-compliance-constraints §2a, the AI layer consumes only
pre-computed metrics — never raw ScheduleData. This module accepts a
mapping of metric labels to values and produces a sanitized prompt
string suitable for handing to AIClient.generate(). All task-name-like
strings are routed through DataSanitizer before they appear in the
returned prompt.
"""

from __future__ import annotations

from typing import Any

from app.ai.sanitizer import DataSanitizer

_PROMPT_HEADER = (
    "You are a senior NASA forensic schedule analyst. Below is a set of "
    "pre-computed schedule metrics for a single analysis run. Write a "
    "concise executive narrative (3-5 paragraphs) describing what the "
    "metrics show, why it matters, and what the analyst should "
    "investigate next. Use only the values provided; do not speculate "
    "beyond them.\n\n"
    "Metrics:\n"
)


def build_prompt(
    metrics: dict[str, Any],
    sensitive_strings: list[str],
    sanitizer: DataSanitizer,
) -> str:
    """Construct a sanitized narrative prompt.

    ``metrics`` is a flat dict of metric-name -> value pairs (already
    aggregated from AnalysisResult). ``sensitive_strings`` is the list
    of original strings (task names, WBS labels, resource names) that
    appear anywhere in ``metrics``. ``sanitizer`` is built from those
    strings before this function is called.

    The returned prompt contains only opaque labels in place of any
    sensitive_strings value — even if metrics values contain those
    strings verbatim. Acceptance criterion #5: DataSanitizer replaces
    task names with labels before the prompt reaches any client.
    """
    if not sensitive_strings:
        raise ValueError("sensitive_strings must be non-empty")
    body_lines = []
    for key, value in metrics.items():
        body_lines.append(f"- {key}: {value}")
    body = "\n".join(body_lines)
    raw_prompt = _PROMPT_HEADER + body
    return sanitizer.sanitize(raw_prompt)
