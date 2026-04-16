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

Extended thinking
-----------------
Claude 4.x Opus/Sonnet support "extended thinking" — the model
generates private reasoning tokens before producing its final answer.
The thinking tokens are billed but never shown to the user; only the
final text blocks are returned. This defaults **on** for forensic
analysis because it materially improves the quality of multi-step
delay-cause narratives. Set ``ANTHROPIC_THINKING=false`` to disable,
or tune the budget via ``ANTHROPIC_THINKING_BUDGET``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterator, Optional

from app.ai.base import AIBackend
from app.ai.prompt_builder import build_prompt

DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_THINKING_ENABLED = True
DEFAULT_THINKING_BUDGET = 10000

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
        thinking_enabled: bool = DEFAULT_THINKING_ENABLED,
        thinking_budget: int = DEFAULT_THINKING_BUDGET,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_enabled = thinking_enabled
        self.thinking_budget = thinking_budget
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

    def _build_request_kwargs(self, prompt: str) -> Dict[str, Any]:
        """Compose the kwargs for ``messages.create`` / ``messages.stream``.

        When extended thinking is enabled, the Anthropic API requires:
          * ``max_tokens`` strictly greater than ``budget_tokens``
          * temperature must be left at its default (1.0); we don't
            set it explicitly
          * ``top_p`` / ``top_k`` must not be set
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.thinking_enabled and self.thinking_budget > 0:
            if self.thinking_budget >= self.max_tokens:
                raise RuntimeError(
                    f"ANTHROPIC_THINKING_BUDGET ({self.thinking_budget}) "
                    f"must be less than ANTHROPIC_MAX_TOKENS "
                    f"({self.max_tokens}). Lower the budget or raise the "
                    f"max-tokens ceiling."
                )
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }
        return kwargs

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #

    def analyze_schedule(
        self, engine_results: Dict[str, Any], request: str
    ) -> str:
        prompt = build_prompt(engine_results, request)
        client = self._get_client()
        message = client.messages.create(**self._build_request_kwargs(prompt))
        # `message.content` is a list of content blocks. Thinking blocks
        # (`type == "thinking"`) have a `.thinking` attribute but no
        # `.text` — we skip them so the user never sees the private
        # reasoning. Only final text blocks are concatenated.
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
        with client.messages.stream(**self._build_request_kwargs(prompt)) as stream:
            # `text_stream` yields only text from text blocks, so
            # thinking tokens are transparently skipped even when
            # extended thinking is enabled.
            for text in stream.text_stream:
                if text:
                    yield text
