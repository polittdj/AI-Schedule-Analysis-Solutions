"""Tests for the NASA governance-milestone taxonomy (Milestone 8
Block 2).

Covers :data:`app.overlay.nasa_milestones.GOVERNANCE_PATTERNS` and
the :func:`is_governance_milestone` / :func:`match_governance_pattern`
matchers. The patterns are externalized so analysts can edit the
taxonomy without touching overlay logic (BUILD-PLAN §5 M8 AC #4);
these tests verify the match surface covers every governance
acronym named in the milestone and that substring false positives
do not match.
"""

from __future__ import annotations

import pytest

from app.overlay.nasa_milestones import (
    GOVERNANCE_PATTERNS,
    is_governance_milestone,
    match_governance_pattern,
)

# ----- positive matches ------------------------------------------


@pytest.mark.parametrize(
    ("task_name", "expected_acronym"),
    [
        ("CDR Review", "CDR"),
        ("Preliminary Design Review (PDR)", "PDR"),
        ("System Requirements Review (SRR)", "SRR"),
        ("Mission Concept Review - MCR", "MCR"),
        ("MDR milestone", "MDR"),
        ("SDR Review", "SDR"),
        ("SIR gate", "SIR"),
        ("Operational Readiness Review (ORR)", "ORR"),
        ("FRR: Flight Readiness Review", "FRR"),
        ("MRR Mission Readiness", "MRR"),
        # KDP variants (letter)
        ("KDP-A milestone", "KDP-A"),
        ("KDP-B approval", "KDP-B"),
        ("KDP-C at PDR", "KDP-C"),
        ("KDP C spaced", "KDP C"),
        ("KDP D confirmation", "KDP D"),
        # KDP variants (Roman numeral)
        ("KDP-I program transition", "KDP-I"),
        ("KDP II checkpoint", "KDP II"),
        ("KDP-VII finish", "KDP-VII"),
        # Bare KDP (no suffix)
        ("Prep for KDP Review", "KDP"),
    ],
)
def test_match_governance_pattern_positive(
    task_name: str, expected_acronym: str
) -> None:
    result = match_governance_pattern(task_name)
    assert result is not None
    # match_governance_pattern returns upper-cased text; compare
    # case-insensitively against the expected acronym but also check
    # the upper-casing invariant.
    assert result.upper() == expected_acronym.upper()
    assert is_governance_milestone(task_name) is True


# ----- case-insensitivity -----------------------------------------


@pytest.mark.parametrize(
    "task_name",
    ["cdr review", "Cdr Review", "CDR REVIEW", "cDr"],
)
def test_case_insensitive_match(task_name: str) -> None:
    assert is_governance_milestone(task_name) is True
    result = match_governance_pattern(task_name)
    assert result == "CDR"  # normalized upper-case


# ----- substring false positives do NOT match ---------------------


@pytest.mark.parametrize(
    "task_name",
    [
        "CDRCodec verification",   # CDR followed by alphanum — no match
        "PDRA analysis",           # PDR followed by alphanum — no match
        "ORRA parameter sweep",    # ORR followed by alphanum — no match
        "SRRS drop",               # SRR followed by alphanum — no match
        "aMCRb",                   # MCR embedded in a token
        "FirMRR",                  # MRR as a suffix of a longer token
        "SIR5 component",          # SIR followed by digit
        "MDRx",                    # MDR followed by alphanum
    ],
)
def test_substring_false_positives_do_not_match(task_name: str) -> None:
    assert is_governance_milestone(task_name) is False
    assert match_governance_pattern(task_name) is None


# ----- empty and None-ish inputs ----------------------------------


def test_empty_string_returns_none() -> None:
    assert match_governance_pattern("") is None
    assert is_governance_milestone("") is False


# ----- punctuation boundaries ------------------------------------


@pytest.mark.parametrize(
    "task_name",
    [
        "CDR.",
        "(PDR)",
        "[ORR]",
        "-SIR-",
        "/MCR/",
        "CDR,milestone",
    ],
)
def test_punctuation_boundaries_match(task_name: str) -> None:
    # Non-alphanumeric punctuation counts as a word boundary under
    # the taxonomy's regex — verified here so a stray punctuation
    # variant from a real IMS does not silently fail to match.
    assert is_governance_milestone(task_name) is True


# ----- taxonomy coverage ------------------------------------------


def test_every_acronym_has_a_compiled_pattern() -> None:
    # Sanity: GOVERNANCE_PATTERNS is populated (no empty taxonomy).
    # The exact length depends on the acronym list; the guarantee
    # here is that every acronym named in the M8 scope is reachable.
    named = {"KDP", "MCR", "SRR", "MDR", "SDR", "PDR", "CDR",
             "SIR", "ORR", "FRR", "MRR"}
    for acronym in named:
        assert is_governance_milestone(f"{acronym} Review"), acronym
    assert len(GOVERNANCE_PATTERNS) >= len(named)


def test_first_match_wins_when_multiple_acronyms_in_name() -> None:
    # "KDP-C at PDR" contains both KDP (with suffix) and PDR. The
    # first pattern to match in GOVERNANCE_PATTERNS wins per the
    # module docstring; KDP is listed first, so we expect the KDP
    # variant.
    result = match_governance_pattern("KDP-C at PDR")
    assert result is not None
    assert "KDP" in result
