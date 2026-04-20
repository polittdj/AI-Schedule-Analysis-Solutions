"""Overlay exception hierarchy.

Mirrors the split in ``app.metrics.exceptions`` and
``app.engine.exceptions``: structured errors raised when an overlay
rule cannot run safely, with ordinary informational output reserved
for :class:`~app.overlay.nasa_overlay.OverlayResult`. Per BUILD-PLAN
§6 AC bar #3 and ``dcma-14-point-assessment §6 Rule 1``
(indicators-not-verdicts), a defective input fails loudly rather
than silently producing a misleading adjusted denominator.

Authority:

* Indicator-not-verdict framing — ``dcma-14-point-assessment §6
  Rule 1``.
* M8 overlay is emit-side only; M11 is the downstream consumer.
"""

from __future__ import annotations


class OverlayError(Exception):
    """Base class for NASA SMH overlay errors.

    Catching :class:`OverlayError` traps every overlay-raised
    exception without also trapping unrelated :class:`Exception`
    subclasses raised by the metrics layer, the engine, or Pydantic.
    """


class MissingMetricResultError(OverlayError):
    """Raised when an overlay rule is invoked without a required
    :class:`~app.metrics.base.MetricResult`.

    Every overlay rule takes the underlying DCMA metric's result as
    an explicit argument — the overlay does not re-run the metric.
    Supplying ``None`` is a programming error, not a schedule finding.
    """

    def __init__(self, overlay_rule: str, metric_id: str) -> None:
        self.overlay_rule = overlay_rule
        self.metric_id = metric_id
        super().__init__(
            f"overlay rule {overlay_rule!r} requires a MetricResult "
            f"for {metric_id!r} but none was supplied "
            "(nasa-schedule-management §6)"
        )
