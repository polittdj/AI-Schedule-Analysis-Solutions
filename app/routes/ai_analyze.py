"""POST /ai-analyze — generate AI narrative from pre-computed metrics.

Per cui-compliance-constraints:
- §2a: route consumes pre-computed metrics + sensitive_strings; never raw ScheduleData.
- §2b/§2f: routing through ``app.ai.router.select_client``; cloud opt-in only.
- §2f: when classification is CUI and Ollama is unreachable, returns
  HTTP 503 with the literal halt message — no silent fallback.
- §2g: when classification is "unclassified", the response payload includes
  banner metadata so the frontend can render the persistent cloud-active banner.

Request body (application/json):

    {
        "metrics": {<metric-name>: <value>, ...},
        "sensitive_strings": ["<original-string>", ...]
    }

Response (application/json) on success (200):

    {
        "narrative": "<desanitized text>",
        "backend": "ollama" | "claude",
        "classification": "cui" | "unclassified",
        "banner": {  # present only when classification == "unclassified"
            "model": "<model-id>",
            "endpoint": "<api-endpoint>"
        }
    }

Halt response (503), per §2f, when Ollama is unavailable and classification is CUI:

    body: "Ollama unavailable — no cloud fallback permitted for CUI projects."
    Content-Type: text/plain
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session
from flask.wrappers import Response

from app.ai import (
    CLAUDE_API_ENDPOINT,
    CLAUDE_MODEL_ID,
    ClaudeClient,
    CuiViolationError,
    DataSanitizer,
    OllamaClient,
    build_prompt,
    desanitize_text,
    select_client,
)

ai_analyze_bp = Blueprint("ai_analyze", __name__)

OLLAMA_HALT_MESSAGE = "Ollama unavailable — no cloud fallback permitted for CUI projects."


@ai_analyze_bp.post("/ai-analyze")
def ai_analyze() -> tuple[Response, int] | tuple[str, int, dict[str, str]]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid_body", "message": "JSON object required."}), 400

    metrics = body.get("metrics")
    sensitive_strings = body.get("sensitive_strings")
    if not isinstance(metrics, dict) or not metrics:
        return (
            jsonify({"error": "invalid_metrics", "message": "metrics must be a non-empty object."}),
            400,
        )
    if not isinstance(sensitive_strings, list) or not sensitive_strings:
        return (
            jsonify(
                {
                    "error": "invalid_sensitive_strings",
                    "message": "sensitive_strings must be a non-empty list of strings.",
                }
            ),
            400,
        )
    if not all(isinstance(s, str) and s for s in sensitive_strings):
        return (
            jsonify(
                {
                    "error": "invalid_sensitive_strings",
                    "message": "sensitive_strings must contain non-empty strings.",
                }
            ),
            400,
        )

    classification = session.get("classification", "cui")

    try:
        client = select_client(classification)
    except CuiViolationError as exc:
        return jsonify({"error": "cui_violation", "message": str(exc)}), 409

    # §2f: halt path. Only fires for the local backend; cloud client's
    # is_available() is True by construction, and a non-CUI session has
    # already opted into cloud routing.
    if isinstance(client, OllamaClient) and not client.is_available():
        return OLLAMA_HALT_MESSAGE, 503, {"Content-Type": "text/plain; charset=utf-8"}

    sanitizer = DataSanitizer()
    sanitizer.build(sensitive_strings)
    prompt = build_prompt(
        metrics=metrics,
        sensitive_strings=sensitive_strings,
        sanitizer=sanitizer,
    )

    try:
        chunks = list(client.generate(prompt))
    except RuntimeError as exc:
        # Ollama raised mid-stream after passing is_available(). Per §2f
        # this is still a halt; the route surfaces it as 503 so the UI
        # cannot offer a "try the other backend" affordance.
        return (
            jsonify({"error": "ollama_transport_failure", "message": str(exc)}),
            503,
        )

    sanitized_narrative = "".join(chunks)
    narrative = desanitize_text(sanitized_narrative, sanitizer)

    backend = "claude" if isinstance(client, ClaudeClient) else "ollama"
    payload: dict[str, object] = {
        "narrative": narrative,
        "backend": backend,
        "classification": classification,
    }
    if classification == "unclassified":
        payload["banner"] = {
            "model": CLAUDE_MODEL_ID,
            "endpoint": CLAUDE_API_ENDPOINT,
        }

    return jsonify(payload), 200
