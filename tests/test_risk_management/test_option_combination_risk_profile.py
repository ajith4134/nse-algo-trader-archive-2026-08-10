from datetime import date

import pytest

from nse_algo_trader.risk_management import (
    PositionRiskCategory,
    assess_option_combination_risk,
)
from nse_algo_trader.strategy_engine import OptionLegAction, OptionLegIntent
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

EXPIRY = date(2026, 7, 28)
FAR_EXPIRY = date(2026, 8, 25)


def _leg(
    strike: float,
    right: OptionRight,
    action: OptionLegAction,
    lots: int = 1,
    lot_size: int = 75,
    expiry: date = EXPIRY,
) -> OptionLegIntent:
    right_code = "CE" if right is OptionRight.CALL else "PE"
    instrument = Instrument(
        instrument_token=int(strike * 10), trading_symbol=f"X{strike:.0f}{right_code}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=lot_size, tick_size=0.05, underlying_symbol="X",
        strike_price=strike, option_right=right, expiry_date=expiry,
    )
    return OptionLegIntent(instrument, action, lots)


class TestDefinedRiskCombinations:
    def test_bull_put_spread_max_loss_is_width_times_quantity(self):
        profile = assess_option_combination_risk([
            _leg(23750.0, OptionRight.PUT, OptionLegAction.SELL),
            _leg(23650.0, OptionRight.PUT, OptionLegAction.BUY),
        ])
        assert profile.category is PositionRiskCategory.DEFINED_RISK
        assert profile.worst_case_structural_loss == pytest.approx(100.0 * 75)
        assert not profile.has_unlimited_upside_loss
        assert not profile.has_unpaired_short_leg

    def test_iron_condor_is_defined_with_worst_wing_as_max_loss(self):
        profile = assess_option_combination_risk([
            _leg(23500.0, OptionRight.PUT, OptionLegAction.SELL),
            _leg(23300.0, OptionRight.PUT, OptionLegAction.BUY),
            _leg(24500.0, OptionRight.CALL, OptionLegAction.SELL),
            _leg(24700.0, OptionRight.CALL, OptionLegAction.BUY),
        ])
        assert profile.category is PositionRiskCategory.DEFINED_RISK
        assert profile.worst_case_structural_loss == pytest.approx(200.0 * 75)

    def test_long_straddle_has_zero_structural_loss(self):
        # premium paid is the real loss; structurally a long straddle can't lose
        profile = assess_option_combination_risk([
            _leg(24000.0, OptionRight.CALL, OptionLegAction.BUY),
            _leg(24000.0, OptionRight.PUT, OptionLegAction.BUY),
        ])
        assert profile.category is PositionRiskCategory.DEFINED_RISK
        assert profile.worst_case_structural_loss == 0.0


class TestAdversarialUndefinedRiskDetection:
    """Positions deliberately constructed to sneak past the guardrail."""

    def test_naked_short_call_is_unlimited(self):
        profile = assess_option_combination_risk(
            [_leg(24500.0, OptionRight.CALL, OptionLegAction.SELL)]
        )
        assert profile.category is PositionRiskCategory.UNDEFINED_RISK
        assert profile.has_unlimited_upside_loss
        assert profile.worst_case_structural_loss is None

    def test_naked_short_put_is_flagged_even_though_loss_is_finite(self):
        profile = assess_option_combination_risk(
            [_leg(23500.0, OptionRight.PUT, OptionLegAction.SELL)]
        )
        assert profile.category is PositionRiskCategory.UNDEFINED_RISK
        assert profile.has_unpaired_short_leg
        assert profile.worst_case_structural_loss == pytest.approx(23500.0 * 75)

    def test_short_strangle_is_undefined(self):
        profile = assess_option_combination_risk([
            _leg(24500.0, OptionRight.CALL, OptionLegAction.SELL),
            _leg(23500.0, OptionRight.PUT, OptionLegAction.SELL),
        ])
        assert profile.category is PositionRiskCategory.UNDEFINED_RISK

    def test_ratio_spread_with_net_short_calls_is_unlimited(self):
        # buy 1 lot, sell 2 lots — "hedged" at a glance, net short 1 lot
        profile = assess_option_combination_risk([
            _leg(24000.0, OptionRight.CALL, OptionLegAction.BUY, lots=1),
            _leg(24200.0, OptionRight.CALL, OptionLegAction.SELL, lots=2),
        ])
        assert profile.category is PositionRiskCategory.UNDEFINED_RISK
        assert profile.has_unlimited_upside_loss

    def test_hedge_on_wrong_expiry_does_not_count_as_pairing(self):
        # short this week's put "hedged" by next month's long put
        profile = assess_option_combination_risk([
            _leg(23750.0, OptionRight.PUT, OptionLegAction.SELL, expiry=EXPIRY),
            _leg(23650.0, OptionRight.PUT, OptionLegAction.BUY, expiry=FAR_EXPIRY),
        ])
        assert profile.has_unpaired_short_leg
        assert profile.category is PositionRiskCategory.UNDEFINED_RISK

    def test_hedge_on_wrong_right_does_not_count_as_pairing(self):
        # short put "hedged" by a long CALL — different risk side entirely
        profile = assess_option_combination_risk([
            _leg(23750.0, OptionRight.PUT, OptionLegAction.SELL),
            _leg(23650.0, OptionRight.CALL, OptionLegAction.BUY),
        ])
        assert profile.has_unpaired_short_leg

    def test_mismatched_lot_sizes_cannot_hide_net_short_exposure(self):
        # 1 short lot of 150-share contract vs 1 long lot of 75-share contract
        profile = assess_option_combination_risk([
            _leg(24000.0, OptionRight.CALL, OptionLegAction.SELL, lot_size=150),
            _leg(24200.0, OptionRight.CALL, OptionLegAction.BUY, lot_size=75),
        ])
        assert profile.category is PositionRiskCategory.UNDEFINED_RISK
        assert profile.has_unlimited_upside_loss

    def test_empty_combination_raises(self):
        with pytest.raises(ValueError):
            assess_option_combination_risk([])
