"""Tests for app.ai.sanitizer.DataSanitizer and app.ai.base.AIClient.

Covers M12 acceptance criterion #5 (DataSanitizer replaces task names with
labels before the prompt reaches any client; desanitize_text restores them
on stream emission) and the structural ABC contract for AIClient.

Synthetic data only per cui-compliance-constraints §2e.
"""

from __future__ import annotations

import pytest

from app.ai import AIClient, DataSanitizer, SanitizationMap, desanitize_text


def test_build_creates_forward_and_reverse_maps_in_insertion_order():
    sanitizer = DataSanitizer()
    sanitizer.build(["Alpha", "Bravo", "Charlie"])

    assert sanitizer._map.forward == {
        "Alpha": "<TASK_1>",
        "Bravo": "<TASK_2>",
        "Charlie": "<TASK_3>",
    }
    assert sanitizer._map.reverse == {
        "<TASK_1>": "Alpha",
        "<TASK_2>": "Bravo",
        "<TASK_3>": "Charlie",
    }


def test_build_deduplicates_originals_preserving_first_occurrence():
    sanitizer = DataSanitizer()
    sanitizer.build(["Alpha", "Bravo", "Alpha", "Charlie", "Bravo"])

    assert sanitizer._map.forward == {
        "Alpha": "<TASK_1>",
        "Bravo": "<TASK_2>",
        "Charlie": "<TASK_3>",
    }


def test_build_rejects_empty_originals_list():
    sanitizer = DataSanitizer()
    with pytest.raises(ValueError, match="originals must be non-empty"):
        sanitizer.build([])


def test_build_rejects_empty_string_in_originals():
    sanitizer = DataSanitizer()
    with pytest.raises(ValueError, match="must not contain empty strings"):
        sanitizer.build(["Alpha", "", "Charlie"])


def test_sanitize_replaces_originals_with_labels():
    sanitizer = DataSanitizer()
    sanitizer.build(["Alpha", "Bravo"])

    result = sanitizer.sanitize("Alpha precedes Bravo by 5 days.")

    assert result == "<TASK_1> precedes <TASK_2> by 5 days."


def test_sanitize_handles_substring_overlap_longest_first():
    sanitizer = DataSanitizer()
    sanitizer.build(["Foundation", "Foundation Pour"])

    result = sanitizer.sanitize("Foundation Pour follows Foundation.")

    assert result == "<TASK_2> follows <TASK_1>."
    assert "Foundation Pour" not in result
    assert "Foundation" not in result


def test_sanitize_raises_if_not_built():
    sanitizer = DataSanitizer()
    with pytest.raises(RuntimeError, match="sanitizer not built"):
        sanitizer.sanitize("anything")


def test_desanitize_round_trip_recovers_original_text():
    sanitizer = DataSanitizer()
    sanitizer.build(["Excavate Trench", "Pour Footings", "Backfill"])

    original = (
        "Excavate Trench drives Pour Footings; Backfill follows Pour Footings."
    )
    sanitized = sanitizer.sanitize(original)
    restored = sanitizer.desanitize(sanitized)

    assert "<TASK_" in sanitized
    assert restored == original


def test_desanitize_module_helper_matches_method():
    sanitizer = DataSanitizer()
    sanitizer.build(["Alpha", "Bravo"])

    sanitized = sanitizer.sanitize("Alpha and Bravo are tasks.")

    assert desanitize_text(sanitized, sanitizer) == sanitizer.desanitize(sanitized)


def test_desanitize_raises_if_not_built():
    sanitizer = DataSanitizer()
    with pytest.raises(RuntimeError, match="sanitizer not built"):
        sanitizer.desanitize("anything")


def test_custom_prefix_is_applied():
    sanitizer = DataSanitizer()
    sanitizer.build(["1.1.1 Site Prep", "1.1.2 Foundations"], prefix="WBS")

    assert sanitizer._map.forward == {
        "1.1.1 Site Prep": "<WBS_1>",
        "1.1.2 Foundations": "<WBS_2>",
    }
    sanitized = sanitizer.sanitize("1.1.1 Site Prep precedes 1.1.2 Foundations.")
    assert sanitized == "<WBS_1> precedes <WBS_2>."


def test_aiclient_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        AIClient()  # type: ignore[abstract]
