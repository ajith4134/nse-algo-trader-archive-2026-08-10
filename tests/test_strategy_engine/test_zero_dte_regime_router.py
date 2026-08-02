"""B32: the 0-DTE structure router maps each regime to the right defined-risk structure, and
abstains (counted) when no structure has an edge."""

from nse_algo_trader.indicators.dealer_gamma_exposure import (
    DealerGammaExposureReading,
    DealerGammaRegime,
)
from nse_algo_trader.indicators.yang_zhang_realized_volatility import (
    VolatilityExpansionReading,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.strategy_engine.zero_dte_regime_router import (
    ExpiryDayTimeWindow,
    ZeroDteEntryTrigger,
    ZeroDteRouterInputs,
    ZeroDteStructure,
    route_zero_dte_structure,
)


def _vol(is_expanding: bool) -> VolatilityExpansionReading:
    return VolatilityExpansionReading(
        is_expanding=is_expanding, current_realized_volatility=0.02,
        band_mean=0.01, band_upper_threshold=0.015, abstain_reason=None,
    )


def _gamma(regime: DealerGammaRegime) -> DealerGammaExposureReading:
    return DealerGammaExposureReading(
        total_gamma_exposure=(1.0 if regime is DealerGammaRegime.LONG_GAMMA_PIN else -1.0),
        regime=regime, contributing_strike_count=10, abstain_reason=None,
    )


def _inputs(**overrides) -> ZeroDteRouterInputs:
    base = dict(
        adx_regime=MarketRegime.INDECISIVE,
        volatility_expansion=_vol(False),
        dealer_gamma=_gamma(DealerGammaRegime.NEUTRAL),
        momentum_direction=None,
        opening_range_breakout_direction=None,
        time_window=ExpiryDayTimeWindow.OTHER,
        implied_volatility_is_rich=None,
        near_max_pain=False,
    )
    base.update(overrides)
    return ZeroDteRouterInputs(**base)


def test_orb_breakout_routes_to_directional_in_break_direction():
    d = route_zero_dte_structure(_inputs(opening_range_breakout_direction=SignalDirection.LONG))
    assert d.structure is ZeroDteStructure.DIRECTIONAL_LONG_OPTION
    assert d.direction is SignalDirection.LONG
    assert d.trigger is ZeroDteEntryTrigger.OPENING_RANGE_BREAKOUT


def test_trend_plus_vol_expansion_routes_directional():
    d = route_zero_dte_structure(_inputs(
        adx_regime=MarketRegime.TRENDING,
        volatility_expansion=_vol(True),
        momentum_direction=SignalDirection.SHORT,
    ))
    assert d.structure is ZeroDteStructure.DIRECTIONAL_LONG_OPTION
    assert d.direction is SignalDirection.SHORT


def test_short_gamma_amplify_routes_directional_via_flow():
    d = route_zero_dte_structure(_inputs(
        dealer_gamma=_gamma(DealerGammaRegime.SHORT_GAMMA_TREND),
        volatility_expansion=_vol(True),
        momentum_direction=SignalDirection.LONG,
    ))
    assert d.structure is ZeroDteStructure.DIRECTIONAL_LONG_OPTION
    assert d.trigger is ZeroDteEntryTrigger.DEALER_GAMMA_FLOW


def test_ambiguous_vol_expansion_routes_to_straddle():
    d = route_zero_dte_structure(_inputs(
        volatility_expansion=_vol(True), momentum_direction=None,
    ))
    assert d.structure is ZeroDteStructure.LONG_STRADDLE
    assert d.direction is None


def test_pin_long_gamma_iv_rich_routes_short_premium():
    d = route_zero_dte_structure(_inputs(
        dealer_gamma=_gamma(DealerGammaRegime.LONG_GAMMA_PIN),
        implied_volatility_is_rich=True,
    ))
    assert d.structure is ZeroDteStructure.SHORT_PREMIUM_SPREAD


def test_range_bound_near_max_pain_routes_short_premium():
    d = route_zero_dte_structure(_inputs(
        adx_regime=MarketRegime.RANGE_BOUND, near_max_pain=True,
    ))
    assert d.structure is ZeroDteStructure.SHORT_PREMIUM_SPREAD


def test_no_edge_abstains_with_reason():
    d = route_zero_dte_structure(_inputs())
    assert d.structure is ZeroDteStructure.ABSTAIN
    assert d.trigger is ZeroDteEntryTrigger.NONE
    assert d.reason


def test_pin_without_confirmation_does_not_short_premium():
    # long-gamma pin but IV not rich and not near max-pain → no theta harvest, abstain.
    d = route_zero_dte_structure(_inputs(
        dealer_gamma=_gamma(DealerGammaRegime.LONG_GAMMA_PIN),
        implied_volatility_is_rich=None, near_max_pain=False,
    ))
    assert d.structure is ZeroDteStructure.ABSTAIN
