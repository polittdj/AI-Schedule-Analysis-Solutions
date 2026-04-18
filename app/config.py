"""Configuration constants for the Schedule Forensics Flask app.

The 500 MB upload limit is locked per BUILD-PLAN.md §2.11 and
Milestone 1 Acceptance Criterion 3. Changing ``UPLOAD_LIMIT_BYTES``
requires a locked-architectural-decision override.
"""

from __future__ import annotations

UPLOAD_LIMIT_BYTES: int = 500 * 1024 * 1024


class Config:
    """Default Flask configuration."""

    MAX_CONTENT_LENGTH: int = UPLOAD_LIMIT_BYTES
    TESTING: bool = False
