"""Validation harness — diff parser output against the MS Project UI.

Stub landed in the M3 cleanup session per BUILD-PLAN §5 M3 AC7. The
real harness runs only on a workstation with MS Project installed
and real `.mpp` files available; because `.mpp` files are CUI
(``cui-compliance-constraints §§2a, 2c``) the harness is explicitly
local-only and not exercised by CI.

Workflow (reproduced from
``.claude/skills/mpp-parsing-com-automation/SKILL.md §4``)
--------------------------------------------------------

1. Open the target ``.mpp`` file in the MS Project UI on the host
   running this harness.
2. Select 10+ representative tasks spanning summary, milestone,
   critical, LOE, constrained, non-zero ``TotalSlack``, baselined,
   and in-progress cases.
3. Hand-record every Appendix B field per task: ``UniqueID``, ``ID``,
   ``Name``, ``WBS``, ``OutlineLevel``, ``Start``, ``Finish``,
   ``BaselineStart``, ``BaselineFinish``, ``ActualStart``,
   ``ActualFinish``, ``EarlyStart``, ``EarlyFinish``, ``LateStart``,
   ``LateFinish``, ``Duration``, ``RemainingDuration``,
   ``ActualDuration``, ``BaselineDuration``, ``TotalSlack``,
   ``FreeSlack``, ``PercentComplete``, ``Critical``, ``Milestone``,
   ``Summary``, ``ConstraintType``, ``ConstraintDate``, ``Deadline``.
4. Run ``parse_mpp`` against the same file.
5. Diff parser output against the hand-recorded UI values. Any
   mismatch is a parser defect (skill §4 "a parser that runs
   without errors is not a parser that extracts correct values").
6. Also validate project-level fields: ``StatusDate``, ``Start``,
   ``Finish``, default calendar, ``LastSavedDate``.

Invocation
----------

Intended use is interactive on the ZBook::

    python scripts/validate_against_msp.py path\\to\\schedule.mpp

The implementation lands alongside the first real ``.mpp`` fixture
the operator clears for local use; until then the harness prints
the workflow pointer and exits 0 so the file-exists AC is
satisfied without executing COM.
"""

from __future__ import annotations

import sys


_WORKFLOW_POINTER = (
    "validate_against_msp.py is a stub; the real harness is not yet "
    "implemented. See .claude/skills/mpp-parsing-com-automation/"
    "SKILL.md §4 for the field-by-field comparison workflow."
)


def main(argv: list[str] | None = None) -> int:
    """Print the workflow pointer and exit cleanly.

    Returns ``0`` so that a CI step that naively invokes the script
    (there is none today, but the AC requires the file to exist)
    does not fail.
    """
    _ = argv  # argv accepted for interface compatibility; unused in stub
    print(_WORKFLOW_POINTER)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
