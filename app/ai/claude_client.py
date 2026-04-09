"""Anthropic Claude API backend (unclassified-only).

Calls the cloud Claude API via the official `anthropic` Python SDK.

WARNING
-------
This backend transmits pre-computed schedule metrics over the public
internet to Anthropic's API. It must only be used for projects that
are explicitly marked unclassified. Any CUI or higher must use the
local Ollama backend instead. The `app.config.Config.is_cui_safe_mode`
helper enforces this at the application layer.

The cloud payload is the *prompt* built from deterministic engine
output — never the raw MPP file or raw task metadata — but operators
should still opt in consciously per project.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterator, Optional

from app.ai.base import AIBackend
from app.ai.prompt_builder import build_prompt

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096

CLOUD_WARNING = (
    "Cloud AI mode transmits the pre-computed forensic prompt to "
    "Anthropic's Claude API over the public internet. Only use this "
    "backend for projects that are explicitly rated UNCLASSIFIED. Any "
    "CUI-rated or higher data must use the local Ollama backend."
)


class ClaudeClient(AIBackend):
    """Anthropic Claude API client for unclassified projects."""

    name = "claude"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self._client = None  # lazy

    # ------------------------------------------------------------------ #
    # Readiness
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """Claude is 'available' as soon as an API key is present.

        We deliberately don't make a network call here; that would be
        slow and would cost a request every time the UI checks. If the
        API key is invalid the actual analyze call will surface that.
        """
        return bool(self.api_key)

    @property
    def warning_message(self) -> str:
        return CLOUD_WARNING

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Cloud AI backend cannot run. "
                "Set the environment variable or switch to local mode."
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "`anthropic` Python package is not installed. "
                "Run: pip install anthropic"
            ) from exc
        self._client = Anthropic(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #

    def analyze_schedule(
        self, engine_results: Dict[str, Any], request: str
    ) -> str:
        prompt = build_prompt(engine_results, request)
        client = self._get_client()
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # `message.content` is a list of content blocks; concatenate text blocks.
        parts = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)

    def stream_analyze(
        self, engine_results: Dict[str, Any], request: str
    ) -> Iterator[str]:
        prompt = build_prompt(engine_results, request)
        client = self._get_client()
        with client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
