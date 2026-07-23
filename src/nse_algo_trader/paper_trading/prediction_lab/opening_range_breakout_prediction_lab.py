"""Wires the falsification lab onto the ORB paper engine (PLAN §9).

The confidence signal (ADX) must be WARMED and free of lookahead. ADX
needs ~2*period bars to warm up, so intraday ADX at an early breakout bar
is meaningless (the lab caught this on its first real run). The fix: run
ADX over the CONTINUOUS multi-session bar stream, and for each session's
breakout use the ADX value at that bar — warmed by prior sessions, using
only bars up to the breakout (no future information).

`run_orb_prediction_lab_session` takes the regime ADX as a plain input so
it stays simple and testable; `run_orb_prediction_lab_over_replay` is the
batch driver that computes the continuous ADX and feeds each session.
"""

from dataclasses import dataclass

from nse_algo_trader.broker_oms import SimulatedBrokerClient
from nse_algo_trader.indicators import compute_average_directional_index
from nse_algo_trader.market_data import PriceBar
from nse_algo_trader.paper_trading.opening_range_breakout_paper_engine import (
    PaperSessionOutcome,
    PaperSessionResult,
    group_bars_into_sessions,
    run_opening_range_breakout_paper_session,
)
from nse_algo_trader.paper_trading.paper_trading_ledger import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab.adx_confidence_prediction import (
    build_orb_prediction_record,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_outcome_grading import (
    GradedPrediction,
    grade_prediction,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)
from nse_algo_trader.risk_management import RiskBudgetConfig
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutConfig,
    detect_opening_range_breakout,
)
from nse_algo_trader.universe_registry import Instrument


@dataclass(frozen=True)
class LabSessionResult:
    paper_result: PaperSessionResult
    graded_prediction: GradedPrediction | None  # None when no trade was taken


def run_orb_prediction_lab_session(
    single_session_bars: list[PriceBar],
    instrument: Instrument,
    simulated_broker: SimulatedBrokerClient,
    risk_budget: RiskBudgetConfig,
    ledger: PaperTradingLedger,
    scoreboard: PredictionTableScoreboard,
    regime_adx_value: float,
    strategy_config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
) -> LabSessionResult:
    signal = detect_opening_range_breakout(
        single_session_bars, instrument, strategy_config
    )
    if signal is None:
        paper_result = PaperSessionResult(
            single_session_bars[0].timestamp.date(), PaperSessionOutcome.NO_SIGNAL
        )
        return LabSessionResult(paper_result, None)

    prediction_record = build_orb_prediction_record(
        signal=signal,
        adx_value=regime_adx_value,
        session_date=single_session_bars[0].timestamp.date(),
        target_reward_multiple=strategy_config.target_risk_reward_ratio,
    )
    paper_result = run_opening_range_breakout_paper_session(
        single_session_bars, instrument, simulated_broker, risk_budget, ledger,
        strategy_config,
    )
    if paper_result.outcome is PaperSessionOutcome.RISK_REJECTED:
        return LabSessionResult(paper_result, None)

    graded = grade_prediction(prediction_record, paper_result.realized_pnl)
    scoreboard.add_graded_prediction(graded)
    return LabSessionResult(paper_result, graded)


def run_orb_prediction_lab_over_replay(
    chronological_bars: list[PriceBar],
    instrument: Instrument,
    simulated_broker: SimulatedBrokerClient,
    risk_budget: RiskBudgetConfig,
    ledger: PaperTradingLedger,
    scoreboard: PredictionTableScoreboard,
    strategy_config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
) -> list[LabSessionResult]:
    """Runs the lab across a replay stream. ADX is computed once over the
    whole continuous stream (warmed), and each session's breakout reads the
    ADX at that bar — no per-session warmup gap, no lookahead."""
    adx_by_timestamp = _continuous_adx_by_timestamp(chronological_bars)
    sessions = group_bars_into_sessions(chronological_bars)
    lab_results: list[LabSessionResult] = []
    for session_date in sorted(sessions):
        session_bars = sessions[session_date]
        signal = detect_opening_range_breakout(session_bars, instrument, strategy_config)
        regime_adx = 0.0
        if signal is not None:
            regime_adx = _warmed_adx_at_or_before(
                adx_by_timestamp, session_bars, signal.triggered_at
            )
        lab_results.append(
            run_orb_prediction_lab_session(
                session_bars, instrument, simulated_broker, risk_budget, ledger,
                scoreboard, regime_adx, strategy_config,
            )
        )
    return lab_results


def _continuous_adx_by_timestamp(chronological_bars: list[PriceBar]) -> dict:
    adx_series = compute_average_directional_index(chronological_bars)
    return {
        bar.timestamp: adx_value
        for bar, adx_value in zip(chronological_bars, adx_series.adx)
        if adx_value is not None
    }


def _warmed_adx_at_or_before(adx_by_timestamp, session_bars, at_timestamp) -> float:
    latest = 0.0
    for bar in session_bars:
        if bar.timestamp > at_timestamp:
            break
        if bar.timestamp in adx_by_timestamp:
            latest = adx_by_timestamp[bar.timestamp]
    return latest
