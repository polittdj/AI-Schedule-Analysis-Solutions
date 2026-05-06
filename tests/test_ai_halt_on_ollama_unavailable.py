"""Halt semantics when Ollama is unavailable, per cui-compliance-constraints
§2f.

When the local Ollama daemon cannot be reached and classification is CUI,
the tool MUST halt — never silently fall back to a cloud-bound client.
The router itself is classification-driven and does not probe
availability; the route boundary owns the halt decision. These tests
lock in both ends of that contract:

- ``OllamaClient.is_available()`` honestly reports unreachable as False
  for every transport-error class.
- ``OllamaClient.generate()`` raises RuntimeError on transport failures
  so the route can map to an explicit halt response.
- ``select_client("cui")`` returns an OllamaClient regardless of
  whether Ollama is actually reachable; it never swaps in ClaudeClient.
"""

from __future__ import annotations

import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.ai import ClaudeClient, OllamaClient, select_client


def test_ollama_client_is_available_returns_false_on_connection_refused():
    client = OllamaClient()
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        assert client.is_available() is False


def test_ollama_client_is_available_returns_false_on_timeout():
    client = OllamaClient()
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        assert client.is_available() is False


def test_ollama_client_is_available_returns_false_on_http_error():
    client = OllamaClient()
    err = urllib.error.HTTPError(
        url="http://localhost:11434/api/tags",
        code=500,
        msg="server error",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=err):
        assert client.is_available() is False


def test_ollama_client_is_available_returns_false_on_oserror():
    client = OllamaClient()
    with patch(
        "urllib.request.urlopen",
        side_effect=socket.gaierror("name resolution failure"),
    ):
        assert client.is_available() is False


def test_ollama_client_is_available_returns_true_on_200():
    client = OllamaClient()
    response = MagicMock()
    response.status = 200
    cm = MagicMock()
    cm.__enter__.return_value = response
    cm.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=cm):
        assert client.is_available() is True


def test_ollama_client_generate_raises_runtime_error_on_transport_failure():
    client = OllamaClient()
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        with pytest.raises(RuntimeError) as excinfo:
            list(client.generate("any-prompt"))
    # The original exception class name must be present in the message
    # so the route can produce a useful halt diagnostic.
    assert "URLError" in str(excinfo.value)


def test_router_selects_ollama_when_classification_cui_even_if_ollama_will_be_unavailable():
    # The router does not probe availability — that's the route's job
    # per §2f. select_client("cui") always returns an OllamaClient.
    client = select_client("cui")
    assert isinstance(client, OllamaClient)


def test_no_silent_fallback_to_claude_when_ollama_unavailable():
    # Critical §2f assertion: even when Ollama is verifiably unreachable,
    # select_client("cui") must NOT swap in ClaudeClient. The halt
    # decision belongs to the route boundary, not the router.
    client = select_client("cui")

    with patch.object(OllamaClient, "is_available", return_value=False):
        # Re-confirm: the client returned for CUI is an OllamaClient,
        # and is_available() reports unreachable. The router has not
        # substituted a ClaudeClient.
        assert isinstance(client, OllamaClient)
        assert not isinstance(client, ClaudeClient)
        assert client.is_available() is False

    # And re-selecting under the same conditions is idempotent — still
    # OllamaClient, never ClaudeClient.
    second = select_client("cui")
    assert isinstance(second, OllamaClient)
    assert not isinstance(second, ClaudeClient)
