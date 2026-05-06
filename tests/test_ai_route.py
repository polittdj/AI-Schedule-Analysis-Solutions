"""Route-level tests for /classification, /ai-analyze, and the
cloud-active banner template (base.html).

Covers cui-compliance-constraints §2a, §2b, §2f, §2g via the Flask
boundary rather than the engine boundary. Every test that touches the
AI clients mocks transport (no real HTTP). The `monkeypatch` fixture
is used to flip ``Config.CUI_SAFE_MODE`` per-test.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.ai import ClaudeClient, OllamaClient
from app.config import Config
from app.routes.ai_analyze import OLLAMA_HALT_MESSAGE


@pytest.fixture(scope="module")
def ai_app() -> Flask:
    # Config.TESTING is set globally by tests/conftest.py so that
    # Config.resolve_secret_key returns an ephemeral key. CUI_SAFE_MODE
    # inherits the default True; tests that flip it use
    # monkeypatch.setattr against ``app.config.Config``.
    return create_app()


@pytest.fixture()
def ai_client(ai_app: Flask) -> Iterator[FlaskClient]:
    with ai_app.test_client() as test_client:
        yield test_client


# ---------------------------------------------------------------------
# /classification — toggle endpoint
# ---------------------------------------------------------------------


def test_classification_get_defaults_to_cui(ai_client: FlaskClient) -> None:
    response = ai_client.get("/classification")
    assert response.status_code == 200
    assert response.get_json() == {"classification": "cui"}


def test_classification_post_rejects_non_json(ai_client: FlaskClient) -> None:
    response = ai_client.post("/classification", data="hello")
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_body"


def test_classification_post_rejects_invalid_classification(ai_client: FlaskClient) -> None:
    response = ai_client.post("/classification", json={"classification": "secret"})
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_classification"


def test_classification_post_rejects_missing_classification_field(ai_client: FlaskClient) -> None:
    response = ai_client.post("/classification", json={})
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_classification"


def test_classification_post_to_cui_succeeds(ai_client: FlaskClient) -> None:
    response = ai_client.post("/classification", json={"classification": "cui"})
    assert response.status_code == 200
    assert response.get_json() == {"classification": "cui"}

    follow_up = ai_client.get("/classification")
    assert follow_up.get_json() == {"classification": "cui"}


def test_classification_post_to_unclassified_blocked_when_cui_safe_mode_active(
    ai_client: FlaskClient,
) -> None:
    assert Config.is_cui_safe_mode() is True
    response = ai_client.post("/classification", json={"classification": "unclassified"})
    assert response.status_code == 409
    body = response.get_json()
    assert body["error"] == "cui_safe_mode_active"


def test_classification_post_to_unclassified_succeeds_when_cui_safe_mode_off(
    ai_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.Config.CUI_SAFE_MODE", False)
    response = ai_client.post("/classification", json={"classification": "unclassified"})
    assert response.status_code == 200
    assert response.get_json() == {"classification": "unclassified"}

    follow_up = ai_client.get("/classification")
    assert follow_up.get_json() == {"classification": "unclassified"}


# ---------------------------------------------------------------------
# /ai-analyze — request validation
# ---------------------------------------------------------------------


def test_ai_analyze_rejects_non_json(ai_client: FlaskClient) -> None:
    response = ai_client.post("/ai-analyze", data="hello")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_body"


def test_ai_analyze_rejects_missing_metrics(ai_client: FlaskClient) -> None:
    response = ai_client.post("/ai-analyze", json={"sensitive_strings": ["x"]})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_metrics"


def test_ai_analyze_rejects_empty_metrics(ai_client: FlaskClient) -> None:
    response = ai_client.post(
        "/ai-analyze", json={"metrics": {}, "sensitive_strings": ["x"]}
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_metrics"


def test_ai_analyze_rejects_missing_sensitive_strings(ai_client: FlaskClient) -> None:
    response = ai_client.post("/ai-analyze", json={"metrics": {"k": "v"}})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_sensitive_strings"


def test_ai_analyze_rejects_empty_sensitive_strings(ai_client: FlaskClient) -> None:
    response = ai_client.post(
        "/ai-analyze", json={"metrics": {"k": "v"}, "sensitive_strings": []}
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_sensitive_strings"


def test_ai_analyze_rejects_non_string_sensitive_strings(ai_client: FlaskClient) -> None:
    response = ai_client.post(
        "/ai-analyze", json={"metrics": {"k": "v"}, "sensitive_strings": [1, 2]}
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_sensitive_strings"


# ---------------------------------------------------------------------
# /ai-analyze — Ollama halt path (§2f, AC#3)
# ---------------------------------------------------------------------


def test_ai_analyze_returns_503_when_ollama_unavailable_under_cui(
    ai_client: FlaskClient,
) -> None:
    with patch.object(OllamaClient, "is_available", return_value=False):
        response = ai_client.post(
            "/ai-analyze",
            json={"metrics": {"BEI": 0.95}, "sensitive_strings": ["MyTask"]},
        )
    assert response.status_code == 503
    assert response.data.decode() == OLLAMA_HALT_MESSAGE
    assert response.headers["Content-Type"].startswith("text/plain")


def test_ai_analyze_does_NOT_swap_to_claude_when_ollama_unavailable_under_cui(
    ai_client: FlaskClient,
) -> None:
    """Critical §2f assertion: even if a buggy caller has flipped
    ClaudeClient at the import surface, the route must NOT route to
    Claude when Ollama is unavailable under CUI. The 503 halt is the
    no-silent-fallback gate at the route level."""
    with patch.object(OllamaClient, "is_available", return_value=False):
        response = ai_client.post(
            "/ai-analyze",
            json={"metrics": {"BEI": 0.95}, "sensitive_strings": ["MyTask"]},
        )
    assert response.status_code == 503
    assert response.status_code != 200
    body_text = response.data.decode()
    assert "narrative" not in body_text
    assert body_text == OLLAMA_HALT_MESSAGE


def test_ai_analyze_returns_503_on_ollama_transport_failure_after_is_available_passed(
    ai_client: FlaskClient,
) -> None:
    def _raise(self: OllamaClient, prompt: str) -> Iterator[str]:
        raise RuntimeError("Ollama transport error: URLError")
        yield  # pragma: no cover

    with (
        patch.object(OllamaClient, "is_available", return_value=True),
        patch.object(OllamaClient, "generate", _raise),
    ):
        response = ai_client.post(
            "/ai-analyze",
            json={"metrics": {"BEI": 0.95}, "sensitive_strings": ["MyTask"]},
        )
    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "ollama_transport_failure"


# ---------------------------------------------------------------------
# /ai-analyze — happy paths
# ---------------------------------------------------------------------


def test_ai_analyze_returns_200_with_narrative_under_ollama_when_available(
    ai_client: FlaskClient,
) -> None:
    def _stream(self: OllamaClient, prompt: str) -> Iterator[str]:
        yield from ["the ", "<TASK_1>", " is critical"]

    with (
        patch.object(OllamaClient, "is_available", return_value=True),
        patch.object(OllamaClient, "generate", _stream),
    ):
        response = ai_client.post(
            "/ai-analyze",
            json={"metrics": {"BEI": 0.95}, "sensitive_strings": ["MyTask"]},
        )
    assert response.status_code == 200
    body = response.get_json()
    assert body["narrative"] == "the MyTask is critical"
    assert body["backend"] == "ollama"
    assert body["classification"] == "cui"
    assert "banner" not in body


def test_ai_analyze_returns_banner_when_classification_unclassified(
    ai_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.Config.CUI_SAFE_MODE", False)

    with ai_client.session_transaction() as sess:
        sess["classification"] = "unclassified"

    def _stream(self: ClaudeClient, prompt: str) -> Iterator[str]:
        yield from ["narrative content"]

    with patch.object(ClaudeClient, "generate", _stream):
        response = ai_client.post(
            "/ai-analyze",
            json={"metrics": {"BEI": 0.95}, "sensitive_strings": ["MyTask"]},
        )
    assert response.status_code == 200
    body = response.get_json()
    assert body["backend"] == "claude"
    assert body["classification"] == "unclassified"
    assert body["banner"]["model"] == "claude-sonnet-4-6"
    assert body["banner"]["endpoint"] == "https://api.anthropic.com/v1/messages"


def test_ai_analyze_desanitizes_output_before_returning(ai_client: FlaskClient) -> None:
    """Round-trip: Ollama yields chunks containing opaque labels, the
    route must restore the originals via ``desanitize_text`` before
    returning."""

    def _stream(self: OllamaClient, prompt: str) -> Iterator[str]:
        yield from ["The ", "<TASK_1>", " precedes ", "<TASK_2>", "."]

    with (
        patch.object(OllamaClient, "is_available", return_value=True),
        patch.object(OllamaClient, "generate", _stream),
    ):
        response = ai_client.post(
            "/ai-analyze",
            json={
                "metrics": {"BEI": 0.95},
                "sensitive_strings": ["Foundation Pour", "Backfill"],
            },
        )
    assert response.status_code == 200
    body = response.get_json()
    assert "Foundation Pour" in body["narrative"]
    assert "Backfill" in body["narrative"]
    assert "<TASK_1>" not in body["narrative"]
    assert "<TASK_2>" not in body["narrative"]


# ---------------------------------------------------------------------
# base.html — banner template tests (§2g)
# ---------------------------------------------------------------------


def test_base_template_renders_banner_when_classification_unclassified(
    ai_app: Flask,
) -> None:
    template = ai_app.jinja_env.get_template("base.html")
    output = template.render(
        classification="unclassified",
        cloud_model="claude-sonnet-4-6",
        cloud_endpoint="https://api.anthropic.com/v1/messages",
    )
    assert "CLOUD AI ACTIVE" in output
    assert "claude-sonnet-4-6" in output
    assert "cloud-active-banner" in output
    assert "https://api.anthropic.com/v1/messages" in output


def test_base_template_omits_banner_when_classification_cui(ai_app: Flask) -> None:
    template = ai_app.jinja_env.get_template("base.html")
    output = template.render(classification="cui")
    assert "cloud-active-banner" not in output
    assert "CLOUD AI ACTIVE" not in output


def test_base_template_omits_banner_when_classification_empty(ai_app: Flask) -> None:
    template = ai_app.jinja_env.get_template("base.html")
    output = template.render(classification="")
    assert "cloud-active-banner" not in output
    assert "CLOUD AI ACTIVE" not in output
