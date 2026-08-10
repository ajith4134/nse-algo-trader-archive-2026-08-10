"""Tests for the intraday mean-reversion signal family (L4, docs/research/170).

Synthetic session bars, in the ORB-test style: a flat baseline builds a
small residual band, then one stretched bar arms the fade. All the mean /
dispersion / stretch numbers are recomputed by the engine from these bars
(nothing is hard-coded), so the assertions pin the sign conventions and
the regime + degeneracy guards rather than magic levels.
"""

from datetime import datetime, timedelta

import pytest

from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.strategy_engine.intraday_mean_reversion_strategy import (
    IntradayMeanReversionConfig,
    MeanReversionMeanBasis,
    MeanReversionSignal,
    MeanReversionThresholdMode,
    detect_intraday_mean_reversion,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

SESSION_START = datetime(2026, 7, 22, 9, 15)

SIGNAL_INSTRUMENT = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)

# Small lookback keeps the synthetic sessions short (like the ORB tests).
SMA_LOOKBACK_5 = IntradayMeanReversionConfig(
    mean_basis=MeanReversionMeanBasis.ROLLING_SMA,
    dispersion_lookback_bars=5,
)
RANGE_BOUND_ADX = 10.0  # <= 20 range-bound threshold -> fading allowed
TRENDING_ADX = 30.0  # > threshold -> fading forbidden


def _session_bars(closes: list[float]) -> list[PriceBar]:
    """One five-minute session; high=low=close so VWAP typical == close."""
    return [
        PriceBar(
            instrument_token=408065,
            timestamp=SESSION_START + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5,
            open_price=c, high_price=c, low_price=c, close_price=c, volume=1000,
        )
        for i, c in enumerate(closes)
    ]


# Nine flat bars at 100 (builds the SMA window), then the stretched bar.
FLAT_BASELINE = [100.0] * 9


class TestOversoldLongReversion:
    def test_clear_oversold_stretch_fires_long_targeting_the_mean(self):
        signal = detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [90.0]),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        )
        assert isinstance(signal, MeanReversionSignal)
        assert signal.direction is SignalDirection.LONG
        assert signal.entry_reference_price == 90.0  # entry at the stretched close
        # SMA over closes [100,100,100,100,90] = 98 -> target == the mean.
        assert signal.intraday_mean_price == pytest.approx(98.0)
        assert signal.target_price == pytest.approx(98.0)  # full reversion to mean
        assert signal.stop_loss_price < signal.entry_reference_price  # stop below
        assert signal.stretch_in_sigma < 0  # oversold => negative z
        assert signal.regime_adx_at_entry == RANGE_BOUND_ADX
        assert signal.triggered_at == SESSION_START + timedelta(minutes=5 * 9)

    def test_target_toward_mean_and_stop_away_from_mean(self):
        signal = detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [90.0]),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        )
        assert signal is not None
        # LONG fades a drop: target ABOVE entry (toward mean), stop BELOW.
        assert signal.stop_loss_price < signal.entry_reference_price < signal.target_price
        assert signal.target_price <= signal.intraday_mean_price + 1e-9


class TestOverboughtShortReversion:
    def test_clear_overbought_stretch_fires_short_targeting_the_mean(self):
        signal = detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [110.0]),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        )
        assert signal is not None
        assert signal.direction is SignalDirection.SHORT
        assert signal.entry_reference_price == 110.0
        assert signal.intraday_mean_price == pytest.approx(102.0)  # SMA of the spike
        assert signal.target_price == pytest.approx(102.0)
        assert signal.stretch_in_sigma > 0  # overbought => positive z

    def test_short_target_below_entry_and_stop_above(self):
        signal = detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [110.0]),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        )
        assert signal is not None
        # SHORT fades a spike: target BELOW entry (toward mean), stop ABOVE.
        assert signal.target_price < signal.entry_reference_price < signal.stop_loss_price


class TestRegimeGate:
    def test_trending_session_never_fades_even_when_stretched(self):
        # Same oversold stretch, but a trending (high-ADX) tape: no fade.
        assert detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [90.0]),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=TRENDING_ADX,
        ) is None

    def test_unknown_regime_abstains(self):
        assert detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [90.0]),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=None,
        ) is None


