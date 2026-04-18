"""Shared validator utilities for the core data model.

These helpers are model-internal. They are not part of the public API
exposed via ``app.models.__init__``.
"""

from __future__ import annotations

from datetime import datetime


def require_tz_aware(value: datetime | None) -> datetime | None:
    """Reject naive ``datetime`` instances.

    Per Milestone 2 Gotcha G1: every date field on the model is
    timezone-aware. The Milestone 3 COM adapter converts MS-Project's
    locale-formatted ``datetime`` (Gotcha 10 in
    ``mpp-parsing-com-automation §3.10``) into a UTC-aware ISO 8601
    value before populating the model.
    """
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime must be timezone-aware (UTC or named tz)")
    return value
