"""Lock in profit as it accumulates, and never give the lock back.

The operator's requirement: *"protect and lock the profit movement as profit increases"*, while still
*"catching big wins"*. Those pull against each other — the resolution is a stop that ratchets toward
profit and a target that retreats ahead of a running trade.

Everything here works in **profit space (rupees)**, never price space, because the three position
types disagree about which direction of price is good (a credit spread profits when the net premium
FALLS). One monotone quantity means one set of comparisons and no per-type sign handling — the sign
trap that would otherwise turn a protective stop into a guaranteed loss on spreads.

## Why "hybrid of all four" is implemented the way it is

**ARM trigger — earliest-of THREE, not four.** "Arm immediately from entry" fires at any profit > 0,
so OR-ing it with the others makes it always win and the rest decorative. It is therefore not a
fourth arm; it is the degenerate configuration of any arm with its threshold set to 0. The three real
yardsticks each guard a different failure mode:

* **R-multiple** — the primary, valid whenever the stop distance is meaningful.
* **ATR multiple** — covers a stop placed without regard to current volatility.
* **profit fraction** — the floor for a pathologically tight stop, where 1R is just noise.

**TRAIL distance — median of four candidates.** Taking `max` means the tightest method always wins
and the other three are decorative; `min` means the loosest always wins. Neither is a hybrid. The
median is a genuine consensus and is robust to any single candidate going pathological (an ATR spike,
a degenerate stop distance).

**The ratchet is enforced OUTSIDE the blend.** `locked_profit = max(previous, blended)` — so no
blend, parameter, or future candidate can ever loosen a lock. That invariant is the whole feature;
it is deliberately not a property of the arithmetic that produces the candidates.

See `docs/research/b23_profit_trail_and_excursion_design_2026-07-27.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

#: A trail that has never armed locks nothing. Distinct from "locked at breakeven" (0.0).
NOT_YET_LOCKED: float | None = None


@dataclass(frozen=True)
class ProfitTrailPolicy:
    """The tunable shape of the trail. Defaults are deliberately conservative: the trail protects
    from 1R, and the target extension is INERT (0.0) until it is earned — see Rule Q and the design
    doc §4. Moving targets outward converts a high-win-rate/small-win system into a
    lower-win-rate/larger-win one, which must be evidence-led, not assumed."""

    # -- arm triggers (earliest-of; each abstains when its input is unavailable) --
    arm_at_risk_multiple: float = 1.0
    arm_at_atr_multiple: float = 2.0
    arm_at_profit_fraction_of_notional: float = 0.01

    # -- trail-distance candidates (median of whichever can be computed) --
    give_back_fraction_of_peak: float = 0.50
    step_ratchet_risk_multiple: float = 1.0
    atr_chandelier_multiple: float = 2.5
    fixed_give_back_fraction: float = 0.35

    #: Rule Q: 0.0 = target never moves (inert). Raised only once persisted MFE proves that targets
    #: are capping runs. The MECHANISM is complete either way; only its activation is gated.
    target_extension_risk_multiple: float = 0.0


@dataclass
class ProfitTrailState:
    """The carried state of one position's trail. `locked_profit` is the ratchet."""

    locked_profit: float | None = NOT_YET_LOCKED
    armed_reason: str = ""
    #: Every arm/candidate that abstained, and why — so an inert trail is diagnosable rather than
    #: silently doing nothing (Rule O.3).
    abstained_inputs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_armed(self) -> bool:
        return self.locked_profit is not None


