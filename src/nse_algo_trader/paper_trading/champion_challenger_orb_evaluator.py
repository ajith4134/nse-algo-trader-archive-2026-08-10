"""Champion-challenger tournament over ORB configurations (§53 slice 5c-i; research/87).

Scores an incumbent CHAMPION `OpeningRangeBreakoutConfig` against CHALLENGER configs over a
shared set of real replay sessions, and promotes a challenger only if it is the top scorer
AND clears the multiple-testing-aware Deflated-Sharpe gate — so we never adopt a config that
merely won by overfitting to a handful of sessions. Reuses (Rule I):
`replay_session_orb_backtester` for per-session outcomes and `strategy_promotion_gate` for
the significance test. PURE (no I/O); the store persists the winning config separately.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.paper_trading.replay_session_orb_backtester import (
    backtest_orb_session_return,
)
from nse_algo_trader.paper_trading.strategy_promotion_gate import (
    StrategyPromotionConfig,
    compute_sharpe_ratio,
    evaluate_strategy_for_promotion,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)
from nse_algo_trader.universe_registry import Instrument

# One evaluation session = its bars + the instrument they belong to.
ReplaySession = tuple[list[PriceBar], Instrument]


@dataclass(frozen=True)
class ConfigurationScorecard:
    """How one ORB config performed across the evaluation sessions."""

    config: OpeningRangeBreakoutConfig
    sessions_traded: int  # sessions that produced a signal
    per_session_returns: list[float]
    hit_rate: float | None
    total_return: float
    sharpe_ratio: float


@dataclass(frozen=True)
class ChampionChallengerDecision:
    """The tournament outcome: the scorecards, the winner, and whether the champion was
    replaced (only when a challenger both wins AND clears the Deflated-Sharpe gate)."""

    champion_scorecard: ConfigurationScorecard
    challenger_scorecards: list[ConfigurationScorecard]
    winning_config: OpeningRangeBreakoutConfig
    champion_replaced: bool
    promotion_deflated_sharpe: float
    promotion_reason: str


def score_orb_configuration(
    config: OpeningRangeBreakoutConfig, sessions: list[ReplaySession]
) -> ConfigurationScorecard:
    """Backtest `config` over every session and aggregate. Sessions with no signal don't
    count as trades (only realized trades score)."""
    returns = [
        r
        for bars, instrument in sessions
        if (r := backtest_orb_session_return(bars, instrument, config)) is not None
    ]
    wins = sum(1 for r in returns if r > 0)
    return ConfigurationScorecard(
        config=config,
        sessions_traded=len(returns),
        per_session_returns=returns,
        hit_rate=(wins / len(returns) if returns else None),
        total_return=sum(returns),
        sharpe_ratio=compute_sharpe_ratio(returns),
    )


def evaluate_champion_vs_challengers(
    champion_config: OpeningRangeBreakoutConfig,
    challenger_configs: list[OpeningRangeBreakoutConfig],
    sessions: list[ReplaySession],
    promotion_config: StrategyPromotionConfig = StrategyPromotionConfig(),
) -> ChampionChallengerDecision:
    """Run the tournament. A challenger replaces the champion ONLY when it is the highest-
    Sharpe config and clears the Deflated-Sharpe gate (deflated by the number of configs
    tried) — otherwise the incumbent champion is kept (conservative, overfitting-safe)."""
    champion_scorecard = score_orb_configuration(champion_config, sessions)
    challenger_scorecards = [
        score_orb_configuration(config, sessions) for config in challenger_configs
    ]
    all_scorecards = [champion_scorecard, *challenger_scorecards]
    number_of_trials = len(all_scorecards)
    sharpe_std_across_trials = (
        statistics.pstdev([s.sharpe_ratio for s in all_scorecards])
        if number_of_trials > 1
        else 0.0
    )

    best = max(all_scorecards, key=lambda s: s.sharpe_ratio)
    if best.config == champion_config:
        return ChampionChallengerDecision(
            champion_scorecard=champion_scorecard,
            challenger_scorecards=challenger_scorecards,
            winning_config=champion_config,
            champion_replaced=False,
            promotion_deflated_sharpe=0.0,
            promotion_reason="champion is the top scorer — kept",
        )

    gate = evaluate_strategy_for_promotion(
        best.per_session_returns, number_of_trials, sharpe_std_across_trials, promotion_config
    )
    replaced = gate.promoted
    return ChampionChallengerDecision(
        champion_scorecard=champion_scorecard,
        challenger_scorecards=challenger_scorecards,
        winning_config=(best.config if replaced else champion_config),
        champion_replaced=replaced,
        promotion_deflated_sharpe=gate.deflated_sharpe_ratio,
        promotion_reason=(
            f"challenger promoted ({gate.outcome.value})"
            if replaced
            else f"top challenger did not clear the gate ({gate.outcome.value}) — champion kept"
        ),
    )
