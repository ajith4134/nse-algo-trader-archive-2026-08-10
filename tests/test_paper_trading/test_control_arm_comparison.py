"""Hermetic test for the skill-vs-luck control arm (Layer 7.5 slice 1; research/95): the
RANDOM-CONTROL backtester is seeded-deterministic and takes both directions, and the comparison
scores both arms + applies the conservative both-must-agree edge verdict. Deterministic, no I/O.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.control_arm_backtester import (
    backtest_random_control_session_return,
)
from nse_algo_trader.paper_trading.control_arm_comparison import (
    ControlArmStats,
    _edge_verdict,
    compare_control_arms,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")
_OPEN = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
_CONFIG = OpeningRangeBreakoutConfig(opening_range_minutes=15, target_risk_reward_ratio=2.0)


def _instr() -> Instrument:
    return Instrument(
        instrument_token=1, trading_symbol="INFY",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _bar(i, o, h, l, c) -> PriceBar:
    return PriceBar(
        instrument_token=1, timestamp=_OPEN + timedelta(minutes=5 * i),
        interval=BarInterval.MINUTE_5, open_price=o, high_price=h, low_price=l,
        close_price=c, volume=1000, open_interest=None,
    )


def _bullish_breakout_session():
    # range (bars 0-2) high 101; bar 3 closes 102 → entry 102, stop 99 (risk 3), target 108;
    # bar 4 runs up to 109. LONG wins (+5.88%); a random SHORT loses at stop 105 (-2.94%).
    return [
        _bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 101, 99, 100),
        _bar(3, 100, 102, 100, 102),
        _bar(4, 102, 109, 102, 108),
    ]


def test_no_signal_session_returns_none():
    flat = [_bar(i, 100, 100.5, 99.5, 100) for i in range(20)]
    assert backtest_random_control_session_return(flat, _instr(), _CONFIG, seed=1) is None


def test_random_control_is_deterministic_per_seed():
    bars = _bullish_breakout_session()
    r1 = backtest_random_control_session_return(bars, _instr(), _CONFIG, seed=7)
    r2 = backtest_random_control_session_return(bars, _instr(), _CONFIG, seed=7)
    assert r1 == r2  # same seed → same coin-flip → same trade


def test_random_control_takes_both_directions_across_seeds():
    bars = _bullish_breakout_session()
    outcomes = {
        round(backtest_random_control_session_return(bars, _instr(), _CONFIG, seed=s), 4)
        for s in range(16)
    }
    assert round((108 - 102) / 102, 4) in outcomes   # a seeded LONG wins (target)
    assert round((102 - 105) / 102, 4) in outcomes    # a seeded SHORT loses (symmetric stop)


def test_comparison_scores_both_arms_and_is_reproducible():
    sessions = [(_bullish_breakout_session(), _instr())]
    a = compare_control_arms(sessions, _CONFIG)
    b = compare_control_arms(sessions, _CONFIG)
    assert a.real.trades == 1 and a.random_control.trades == 1
    assert a.real.hit_rate == 1.0  # the real LONG wins this bullish session
    assert a == b  # seeded per session → fully reproducible
    assert a.has_edge is False and "gathering" in a.verdict  # 1 < min-trades → no verdict


def test_edge_verdict_requires_both_sharpe_and_hitrate_above_random():
    real = ControlArmStats("real", 12, 0.60, 0.01, 0.12, 1.5)
    beaten = ControlArmStats("random", 12, 0.40, -0.005, -0.06, 0.30)
    has_edge, verdict = _edge_verdict(real, beaten)
    assert has_edge is True and "EDGE" in verdict

    # random beats real on hit-rate → NO edge even if Sharpe is higher
    higher_hit = ControlArmStats("random", 12, 0.70, 0.0, 0.0, 0.10)
    no_edge, verdict2 = _edge_verdict(real, higher_hit)
    assert no_edge is False and "NO demonstrated edge" in verdict2

    # thin data → gathering, never a verdict
    thin, verdict3 = _edge_verdict(ControlArmStats("real", 5, 0.6, 0, 0, 1.0), beaten)
    assert thin is False and "gathering" in verdict3
