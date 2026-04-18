"""Health-check blueprint. The /health endpoint is the CI smoke target."""

from __future__ import annotations

from flask import Blueprint, jsonify
from flask.wrappers import Response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> Response:
    return jsonify({"status": "ok"})
