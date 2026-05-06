"""Configuration constants for the Schedule Forensics Flask app.

The 500 MB upload limit is locked per BUILD-PLAN.md §2.11 and
Milestone 1 Acceptance Criterion 3. Changing ``UPLOAD_LIMIT_BYTES``
requires a locked-architectural-decision override.
"""

from __future__ import annotations

import os
import secrets

UPLOAD_LIMIT_BYTES: int = 500 * 1024 * 1024


class Config:
    """Default Flask configuration."""

    MAX_CONTENT_LENGTH: int = UPLOAD_LIMIT_BYTES
    TESTING: bool = False

    # Per cui-compliance-constraints §2b, the tool defaults to CUI-safe
    # mode (Ollama-only, no cloud egress). The Flask app sets this to
    # False per-session only when the analyst manually toggles
    # classification to "unclassified" via the web UI. Tests override
    # this class attribute directly to exercise both modes.
    CUI_SAFE_MODE: bool = True

    @classmethod
    def is_cui_safe_mode(cls) -> bool:
        """Return True iff CUI-safe mode is active. Per §2b/§2f, the
        router uses this to gate construction of cloud-bound clients."""
        return cls.CUI_SAFE_MODE

    @classmethod
    def resolve_secret_key(cls) -> str:
        """Resolve the Flask SECRET_KEY for this app.

        Resolution order:
        1. ``FLASK_SECRET_KEY`` environment variable, if set and non-empty.
        2. If ``cls.TESTING`` is True, an ephemeral ``secrets.token_hex(32)``
           generated per-app. Tests should not depend on session
           persistence across app instances.
        3. Otherwise (production / non-TESTING), raise RuntimeError. The
           operator must set FLASK_SECRET_KEY explicitly so sessions
           persist deterministically across restarts.
        """
        env_value = os.environ.get("FLASK_SECRET_KEY", "").strip()
        if env_value:
            return env_value
        if cls.TESTING:
            return secrets.token_hex(32)
        raise RuntimeError(
            "FLASK_SECRET_KEY is not set. Set the environment variable "
            "before invoking create_app() in production. Tests bypass "
            "this requirement by setting Config.TESTING = True."
        )
