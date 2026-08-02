"""Apply fractional size-down levers to an INDIVISIBLE lot count, correctly.

Option lots cannot be subdivided: an NSE option position is a whole number of lots or nothing.
The size-down levers elsewhere in the system (debate risk, index-level caution, organism vitality,
global-workspace caution) are fractional multipliers designed for share quantities in the hundreds,
where `int(quantity * 0.90)` is a harmless approximation.

Applied to a lot count the same arithmetic is catastrophic: `int(1 * 0.90) == 0`, so a lever that
means "trim this position by 10%" silently means "never place this order". That defect blocked
100% of option entries (see `docs/research/live_session_diagnosis_2026-07-27.md` §7a) — the bot
never opened a single index-option position.

This module is the ONE place that decision is made, so every option entry site shares identical,
tested semantics:

* multipliers are **composed once** and applied **once** — never truncated stepwise, which floors
  to zero twice on a small base;
* the composed fraction is applied with **round-half-up**, which picks the nearest *achievable*
  position to the intended exposure — so `0.9` of one lot rounds UP to one lot (still tradable,
  still smaller than the un-trimmed intent) while `0.25` of one lot rounds DOWN to zero (a quarter
  lot genuinely cannot be traded);
* composition is **tighten-only by construction** — every multiplier is clamped into `[0, 1]`
  before multiplying, so no configuration or upstream bug can ever *increase* a position;
* a non-finite multiplier (NaN/inf) is treated as a **veto**, never silently as 1.0;
* every stand-aside carries a human-readable reason — never a bare `0` (Rule O.3: no silent skips).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: A lever at exactly this value is an explicit veto ("do not trade"), distinct from a trim.
VETOING_SIZE_DOWN_MULTIPLIER = 0.0


@dataclass(frozen=True)
class DiscreteLotSizeDownDecision:
    """How many whole lots survive the size-down levers, and why."""

    granted_lots: int
    #: `base_lots * composed_multiplier` before rounding — kept for logging/telemetry, so an
    #: operator can see how close a stood-aside candidate was to being tradable.
    intended_lots: float
    composed_multiplier: float
    #: None when lots were granted; otherwise why the entry was refused.
    stood_aside_reason: str | None

    @property
    def permits_order(self) -> bool:
        return self.granted_lots > 0


def compose_size_down_multipliers(*multipliers: float) -> float:
    """Fold size-down levers into a single tighten-only fraction in `[0, 1]`.

    Each lever is clamped into `[0, 1]` BEFORE multiplying, so a lever that erroneously reports a
    value above 1.0 can never up-size a position. A non-finite lever is treated as a veto (0.0)
    rather than ignored: unreadable risk telemetry is not evidence that trading is safe.
    """
    composed = 1.0
    for multiplier in multipliers:
        value = float(multiplier)
        if not math.isfinite(value):
            return VETOING_SIZE_DOWN_MULTIPLIER
        composed *= max(0.0, min(value, 1.0))
    return composed


def size_down_discrete_lots(
    base_lots: int,
    composed_multiplier: float,
    minimum_tradable_lots: int = 1,
) -> DiscreteLotSizeDownDecision:
    """Resolve a risk-sized lot count plus a composed size-down fraction into whole tradable lots.

    `base_lots` is the count the risk gate already approved (NOT a hard-coded 1). The composed
    fraction is applied once, with round-half-up, and the result is refused rather than silently
    floored when it lands below the minimum tradable unit.
    """
    if base_lots <= 0:
        return DiscreteLotSizeDownDecision(
            granted_lots=0,
            intended_lots=0.0,
            composed_multiplier=composed_multiplier,
            stood_aside_reason="risk gate approved no lots",
        )
    if minimum_tradable_lots < 1:
        raise ValueError("minimum_tradable_lots must be at least 1 — lots are indivisible")
    if not math.isfinite(composed_multiplier):
        return DiscreteLotSizeDownDecision(
            granted_lots=0,
            intended_lots=0.0,
            composed_multiplier=composed_multiplier,
            stood_aside_reason="a size-down lever reported a non-finite multiplier",
        )
    if composed_multiplier <= VETOING_SIZE_DOWN_MULTIPLIER:
        return DiscreteLotSizeDownDecision(
            granted_lots=0,
            intended_lots=0.0,
            composed_multiplier=0.0,
            stood_aside_reason="a size-down lever vetoed the entry (multiplier 0)",
        )

    intended_lots = base_lots * composed_multiplier
    # Round-half-up: the nearest ACHIEVABLE position to the intended exposure. Python's built-in
    # round() is banker's rounding (round-half-to-EVEN), which would send an intended 0.5 lots to 0
    # and 1.5 lots to 2 — inconsistent at exactly the boundary that decides trade-or-not.
    granted_lots = int(math.floor(intended_lots + 0.5))

    if granted_lots < minimum_tradable_lots:
        return DiscreteLotSizeDownDecision(
            granted_lots=0,
            intended_lots=intended_lots,
            composed_multiplier=composed_multiplier,
            stood_aside_reason=(
                f"size-down levers reduced {base_lots} lot(s) to an intended "
                f"{intended_lots:.3f} lots, below the {minimum_tradable_lots}-lot minimum "
                f"tradable unit (composed multiplier {composed_multiplier:.4f})"
            ),
        )
    return DiscreteLotSizeDownDecision(
        granted_lots=granted_lots,
        intended_lots=intended_lots,
        composed_multiplier=composed_multiplier,
        stood_aside_reason=None,
    )
