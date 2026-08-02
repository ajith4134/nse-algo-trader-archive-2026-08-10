"""The system's EXPLICIT utility function (Trunk XIV AXIOLOGY; research/153). PURE — no I/O.

Makes the previously-implicit objective explicit: a scalar utility over the realized-return series with
a NAMED, inspectable decomposition —
    U = w_return·mean − w_risk·volatility − w_drawdown·max_drawdown − w_tail·tail_loss(CVaR-5%)
The `ValueWeights` ARE the system's stated values (capital-preservation-leaning by default: risk,
drawdown and the tail are weighted above raw return). Risk measures are standard formulas (mean-var,
max-drawdown, CVaR) built bespoke — portfolio-allocation libs (Riskfolio-Lib/skfolio) are the wrong
shape (they optimise weights; we SCORE realized outcomes), research/153 §Sourcing.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

_CVAR_TAIL_FRACTION = 0.05  # CVaR-5%: the mean of the worst 5% of returns


@dataclass(frozen=True)
class ValueWeights:
    """The system's STATED values, made explicit. Higher weight = the system cares more about it."""

    w_return: float = 1.0      # reward realized return
    w_risk: float = 1.0        # penalise volatility
    w_drawdown: float = 1.5    # penalise the worst peak-to-trough loss (capital preservation)
    w_tail: float = 2.0        # penalise the tail (CVaR) most — survive the bad days


@dataclass(frozen=True)
class UtilityScore:
    utility: float
    # the raw value metrics (all as fractions; drawdown/tail_loss are positive loss magnitudes)
    mean_return: float
    volatility: float
    max_drawdown: float
    tail_loss_cvar5: float
    sample_size: int
    # the named contribution of each value term to the scalar utility (sum = utility)
    return_term: float
    risk_term: float
    drawdown_term: float
    tail_term: float
    summary: str = ""


def _max_drawdown(returns) -> float:
    """Worst peak-to-trough drop of the cumulative (additive) return path, as a positive magnitude."""
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for r in returns:
        cumulative += r
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return -worst  # positive magnitude


def _cvar_tail_loss(returns, tail_fraction: float = _CVAR_TAIL_FRACTION) -> float:
    """CVaR: mean of the worst `tail_fraction` of returns, returned as a positive loss magnitude."""
    ordered = sorted(returns)
    k = max(1, int(len(ordered) * tail_fraction))
    worst_slice = ordered[:k]
    return -min(0.0, statistics.fmean(worst_slice))  # positive when the tail is a loss


def evaluate_utility(returns, weights: ValueWeights = ValueWeights()) -> UtilityScore:
    """Score a realized-return series against the explicit value weights. Empty → zeroed utility."""
    returns = [float(r) for r in returns]
    if not returns:
        return UtilityScore(0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, "no returns to evaluate")

    mean_return = statistics.fmean(returns)
    volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    max_drawdown = _max_drawdown(returns)
    tail_loss = _cvar_tail_loss(returns)

    return_term = weights.w_return * mean_return
    risk_term = -weights.w_risk * volatility
    drawdown_term = -weights.w_drawdown * max_drawdown
    tail_term = -weights.w_tail * tail_loss
    utility = return_term + risk_term + drawdown_term + tail_term

    summary = (
        f"U={utility:+.4f} = return {return_term:+.4f} + risk {risk_term:+.4f} + "
        f"drawdown {drawdown_term:+.4f} + tail {tail_term:+.4f}  (n={len(returns)}, "
        f"mean {mean_return:+.2%}, vol {volatility:.2%}, maxDD {max_drawdown:.2%}, CVaR5 {tail_loss:.2%})"
    )
    return UtilityScore(
        utility=utility, mean_return=mean_return, volatility=volatility, max_drawdown=max_drawdown,
        tail_loss_cvar5=tail_loss, sample_size=len(returns), return_term=return_term, risk_term=risk_term,
        drawdown_term=drawdown_term, tail_term=tail_term, summary=summary)
