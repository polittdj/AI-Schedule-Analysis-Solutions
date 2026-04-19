"""Tests for per-relation-type bounds and driving-slack formulas.

Covers BUILD-PLAN §5 M4 E4-E7 (FS/SS/FF/SF + lead/lag) and
``driving-slack-and-paths §2.4`` worked-example DS values.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.relations import (
    backward_link_bound,
    forward_link_bound,
    link_driving_slack_minutes,
)
from app.models.calendar import Calendar
from app.models.enums import RelationType


@pytest.fixture
def cal() -> Calendar:
    return Calendar(name="Std")


def _dt(d: int, h: int = 8) -> datetime:
    return datetime(2026, 4, d, h, 0, tzinfo=UTC)


# ---- Forward-pass bounds ------------------------------------------


def test_fs_forward_bound_is_es_from_pred_ef(cal: Calendar) -> None:
    field, dt = forward_link_bound(RelationType.FS, _dt(20), _dt(21), 0, cal)
    assert field == "ES"
    assert dt == _dt(21)


def test_fs_forward_lag_shifts_later(cal: Calendar) -> None:
    # +120 min lag → ES = pred EF + 2 hours, same day.
    _, dt = forward_link_bound(RelationType.FS, _dt(20), _dt(21, 10), 120, cal)
    assert dt == _dt(21, 12)


def test_fs_forward_lead_shifts_earlier(cal: Calendar) -> None:
    # -120 min lead → ES = pred EF - 2 hours, same day.
    _, dt = forward_link_bound(
        RelationType.FS, _dt(20), _dt(21, 12), -120, cal
    )
    assert dt == _dt(21, 10)


def test_ss_forward_from_pred_es(cal: Calendar) -> None:
    field, dt = forward_link_bound(RelationType.SS, _dt(20, 10), _dt(22), 0, cal)
    assert field == "ES"
    # ES(succ) >= ES(pred) + lag: at Mon 10:00.
    assert dt == _dt(20, 10)


def test_ff_forward_imposes_ef_bound(cal: Calendar) -> None:
    field, dt = forward_link_bound(RelationType.FF, _dt(20), _dt(21, 12), 0, cal)
    assert field == "EF"
    assert dt == _dt(21, 12)


def test_sf_forward_imposes_ef_bound(cal: Calendar) -> None:
    field, dt = forward_link_bound(RelationType.SF, _dt(20, 10), _dt(22), 0, cal)
    assert field == "EF"
    assert dt == _dt(20, 10)


def test_forward_unknown_relation_raises(cal: Calendar) -> None:
    with pytest.raises(ValueError):
        forward_link_bound(99, _dt(20), _dt(20), 0, cal)  # type: ignore[arg-type]


# ---- Backward-pass bounds -----------------------------------------


def test_fs_backward_bound_is_lf(cal: Calendar) -> None:
    field, dt = backward_link_bound(RelationType.FS, _dt(22, 10), _dt(23), 0, cal)
    assert field == "LF"
    # LF(pred) <= LS(succ) - lag: at Wed 10:00 (zero lag, same-day subtract).
    assert dt == _dt(22, 10)


def test_fs_backward_with_lag(cal: Calendar) -> None:
    field, dt = backward_link_bound(RelationType.FS, _dt(22, 10), _dt(22, 12), 60, cal)
    assert field == "LF"
    assert dt == _dt(22, 9)


def test_ss_backward_bound_is_ls(cal: Calendar) -> None:
    field, _ = backward_link_bound(RelationType.SS, _dt(22), _dt(23), 0, cal)
    assert field == "LS"


def test_ff_backward_bound_is_lf(cal: Calendar) -> None:
    field, _ = backward_link_bound(RelationType.FF, _dt(22), _dt(23), 0, cal)
    assert field == "LF"


def test_sf_backward_bound_is_ls(cal: Calendar) -> None:
    field, _ = backward_link_bound(RelationType.SF, _dt(22), _dt(23), 0, cal)
    assert field == "LS"


def test_backward_unknown_relation_raises(cal: Calendar) -> None:
    with pytest.raises(ValueError):
        backward_link_bound(99, _dt(22), _dt(23), 0, cal)  # type: ignore[arg-type]


# ---- Link driving slack -------------------------------------------


def test_link_driving_slack_fs_zero(cal: Calendar) -> None:
    # succ ES == pred EF → DS 0.
    ds = link_driving_slack_minutes(
        RelationType.FS, _dt(20), _dt(20, 16), _dt(21, 8), _dt(21, 16), 0, cal
    )
    assert ds == 0


def test_link_driving_slack_fs_positive(cal: Calendar) -> None:
    # pred EF Mon 12:00, succ ES Tue 08:00 → 4 working hours + 0 weekend
    # Actually: Mon 12:00 to Mon 16:00 = 240 min, then Mon 16:00 to
    # Tue 08:00 = 0 working min, so DS = 240.
    ds = link_driving_slack_minutes(
        RelationType.FS, _dt(20, 8), _dt(20, 12), _dt(21, 8), _dt(21, 16), 0, cal
    )
    assert ds == 240


def test_link_driving_slack_ss(cal: Calendar) -> None:
    # Both ES same day: DS 0.
    ds = link_driving_slack_minutes(
        RelationType.SS, _dt(20, 8), _dt(20, 16), _dt(20, 8), _dt(20, 16), 0, cal
    )
    assert ds == 0


def test_link_driving_slack_ff(cal: Calendar) -> None:
    ds = link_driving_slack_minutes(
        RelationType.FF, _dt(20), _dt(20, 16), _dt(20), _dt(20, 16), 0, cal
    )
    assert ds == 0


def test_link_driving_slack_sf_nonzero(cal: Calendar) -> None:
    # pred starts Mon 08:00, succ finishes Tue 16:00.
    # Working minutes Mon 08:00 → Tue 16:00 = 2 * 480 = 960.
    ds = link_driving_slack_minutes(
        RelationType.SF, _dt(20, 8), _dt(20, 16), _dt(21, 8), _dt(21, 16), 0, cal
    )
    assert ds == 960


def test_link_driving_slack_fs_with_lag_subtracted(cal: Calendar) -> None:
    # Gap 240 min, lag 120 → DS 120.
    ds = link_driving_slack_minutes(
        RelationType.FS, _dt(20, 8), _dt(20, 12), _dt(21, 8), _dt(21, 16), 120, cal
    )
    assert ds == 120


def test_link_driving_slack_unknown_relation(cal: Calendar) -> None:
    with pytest.raises(ValueError):
        link_driving_slack_minutes(
            99,  # type: ignore[arg-type]
            _dt(20), _dt(20), _dt(20), _dt(20), 0, cal,
        )


def test_e4_fs_positive_lag_shifts_successor_later(cal: Calendar) -> None:
    """E4: positive lag shifts successor ES later."""
    _, with_lag = forward_link_bound(RelationType.FS, _dt(20), _dt(20, 16), 120, cal)
    _, no_lag = forward_link_bound(RelationType.FS, _dt(20), _dt(20, 16), 0, cal)
    assert with_lag > no_lag


def test_e4_fs_negative_lag_shifts_successor_earlier(cal: Calendar) -> None:
    """E4: negative lag (lead) shifts successor earlier."""
    _, with_lead = forward_link_bound(
        RelationType.FS, _dt(20), _dt(20, 12), -60, cal
    )
    _, no_lag = forward_link_bound(RelationType.FS, _dt(20), _dt(20, 12), 0, cal)
    assert with_lead < no_lag


def test_e5_ss_uses_pred_es_not_ef(cal: Calendar) -> None:
    """E5: SS successor ES = pred ES + lag (not pred EF)."""
    pred_es = _dt(20, 8)
    pred_ef = _dt(25, 16)  # deliberately far later than pred_es
    _, bound = forward_link_bound(RelationType.SS, pred_es, pred_ef, 0, cal)
    # Bound tracks pred_es, not pred_ef.
    assert bound == pred_es


def test_e6_ff_uses_pred_ef(cal: Calendar) -> None:
    """E6: FF successor EF = pred EF + lag (not pred ES)."""
    _, bound_from_ef = forward_link_bound(
        RelationType.FF, _dt(20, 8), _dt(21, 12), 0, cal
    )
    # Same pred_ef, different pred_es → FF bound unchanged.
    _, bound_from_ef_different_es = forward_link_bound(
        RelationType.FF, _dt(19, 8), _dt(21, 12), 0, cal
    )
    assert bound_from_ef == bound_from_ef_different_es == _dt(21, 12)


def test_e7_sf_uses_pred_es(cal: Calendar) -> None:
    """E7: SF successor EF = pred ES + lag."""
    _, bound = forward_link_bound(
        RelationType.SF, _dt(20, 8), _dt(21, 16), 0, cal
    )
    assert bound == _dt(20, 8)
