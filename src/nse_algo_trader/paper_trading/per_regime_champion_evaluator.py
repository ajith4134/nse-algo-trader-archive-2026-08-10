"""Per-market-regime champion-challenger tournament (§53 slice 5c-iii; research/90).

One global champion is a compromise across all conditions; a config that wins in TRENDING
sessions may lose in RANGE_BOUND ones. Using the 5a session-regime classifier, this
partitions the evaluation sessions by their market regime and runs the existing
`evaluate_champion_vs_challengers` (5c-i) PER regime — yielding a champion per regime, each
gated by the same conservative Deflated-Sharpe test. PURE (no I/O); the store persists the
per-regime champions and the service selects by the live session's regime.
"""

from __future__ import annotations

from nse_algo_trader.paper_trading.champion_challenger_orb_evaluator import (
    ChampionChallengerDecision,
    ReplaySession,
    evaluate_champion_vs_challengers,
)
from nse_algo_trader.paper_trading.strategy_promotion_gate import StrategyPromotionConfig
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)

# One labelled session = its bars + instrument + the market regime it traded in.
RegimeLabelledSession = tuple[list, object, str]


def partition_sessions_by_regime(
    labelled_sessions: list[RegimeLabelledSession],
) -> dict[str, list[ReplaySession]]:
    """Group `(bars, instrument, regime)` sessions into `{regime: [(bars, instrument), …]}`."""
    by_regime: dict[str, list[ReplaySession]] = {}
    for bars, instrument, market_regime in labelled_sessions:
        by_regime.setdefault(market_regime, []).append((bars, instrument))
    return by_regime


def evaluate_per_regime_champions(
    labelled_sessions: list[RegimeLabelledSession],
    champion_by_regime: dict[str, OpeningRangeBreakoutConfig],
    challenger_configs: list[OpeningRangeBreakoutConfig],
    default_champion: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
    promotion_config: StrategyPromotionConfig = StrategyPromotionConfig(),
    trial_registry=None,
) -> dict[str, ChampionChallengerDecision]:
    """Run the champion-challenger tournament independently within each market regime. The
    incumbent for a regime is `champion_by_regime[regime]` or `default_champion`. Returns a
    decision per regime that has sessions. Each regime accrues its OWN honest trial count in the shared
    `trial_registry` (family `orb_cash_<regime>`) — regimes are independent selection problems, so their
    DSR deflation must not be pooled (research/166)."""
    decisions: dict[str, ChampionChallengerDecision] = {}
    for market_regime, sessions in partition_sessions_by_regime(labelled_sessions).items():
        incumbent = champion_by_regime.get(market_regime, default_champion)
        decisions[market_regime] = evaluate_champion_vs_challengers(
            incumbent, challenger_configs, sessions, promotion_config,
            trial_registry=trial_registry, strategy_family=f"orb_cash_{market_regime}",
        )
    return decisions
