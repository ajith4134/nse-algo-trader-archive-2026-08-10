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
from dataclasses import asdict, dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # injected instances only — imported lazily to keep this module pure/import-cheap
    from nse_algo_trader.paper_trading.holdout_custodian import HoldoutCustodian
    from nse_algo_trader.paper_trading.strategy_trial_registry import StrategyTrialRegistry

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


def _session_date(session: ReplaySession) -> date | None:
    """The calendar date of an evaluation session = the date of its first bar (None if it has none)."""
    bars = session[0]
    return bars[0].timestamp.date() if bars else None


def evaluate_champion_vs_challengers(
    champion_config: OpeningRangeBreakoutConfig,
    challenger_configs: list[OpeningRangeBreakoutConfig],
    sessions: list[ReplaySession],
    promotion_config: StrategyPromotionConfig = StrategyPromotionConfig(),
    trial_registry: StrategyTrialRegistry | None = None,
    holdout_custodian: HoldoutCustodian | None = None,
    strategy_family: str = "orb_cash",
) -> ChampionChallengerDecision:
    """Run the tournament. A challenger replaces the champion ONLY when it is the highest-Sharpe config
    AND clears the promotion gate — otherwise the incumbent is kept (conservative, overfitting-safe).

    L2 validation engine (research/166): when a `trial_registry` is injected the DSR is deflated by the
    HONEST cumulative count of every config ever trialed (not just this batch), and every config here is
    registered as a trial; the MinBTL gate then rejects a backtest too short for that trial count. When a
    `holdout_custodian` is injected the tournament runs ONLY on the RESEARCH window (the sealed holdout can
    never leak into config selection), and a promoted winner must additionally survive a one-shot re-score
    on the sealed holdout. All three are optional — absent, this behaves exactly as before (Rule G safe)."""
    # Holdout discipline: the champion-challenger SELECTION must never see the holdout window.
    tournament_sessions = sessions
    holdout_sessions: list[ReplaySession] = []
    if holdout_custodian is not None:
        tournament_sessions = [
            s for s in sessions
            if (d := _session_date(s)) is not None and holdout_custodian.is_in_research(d)
        ]
        holdout_sessions = [
            s for s in sessions
            if (d := _session_date(s)) is not None and holdout_custodian.is_in_holdout(d)
        ]

    champion_scorecard = score_orb_configuration(champion_config, tournament_sessions)
    challenger_scorecards = [
        score_orb_configuration(config, tournament_sessions) for config in challenger_configs
    ]
    all_scorecards = [champion_scorecard, *challenger_scorecards]

    # Register every trialed config (honest cumulative N for the DSR — the core overfitting fix).
    number_of_trials = len(all_scorecards)
    sharpe_std_across_trials = (
        statistics.pstdev([s.sharpe_ratio for s in all_scorecards]) if number_of_trials > 1 else 0.0
    )
    if trial_registry is not None:
        from nse_algo_trader.paper_trading.strategy_trial_registry import stable_config_hash

        for scorecard in all_scorecards:
            trial_registry.register_trial(
                strategy_family=strategy_family,
                config_hash=stable_config_hash(asdict(scorecard.config)),
                trial_sharpe=scorecard.sharpe_ratio,
                observation_count=len(scorecard.per_session_returns),
                kept=False,
            )
        honest_trials = trial_registry.cumulative_trial_count(strategy_family)
        if honest_trials >= 2:
            number_of_trials = honest_trials
            sharpe_std_across_trials = trial_registry.sharpe_std_across_trials(strategy_family)

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
        best.per_session_returns, number_of_trials, sharpe_std_across_trials, promotion_config,
        observation_count=len(best.per_session_returns),  # backtest length → MinBTL gate
    )
    replaced = gate.promoted
    promotion_reason = (
        f"challenger promoted ({gate.outcome.value})"
        if replaced
        else f"top challenger did not clear the gate ({gate.outcome.value}) — champion kept"
    )

    # One-shot HOLDOUT validation: a winner selected on research must also earn a positive Sharpe on the
    # sealed holdout it was never tuned on, or it is rejected (López de Prado's final out-of-sample test).
    if replaced and holdout_custodian is not None and holdout_sessions:
        holdout_custodian.unseal_for_final_validation(
            f"champion-challenger final validation: {strategy_family}"
        )
        holdout_scorecard = score_orb_configuration(best.config, holdout_sessions)
        if holdout_scorecard.sharpe_ratio <= 0.0:
            replaced = False
            promotion_reason = (
                f"challenger won research + gate ({gate.outcome.value}) but FAILED the sealed "
                f"holdout (holdout Sharpe {holdout_scorecard.sharpe_ratio:.2f} ≤ 0) — champion kept"
            )
    if replaced and trial_registry is not None:  # mark the promoted config as KEPT in the registry
        from nse_algo_trader.paper_trading.strategy_trial_registry import stable_config_hash

        trial_registry.register_trial(
            strategy_family=strategy_family,
            config_hash=stable_config_hash(asdict(best.config)),
            trial_sharpe=best.sharpe_ratio,
            observation_count=len(best.per_session_returns),
            kept=True,
        )

    return ChampionChallengerDecision(
        champion_scorecard=champion_scorecard,
        challenger_scorecards=challenger_scorecards,
        winning_config=(best.config if replaced else champion_config),
        champion_replaced=replaced,
        promotion_deflated_sharpe=gate.deflated_sharpe_ratio,
        promotion_reason=promotion_reason,
    )
