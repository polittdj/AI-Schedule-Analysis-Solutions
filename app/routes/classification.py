"""Per-session classification toggle endpoint.

Per cui-compliance-constraints §2b, the analyst must explicitly toggle
classification before any cloud-bound AI client can be constructed.
This endpoint is the single place that mutates session classification;
all other code reads it via ``flask.session.get("classification")``
with a default of "cui".

Accepts JSON ``{"classification": "cui" | "unclassified"}``. Returns
the current classification on success. Per §2b, switching to
``"unclassified"`` is rejected with HTTP 409 if
``Config.is_cui_safe_mode()`` is True — the operator must flip the
config flag before sessions can opt into cloud routing.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session
from flask.wrappers import Response

from app.config import Config

classification_bp = Blueprint("classification", __name__)

ALLOWED_CLASSIFICATIONS = frozenset({"cui", "unclassified"})


@classification_bp.post("/classification")
def set_classification() -> tuple[Response, int]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid_body", "message": "JSON object required."}), 400
    value = body.get("classification")
    if value not in ALLOWED_CLASSIFICATIONS:
        return (
            jsonify(
                {
                    "error": "invalid_classification",
                    "message": f"classification must be one of {sorted(ALLOWED_CLASSIFICATIONS)}.",
                }
            ),
            400,
        )
    if value == "unclassified" and Config.is_cui_safe_mode():
        return (
            jsonify(
                {
                    "error": "cui_safe_mode_active",
                    "message": (
                        "Cannot set classification to 'unclassified' while "
                        "Config.is_cui_safe_mode() is True. Per "
                        "cui-compliance-constraints §2b, the operator must "
                        "flip the config flag before any session can opt "
                        "into cloud routing."
                    ),
                }
            ),
            409,
        )
    session["classification"] = value
    return jsonify({"classification": value}), 200


@classification_bp.get("/classification")
def get_classification() -> tuple[Response, int]:
    return jsonify({"classification": session.get("classification", "cui")}), 200
