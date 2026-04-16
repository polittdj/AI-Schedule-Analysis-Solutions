"""Abstract AI backend interface.

Both the local Ollama client (CUI-safe) and the cloud Claude client
(unclassified-only) inherit from `AIBackend`. The forensic engine
talks to this abstraction — never to the concrete clients directly —
so raw schedule data never has a path into either backend without
going through the deterministic pre-processing first.

Contract
--------
Every backend must implement:

* `is_available()` — fast, cheap readiness probe (no network beyond a
  ping for the local client; just env-var check for Claude).
* `analyze_schedule(engine_results, request)` — synchronous blocking
  call that returns the full narrative as a string.

`stream_analyze` is optional; the default implementation yields the
whole analysis as a single chunk so callers can uniformly iterate.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator


class AIBackend(ABC):
    """Abstract base class for every AI narrative backend."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend is usable right now."""

    @abstractmethod
    def analyze_schedule(
        self, engine_results: Dict[str, Any], request: str
    ) -> str:
        """Produce a narrative analysis from pre-computed engine results.

        Parameters
        ----------
        engine_results
            A dict containing any subset of: ``comparison``, ``dcma``,
            ``manipulation``, ``cpm``, ``delay``, ``earned_value``,
            ``float_analysis``. Values may be Pydantic models or dicts.
        request
            The human-readable prompt/question to drive the narrative.
        """

    def stream_analyze(
        self, engine_results: Dict[str, Any], request: str
    ) -> Iterator[str]:
        """Yield narrative chunks as they're produced.

        Default implementation yields one chunk containing the full
        response; concrete backends that actually support streaming
        should override this.
        """
        yield self.analyze_schedule(engine_results, request)
