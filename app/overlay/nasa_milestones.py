"""NASA governance-milestone name patterns (Milestone 8 Block 2).

Externalized per BUILD-PLAN §5 M8 AC #4: analysts edit this module
to add or tune patterns without touching overlay logic or metric
code. The patterns are compiled once at import time and reused by
the governance-milestone triage rule in
:mod:`app.overlay.nasa_overlay`.

Taxonomy source. NASA governance milestones that legitimately drive
Must-Start-On / Must-Finish-On / Start-No-Later-Than /
Finish-No-Later-Than constraints per
``nasa-program-project-governance §§4, 5`` (KDPs, LCRs, SRB scope):

* KDP — Key Decision Point. Programs use Roman-numeral KDP-0 / I /
  II / III / IV / V / VI / VII; projects and single-project programs
  use letter KDP-A through KDP-F (``[NID] §2.2.7 p.26``;
  ``nasa-program-project-governance §4``).
* MCR — Mission Concept Review.
* SRR — System Requirements Review.
* MDR / SDR — Mission / System Definition Review.
* PDR — Preliminary Design Review.
* CDR — Critical Design Review.
* SIR — System Integration Review.
* ORR — Operational Readiness Review.
* FRR / MRR — Flight / Mission Readiness Review.

The patterns match case-insensitively against the task name and are
word-boundary anchored so ``"CDR Review"`` matches and ``"CDRCodec"``
does not. ``"PDR"`` matches, ``"Pre-PDR Trade Study"`` matches
(``"PDR"`` is a standalone word between the hyphen and space),
``"PDR5"`` does not.

Consumer. :mod:`app.overlay.nasa_overlay` imports
:data:`GOVERNANCE_PATTERNS` and calls
:func:`match_governance_pattern` for every task flagged in DCMA
Metric 5's offender list. A match emits an
:class:`~app.overlay.nasa_overlay.OverlayNote` with kind
``GOVERNANCE_MILESTONE_TRIAGE``; M11 reads the note and suppresses
the constraint-injection raise for that task.
"""

from __future__ import annotations

import re

_GOVERNANCE_ACRONYMS: tuple[str, ...] = (
    # KDP matches both the plain token and the letter / Roman-numeral
    # variants (KDP-A through KDP-F for projects; KDP 0 / I / II / III /
    # IV / V / VI / VII for programs). The pattern below covers the
    # bare acronym plus the hyphenated / spaced variants in one regex
    # per NID-approved naming.
    r"KDP(?:[-\s]*(?:[A-F]|0|I|II|III|IV|V|VI|VII))?",
    r"MCR",
    r"SRR",
    r"MDR",
    r"SDR",
    r"PDR",
    r"CDR",
    r"SIR",
    r"ORR",
    r"FRR",
    r"MRR",
)


def _compile(acronym: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9])(?:{acronym})(?![A-Za-z0-9])",
                      re.IGNORECASE)


GOVERNANCE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    _compile(a) for a in _GOVERNANCE_ACRONYMS
)
"""Compiled governance-milestone name patterns, case-insensitive and
word-boundary anchored (``(?<![A-Za-z0-9])`` / ``(?![A-Za-z0-9])``).

Matching against a task name returns an :class:`re.Match` object on
hit, ``None`` on miss. Use :func:`is_governance_milestone` or
:func:`match_governance_pattern` at call sites rather than iterating
this tuple directly."""


def is_governance_milestone(task_name: str) -> bool:
    """Return ``True`` iff ``task_name`` contains any governance-
    milestone acronym as a whole word.

    Empty strings and strings containing only substring matches (e.g.
    ``"CDRCodec"``) return ``False``.
    """
    if not task_name:
        return False
    return any(p.search(task_name) for p in GOVERNANCE_PATTERNS)


def match_governance_pattern(task_name: str) -> str | None:
    """Return the first matched acronym string (upper-cased), or
    ``None`` when no governance-milestone pattern matches.

    When multiple patterns match the same task name, the first in
    :data:`GOVERNANCE_PATTERNS` wins. Callers that need the literal
    matched substring from the task name should use
    :data:`GOVERNANCE_PATTERNS` directly.
    """
    if not task_name:
        return None
    for p in GOVERNANCE_PATTERNS:
        m = p.search(task_name)
        if m:
            # Return the acronym label (normalized upper-case) rather
            # than the raw matched substring so downstream consumers
            # can route on a stable token (e.g. "PDR" rather than
            # "pdr" or "Pdr").
            return m.group(0).upper()
    return None
