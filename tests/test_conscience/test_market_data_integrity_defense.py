"""Hermetic test for the market-data integrity / adversarial-input defense (Trunk VII; research/121):
clean bars pass; crossed candles, non-positive prices, impossible moves, and duplicate timestamps are
each flagged; the state gate blocks a corrupted series + counts. Pure, no I/O.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from nse_algo_trader.conscience.market_data_integrity_defense import (
    screen_bar,
    screen_bar_series,
)
from nse_algo_trader.market_data import BarInterval
from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def _bar(minute, o, h, l, c):
    return PriceBar(
        instrument_token=1, timestamp=datetime(2026, 7, 20, 9, 15) + timedelta(minutes=minute),
        interval=BarInterval.MINUTE_5, open_price=o, high_price=h, low_price=l,
        close_price=c, volume=1000,
    )


def test_clean_bar_and_series_pass():
    assert screen_bar(_bar(0, 100, 101, 99, 100), previous_close=100).clean
    series = [_bar(i * 5, 100, 101, 99, 100.5) for i in range(5)]
    assert screen_bar_series(series).clean


def test_crossed_candle_flagged():
    v = screen_bar(_bar(0, 100, 98, 102, 100), previous_close=100)  # high < low
    assert not v.clean and "crossed-candle(high<low)" in v.anomalies


def test_non_positive_price_flagged():
    v = screen_bar(_bar(0, 0, 101, 99, 100), previous_close=100)
    assert not v.clean and "non-positive-price" in v.anomalies


def test_impossible_move_flagged():
    v = screen_bar(_bar(0, 100, 130, 99, 130), previous_close=100)  # +30% jump
    assert not v.clean and any("impossible-move" in a for a in v.anomalies)


def test_ohlc_inconsistency_flagged():
    v = screen_bar(_bar(0, 105, 101, 99, 100), previous_close=100)  # open above high
    assert not v.clean and "ohlc-inconsistent" in v.anomalies


def test_duplicate_timestamp_flagged():
    b = _bar(0, 100, 101, 99, 100)
    series = [b, b]  # same timestamp twice
    v = screen_bar_series(series)
    assert not v.clean and "duplicate-timestamp" in v.anomalies


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )


def test_state_gate_passes_clean_blocks_corrupt_and_counts():
    state = _state()
    clean = [_bar(i * 5, 100, 101, 99, 100.5) for i in range(4)]
    assert state.market_data_integrity_permits_signal(clean) is True
    corrupt = [_bar(0, 100, 98, 102, 100)]  # crossed candle
    assert state.market_data_integrity_permits_signal(corrupt) is False
    assert state.market_data_series_screened_count == 2
    assert state.market_data_integrity_blocked_signal_count == 1
    assert state.market_data_integrity_anomaly_count >= 1
