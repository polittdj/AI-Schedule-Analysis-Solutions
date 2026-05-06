"""Classification-gated AI client construction.

Per cui-compliance-constraints §2b, the Anthropic Claude API may only
be instantiated when classification is explicitly 'unclassified'. Per
§2f, when Ollama is unavailable and classification is CUI, the tool
must halt — never silently fall back to Claude.

This module is the single canonical place where the classification
gate lives. Routes call ``select_client`` to obtain the appropriate
client; they never instantiate clients themselves.
"""

from __future__ import annotations

from app.ai.base import AIClient, CuiViolationError
from app.ai.claude_client import ClaudeClient
from app.ai.ollama_client import OllamaClient
from app.config import Config


def select_client(classification: str) -> AIClient:
    """Return the appropriate AIClient for the given classification.

    ``classification`` is the per-session classification string. The
    only value that opens the cloud path is the literal string
    ``"unclassified"`` (case-sensitive). Anything else — including
    ``"cui"``, ``"sbu"``, ``""``, or any unrecognized value — yields
    the local Ollama client.

    Raises CuiViolationError per §2b/§2f if the caller passes
    ``"unclassified"`` while ``Config.is_cui_safe_mode()`` returns
    True. This double-gate (classification arg AND config flag) is
    intentional: a buggy caller that hard-codes ``"unclassified"``
    must still be blocked when the operator has not toggled CUI-safe
    mode off.
    """
    if classification == "unclassified":
        if Config.is_cui_safe_mode():
            raise CuiViolationError(
                "select_client refused to construct a cloud-bound "
                "client: classification was 'unclassified' but "
                "Config.is_cui_safe_mode() is True. The Config flag "
                "must be flipped before cloud routing is permitted. "
                "Per cui-compliance-constraints §2b and §2f."
            )
        return ClaudeClient()
    return OllamaClient()
