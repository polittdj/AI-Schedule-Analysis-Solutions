"""Unit tests for the Phase 3 AI integration layer.

Covers:
* `prompt_builder.build_prompt` — produces a bounded string from
  realistic engine output and includes every section header.
* `DataSanitizer` — replaces task/project/resource names, preserves
  numeric data, and round-trips through `desanitize_text`.
* `OllamaClient.is_available` — returns False against a closed port
  (no network dependency on a running Ollama server).
* `ClaudeClient.is_available` — True when `ANTHROPIC_API_KEY` is set,
  False otherwise.
* `Config` — loads documented defaults when env vars are cleared.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict

import pytest

from app.ai.base import AIBackend
from app.ai.claude_client import ClaudeClient
from app.ai.ollama_client import OllamaClient
from app.ai.prompt_builder import (
    CONTEXT_END_TAG,
    CONTEXT_START_TAG,
    DEFAULT_MAX_TOKENS,
    build_prompt,
    estimate_tokens,
    summarize_for_prompt,
)
from app.ai.sanitizer import DataSanitizer
from app.config import (
    DEFAULT_AI_MODE,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_MAX_PROMPT_TOKENS,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TIMEOUT,
    DEFAULT_OLLAMA_URL,
    Config,
    load_config,
)
from app.engine.comparator import compare_schedules
from app.engine.cpm import compute_cpm
from app.engine.dcma import compute_dcma
from app.engine.earned_value import compute_earned_value
from app.engine.float_analysis import analyze_float
from app.engine.manipulation import detect_manipulations
from app.parser.schema import (
    ProjectInfo,
    Relationship,
    ScheduleData,
    TaskData,
)


# --------------------------------------------------------------------------- #
# Shared fixture: a realistic two-schedule engine_results payload
# --------------------------------------------------------------------------- #


def _make_task(uid, name, **kwargs) -> TaskData:
    return TaskData(uid=uid, id=uid, name=name, **kwargs)


def _build_engine_results() -> Dict:
    """Construct a plausible engine_results dict with data from every module."""
    prior_tasks = [
        _make_task(
            1,
            "Mobilization",
            duration=5.0,
            start=datetime(2026, 1, 5),
            finish=datetime(2026, 1, 9),
            baseline_start=datetime(2026, 1, 5),
            baseline_finish=datetime(2026, 1, 9),
            baseline_duration=5.0,
            percent_complete=100.0,
            total_slack=0.0,
            critical=True,
            predecessors=[],
            successors=[2],
            notes="Mobilize crane and lay-down yard.",
        ),
        _make_task(
            2,
            "Excavation",
            duration=8.0,
            start=datetime(2026, 1, 12),
            finish=datetime(2026, 1, 21),
            baseline_start=datetime(2026, 1, 12),
            baseline_finish=datetime(2026, 1, 21),
            baseline_duration=8.0,
            percent_complete=50.0,
            total_slack=0.0,
            critical=True,
            predecessors=[1],
            successors=[3],
        ),
        _make_task(
            3,
            "Concrete pour",
            duration=10.0,
            start=datetime(2026, 1, 22),
            finish=datetime(2026, 2, 4),
            baseline_start=datetime(2026, 1, 22),
            baseline_finish=datetime(2026, 2, 4),
            baseline_duration=10.0,
            percent_complete=0.0,
            total_slack=0.0,
            critical=True,
            predecessors=[2],
            successors=[4],
            notes="Primary slab pour. Weather-sensitive.",
        ),
        _make_task(
            4,
            "Curing",
            duration=7.0,
            start=datetime(2026, 2, 5),
            finish=datetime(2026, 2, 13),
            baseline_start=datetime(2026, 2, 5),
            baseline_finish=datetime(2026, 2, 13),
            baseline_duration=7.0,
            percent_complete=0.0,
            total_slack=0.0,
            critical=True,
            predecessors=[3],
        ),
    ]

    later_tasks = [
        t.model_copy(deep=True) for t in prior_tasks
    ]
    # Slip task 3 by 5 days (weather)
    later_tasks[2] = later_tasks[2].model_copy(
        update={
            "start": datetime(2026, 1, 27),
            "finish": datetime(2026, 2, 9),
            "notes": "Delayed 5 days by storm system. Site shut down.",
        }
    )
    later_tasks[3] = later_tasks[3].model_copy(
        update={
            "start": datetime(2026, 2, 10),
            "finish": datetime(2026, 2, 18),
        }
    )

    rels = [
        Relationship(predecessor_uid=1, successor_uid=2),
        Relationship(predecessor_uid=2, successor_uid=3),
        Relationship(predecessor_uid=3, successor_uid=4),
    ]

    prior = ScheduleData(
        project_info=ProjectInfo(
            name="Bridge Replacement 42",
            status_date=datetime(2026, 1, 19),
            start_date=datetime(2026, 1, 5),
            finish_date=datetime(2026, 2, 13),
        ),
        tasks=prior_tasks,
        relationships=rels,
    )
    later = ScheduleData(
        project_info=ProjectInfo(
            name="Bridge Replacement 42",
            status_date=datetime(2026, 1, 26),
            start_date=datetime(2026, 1, 5),
            finish_date=datetime(2026, 2, 18),
        ),
        tasks=later_tasks,
        relationships=rels,
    )

    comparison = compare_schedules(prior, later)
    cpm_result = compute_cpm(later)
    dcma = compute_dcma(later, cpm_result)
    manipulation = detect_manipulations(comparison, prior, later)
    ev = compute_earned_value(later)
    fa = analyze_float(comparison, prior, later)

    return {
        "prior_schedule": prior,
        "later_schedule": later,
        "comparison": comparison,
        "cpm": cpm_result,
        "dcma": dcma,
        "manipulation": manipulation,
        "earned_value": ev,
        "float_analysis": fa,
    }


# --------------------------------------------------------------------------- #
# Prompt builder
# --------------------------------------------------------------------------- #


class TestPromptBuilder:
    def test_produces_string_under_token_budget(self):
        results = _build_engine_results()
        prompt = build_prompt(results, user_request="Explain the slip to the owner.")
        assert isinstance(prompt, str)
        tokens = estimate_tokens(prompt)
        assert tokens < DEFAULT_MAX_TOKENS, (
            f"prompt is {tokens} tokens, exceeds {DEFAULT_MAX_TOKENS}"
        )

    def test_contains_all_section_headers(self):
        prompt = build_prompt(_build_engine_results())
        for header in (
            "## PROJECT OVERVIEW",
            "## SCHEDULE HEALTH",
            "## CRITICAL PATH",
            "## SLIPPAGE SUMMARY",
            "## DURATION CHANGES",
            "## MANIPULATION FINDINGS",
            "## FLOAT ANALYSIS",
            "## EARNED VALUE",
        ):
            assert header in prompt, f"missing section header: {header}"

    def test_rag_placeholders_present(self):
        prompt = build_prompt(_build_engine_results())
        assert CONTEXT_START_TAG in prompt
        assert CONTEXT_END_TAG in prompt
        # And CONTEXT_START comes before CONTEXT_END.
        assert prompt.index(CONTEXT_START_TAG) < prompt.index(CONTEXT_END_TAG)

    def test_user_request_included(self):
        prompt = build_prompt(
            _build_engine_results(),
            user_request="Focus on weather-driven delays.",
        )
        assert "Focus on weather-driven delays." in prompt
        assert "## REQUEST" in prompt

    def test_truncation_enforces_budget(self):
        # Ridiculously low budget should trigger truncation.
        prompt = build_prompt(_build_engine_results(), max_tokens=200)
        assert estimate_tokens(prompt) <= 200 + 10  # allow small marker slack
        assert "truncated" in prompt.lower()

    def test_empty_engine_results_still_valid(self):
        prompt = build_prompt({}, user_request="Give a generic answer.")
        assert isinstance(prompt, str)
        assert "## REQUEST" in prompt

    def test_summarize_for_prompt_ranks_and_truncates(self):
        rows = [{"uid": i, "slip": i * 1.5} for i in range(20)]
        top5 = summarize_for_prompt(rows, "slip", 5)
        assert len(top5) == 5
        assert top5[0]["uid"] == 19  # largest first


# --------------------------------------------------------------------------- #
# Sanitizer
# --------------------------------------------------------------------------- #


class TestSanitizer:
    def _sample_engine_results(self) -> Dict:
        return {
            "comparison": {
                "prior_project_name": "Secret Bridge Project",
                "later_project_name": "Secret Bridge Project",
                "task_deltas": [
                    {
                        "uid": 1,
                        "name": "Foundation pour",
                        "finish_slip_days": 5.0,
                        "duration_change_days": -2.0,
                        "predecessors_added": [],
                        "predecessors_removed": [],
                        "relationship_type_changes": [],
                        "lag_changes": [],
                    },
                    {
                        "uid": 2,
                        "name": "Classified Inspection by Bob Smith",
                        "finish_slip_days": 10.0,
                        "duration_change_days": 0.0,
                        "predecessors_added": [],
                        "predecessors_removed": [],
                        "relationship_type_changes": [],
                        "lag_changes": [],
                    },
                ],
            },
            "later_schedule": {
                "tasks": [
                    {
                        "uid": 1,
                        "name": "Foundation pour",
                        "duration": 10.0,
                        "notes": "Contractor-sensitive notes here.",
                        "resource_names": "John Smith, Jane Doe",
                    },
                    {
                        "uid": 2,
                        "name": "Classified Inspection by Bob Smith",
                        "duration": 3.0,
                        "notes": "Inspector name: Redacted",
                        "resource_names": "Bob Smith",
                    },
                ],
                "resources": [
                    {"uid": 10, "name": "John Smith", "type": "WORK", "max_units": 1.0},
                    {"uid": 11, "name": "Bob Smith", "type": "WORK", "max_units": 1.0},
                ],
            },
            "delay": {
                "first_mover_uid": 2,
                "first_mover_name": "Classified Inspection by Bob Smith",
                "first_mover_slip_days": 10.0,
                "root_causes": [
                    {
                        "task_uid": 2,
                        "task_name": "Classified Inspection by Bob Smith",
                        "slip_days": 10.0,
                        "category": "third_party",
                    }
                ],
            },
        }

    def test_task_names_replaced(self):
        sanitizer = DataSanitizer()
        sanitized = sanitizer.sanitize(self._sample_engine_results())
        later_tasks = sanitized["later_schedule"]["tasks"]
        names = [t["name"] for t in later_tasks]
        assert "Foundation pour" not in names
        assert "Classified Inspection by Bob Smith" not in names
        assert all(n.startswith("Task ") for n in names)
        assert len(set(names)) == len(names)  # unique labels

    def test_numeric_data_preserved(self):
        sanitizer = DataSanitizer()
        original = self._sample_engine_results()
        sanitized = sanitizer.sanitize(original)
        sanitized_deltas = sanitized["comparison"]["task_deltas"]
        original_deltas = original["comparison"]["task_deltas"]
        for s, o in zip(sanitized_deltas, original_deltas):
            assert s["uid"] == o["uid"]
            assert s["finish_slip_days"] == o["finish_slip_days"]
            assert s["duration_change_days"] == o["duration_change_days"]
        for s, o in zip(
            sanitized["later_schedule"]["tasks"],
            original["later_schedule"]["tasks"],
        ):
            assert s["duration"] == o["duration"]

    def test_project_name_replaced(self):
        sanitizer = DataSanitizer()
        sanitized = sanitizer.sanitize(self._sample_engine_results())
        assert sanitized["comparison"]["prior_project_name"] == "Project X"
        assert sanitized["comparison"]["later_project_name"] == "Project X"

    def test_notes_and_resource_names_blanked(self):
        sanitizer = DataSanitizer()
        sanitized = sanitizer.sanitize(self._sample_engine_results())
        for t in sanitized["later_schedule"]["tasks"]:
            assert t["notes"] == ""
            assert t["resource_names"] == ""

    def test_resources_list_anonymized(self):
        sanitizer = DataSanitizer()
        sanitized = sanitizer.sanitize(self._sample_engine_results())
        resource_names = [r["name"] for r in sanitized["later_schedule"]["resources"]]
        assert "John Smith" not in resource_names
        assert "Bob Smith" not in resource_names
        assert all(r.startswith("Resource ") for r in resource_names)

    def test_task_name_ref_fields_anonymized(self):
        sanitizer = DataSanitizer()
        sanitized = sanitizer.sanitize(self._sample_engine_results())
        fm_name = sanitized["delay"]["first_mover_name"]
        assert fm_name.startswith("Task ")
        rc_name = sanitized["delay"]["root_causes"][0]["task_name"]
        assert rc_name.startswith("Task ")
        assert rc_name == fm_name  # same UID → same label

    def test_consistent_labels_across_locations(self):
        sanitizer = DataSanitizer()
        sanitized = sanitizer.sanitize(self._sample_engine_results())
        # Find the sanitized name for uid 2 in the later_schedule
        t2 = next(
            t for t in sanitized["later_schedule"]["tasks"] if t["uid"] == 2
        )
        d2 = next(
            d for d in sanitized["comparison"]["task_deltas"] if d["uid"] == 2
        )
        # The comparator doesn't have a per-delta "name" field with a
        # task-uid pair in the same dict shape, so we can't rely on it.
        # What we CAN rely on is: first_mover_name should match t2's name.
        assert sanitized["delay"]["first_mover_name"] == t2["name"]

    def test_desanitize_text_reverses_labels(self):
        sanitizer = DataSanitizer()
        sanitizer.sanitize(self._sample_engine_results())
        # Pretend the AI produced a narrative using the sanitized labels.
        label_1 = sanitizer.task_mapping[1]
        label_2 = sanitizer.task_mapping[2]
        ai_text = (
            f"{label_2} slipped by 10 days, making it the first mover. "
            f"{label_1} also slipped by 5 days."
        )
        restored = sanitizer.desanitize_text(ai_text)
        assert "Classified Inspection by Bob Smith" in restored
        assert "Foundation pour" in restored
        assert label_1 not in restored
        assert label_2 not in restored

    def test_labels_are_letter_sequences(self):
        sanitizer = DataSanitizer()
        # Generate more than 26 labels to exercise the AA/AB wraparound.
        for i in range(30):
            sanitizer._register(i, f"Task {i}")
        assert sanitizer.task_mapping[0] == "Task A"
        assert sanitizer.task_mapping[25] == "Task Z"
        assert sanitizer.task_mapping[26] == "Task AA"
        assert sanitizer.task_mapping[27] == "Task AB"


# --------------------------------------------------------------------------- #
# Ollama client
# --------------------------------------------------------------------------- #


class TestOllamaClient:
    def test_is_available_false_on_wrong_port(self):
        # Port 1 is reserved; connection will be refused immediately.
        client = OllamaClient(url="http://127.0.0.1:1")
        assert client.is_available() is False

    def test_is_available_false_on_unreachable_host(self):
        # Non-routable IP (TEST-NET-1) — connection attempt will fail fast
        # under our 2-second readiness timeout.
        client = OllamaClient(url="http://192.0.2.1:11434")
        assert client.is_available() is False

    def test_inherits_from_base_backend(self):
        client = OllamaClient()
        assert isinstance(client, AIBackend)
        assert client.name == "ollama"

    def test_analyze_raises_on_connection_error(self):
        client = OllamaClient(url="http://127.0.0.1:1", timeout=1)
        with pytest.raises(RuntimeError):
            client.analyze_schedule({}, "test request")


# --------------------------------------------------------------------------- #
# Claude client
# --------------------------------------------------------------------------- #


class TestClaudeClient:
    def test_is_available_false_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = ClaudeClient()
        assert client.is_available() is False

    def test_is_available_true_with_api_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        client = ClaudeClient()
        assert client.is_available() is True

    def test_inherits_from_base_backend(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = ClaudeClient()
        assert isinstance(client, AIBackend)
        assert client.name == "claude"

    def test_warning_message_mentions_cloud(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = ClaudeClient()
        warning = client.warning_message
        assert "cloud" in warning.lower() or "anthropic" in warning.lower()
        assert "unclassified" in warning.lower()


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


@pytest.fixture
def clean_env(monkeypatch):
    """Clear every configurable env var before the test runs."""
    for key in (
        "AI_MODE",
        "OLLAMA_URL",
        "OLLAMA_MODEL",
        "OLLAMA_TIMEOUT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "SANITIZE_DATA",
        "UPLOAD_FOLDER",
        "MAX_FILE_SIZE",
        "ALLOWED_EXTENSIONS",
        "SECRET_KEY",
        "MAX_PROMPT_TOKENS",
    ):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


class TestConfig:
    def test_loads_defaults(self, clean_env):
        cfg = Config()
        assert cfg.AI_MODE == DEFAULT_AI_MODE
        assert cfg.OLLAMA_URL == DEFAULT_OLLAMA_URL
        assert cfg.OLLAMA_MODEL == DEFAULT_OLLAMA_MODEL
        assert cfg.OLLAMA_TIMEOUT == DEFAULT_OLLAMA_TIMEOUT
        assert cfg.ANTHROPIC_MODEL == DEFAULT_ANTHROPIC_MODEL
        assert cfg.ANTHROPIC_API_KEY is None
        assert cfg.SANITIZE_DATA is False
        assert cfg.MAX_FILE_SIZE == DEFAULT_MAX_FILE_SIZE
        assert cfg.MAX_PROMPT_TOKENS == DEFAULT_MAX_PROMPT_TOKENS

    def test_is_cui_safe_mode_local(self, clean_env):
        cfg = Config()
        assert cfg.is_cui_safe_mode() is True

    def test_is_cui_safe_mode_cloud(self, clean_env):
        clean_env.setenv("AI_MODE", "cloud")
        cfg = Config()
        assert cfg.is_cui_safe_mode() is False

    def test_sanitize_data_parses_true(self, clean_env):
        clean_env.setenv("SANITIZE_DATA", "true")
        assert Config().SANITIZE_DATA is True
        clean_env.setenv("SANITIZE_DATA", "1")
        assert Config().SANITIZE_DATA is True
        clean_env.setenv("SANITIZE_DATA", "yes")
        assert Config().SANITIZE_DATA is True

    def test_sanitize_data_parses_false(self, clean_env):
        clean_env.setenv("SANITIZE_DATA", "false")
        assert Config().SANITIZE_DATA is False
        clean_env.setenv("SANITIZE_DATA", "no")
        assert Config().SANITIZE_DATA is False

    def test_overrides_applied(self, clean_env):
        clean_env.setenv("OLLAMA_URL", "http://remote:9999")
        clean_env.setenv("OLLAMA_MODEL", "llama3")
        clean_env.setenv("MAX_FILE_SIZE", "10485760")
        cfg = Config()
        assert cfg.OLLAMA_URL == "http://remote:9999"
        assert cfg.OLLAMA_MODEL == "llama3"
        assert cfg.MAX_FILE_SIZE == 10485760

    def test_load_config_returns_fresh_instance(self, clean_env):
        cfg1 = load_config()
        clean_env.setenv("AI_MODE", "cloud")
        cfg2 = load_config()
        assert cfg1.AI_MODE == "local"
        assert cfg2.AI_MODE == "cloud"

    def test_as_dict_masks_api_key(self, clean_env):
        clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret-key-12345")
        snap = Config().as_dict()
        assert "super" not in str(snap)
        assert "secret" not in str(snap)
        assert snap["anthropic_api_key_set"] is not None
