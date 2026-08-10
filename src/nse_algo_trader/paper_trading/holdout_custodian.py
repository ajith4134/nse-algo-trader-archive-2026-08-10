"""Holdout custodian — the one-shot final-test seal (L2 validation; docs/research/166).

López de Prado's holdout discipline: the last slice of the timeline is reserved
as a *never-touched* out-of-sample window. Research, optimization, hyper-parameter
tuning, strategy selection — every activity that can overfit — is allowed to see
ONLY the earlier RESEARCH window. The most-recent HOLDOUT window is sealed and
refuses to hand back its returns until an explicit, logged, one-way
`unseal_for_final_validation` is called, exactly once, for the single final
validation pass. A holdout you peek at twice is no longer a holdout.

This custodian is the enforcement mechanism, not a convention:

* `partition_returns` is the SAFE research accessor — it always returns the
  research returns and withholds the holdout returns (empty slot) while sealed,
  so research code physically cannot read the final window through it.
* `holdout_returns` (and any holdout accessor) RAISES `HoldoutSealedError` until
  unsealed — the seal is a hard gate, not a warning.
* `unseal_for_final_validation` is ONE-WAY within an instance: it logs the reason
  and an injected-clock timestamp, increments the unseal counter, and a SECOND
  unseal is recorded as a violation AND raised (`HoldoutSealViolationError`) so
  the one-shot breach is surfaced, never silently allowed.

Sourcing (docs/research/166 / Rule O-1a): sklearn/mlxtend `PredefinedHoldoutSplit`,
deepchecks train-test-validation, and mlfinlab splitters were surveyed — all
merely *split* indices; none ENFORCE a sealed, unseal-gated, audited one-shot
holdout. Bespoke by necessity; the boundary math mirrors the time-ordered,
most-recent-fraction conventions used in `combinatorial_purged_cross_validation`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Minimum observations to define both a research and a holdout window: with a
# single date there is nothing to hold out.
_MINIMUM_TIMELINE_LENGTH = 2


class HoldoutSealedError(RuntimeError):
    """Raised when holdout data is requested before an explicit unseal."""


class HoldoutSealViolationError(RuntimeError):
    """Raised when the one-shot holdout is unsealed more than once."""


def _default_iso_clock() -> str:
    """UTC ISO-8601 timestamp; the production audit clock for unseal events."""
    return datetime.now(UTC).isoformat()


def _partition_timeline_into_windows(
    time_ordered_dates: Sequence[date], holdout_fraction: float
) -> tuple[tuple[date, date], tuple[date, date]]:
    """Split a sorted, de-duplicated date timeline into (research, holdout) windows.

    The most-RECENT `holdout_fraction` of the observations becomes the holdout;
    the earlier observations are the research window. The boundary is a REAL date
    taken from the timeline (never hard-coded), and at least one observation is
    guaranteed on each side.
    """
    observation_count = len(time_ordered_dates)
    holdout_length = round(observation_count * holdout_fraction)
    # Guarantee a non-empty window on each side regardless of rounding.
    holdout_length = max(1, min(observation_count - 1, holdout_length))
    boundary_index = observation_count - holdout_length
    research_window = (time_ordered_dates[0], time_ordered_dates[boundary_index - 1])
    holdout_window = (time_ordered_dates[boundary_index], time_ordered_dates[-1])
    return research_window, holdout_window


class HoldoutCustodian:
    """Guardian that seals the most-recent slice of a timeline as a one-shot holdout.

    Construct from a time-ordered set of observation dates (the primary path,
    which honours real trading-day gaps) or from a `(start_date, end_date)` span
    via :meth:`from_date_span`. The holdout is the most-recent `holdout_fraction`
    of the timeline; the earlier part is the research window.
    """

    def __init__(
        self,
        observation_dates: Sequence[date],
        holdout_fraction: float = 0.2,
        *,
        audit_clock: Callable[[], str] | None = None,
    ) -> None:
        if not 0.0 < holdout_fraction < 1.0:
            raise ValueError(
                f"holdout_fraction must lie in the open interval (0, 1); got {holdout_fraction!r}"
            )
        time_ordered_dates = sorted(set(observation_dates))
        if len(time_ordered_dates) < _MINIMUM_TIMELINE_LENGTH:
            raise ValueError(
                "need at least two distinct observation dates to seal a holdout; "
                f"got {len(time_ordered_dates)}"
            )

        self._holdout_fraction = holdout_fraction
        self._audit_clock: Callable[[], str] = audit_clock or _default_iso_clock
        (
            self._research_window,
            self._holdout_window,
        ) = _partition_timeline_into_windows(time_ordered_dates, holdout_fraction)

        # Seal + audit state. The custodian starts SEALED.
        self._sealed: bool = True
        self._unseal_count: int = 0
        self._unseal_reasons: list[str] = []
        self._unseal_events: list[dict[str, str]] = []
        self._violations: list[str] = []

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_date_span(
        cls,
        start_date: date,
        end_date: date,
        holdout_fraction: float = 0.2,
        *,
        audit_clock: Callable[[], str] | None = None,
    ) -> HoldoutCustodian:
        """Build a custodian over a contiguous daily span [start_date, end_date]."""
        if end_date <= start_date:
            raise ValueError(
                f"end_date ({end_date}) must be strictly after start_date ({start_date})"
            )
        span_length_days = (end_date - start_date).days + 1
        daily_dates = [start_date + timedelta(days=offset) for offset in range(span_length_days)]
        return cls(daily_dates, holdout_fraction, audit_clock=audit_clock)

    # ------------------------------------------------------------------ #
    # Windows / membership
    # ------------------------------------------------------------------ #
    def research_window(self) -> tuple[date, date]:
        """(first_research_date, last_research_date) — the in-sample window."""
        return self._research_window

    def holdout_window(self) -> tuple[date, date]:
        """(first_holdout_date, last_holdout_date) — the sealed out-of-sample window."""
        return self._holdout_window

    def holdout_boundary_date(self) -> date:
        """First date of the holdout window — the seal boundary (a real timeline date)."""
        return self._holdout_window[0]

    def is_in_research(self, observation_date: date) -> bool:
        """True iff the date falls within the research (in-sample) window."""
        research_start, research_end = self._research_window
        return research_start <= observation_date <= research_end

    def is_in_holdout(self, observation_date: date) -> bool:
        """True iff the date falls within the holdout (out-of-sample) window."""
        holdout_start, holdout_end = self._holdout_window
        return holdout_start <= observation_date <= holdout_end

    # ------------------------------------------------------------------ #
    # Safe (research) accessors
    # ------------------------------------------------------------------ #
    def research_returns(self, returns_by_date: Mapping[date, float]) -> list[float]:
        """Research-window returns only, in date order. Never touches the holdout."""
        return [
            returns_by_date[observation_date]
            for observation_date in sorted(returns_by_date)
            if self.is_in_research(observation_date)
        ]

    def partition_returns(
        self, returns_by_date: Mapping[date, float]
    ) -> tuple[list[float], list[float]]:
        """SAFE partition → (research_returns, holdout_returns) in date order.

        The research list is always fully populated. The holdout list is
        WITHHELD (returned empty) while the custodian is sealed, so research code
        that only ever calls this accessor cannot read the final window. Once
        unsealed, the holdout list is populated for the final-validation pass.
        Dates outside the timeline are silently excluded from both lists.
        """
        research_returns = self.research_returns(returns_by_date)
        if self._sealed:
            return research_returns, []
        return research_returns, self._collect_holdout_returns(returns_by_date)

    # ------------------------------------------------------------------ #
    # Sealed (holdout) accessor
    # ------------------------------------------------------------------ #
    def holdout_returns(self, returns_by_date: Mapping[date, float]) -> list[float]:
        """Holdout-window returns, in date order. RAISES until explicitly unsealed."""
        if self._sealed:
            raise HoldoutSealedError(
                "holdout window is sealed; call unseal_for_final_validation(reason) "
                "exactly once before reading holdout returns (one-shot discipline)"
            )
        return self._collect_holdout_returns(returns_by_date)

    def _collect_holdout_returns(self, returns_by_date: Mapping[date, float]) -> list[float]:
        return [
            returns_by_date[observation_date]
            for observation_date in sorted(returns_by_date)
            if self.is_in_holdout(observation_date)
        ]

    # ------------------------------------------------------------------ #
    # One-way unseal
    # ------------------------------------------------------------------ #
    def unseal_for_final_validation(self, reason: str) -> None:
        """One-way unseal of the holdout for the single final-validation pass.

        Logs `(reason, timestamp)` via the injected audit clock and increments the
        unseal counter. Calling it a SECOND time is a one-shot-discipline
        violation: the attempt is recorded in the audit trail AND
        `HoldoutSealViolationError` is raised so the breach is surfaced.
        """
        if not reason or not reason.strip():
            raise ValueError("unseal reason must be a non-empty, human-readable string")

        timestamp = self._audit_clock()
        self._unseal_count += 1
        self._unseal_reasons.append(reason)
        self._unseal_events.append({"reason": reason, "timestamp": timestamp})

        if self._unseal_count > 1:
            violation = (
                f"one-shot holdout discipline VIOLATED: unseal_for_final_validation called "
                f"{self._unseal_count} times (latest reason={reason!r} at {timestamp})"
            )
            self._violations.append(violation)
            _LOGGER.error(violation)
            raise HoldoutSealViolationError(violation)

        self._sealed = False
        _LOGGER.warning(
            "Holdout UNSEALED for final validation (reason=%r at %s); this is one-shot.",
            reason,
            timestamp,
        )

    # ------------------------------------------------------------------ #
    # Audit surface
    # ------------------------------------------------------------------ #
    def seal_status(self) -> dict[str, Any]:
        """Audit/dashboard snapshot of the seal and its unseal history."""
        return {
            "sealed": self._sealed,
            "unseal_count": self._unseal_count,
            "unseal_reasons": list(self._unseal_reasons),
            "unseal_events": [dict(event) for event in self._unseal_events],
            "violations": list(self._violations),
            "holdout_fraction": self._holdout_fraction,
            "research_window": self._research_window,
            "holdout_window": self._holdout_window,
            "holdout_boundary_date": self.holdout_boundary_date(),
        }
