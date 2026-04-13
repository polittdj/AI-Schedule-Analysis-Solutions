"""Application configuration.

Environment-variable driven so the same codebase runs in three
deployment contexts:

* **Dev workstation (default):** local Ollama, no cloud, uploads in
  ``./uploads``, 500 MB max file size.
* **Production local mode:** Ollama on a secured workstation; operator
  may override the model name, timeout, or sanitize flag.
* **Ad-hoc cloud mode:** only used for explicitly unclassified
  projects. Requires ``ANTHROPIC_API_KEY``.

Everything is wrapped in a `Config` *class* (not module-level
constants) so unit tests can instantiate a fresh `Config()` after
monkeypatching ``os.environ`` — module-level constants get frozen at
import time and can't be re-read.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


BASE_DIR = Path(__file__).resolve().parent.parent

# Defaults — documented so operators know what to override.
DEFAULT_AI_MODE = "local"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "schedule-analyst"
DEFAULT_OLLAMA_TIMEOUT = 120
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
DEFAULT_MAX_PROMPT_TOKENS = 6000
DEFAULT_SECRET_KEY = "dev-key-change-in-production"  # intentionally insecure


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


class Config:
    """Immutable snapshot of the runtime configuration.

    Reads every value from ``os.environ`` at construction time. Call
    ``Config()`` again to re-read after changing environment variables.
    """

    def __init__(self) -> None:
        self.AI_MODE: str = os.environ.get("AI_MODE", DEFAULT_AI_MODE).lower()

        # Ollama (local)
        self.OLLAMA_URL: str = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
        self.OLLAMA_MODEL: str = os.environ.get(
            "OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL
        )
        self.OLLAMA_TIMEOUT: int = int(
            os.environ.get("OLLAMA_TIMEOUT", str(DEFAULT_OLLAMA_TIMEOUT))
        )

        # Anthropic (cloud)
        self.ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")
        self.ANTHROPIC_MODEL: str = os.environ.get(
            "ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL
        )

        # Data handling
        self.SANITIZE_DATA: bool = _parse_bool(
            os.environ.get("SANITIZE_DATA", "false")
        )

        # File upload
        self.UPLOAD_FOLDER: Path = Path(
            os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
        )
        self.MAX_FILE_SIZE: int = int(
            os.environ.get("MAX_FILE_SIZE", str(DEFAULT_MAX_FILE_SIZE))
        )
        self.ALLOWED_EXTENSIONS = frozenset(
            {
                ext.strip().lstrip(".")
                for ext in os.environ.get(
                    "ALLOWED_EXTENSIONS", "mpp,xml,mpx"
                ).split(",")
                if ext.strip()
            }
        )

        # Flask secrets
        self.SECRET_KEY: str = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY)

        # Prompt budget
        self.MAX_PROMPT_TOKENS: int = int(
            os.environ.get("MAX_PROMPT_TOKENS", str(DEFAULT_MAX_PROMPT_TOKENS))
        )

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    def is_cui_safe_mode(self) -> bool:
        """True when the configured AI backend keeps data on the workstation."""
        return self.AI_MODE == "local"

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly snapshot (API key is masked)."""
        masked = (
            f"{self.ANTHROPIC_API_KEY[:4]}…" if self.ANTHROPIC_API_KEY else None
        )
        return {
            "ai_mode": self.AI_MODE,
            "ollama_url": self.OLLAMA_URL,
            "ollama_model": self.OLLAMA_MODEL,
            "ollama_timeout": self.OLLAMA_TIMEOUT,
            "anthropic_api_key_set": masked,
            "anthropic_model": self.ANTHROPIC_MODEL,
            "sanitize_data": self.SANITIZE_DATA,
            "upload_folder": str(self.UPLOAD_FOLDER),
            "max_file_size": self.MAX_FILE_SIZE,
            "allowed_extensions": sorted(self.ALLOWED_EXTENSIONS),
            "max_prompt_tokens": self.MAX_PROMPT_TOKENS,
            "is_cui_safe_mode": self.is_cui_safe_mode(),
        }


def load_config() -> Config:
    """Return a fresh `Config()` reading current environment variables."""
    return Config()
