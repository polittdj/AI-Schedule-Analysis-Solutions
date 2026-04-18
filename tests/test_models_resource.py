"""Tests for ``app.models.resource``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import ResourceType
from app.models.resource import Resource, ResourceAssignment


class TestResource:
    def test_minimal_construction(self) -> None:
        r = Resource(unique_id=1, resource_id=1, name="Engineer A")
        assert r.unique_id == 1
        assert r.resource_type is ResourceType.WORK
        assert r.max_units == 1.0

    def test_g3_zero_unique_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Resource(unique_id=0, resource_id=0, name="X")

    def test_g3_negative_unique_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Resource(unique_id=-1, resource_id=1, name="X")

    def test_resource_id_zero_allowed(self) -> None:
        """``resource_id`` is a display row; 0 is permissible."""
        r = Resource(unique_id=1, resource_id=0, name="Pool")
        assert r.resource_id == 0

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Resource(unique_id=1, resource_id=1, name="X", surprise=True)  # type: ignore[call-arg]

    def test_material_resource(self) -> None:
        r = Resource(
            unique_id=2, resource_id=2, name="Concrete", resource_type=ResourceType.MATERIAL
        )
        assert r.resource_type is ResourceType.MATERIAL


class TestResourceAssignment:
    def test_minimal_assignment(self) -> None:
        a = ResourceAssignment(resource_unique_id=1, task_unique_id=10)
        assert a.units == 1.0
        assert a.work_minutes == 0

    def test_g3_zero_resource_uid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResourceAssignment(resource_unique_id=0, task_unique_id=10)

    def test_g3_zero_task_uid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResourceAssignment(resource_unique_id=1, task_unique_id=0)

    def test_g2_negative_work_rejected(self) -> None:
        """G2 generalized to assignments: negative work minutes invalid."""
        with pytest.raises(ValidationError):
            ResourceAssignment(resource_unique_id=1, task_unique_id=2, work_minutes=-60)

    def test_negative_units_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResourceAssignment(resource_unique_id=1, task_unique_id=2, units=-0.5)

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ResourceAssignment(resource_unique_id=1, task_unique_id=2, oops=1)  # type: ignore[call-arg]
