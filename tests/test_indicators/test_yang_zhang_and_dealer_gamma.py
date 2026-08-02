"""B32 Slice-1 core math: Yang-Zhang realized vol + vol-expansion trigger, BS gamma, and dealer
gamma exposure (GEX). Property + adversarial + abstention coverage (Rule O.6)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.indicators.black_scholes_implied_volatility import (
    compute_black_scholes_gamma,
)
from nse_algo_trader.indicators.dealer_gamma_exposure import (
    DealerGammaRegime,
    OptionChainStrikeInputs,
    compute_dealer_gamma_exposure,
)
from nse_algo_trader.indicators.yang_zhang_realized_volatility import (
    compute_yang_zhang_realized_volatility,
    detect_intraday_volatility_expansion,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar

IST = ZoneInfo("Asia/Kolkata")


def _bar(i: int, o: float, h: float, low: float, c: float) -> PriceBar:
    return PriceBar(
        instrument_token=1,
        timestamp=datetime(2026, 7, 28, 9, 15, tzinfo=IST) + timedelta(minutes=5 * i),
        interval=BarInterval.MINUTE_5,
        open_price=o, high_price=h, low_price=low, close_price=c, volume=1000,
        open_interest=None,
    )


def _calm_then_wild_bars(calm_count: int, wild_count: int) -> list[PriceBar]:
    bars: list[PriceBar] = []
    price = 100.0
    for i in range(calm_count):
        price += 0.02 * (1 if i % 2 else -1)  # tiny oscillation
        bars.append(_bar(i, price, price + 0.03, price - 0.03, price))
    for j in range(wild_count):
        step = 1.5 * (1 if j % 2 else -1)  # large whipsaw
        o = price
        price += step
        bars.append(_bar(calm_count + j, o, max(o, price) + 0.8, min(o, price) - 0.8, price))
    return bars


# ---- Yang-Zhang realized volatility -------------------------------------------------

def test_yang_zhang_abstains_below_minimum_bars():
    assert compute_yang_zhang_realized_volatility(_calm_then_wild_bars(2, 0)) is None


def test_yang_zhang_rises_with_wider_range():
    calm = compute_yang_zhang_realized_volatility(_calm_then_wild_bars(12, 0))
    wild = compute_yang_zhang_realized_volatility(_calm_then_wild_bars(0, 12))
    assert calm is not None and wild is not None
    assert wild > calm > 0.0


def test_yang_zhang_survives_degenerate_zero_price_bar():
    bars = _calm_then_wild_bars(12, 0)
    bars[3] = _bar(3, 0.0, 0.0, 0.0, 0.0)  # a corrupt bar must be skipped, not crash
    assert compute_yang_zhang_realized_volatility(bars) is not None


# ---- volatility-expansion trigger ---------------------------------------------------

def test_expansion_detected_when_volatility_breaks_out():
    reading = detect_intraday_volatility_expansion(
        _calm_then_wild_bars(24, 6), realized_volatility_window_bars=6, band_series_length=12
    )
    assert reading.abstain_reason is None
    assert reading.is_expanding is True
    assert reading.current_realized_volatility > reading.band_upper_threshold


def test_expansion_abstains_while_warming_up():
    reading = detect_intraday_volatility_expansion(
        _calm_then_wild_bars(5, 0), realized_volatility_window_bars=6, band_series_length=12
    )
    assert reading.is_expanding is False
    assert reading.abstain_reason is not None


def test_expansion_quiet_when_volatility_is_stable():
    reading = detect_intraday_volatility_expansion(
        _calm_then_wild_bars(40, 0), realized_volatility_window_bars=6, band_series_length=12
    )
    assert reading.is_expanding is False


# ---- Black-Scholes gamma ------------------------------------------------------------

def test_gamma_is_highest_at_the_money():
    atm = compute_black_scholes_gamma(100.0, 100.0, 30 / 365, 0.2)
    otm = compute_black_scholes_gamma(100.0, 130.0, 30 / 365, 0.2)
    assert atm > otm > 0.0


def test_gamma_collapses_at_expiry_and_never_negative():
    assert compute_black_scholes_gamma(100.0, 100.0, 0.0, 0.2) == 0.0
    assert compute_black_scholes_gamma(100.0, 100.0, 30 / 365, 0.2) >= 0.0


# ---- dealer gamma exposure (GEX) ----------------------------------------------------

def _strike(k: float, coi: int, poi: int) -> OptionChainStrikeInputs:
    return OptionChainStrikeInputs(
        strike_price=k, call_implied_volatility=0.18, put_implied_volatility=0.18,
        call_open_interest=coi, put_open_interest=poi, contract_multiplier=50,
    )


def test_gex_positive_and_pin_when_calls_dominate():
    chain = [_strike(19000, 5000, 100), _strike(20000, 8000, 200), _strike(21000, 4000, 100)]
    reading = compute_dealer_gamma_exposure(20000.0, 0.5 / 365, chain)
    assert reading.total_gamma_exposure is not None and reading.total_gamma_exposure > 0.0
    assert reading.regime is DealerGammaRegime.LONG_GAMMA_PIN


def test_gex_negative_and_trend_when_puts_dominate():
    chain = [_strike(19000, 100, 5000), _strike(20000, 200, 8000), _strike(21000, 100, 4000)]
    reading = compute_dealer_gamma_exposure(20000.0, 0.5 / 365, chain)
    assert reading.total_gamma_exposure is not None and reading.total_gamma_exposure < 0.0
    assert reading.regime is DealerGammaRegime.SHORT_GAMMA_TREND


def test_gex_abstains_on_empty_chain():
    reading = compute_dealer_gamma_exposure(20000.0, 0.5 / 365, [])
    assert reading.total_gamma_exposure is None
    assert reading.regime is DealerGammaRegime.UNKNOWN
