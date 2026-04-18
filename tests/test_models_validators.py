"""Cross-model validator and import-smoke tests.

Covers Milestone 2 AC A7 (no forbidden SDK imports), A8 (public API
clean import), and exercises the G1–G12 gotcha catalogue at package
level to guarantee the smoke surface matches what downstream
milestones will consume.
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime

import pytest


class TestPublicApiSmoke:
    """AC A8: the documented public API imports cleanly."""

    def test_public_symbols_importable(self) -> None:
        from app.models import (
            Calendar,
            CalendarException,
            ConstraintType,
            Relation,
            RelationType,
            Resource,
            ResourceAssignment,
            ResourceType,
            Schedule,
            Task,
            TaskType,
            WorkingTime,
        )

        for sym in (
            Schedule,
            Task,
            Relation,
            Resource,
            ResourceAssignment,
            Calendar,
            CalendarException,
            WorkingTime,
            ConstraintType,
            RelationType,
            ResourceType,
            TaskType,
        ):
            assert sym is not None

    def test_star_exports(self) -> None:
        import app.models as m

        expected = {
            "DATE_BEARING_CONSTRAINTS",
            "HARD_CONSTRAINTS",
            "Calendar",
            "CalendarException",
            "ConstraintType",
            "Relation",
            "RelationType",
            "Resource",
            "ResourceAssignment",
            "ResourceType",
            "Schedule",
            "Task",
            "TaskType",
            "WorkingTime",
        }
        assert expected <= set(m.__all__)


class TestNoForbiddenImports:
    """AC A7: ``app.models`` pulls in no COM / AI / cloud SDK."""

    FORBIDDEN = {
        "win32com",
        "pythoncom",
        "ollama",
        "anthropic",
        "requests",
        "httpx",
        "urllib3",
        "boto3",
        "jpype",
        "mpxj",
    }

    def test_forbidden_modules_absent_after_model_import(self) -> None:
        # Force a fresh import by clearing any cached app.models.*
        for name in list(sys.modules):
            if name == "app.models" or name.startswith("app.models."):
                del sys.modules[name]

        importlib.import_module("app.models")

        leaked = self.FORBIDDEN & set(sys.modules)
        assert leaked == set(), f"forbidden modules imported: {leaked}"


class TestGotchaCatalogueAtPackageLevel:
    """Cross-file regression gate: every gotcha fails through the
    public API the same way it fails inside its own module."""

    def test_g1_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import Task

        with pytest.raises(ValidationError):
            Task(
                unique_id=1,
                task_id=1,
                name="x",
                start=datetime(2026, 4, 1, 8),  # naive
            )

    def test_g3_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import Task

        with pytest.raises(ValidationError):
            Task(unique_id=0, task_id=0, name="x")

    def test_g4_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import Relation

        with pytest.raises(ValidationError):
            Relation(predecessor_unique_id=5, successor_unique_id=5)

    def test_g6_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import ConstraintType, Task

        with pytest.raises(ValidationError):
            Task(
                unique_id=1,
                task_id=1,
                name="x",
                constraint_type=ConstraintType.AS_LATE_AS_POSSIBLE,
                constraint_date=datetime(2026, 4, 1, 8, tzinfo=UTC),
            )

    def test_g7_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import ConstraintType, Task

        with pytest.raises(ValidationError):
            Task(
                unique_id=1,
                task_id=1,
                name="x",
                constraint_type=ConstraintType.MUST_FINISH_ON,
            )

    def test_g10_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import Schedule, Task

        with pytest.raises(ValidationError):
            Schedule(
                tasks=[
                    Task(unique_id=1, task_id=1, name="a"),
                    Task(unique_id=1, task_id=2, name="b"),
                ]
            )

    def test_g11_package_level(self) -> None:
        from pydantic import ValidationError

        from app.models import Relation, Schedule, Task

        with pytest.raises(ValidationError):
            Schedule(
                tasks=[Task(unique_id=1, task_id=1, name="a")],
                relations=[Relation(predecessor_unique_id=1, successor_unique_id=99)],
            )

    def test_g12_package_level(self) -> None:
        from app.models import Schedule

        assert Schedule().tasks == []


class TestModelCopyImmutability:
    """BUILD-PLAN §2 lock: downstream mutation goes through
    ``model_copy(update=...)``; the model must cooperate."""

    def test_schedule_model_copy_preserves_invariants(self) -> None:
        from app.models import Schedule, Task

        s = Schedule(tasks=[Task(unique_id=1, task_id=1, name="a")])
        s2 = s.model_copy(update={"name": "cloned"})
        assert s2.name == "cloned"
        assert s.name == ""
        # The clone still holds a valid task list.
        assert s2.tasks[0].unique_id == 1
