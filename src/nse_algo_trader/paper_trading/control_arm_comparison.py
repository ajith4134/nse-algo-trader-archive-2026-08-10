"""Skill-vs-luck control-arm comparison (Layer 7.5 slice 1; research/95).

Scores the REAL arm (the champion ORB config) against the RANDOM-CONTROL arm (same triggers,
random direction) over the same set of real sessions, and returns per-arm stats plus a
conservative EDGE VERDICT: the strategy has demonstrated an edge only if the real arm beats the
random baseline on BOTH Sharpe AND hit-rate (and both arms have enough trades). On thin data it
reports "gathering" rather than a false verdict. This is the scientific baseline the champion's
positive-looking P&L must clear to be called skill, not luck. PURE (no I/O); reuses the real and
random backtesters + `compute_sharpe_ratio` (Rule I).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.paper_trading.control_arm_backtester import (
    backtest_random_control_session_return,
)
from nse_algo_trader.paper_trading.replay_session_orb_backtester import (
    backtest_orb_session_return,
)
from nse_algo_trader.paper_trading.strategy_promotion_gate import compute_sharpe_ratio
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)
from nse_algo_trader.universe_registry import Instrument

# One evaluation session = its bars + the instrument they belong to (same as the tournament).
ControlArmSession = tuple[list[PriceBar], Instrument]

_MIN_TRADES_FOR_VERDICT = 10  # below this per arm, we report "gathering", never a verdict


@dataclass(frozen=True)
class ControlArmStats:
    """One arm's performance over the scored sessions."""

    arm_name: str
    trades: int  # sessions that produced a signal (a trade)
    hit_rate: float
    mean_return: float
    total_return: float
    sharpe: float


@dataclass(frozen=True)
class ControlArmComparison:
    """The real arm vs the random-control arm, with the skill-vs-luck edge verdict."""

    real: ControlArmStats
    random_control: ControlArmStats
    has_edge: bool
    verdict: str


def compare_control_arms(
    sessions: list[ControlArmSession],
    champion_config: OpeningRangeBreakoutConfig,
    seed: int = 0,
) -> ControlArmComparison:
    """Score the real champion arm and the random-control arm over `sessions` and judge whether
    the real arm has a demonstrated edge over random. The random direction is seeded per session
    from the session date (via the first bar) so the control is reproducible."""
    real_returns: list[float] = []
    random_returns: list[float] = []
    for bars, instrument in sessions:
        real = backtest_orb_session_return(bars, instrument, champion_config)
        if real is not None:
            real_returns.append(real)
        control = backtest_random_control_session_return(
            bars, instrument, champion_config, seed=_session_seed(bars, seed)
        )
        if control is not None:
            random_returns.append(control)

    real_stats = _score_arm("real (champion ORB)", real_returns)
    random_stats = _score_arm("random-control", random_returns)
    has_edge, verdict = _edge_verdict(real_stats, random_stats)
    return ControlArmComparison(
        real=real_stats, random_control=random_stats, has_edge=has_edge, verdict=verdict
    )


def _session_seed(bars: list[PriceBar], base_seed: int) -> int:
    """Reproducible per-session seed from the session date — same session ⇒ same coin-flip."""
    if not bars:
        return base_seed
    return base_seed * 100_003 + bars[0].timestamp.date().toordinal()


def _score_arm(arm_name: str, returns: list[float]) -> ControlArmStats:
    if not returns:
        return ControlArmStats(arm_name, 0, 0.0, 0.0, 0.0, 0.0)
    wins = sum(1 for r in returns if r > 0)
    return ControlArmStats(
        arm_name=arm_name,
        trades=len(returns),
        hit_rate=wins / len(returns),
        mean_return=mean(returns),
        total_return=sum(returns),
        sharpe=compute_sharpe_ratio(returns),
    )


def _edge_verdict(
    real: ControlArmStats, random_control: ControlArmStats
) -> tuple[bool, str]:
    """Conservative both-must-agree read: an edge requires the real arm to beat random-control on
    BOTH Sharpe AND hit-rate, with enough trades in each arm. Otherwise 'gathering' or 'no edge'."""
    if real.trades < _MIN_TRADES_FOR_VERDICT or random_control.trades < _MIN_TRADES_FOR_VERDICT:
        return False, (
            f"gathering: real {real.trades} / random {random_control.trades} trades "
            f"(need ≥{_MIN_TRADES_FOR_VERDICT} each for a verdict)"
        )
    if real.sharpe > random_control.sharpe and real.hit_rate > random_control.hit_rate:
        return True, (
            f"EDGE: real Sharpe {real.sharpe:.2f} > random {random_control.sharpe:.2f} AND "
            f"hit-rate {real.hit_rate:.0%} > {random_control.hit_rate:.0%} — beats luck"
        )
    return False, (
        f"NO demonstrated edge vs random: real Sharpe {real.sharpe:.2f} / hit "
        f"{real.hit_rate:.0%} vs random Sharpe {random_control.sharpe:.2f} / hit "
        f"{random_control.hit_rate:.0%}"
    )
