"""Local Ollama client for the schedule-analyst custom model.

Per cui-compliance-constraints §2b, Ollama is the default backend for
all CUI work and runs on http://localhost:11434. This client opens a
socket only to localhost; it never reaches off-host. Per §2d, this
module logs nothing — the route boundary is responsible for any logging.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator

from app.ai.base import AIClient

OLLAMA_DEFAULT_ENDPOINT = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "schedule-analyst"
_AVAILABILITY_TIMEOUT_SECONDS = 2.0
_GENERATE_TIMEOUT_SECONDS = 60.0


class OllamaClient(AIClient):
    """AIClient implementation backed by a local Ollama daemon.

    Construction does NOT make any network calls. The first network
    activity happens in is_available() or generate(). All traffic stays
    on localhost.
    """

    def __init__(
        self,
        endpoint: str = OLLAMA_DEFAULT_ENDPOINT,
        model: str = OLLAMA_DEFAULT_MODEL,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model = model

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        """Probe the /api/tags endpoint with a short timeout. Returns
        True iff the daemon responds with HTTP 200. Any error
        (connection refused, timeout, non-2xx) returns False — never
        raises. Per §2f the route halts on False; this method does not
        decide policy."""
        url = f"{self._endpoint}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=_AVAILABILITY_TIMEOUT_SECONDS) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            return False

    def generate(self, prompt: str) -> Iterator[str]:
        """Stream tokens from the Ollama /api/generate endpoint. The
        prompt MUST already be sanitized per §2a; this client does not
        sanitize. Tokens are yielded as they arrive. Raises
        RuntimeError on transport errors so the caller can map to an
        explicit halt response per §2f."""
        url = f"{self._endpoint}/api/generate"
        payload = json.dumps(
            {"model": self._model, "prompt": prompt, "stream": True}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_GENERATE_TIMEOUT_SECONDS) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    chunk = obj.get("response", "")
                    if chunk:
                        yield chunk
                    if obj.get("done"):
                        break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Ollama transport error: {type(exc).__name__}") from exc