class TestDegenerateAndNeutralSessions:
    def test_flat_zero_dispersion_session_returns_none_no_div0(self):
        assert detect_intraday_mean_reversion(
            _session_bars([100.0] * 12),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        ) is None

    def test_price_sitting_near_the_mean_gives_no_signal(self):
        gentle_oscillation = [100.0, 101.0, 99.0, 100.0, 101.0, 99.0,
                              100.0, 101.0, 99.0, 100.0, 101.0, 99.0]
        assert detect_intraday_mean_reversion(
            _session_bars(gentle_oscillation),
            SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        ) is None

    def test_empty_session_is_none(self):
        assert detect_intraday_mean_reversion(
            [], SIGNAL_INSTRUMENT, SMA_LOOKBACK_5, regime_adx=RANGE_BOUND_ADX,
        ) is None


class TestPercentileThresholdAdapts:
    def test_percentile_path_fires_where_a_strict_sigma_would_not(self):
        bars = _session_bars(FLAT_BASELINE + [90.0])
        # A deliberately strict sigma threshold does NOT arm this stretch...
        strict_sigma = IntradayMeanReversionConfig(
            mean_basis=MeanReversionMeanBasis.ROLLING_SMA,
            dispersion_lookback_bars=5,
            threshold_mode=MeanReversionThresholdMode.SIGMA,
            entry_sigma=5.0,
        )
        assert detect_intraday_mean_reversion(
            bars, SIGNAL_INSTRUMENT, strict_sigma, regime_adx=RANGE_BOUND_ADX
        ) is None
        # ...but the percentile path, calibrated to the session's own
        # residual tail, recognises the same bar as an extreme and fires.
        percentile_cfg = IntradayMeanReversionConfig(
            mean_basis=MeanReversionMeanBasis.ROLLING_SMA,
            dispersion_lookback_bars=5,
            threshold_mode=MeanReversionThresholdMode.PERCENTILE,
            entry_percentile=5.0,
        )
        signal = detect_intraday_mean_reversion(
            bars, SIGNAL_INSTRUMENT, percentile_cfg, regime_adx=RANGE_BOUND_ADX
        )
        assert signal is not None
        assert signal.direction is SignalDirection.LONG


class TestVwapMeanBasis:
    def test_vwap_basis_fires_long_on_a_drop_below_running_vwap(self):
        # Default config uses SESSION_VWAP as the intraday mean.
        vwap_cfg = IntradayMeanReversionConfig(dispersion_lookback_bars=5)
        assert vwap_cfg.mean_basis is MeanReversionMeanBasis.SESSION_VWAP
        signal = detect_intraday_mean_reversion(
            _session_bars(FLAT_BASELINE + [90.0]),
            SIGNAL_INSTRUMENT, vwap_cfg, regime_adx=RANGE_BOUND_ADX,
        )
        assert signal is not None
        assert signal.direction is SignalDirection.LONG
        assert signal.stop_loss_price < signal.entry_reference_price < signal.target_price


class TestSignalInvariantsAndConfigGuards:
    def test_signal_rejects_inverted_long_levels(self):
        with pytest.raises(ValueError):
            MeanReversionSignal(
                instrument=SIGNAL_INSTRUMENT, direction=SignalDirection.LONG,
                triggered_at=SESSION_START, entry_reference_price=100.0,
                intraday_mean_price=105.0, dispersion_at_entry=2.0,
                stretch_in_sigma=-2.5,
                stop_loss_price=102.0,  # WRONG: stop above entry for a LONG
                target_price=105.0, regime_adx_at_entry=10.0,
            )

    @pytest.mark.parametrize("bad_kwargs", [
        {"entry_sigma": 0.0},
        {"stop_sigma": -1.0},
        {"dispersion_lookback_bars": 1},
        {"target_reversion_fraction": 1.5},
        {"entry_percentile": 60.0},
        {"min_dispersion_fraction_of_price": -0.1},
    ])
    def test_config_validates_parameters(self, bad_kwargs):
        with pytest.raises(ValueError):
            IntradayMeanReversionConfig(**bad_kwargs)
