"""Optional data anonymization for cloud-mode AI calls.

When `SANITIZE_DATA=true`, every task name, resource name, project
name, and free-text note is replaced with a deterministic label
(`Task A`, `Task B`, ...) before the engine results are handed to the
AI backend. The numeric backbone of the schedule — durations, dates,
float, predecessor/successor UIDs, DCMA metrics — is preserved so
analysis quality is untouched.

After the AI responds, the same `DataSanitizer` instance can
`desanitize_text(response)` to substitute the original names back in.

Safety properties
-----------------
* Input is deep-copied; nothing mutates the original engine results.
* The mapping is keyed by task UID — the same UID always yields the
  same label, even across multiple nested locations in the result
  tree, so the AI sees a coherent schedule.
* Re-instantiating `DataSanitizer` gives a fresh mapping; operators
  should use one instance per analysis run.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

# Keys whose values are sensitive and should be blanked.
_BLANK_KEYS = {"notes", "resource_names"}

# Keys representing the *project* name (not task name).
_PROJECT_NAME_KEYS = {
    "prior_project_name",
    "later_project_name",
    "project_name",
}

# Keys whose value is a task name (typically co-located with a task uid).
_TASK_NAME_REF_KEYS = {
    "task_name",
    "first_mover_name",
}

# Replacement text for project names and blanked strings.
PROJECT_PLACEHOLDER = "Project X"
BLANK_PLACEHOLDER = ""


class DataSanitizer:
    """Anonymizes schedule engine results and reverses the labels."""

    def __init__(self) -> None:
        self.task_mapping: Dict[int, str] = {}  # uid → "Task A"
        self.reverse_mapping: Dict[str, str] = {}  # "Task A" → original name
        self._counter = 0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def sanitize(self, engine_results: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deep-copied, anonymized version of `engine_results`."""
        data = self._to_dict(engine_results)
        self._collect_task_names(data)
        return self._walk(data)

    def desanitize_text(self, text: str) -> str:
        """Replace anonymized labels with the original names.

        Processes labels in order of decreasing length so that
        ``Task AA`` is replaced before ``Task A`` — this prevents the
        longer label from having its prefix matched by the shorter one.
        """
        if not text or not self.reverse_mapping:
            return text
        out = text
        for label in sorted(self.reverse_mapping.keys(), key=len, reverse=True):
            original = self.reverse_mapping[label]
            if original:
                out = out.replace(label, original)
        return out

    # ------------------------------------------------------------------ #
    # Labeling
    # ------------------------------------------------------------------ #

    @staticmethod
    def _letter_label(index: int) -> str:
        """0→A, 1→B, ..., 25→Z, 26→AA, 27→AB, ..."""
        if index < 0:
            raise ValueError("index must be non-negative")
        n = index + 1  # 1-indexed for base-26
        letters: List[str] = []
        while n > 0:
            n -= 1
            letters.append(chr(ord("A") + (n % 26)))
            n //= 26
        return "".join(reversed(letters))

    def _register(self, uid: int, original_name: Optional[str]) -> str:
        """Idempotently assign a label to `uid` and return it."""
        if uid in self.task_mapping:
            return self.task_mapping[uid]
        label = f"Task {self._letter_label(self._counter)}"
        self._counter += 1
        self.task_mapping[uid] = label
        self.reverse_mapping[label] = original_name or f"Task {uid}"
        return label

    # ------------------------------------------------------------------ #
    # Passes
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_dict(obj: Any) -> Any:
        """Deep-copy into plain Python (handles Pydantic models transparently)."""
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="python")
        if isinstance(obj, dict):
            return copy.deepcopy({k: DataSanitizer._to_dict(v) for k, v in obj.items()})
        if isinstance(obj, list):
            return [DataSanitizer._to_dict(v) for v in obj]
        return copy.deepcopy(obj)

    def _collect_task_names(self, obj: Any) -> None:
        """First pass: register every (uid, name) pair we can find.

        We collect up front so that references like ``task_name`` /
        ``first_mover_name`` always map to a registered label even if
        they're encountered before the defining task dict. Resource
        dicts are skipped — their UIDs live in a separate namespace.
        """
        if isinstance(obj, dict):
            uid = obj.get("uid")
            if (
                isinstance(uid, int)
                and "name" in obj
                and not self._is_resource_dict(obj)
            ):
                self._register(uid, obj.get("name"))
            for v in obj.values():
                self._collect_task_names(v)
        elif isinstance(obj, list):
            for item in obj:
                self._collect_task_names(item)

    def _walk(self, obj: Any) -> Any:
        """Second pass: build a new dict with sanitized values."""
        if isinstance(obj, dict):
            is_resource = self._is_resource_dict(obj)
            is_task_like = (
                isinstance(obj.get("uid"), int)
                and "name" in obj
                and not is_resource
            )
            out: Dict[str, Any] = {}
            for key, val in obj.items():
                if key in _BLANK_KEYS:
                    out[key] = BLANK_PLACEHOLDER if val is not None else None
                elif key in _PROJECT_NAME_KEYS:
                    out[key] = PROJECT_PLACEHOLDER if val is not None else None
                elif key == "name" and is_resource:
                    # Anonymize resource names in their own namespace.
                    out[key] = f"Resource {obj.get('uid', '?')}"
                elif key == "name" and is_task_like:
                    out[key] = self.task_mapping.get(
                        obj["uid"], self._register(obj["uid"], val)
                    )
                elif key in _TASK_NAME_REF_KEYS:
                    # Look up by a sibling uid field if present.
                    ref_uid = obj.get("first_mover_uid") if key == "first_mover_name" else obj.get("task_uid")
                    if isinstance(ref_uid, int) and ref_uid in self.task_mapping:
                        out[key] = self.task_mapping[ref_uid]
                    else:
                        out[key] = BLANK_PLACEHOLDER if val is not None else None
                else:
                    out[key] = self._walk(val)
            return out
        if isinstance(obj, list):
            return [self._walk(item) for item in obj]
        return obj

    @staticmethod
    def _is_resource_dict(obj: Dict[str, Any]) -> bool:
        """Heuristic: a ResourceData has uid + name + (type or max_units)."""
        return (
            isinstance(obj.get("uid"), int)
            and "name" in obj
            and ("max_units" in obj or "type" in obj)
            and "duration" not in obj  # distinguishes from TaskData
        )
