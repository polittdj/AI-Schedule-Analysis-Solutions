"""Ollama local LLM backend (CUI-safe).

Talks to a locally running Ollama server via its REST API. Used for
any project marked CUI or higher: raw schedule data and the
AI-generated narrative both stay on the operator's workstation.

Prerequisites
-------------
* Ollama installed and running: ``ollama serve``
* Model pulled: ``ollama create schedule-analyst -f ollama/Modelfile``
  (or any model name configured via `OLLAMA_MODEL`).
* Nothing else — no API keys, no internet.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, Optional

import requests

from app.ai.base import AIBackend
from app.ai.prompt_builder import build_prompt

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "schedule-analyst"
DEFAULT_TIMEOUT_SECONDS = 120
READINESS_TIMEOUT_SECONDS = 2


class OllamaClient(AIBackend):
    """Local Ollama HTTP client. Safe for CUI-rated projects."""

    name = "ollama"

    def __init__(
        self,
        url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Readiness
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """Quick ping against /api/tags.

        Returns False on any connection error, timeout, or non-200 status.
        We intentionally don't raise — callers use this to decide whether
        to disable the UI "Analyze" button.
        """
        try:
            resp = requests.get(
                f"{self.url}/api/tags", timeout=READINESS_TIMEOUT_SECONDS
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def has_model(self, model: Optional[str] = None) -> bool:
        """Check whether the configured (or supplied) model is loaded."""
        target = model or self.model
        try:
            resp = requests.get(
                f"{self.url}/api/tags", timeout=READINESS_TIMEOUT_SECONDS
            )
            if resp.status_code != 200:
                return False
            tags = resp.json().get("models", [])
            return any(m.get("name", "").startswith(target) for m in tags)
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #

    def analyze_schedule(
        self, engine_results: Dict[str, Any], request: str
    ) -> str:
        """Blocking call: returns the full narrative as a string."""
        prompt = build_prompt(engine_results, request)
        try:
            resp = requests.post(
                f"{self.url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.url}. Is 'ollama serve' running? "
                f"Underlying error: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Ollama request timed out after {self.timeout}s. "
                "Local models can be slow — consider increasing OLLAMA_TIMEOUT."
            ) from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")
        return data.get("response", "")

    def stream_analyze(
        self, engine_results: Dict[str, Any], request: str
    ) -> Iterator[str]:
        """Yield narrative chunks as they arrive from the model."""
        prompt = build_prompt(engine_results, request)
        try:
            with requests.post(
                f"{self.url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": True},
                timeout=self.timeout,
                stream=True,
            ) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Ollama returned HTTP {resp.status_code}: "
                        f"{resp.text[:500]}"
                    )
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise RuntimeError(f"Ollama error: {chunk['error']}")
                    piece = chunk.get("response", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.url}. Is 'ollama serve' running?"
            ) from exc
