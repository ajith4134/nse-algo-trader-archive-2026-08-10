"""§53 slice 5c-i — per-session ORB backtester (hermetic). Shaped sessions drive a target
hit, a stop hit, a no-signal session, and a stop-checked-before-target invariant."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.replay_session_orb_backtester import (
    backtest_orb_session_return,
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


def test_no_signal_session_returns_none():
    # flat range, never breaks out -> no trade.
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(20)]
    assert backtest_orb_session_return(bars, _instr(), _CONFIG) is None


def test_long_target_hit_is_positive_return():
    # opening range (bars 0-2) high=101; a later bar closes above -> LONG; then price runs up.
    bars = [
        _bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 101, 99, 100),
        _bar(3, 100, 102, 100, 102),   # breakout close 102 > range high 101; stop=99, risk=3, target=108
        _bar(4, 102, 109, 102, 108),   # high 109 >= target 108 -> win
    ]
    r = backtest_orb_session_return(bars, _instr(), _CONFIG)
    assert r is not None and r > 0
    # target 108 on entry 102 -> +5.88%
    assert abs(r - (108 - 102) / 102) < 1e-9


def test_long_stop_hit_is_negative_return():
    bars = [
        _bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 101, 99, 100),
        _bar(3, 100, 102, 100, 102),   # LONG entry 102, stop 99
        _bar(4, 102, 102, 98, 99),     # low 98 <= stop 99 -> loss at 99
    ]
    r = backtest_orb_session_return(bars, _instr(), _CONFIG)
    assert r is not None and abs(r - (99 - 102) / 102) < 1e-9  # ~-2.94%


def test_stop_checked_before_target_within_a_bar():
    # a bar that touches BOTH stop and target -> conservative: stop wins (loss).
    bars = [
        _bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 101, 99, 100),
        _bar(3, 100, 102, 100, 102),   # entry 102, stop 99, target 108
        _bar(4, 102, 109, 98, 103),    # touches target 108 AND stop 99 -> stop first
    ]
    r = backtest_orb_session_return(bars, _instr(), _CONFIG)
    assert r < 0  # resolved as the stop, not the target


def test_no_exit_falls_back_to_last_close():
    bars = [
        _bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 101, 99, 100),
        _bar(3, 100, 102, 100, 102),   # entry 102
        _bar(4, 102, 104, 101, 103),   # neither stop(99) nor target(108) -> exit last close 103
    ]
    r = backtest_orb_session_return(bars, _instr(), _CONFIG)
    assert abs(r - (103 - 102) / 102) < 1e-9
