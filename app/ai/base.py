"""Abstract AI client interface and CUI gate for the M12 dual-mode AI backend.

Per cui-compliance-constraints §2a, §2b, §2f, §2g. Concrete clients live in
app/ai/ollama_client.py (default, CUI-safe) and app/ai/claude_client.py
(unclassified opt-in). Construction of ClaudeClient when CUI-safe mode is
active raises CuiViolationError before any HTTP call is made.
"""

from abc import ABC, abstractmethod
from typing import Iterator


class CuiViolationError(RuntimeError):
    """Raised when a code path attempts to construct or call a cloud-bound
    AI client while CUI-safe mode is active. Per §2b/§2f, the only correct
    response is to halt — never to fall back silently to a different
    backend."""


class AIClient(ABC):
    """Abstract interface for AI narrative-generation clients.

    Concrete implementations (OllamaClient, ClaudeClient) consume only
    pre-computed AnalysisResult payloads (§2a) — never raw ScheduleData.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True iff the backend endpoint is reachable and ready.

        Honest availability check; concrete clients do not inspect
        classification themselves — that gating is the router's job.
        """

    @abstractmethod
    def generate(self, prompt: str) -> Iterator[str]:
        """Stream narrative tokens for the given (already-sanitized) prompt.

        The prompt MUST have been processed by app.ai.sanitizer.DataSanitizer
        before reaching this method. Raw task names, WBS labels, and resource
        names must not appear in the prompt string.
        """
