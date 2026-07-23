from datetime import datetime, time, timedelta

import pytest

from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutConfig,
    SignalDirection,
    detect_opening_range_breakout,
)
from nse_algo_trader.universe_registry import ExchangeSegment, Instrument, InstrumentKind

SESSION_START = datetime(2026, 7, 22, 9, 15)

SIGNAL_INSTRUMENT = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)


def _session_bars(ohlc_tuples) -> list[PriceBar]:
    return [
        PriceBar(
            instrument_token=408065,
            timestamp=SESSION_START + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5,
            open_price=o, high_price=h, low_price=l, close_price=c, volume=1000,
        )
        for i, (o, h, l, c) in enumerate(ohlc_tuples)
    ]


# Opening range (first 15 min = 3 five-minute bars): high 102, low 98.
OPENING_RANGE_BARS = [(100, 101, 98, 100), (100, 102, 99, 101), (101, 102, 99, 100)]


class TestOpeningRangeBreakout:
    def test_no_breakout_stays_none(self):
        inside_bars = OPENING_RANGE_BARS + [(100, 101.5, 98.5, 100)] * 5
        assert detect_opening_range_breakout(
            _session_bars(inside_bars), SIGNAL_INSTRUMENT
        ) is None

    def test_wick_beyond_range_without_close_does_not_trigger(self):
        wick_only = OPENING_RANGE_BARS + [(100, 104, 99, 101.5)]  # high pierces, close inside
        assert detect_opening_range_breakout(
            _session_bars(wick_only), SIGNAL_INSTRUMENT
        ) is None

    def test_long_breakout_sets_stop_at_range_low_and_2r_target(self):
        breakout = OPENING_RANGE_BARS + [(101, 104, 100, 103.0)]
        signal = detect_opening_range_breakout(
            _session_bars(breakout), SIGNAL_INSTRUMENT
        )
        assert signal.direction is SignalDirection.LONG
        assert signal.opening_range_high == 102 and signal.opening_range_low == 98
        assert signal.breakout_close_price == 103.0
        assert signal.stop_loss_price == 98  # opposite range bound
        assert signal.target_price == pytest.approx(103.0 + 2.0 * (103.0 - 98))
        assert signal.triggered_at == SESSION_START + timedelta(minutes=15)

    def test_short_breakout_mirrors(self):
        breakdown = OPENING_RANGE_BARS + [(99, 100, 96, 97.0)]
        signal = detect_opening_range_breakout(
            _session_bars(breakdown), SIGNAL_INSTRUMENT
        )
        assert signal.direction is SignalDirection.SHORT
        assert signal.stop_loss_price == 102
        assert signal.target_price == pytest.approx(97.0 - 2.0 * (102 - 97.0))

    def test_only_first_breakout_signals(self):
        double_break = OPENING_RANGE_BARS + [(101, 104, 100, 103.0), (95, 96, 94, 95.0)]
        signal = detect_opening_range_breakout(
            _session_bars(double_break), SIGNAL_INSTRUMENT
        )
        assert signal.direction is SignalDirection.LONG  # the later breakdown is ignored

    def test_breakout_after_entry_cutoff_is_ignored(self):
        # 70 bars inside the range pushes the breakout past 14:30 IST
        late_break = OPENING_RANGE_BARS + [(100, 101.5, 98.5, 100)] * 61 + [(101, 104, 100, 103.0)]
        bars = _session_bars(late_break)
        assert bars[-1].timestamp.time() > time(14, 30)
        assert detect_opening_range_breakout(bars, SIGNAL_INSTRUMENT) is None

    def test_custom_opening_range_window_is_respected(self):
        # With a 25-minute range, bar index 4 (still < 25min) can't trigger
        five_bar_range = OPENING_RANGE_BARS + [(100, 103, 99, 102.5), (100, 105, 99, 104.0)]
        config = OpeningRangeBreakoutConfig(opening_range_minutes=25)
        signal = detect_opening_range_breakout(
            _session_bars(five_bar_range + [(104, 106, 103, 105.5)]),
            SIGNAL_INSTRUMENT,
            config,
        )
        # range now spans first 5 bars: high 105, low 98; breakout = close 105.5
        assert signal.opening_range_high == 105
        assert signal.breakout_close_price == 105.5

    def test_empty_session_is_none(self):
        assert detect_opening_range_breakout([], SIGNAL_INSTRUMENT) is None