def _finite_positive(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        return None
    return numeric


def arm_trigger_reason(
    peak_profit: float,
    initial_risk_amount: float | None,
    atr_profit_amount: float | None,
    entry_notional: float | None,
    policy: ProfitTrailPolicy,
) -> tuple[str, tuple[str, ...]]:
    """Has the trade earned a trail yet? Returns (reason, abstained_inputs); reason "" = not armed.

    Earliest-of: whichever yardstick clears first arms the trail. An unavailable input ABSTAINS —
    it never contributes a fabricated threshold, and it is named in the returned abstentions.
    """
    abstained: list[str] = []

    risk = _finite_positive(initial_risk_amount)
    if risk is None:
        abstained.append("initial_risk (no usable stop distance)")
    elif peak_profit >= policy.arm_at_risk_multiple * risk:
        return (
            f"peak profit {peak_profit:.0f} ≥ {policy.arm_at_risk_multiple:g}R ({risk:.0f})",
            tuple(abstained),
        )

    atr_amount = _finite_positive(atr_profit_amount)
    if atr_amount is None:
        abstained.append("atr (no volatility estimate for this instrument)")
    elif peak_profit >= policy.arm_at_atr_multiple * atr_amount:
        return (
            f"peak profit {peak_profit:.0f} ≥ {policy.arm_at_atr_multiple:g}×ATR "
            f"({atr_amount:.0f})",
            tuple(abstained),
        )

    notional = _finite_positive(entry_notional)
    if notional is None:
        abstained.append("entry_notional")
    elif peak_profit >= policy.arm_at_profit_fraction_of_notional * notional:
        return (
            f"peak profit {peak_profit:.0f} ≥ "
            f"{policy.arm_at_profit_fraction_of_notional:.2%} of notional ({notional:.0f})",
            tuple(abstained),
        )

    return "", tuple(abstained)


def candidate_locked_profit_levels(
    peak_profit: float,
    initial_risk_amount: float | None,
    atr_profit_amount: float | None,
    policy: ProfitTrailPolicy,
) -> list[float]:
    """Every locked-profit level the four methods propose, for whichever inputs are available.

    Levels are clamped into `[0, peak_profit]`: a trail may never lock MORE than the trade has
    actually earned (that would exit instantly at a profit never reached), and never less than
    breakeven once armed.
    """
    candidates: list[float] = [
        peak_profit * policy.give_back_fraction_of_peak,          # give-back fraction
        peak_profit * (1.0 - policy.fixed_give_back_fraction),    # fixed give-back
    ]

    risk = _finite_positive(initial_risk_amount)
    if risk is not None:
        # Step ratchet: breakeven once 1R is banked, +1R at 2R, +2R at 3R …
        completed_r = math.floor(peak_profit / risk)
        candidates.append(max(0.0, (completed_r - 1)) * policy.step_ratchet_risk_multiple * risk)

    atr_amount = _finite_positive(atr_profit_amount)
    if atr_amount is not None:
        candidates.append(peak_profit - policy.atr_chandelier_multiple * atr_amount)

    return [min(max(level, 0.0), peak_profit) for level in candidates if math.isfinite(level)]


def update_profit_trail(
    trail: ProfitTrailState,
    peak_profit: float,
    initial_risk_amount: float | None = None,
    atr_profit_amount: float | None = None,
    entry_notional: float | None = None,
    policy: ProfitTrailPolicy | None = None,
) -> ProfitTrailState:
    """Advance the trail for one position against its peak profit so far.

    Returns a NEW state (the caller stores it), so the ratchet cannot be defeated by a partially
    applied mutation. `locked_profit` is guaranteed non-decreasing across any sequence of calls —
    that is the single most important property of this engine.
    """
    policy = policy or ProfitTrailPolicy()

    if not trail.is_armed:
        reason, abstained = arm_trigger_reason(
            peak_profit, initial_risk_amount, atr_profit_amount, entry_notional, policy
        )
        if not reason:
            return ProfitTrailState(
                locked_profit=NOT_YET_LOCKED, armed_reason="", abstained_inputs=abstained
            )
        trail = ProfitTrailState(
            locked_profit=0.0, armed_reason=reason, abstained_inputs=abstained
        )

    candidates = candidate_locked_profit_levels(
        peak_profit, initial_risk_amount, atr_profit_amount, policy
    )
    blended = median(candidates) if candidates else 0.0

    # THE RATCHET — enforced here, outside the blend, so no candidate, parameter or future method
    # can ever loosen an existing lock.
    previous = trail.locked_profit if trail.locked_profit is not None else 0.0
    return ProfitTrailState(
        locked_profit=max(previous, blended),
        armed_reason=trail.armed_reason,
        abstained_inputs=trail.abstained_inputs,
    )


def trail_exit_triggered(
    trail: ProfitTrailState, current_unrealised_profit: float | None
) -> bool:
    """Should this position be closed on the trail right now?

    Only ever True once armed — before that the position's ORIGINAL stop is the sole protection, so
    the trail can never widen risk or exit a trade early.
    """
    if not trail.is_armed or current_unrealised_profit is None:
        return False
    profit = float(current_unrealised_profit)
    if not math.isfinite(profit):
        return False
    return profit <= float(trail.locked_profit or 0.0)


def extended_target_profit(
    original_target_profit: float | None,
    peak_profit: float,
    initial_risk_amount: float | None,
    policy: ProfitTrailPolicy | None = None,
) -> float | None:
    """Push the profit target ahead of a running trade so it never caps a big win.

    `max(original, peak + k·R)` — while the trade keeps making new highs the target keeps retreating
    ahead of it, and the trail behind it becomes the real exit. Monotone outward only: it can never
    pull a target IN, which would be a hidden risk increase.

    Inert by default (`target_extension_risk_multiple = 0.0`) — Rule Q. The mechanism is complete;
    activation waits on persisted MFE evidence that targets are actually capping runs.
    """
    policy = policy or ProfitTrailPolicy()
    if original_target_profit is None:
        return None
    if policy.target_extension_risk_multiple <= 0.0:
        return original_target_profit
    risk = _finite_positive(initial_risk_amount)
    if risk is None:
        return original_target_profit
    return max(
        float(original_target_profit),
        peak_profit + policy.target_extension_risk_multiple * risk,
    )
