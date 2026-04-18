"""Flask error handlers.

The 413 handler for RequestEntityTooLarge returns a structured JSON
body per BUILD-PLAN.md M1 AC3. The generic 500 handler hides
exception detail to satisfy cui-compliance-constraints §2d (no
schedule content or unredacted traceback to stdout / response body).
"""

from __future__ import annotations

from flask import Flask, jsonify
from flask.wrappers import Response
from werkzeug.exceptions import RequestEntityTooLarge

from app.config import UPLOAD_LIMIT_BYTES

UPLOAD_LIMIT_MB: int = UPLOAD_LIMIT_BYTES // (1024 * 1024)


def register_error_handlers(app: Flask) -> None:
    """Attach the 413 and generic 500 handlers to ``app``."""

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_exc: RequestEntityTooLarge) -> tuple[Response, int]:
        return (
            jsonify(
                {
                    "error": "upload_too_large",
                    "message": f"File exceeds {UPLOAD_LIMIT_MB} MB limit.",
                    "limit_bytes": UPLOAD_LIMIT_BYTES,
                }
            ),
            413,
        )

    @app.errorhandler(500)
    def _internal(_exc: Exception) -> tuple[Response, int]:
        return (
            jsonify({"error": "internal_error", "message": "Internal server error."}),
            500,
        )
