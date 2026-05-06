"""Anthropic Claude client — only constructible when classification is
explicitly 'unclassified'.

Per cui-compliance-constraints §2b/§2f, this client must never be
instantiated while is_cui_safe_mode() returns True. The router enforces
that gate; this client also raises CuiViolationError defensively in its
own __init__ if instantiated under CUI-safe mode, so that a buggy
caller that bypasses the router still cannot construct a cloud-bound
client.

The anthropic SDK is imported lazily inside generate() rather than at
module load time. This keeps Block 2 from requiring the SDK as a hard
dependency: the test suite mocks the route at the construction-gate
boundary and never reaches the lazy import. Block 3 (route + e2e)
adds anthropic to requirements.txt when the route is wired.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.ai.base import AIClient, CuiViolationError
from app.config import Config

CLAUDE_MODEL_ID = "claude-sonnet-4-6"
CLAUDE_API_ENDPOINT = "https://api.anthropic.com/v1/messages"


class ClaudeClient(AIClient):
    """AIClient implementation backed by the Anthropic Claude API.

    Per §2b/§2f, construction raises CuiViolationError if CUI-safe mode
    is active. This is a defense-in-depth check on top of the router
    gate; both must pass for cloud-bound traffic to ever leave the box.
    """

    def __init__(self, model: str = CLAUDE_MODEL_ID) -> None:
        if Config.is_cui_safe_mode():
            raise CuiViolationError(
                "Cannot construct ClaudeClient while CUI-safe mode is "
                "active. Toggle classification to 'unclassified' "
                "explicitly via the web UI before any cloud-bound AI "
                "client is instantiated. Per cui-compliance-constraints "
                "§2b and §2f."
            )
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        return CLAUDE_API_ENDPOINT

    def is_available(self) -> bool:
        """Cloud client is considered available iff it was successfully
        constructed (i.e. classification is unclassified). The actual
        SDK call is deferred to generate(); a separate liveness probe
        would itself transmit data off-host, which is acceptable only
        once construction succeeded."""
        return True

    def generate(self, prompt: str) -> Iterator[str]:
        """Stream tokens from the Claude API. Prompt MUST already be
        sanitized per §2a — this client does not sanitize. The
        anthropic SDK is imported lazily so that Block 2 unit tests do
        not require the package."""
        # Lazy import — Block 3 adds anthropic to requirements.txt.
        from anthropic import Anthropic  # type: ignore[import-not-found]

        client = Anthropic()
        with client.messages.stream(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
