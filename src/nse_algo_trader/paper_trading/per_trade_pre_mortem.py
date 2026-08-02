"""Per-trade pre-mortem — entry-time Monte Carlo over real replay paths (Layer 7.5 slice 3;
research/107).

Before committing to a trade, imagine it has FAILED and quantify how. This runs a MONTE CARLO over
REAL historical post-trigger intraday paths (resampled from the replay store) to estimate the
trade's outcome DISTRIBUTION for a given stop/target: P(hit target), P(hit stop), P(neither →
timeout), the expected return, and the TAIL (CVaR of the worst 5%). Resampling whole real
close-return sequences (not a Gaussian) keeps the fat intraday tail the pre-mortem exists to expose.

Approximation (documented): outcomes are judged on the CLOSE path (touch when the running close
crosses stop/target, stop checked first — conservative), not intrabar high/low — so this is a
DISTRIBUTIONAL estimate, not an exact fill model (the real backtester uses high/low). PURE (no I/O;
the caller loads the sessions and passes the extracted paths).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
    detect_opening_range_breakout,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.universe_registry import Instrument

_CVAR_TAIL_FRACTION = 0.05


@dataclass(frozen=True)
class PreMortemForecast:
    """The Monte-Carlo outcome distribution for one trade setup. `conditional_value_at_risk_5pct`
    is the mean of the worst 5% of realized returns — the pre-mortem's tail-loss estimate."""

    trials: int
    probability_target: float
    probability_stop: float
    probability_timeout: float
    mean_return: float
    conditional_value_at_risk_5pct: float
    worst_case_return: float
    verdict: str


def extract_post_trigger_return_paths(
    sessions: list[tuple[list[PriceBar], Instrument]],
    config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
) -> list[list[float]]:
    """For each real session that produced an ORB signal, the per-bar CLOSE returns AFTER the
    trigger — one empirical post-entry path. These are the Monte-Carlo resampling pool."""
    paths: list[list[float]] = []
    for bars, instrument in sessions:
        signal = detect_opening_range_breakout(bars, instrument, config)
        if signal is None:
            continue
        after = [bar for bar in bars if bar.timestamp > signal.triggered_at]
        prev = signal.breakout_close_price
        if prev <= 0 or not after:
            continue
        path: list[float] = []
        for bar in after:
            if prev > 0:
                path.append(bar.close_price / prev - 1.0)
            prev = bar.close_price
        if path:
            paths.append(path)
    return paths


def run_entry_pre_mortem(
    entry_price: float,
    stop_loss_price: float,
    target_price: float,
    direction: SignalDirection,
    return_paths: list[list[float]],
    trials: int = 1000,
    seed: int = 0,
) -> PreMortemForecast | None:
    """Bootstrap-resample `trials` real paths (seeded) and simulate this setup on each: exit at the
    first close-path touch of stop (checked first) or target, else at the path end. Returns the
    outcome distribution, or None if there are no paths / a degenerate setup."""
    if not return_paths or entry_price <= 0:
        return None
    rng = random.Random(seed)
    returns: list[float] = []
    hits = {"target": 0, "stop": 0, "timeout": 0}
    for _ in range(trials):
        path = return_paths[rng.randrange(len(return_paths))]
        realized, outcome = _simulate_close_path(
            entry_price, stop_loss_price, target_price, direction, path
        )
        returns.append(realized)
        hits[outcome] += 1

    returns.sort()
    tail_size = max(1, int(len(returns) * _CVAR_TAIL_FRACTION))
    cvar = mean(returns[:tail_size])
    return PreMortemForecast(
        trials=trials,
        probability_target=hits["target"] / trials,
        probability_stop=hits["stop"] / trials,
        probability_timeout=hits["timeout"] / trials,
        mean_return=mean(returns),
        conditional_value_at_risk_5pct=cvar,
        worst_case_return=returns[0],
        verdict=_verdict(hits, trials, mean(returns), cvar),
    )


def _simulate_close_path(
    entry_price: float,
    stop_loss_price: float,
    target_price: float,
    direction: SignalDirection,
    path: list[float],
) -> tuple[float, str]:
    price = entry_price
    for bar_return in path:
        price = price * (1.0 + bar_return)
        if direction is SignalDirection.LONG:
            if price <= stop_loss_price:  # stop checked first (conservative)
                return (stop_loss_price - entry_price) / entry_price, "stop"
            if price >= target_price:
                return (target_price - entry_price) / entry_price, "target"
        else:  # SHORT
            if price >= stop_loss_price:
                return (entry_price - stop_loss_price) / entry_price, "stop"
            if price <= target_price:
                return (entry_price - target_price) / entry_price, "target"
    signed = (
        (price - entry_price) / entry_price
        if direction is SignalDirection.LONG
        else (entry_price - price) / entry_price
    )
    return signed, "timeout"


def _verdict(hits: dict[str, int], trials: int, mean_return: float, cvar: float) -> str:
    stop_pct = hits["stop"] / trials
    return (
        f"pre-mortem: {stop_pct:.0%} of paths hit the stop; expected return {mean_return:+.2%}, "
        f"worst-5% (CVaR) {cvar:+.2%} — "
        + ("shallow tail" if cvar > -0.02 else "deep tail, size down")
    )
