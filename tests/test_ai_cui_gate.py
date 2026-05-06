"""Primary regression gate for the M12 CUI classification gate.

Per cui-compliance-constraints §2b/§2f, the Anthropic Claude API may
only be reached when classification is explicitly 'unclassified' AND
``Config.is_cui_safe_mode()`` returns False. These tests must fail
against any code path that constructs ``ClaudeClient`` while CUI-safe
mode is active.

No HTTP traffic. The anthropic SDK is not exercised; the gate fires
before any lazy import.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from app.ai import ClaudeClient, CuiViolationError, OllamaClient, select_client
from app.config import Config


def test_select_client_returns_ollama_when_classification_is_cui():
    client = select_client("cui")
    assert isinstance(client, OllamaClient)
    assert not isinstance(client, ClaudeClient)


def test_select_client_returns_ollama_when_classification_is_empty_string():
    client = select_client("")
    assert isinstance(client, OllamaClient)
    assert not isinstance(client, ClaudeClient)


def test_select_client_returns_ollama_when_classification_is_unrecognized():
    client = select_client("secret")
    assert isinstance(client, OllamaClient)
    assert not isinstance(client, ClaudeClient)


def test_select_client_raises_cui_violation_when_classification_unclassified_and_safe_mode_active():
    assert Config.is_cui_safe_mode() is True

    with pytest.raises(CuiViolationError) as excinfo:
        select_client("unclassified")

    message = str(excinfo.value)
    assert "§2b" in message
    assert "§2f" in message


def test_select_client_returns_claude_when_classification_unclassified_and_safe_mode_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "CUI_SAFE_MODE", False)
    assert Config.is_cui_safe_mode() is False

    client = select_client("unclassified")
    assert isinstance(client, ClaudeClient)


def test_claude_client_constructor_raises_cui_violation_when_safe_mode_active():
    assert Config.is_cui_safe_mode() is True

    with pytest.raises(CuiViolationError) as excinfo:
        ClaudeClient()

    message = str(excinfo.value)
    assert "§2b" in message
    assert "§2f" in message


def test_claude_client_constructor_succeeds_when_safe_mode_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "CUI_SAFE_MODE", False)

    client = ClaudeClient()
    assert isinstance(client, ClaudeClient)


def test_claude_client_does_not_import_anthropic_at_module_load():
    # Defensive: ensure a stale prior import doesn't mask the check.
    sys.modules.pop("anthropic", None)
    # Re-import path through the public package surface.
    from app.ai import ClaudeClient as _ReimportedClaudeClient  # noqa: F401

    assert "anthropic" not in sys.modules


def test_claude_client_construction_makes_no_http_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "CUI_SAFE_MODE", False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        ClaudeClient()
        assert mock_urlopen.call_count == 0


def test_select_client_construction_path_is_only_via_router():
    # Importing the router module must not construct a client as a side
    # effect. Routes call select_client; module load does not.
    import importlib

    import app.ai.router as router_module

    importlib.reload(router_module)
    # If any client had been instantiated at import time with CUI-safe
    # mode active, ClaudeClient would have raised. Reaching this line
    # with no exception is the assertion.
    assert hasattr(router_module, "select_client")


def test_config_is_cui_safe_mode_defaults_true():
    assert Config.CUI_SAFE_MODE is True
    assert Config.is_cui_safe_mode() is True
