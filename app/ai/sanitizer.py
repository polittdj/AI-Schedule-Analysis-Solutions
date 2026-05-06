"""UID -> opaque label mapping for AI prompts. Per §2a and watchdog §3,
parsed task content (task.name, task.wbs, resource.name) must be replaced
with opaque labels before any prompt is constructed for any AI backend.

The desanitize step restores labels to original strings on the rendered
narrative output, so the analyst sees real task names in the UI without
those names ever having entered a prompt string."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class SanitizationMap:
    """Immutable forward + reverse map for one analysis. One-shot per
    analysis run; not reused across analyses."""

    forward: Mapping[str, str]  # original -> label
    reverse: Mapping[str, str]  # label -> original


@dataclass
class DataSanitizer:
    """Builds a one-shot sanitization map for a set of original strings
    and provides forward (sanitize) and reverse (desanitize) transforms."""

    _map: SanitizationMap = field(default_factory=lambda: SanitizationMap({}, {}))

    def build(self, originals: list[str], prefix: str = "TASK") -> None:
        """Populate the map with stable opaque labels for each unique
        original. Labels are deterministic by insertion order:
        f"<{prefix}_{N}>" starting at N=1.

        Raises ValueError if originals is empty or contains empty strings.
        """
        if not originals:
            raise ValueError("originals must be non-empty")
        if any(not s for s in originals):
            raise ValueError("originals must not contain empty strings")

        forward: dict[str, str] = {}
        reverse: dict[str, str] = {}
        seen: set[str] = set()
        idx = 1
        for original in originals:
            if original in seen:
                continue
            seen.add(original)
            label = f"<{prefix}_{idx}>"
            forward[original] = label
            reverse[label] = original
            idx += 1

        self._map = SanitizationMap(forward=forward, reverse=reverse)

    def sanitize(self, text: str) -> str:
        """Replace every original substring with its opaque label.
        Replacement is greedy by length descending so that longer originals
        match before shorter ones that may be substrings of the longer."""
        if not self._map.forward:
            raise RuntimeError("sanitizer not built; call build() first")
        out = text
        for original in sorted(self._map.forward, key=len, reverse=True):
            out = out.replace(original, self._map.forward[original])
        return out

    def desanitize(self, text: str) -> str:
        """Replace every opaque label with its original string."""
        if not self._map.reverse:
            raise RuntimeError("sanitizer not built; call build() first")
        out = text
        for label, original in self._map.reverse.items():
            out = out.replace(label, original)
        return out


def desanitize_text(text: str, sanitizer: DataSanitizer) -> str:
    """Module-level helper matching the M12 acceptance-criteria #5 wording.
    Equivalent to sanitizer.desanitize(text)."""
    return sanitizer.desanitize(text)
