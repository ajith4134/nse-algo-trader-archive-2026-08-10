from datetime import datetime, timedelta

import pytest

from nse_algo_trader.indicators import (
    compute_average_directional_index,
    compute_average_true_range,
    compute_exponential_moving_average,
    compute_relative_strength_index,
    compute_session_anchored_vwap,
    compute_supertrend,
    compute_true_range_series,
)
from nse_algo_trader.market_data import BarInterval, PriceBar


def _bars_from_ohlcv(ohlcv_tuples, start=datetime(2026, 7, 22, 9, 15)) -> list[PriceBar]:
    return [
        PriceBar(
            instrument_token=1,
            timestamp=start + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5,
            open_price=o, high_price=h, low_price=l, close_price=c, volume=v,
        )
        for i, (o, h, l, c, v) in enumerate(ohlcv_tuples)
    ]


def _bars_from_closes(closes) -> list[PriceBar]:
    return _bars_from_ohlcv([(c, c, c, c, 100) for c in closes])


class TestExponentialMovingAverage:
    def test_hand_computed_period_3(self):
        ema = compute_exponential_moving_average(
            _bars_from_closes([1.0, 2.0, 3.0, 4.0, 5.0]), period=3
        )
        # SMA seed (1+2+3)/3 = 2; alpha = 0.5: then 3.0, 4.0
        assert ema == [None, None, 2.0, 3.0, 4.0]

    def test_shorter_than_period_is_all_none(self):
        assert compute_exponential_moving_average(
            _bars_from_closes([1.0, 2.0]), period=3
        ) == [None, None]


class TestRelativeStrengthIndex:
    def test_monotonic_rise_is_rsi_100(self):
        rsi = compute_relative_strength_index(
            _bars_from_closes([float(i) for i in range(1, 18)]), period=14
        )
        assert rsi[:14] == [None] * 14
        assert rsi[14] == 100.0 and rsi[16] == 100.0

    def test_hand_computed_symmetric_seed_is_50(self):
        # first `period` changes alternate +0.5/-0.5 -> seed RS=1 -> RSI 50;
        # later Wilder-smoothed values oscillate around 50 (not exactly 50)
        alternating_closes = [10.0 + (0.5 if i % 2 else 0.0) for i in range(20)]
        rsi = compute_relative_strength_index(
            _bars_from_closes(alternating_closes), period=4
        )
        assert rsi[4] == pytest.approx(50.0, abs=1e-9)
        assert all(30.0 < value < 70.0 for value in rsi[5:])


class TestAverageTrueRange:
    def test_true_range_uses_previous_close_gaps(self):
        bars = _bars_from_ohlcv(
            [(10, 12, 9, 11, 100), (14, 15, 13, 14, 100)]  # gap up over close 11
        )
        assert compute_true_range_series(bars) == [3.0, 4.0]  # |15-11| wins

    def test_wilder_seed_and_smoothing_hand_computed(self):
        bars = _bars_from_ohlcv(
            [(0, 11, 9, 10, 1), (0, 12, 10, 11, 1), (0, 13, 11, 12, 1), (0, 18, 12, 15, 1)]
        )
        # TRs: 2, 2, 2, 6 ; ATR(2) seed=(2+2)/2=2 at idx1; idx2=(2*1+2)/2=2; idx3=(2*1+6)/2=4
        assert compute_average_true_range(bars, period=2) == [None, 2.0, 2.0, 4.0]


class TestAverageDirectionalIndex:
    def test_strong_uptrend_has_plus_di_above_minus_di_and_high_adx(self):
        rising = _bars_from_ohlcv(
            [(i, i + 1.0, i - 1.0, i + 0.5, 100) for i in range(10, 50)]
        )
        adx_series = compute_average_directional_index(rising, period=14)
        assert adx_series.adx[: 2 * 14 - 1] == [None] * 27
        last_index = -1
        assert adx_series.plus_directional_indicator[last_index] > (
            adx_series.minus_directional_indicator[last_index]
        )
        assert adx_series.adx[last_index] > 25.0

    def test_flat_market_adx_is_zero(self):
        flat = _bars_from_ohlcv([(10, 11, 9, 10, 100)] * 40)
        adx_series = compute_average_directional_index(flat, period=14)
        assert adx_series.adx[-1] == pytest.approx(0.0)


class TestSupertrend:
    def test_uptrend_rides_lower_band_with_direction_plus_one(self):
        rising = _bars_from_ohlcv(
            [(i, i + 1.0, i - 1.0, i + 0.5, 100) for i in range(10, 40)]
        )
        supertrend = compute_supertrend(rising, atr_period=10, band_multiplier=3.0)
        assert supertrend.trend_direction[-1] == 1
        assert supertrend.supertrend_line[-1] < rising[-1].close_price

    def test_crash_flips_direction_to_minus_one(self):
        rising_then_crash = [(i, i + 1.0, i - 1.0, i + 0.5, 100) for i in range(10, 30)]
        rising_then_crash += [(5.0, 5.5, 3.0, 3.5, 100)] * 3  # collapse far below bands
        supertrend = compute_supertrend(
            _bars_from_ohlcv(rising_then_crash), atr_period=10, band_multiplier=3.0
        )
        assert supertrend.trend_direction[19] == 1
        assert supertrend.trend_direction[-1] == -1
        assert supertrend.supertrend_line[-1] > rising_then_crash[-1][3]


class TestSessionAnchoredVwap:
    def test_hand_computed_cumulative_vwap(self):
        bars = _bars_from_ohlcv([(0, 12, 8, 10, 100), (0, 22, 18, 20, 300)])
        # typical prices 10 and 20 -> (10*100 + 20*300) / 400 = 17.5
        assert compute_session_anchored_vwap(bars) == [10.0, 17.5]

    def test_vwap_resets_on_new_session_date(self):
        day_one = _bars_from_ohlcv([(0, 12, 8, 10, 100)])
        day_two = _bars_from_ohlcv(
            [(0, 42, 38, 40, 100)], start=datetime(2026, 7, 23, 9, 15)
        )
        assert compute_session_anchored_vwap(day_one + day_two) == [10.0, 40.0]
