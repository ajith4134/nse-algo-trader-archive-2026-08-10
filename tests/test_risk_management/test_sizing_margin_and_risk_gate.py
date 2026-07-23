from datetime import date, datetime

import pytest

from nse_algo_trader.risk_management import (
    MarginEstimateConfig,
    RiskBudgetConfig,
    RiskGateDecision,
    RiskRejectionReason,
    estimate_defined_risk_spread_margin,
    estimate_intraday_cash_margin,
    evaluate_credit_spread_signal,
    evaluate_opening_range_breakout_signal,
    size_cash_position_by_stop_distance,
    size_defined_risk_spread_lots,
)
from nse_algo_trader.strategy_engine import (
    CreditSpreadBias,
    CreditSpreadSignal,
    OpeningRangeBreakoutSignal,
    OptionLegAction,
    OptionLegIntent,
    SignalDirection,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

TEN_LAKH_BUDGET = RiskBudgetConfig(account_capital=1_000_000.0)  # 1% risk = 10,000

CASH_INSTRUMENT = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)


def _put_leg(strike: float, action: OptionLegAction, lot_size: int = 75) -> OptionLegIntent:
    return OptionLegIntent(
        Instrument(
            instrument_token=int(strike * 10), trading_symbol=f"NIFTY{strike:.0f}PE",
            exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
            lot_size=lot_size, tick_size=0.05, underlying_symbol="NIFTY",
            strike_price=strike, option_right=OptionRight.PUT,
            expiry_date=date(2026, 7, 28),
        ),
        action, 1,
    )


def _orb_signal(entry: float, stop: float) -> OpeningRangeBreakoutSignal:
    return OpeningRangeBreakoutSignal(
        instrument=CASH_INSTRUMENT, direction=SignalDirection.LONG,
        triggered_at=datetime(2026, 7, 22, 9, 30), breakout_close_price=entry,
        opening_range_high=entry - 1, opening_range_low=stop,
        stop_loss_price=stop, target_price=entry + 2 * (entry - stop),
    )


BULL_PUT_SIGNAL = CreditSpreadSignal(
    underlying_symbol="NIFTY", bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD,
    short_leg=_put_leg(23750.0, OptionLegAction.SELL),
    hedge_leg=_put_leg(23650.0, OptionLegAction.BUY),
    short_leg_estimated_delta=0.24,
)


class TestPositionSizing:
    def test_cash_sizing_is_risk_budget_over_stop_distance(self):
        # risk budget 10,000; stop distance 5 -> 2,000 shares; margin check:
        # 2,000 * 103 * 0.25 = 51,500 < 250,000 margin budget -> risk-limited
        assert size_cash_position_by_stop_distance(103.0, 98.0, TEN_LAKH_BUDGET) == 2000

    def test_cash_sizing_caps_by_margin_when_stop_is_tight(self):
        # stop 0.5 away -> risk allows 20,000 shares, but margin budget
        # 250,000 / (2000*0.25) = 500 shares caps it
        assert size_cash_position_by_stop_distance(2000.0, 1999.5, TEN_LAKH_BUDGET) == 500

    def test_zero_stop_distance_sizes_zero(self):
        assert size_cash_position_by_stop_distance(100.0, 100.0, TEN_LAKH_BUDGET) == 0

    def test_spread_sizing_uses_max_loss_per_lot(self):
        # max loss/lot 7,500 -> risk budget 10,000 -> 1 lot
        assert size_defined_risk_spread_lots(7500.0, 8250.0, TEN_LAKH_BUDGET) == 1

    def test_spread_too_expensive_for_budget_sizes_zero(self):
        assert size_defined_risk_spread_lots(12_000.0, 13_200.0, TEN_LAKH_BUDGET) == 0


class TestMarginEstimates:
    def test_spread_margin_overstates_with_buffer(self):
        assert estimate_defined_risk_spread_margin(7500.0) == pytest.approx(8250.0)

    def test_cash_margin_is_stricter_than_sebi_20_percent_floor(self):
        notional_margin = estimate_intraday_cash_margin(100.0, 1000)
        assert notional_margin == pytest.approx(25_000.0)
        assert notional_margin >= 100.0 * 1000 * 0.20


class TestOpeningRangeBreakoutRiskGate:
    def test_normal_signal_is_approved_with_sized_quantity(self):
        decision = evaluate_opening_range_breakout_signal(
            _orb_signal(entry=103.0, stop=98.0), TEN_LAKH_BUDGET
        )
        assert decision.approved
        assert decision.approved_quantity == 2000
        assert decision.estimated_worst_case_loss == pytest.approx(10_000.0)
        assert decision.estimated_margin == pytest.approx(103.0 * 2000 * 0.25)

    def test_degenerate_stop_is_rejected(self):
        decision = evaluate_opening_range_breakout_signal(
            _orb_signal(entry=100.0, stop=100.0), TEN_LAKH_BUDGET
        )
        assert not decision.approved
        assert RiskRejectionReason.STOP_DISTANCE_NOT_POSITIVE in decision.rejection_reasons

    def test_tiny_account_cannot_afford_one_share_of_pricey_stock(self):
        tiny_budget = RiskBudgetConfig(account_capital=10_000.0)  # 1% = 100
        decision = evaluate_opening_range_breakout_signal(
            _orb_signal(entry=40_000.0, stop=39_500.0), tiny_budget  # MRF-like price
        )
        assert not decision.approved
        assert (
            RiskRejectionReason.RISK_BUDGET_TOO_SMALL_FOR_ONE_UNIT
            in decision.rejection_reasons
        )


class TestCreditSpreadRiskGate:
    def test_normal_spread_is_approved_with_margin_and_max_loss(self):
        decision = evaluate_credit_spread_signal(
            BULL_PUT_SIGNAL, frozenset(), TEN_LAKH_BUDGET
        )
        assert decision.approved
        assert decision.approved_quantity == 1
        assert decision.estimated_worst_case_loss == pytest.approx(7500.0)
        assert decision.estimated_margin == pytest.approx(8250.0)

    def test_banned_underlying_is_rejected(self):
        decision = evaluate_credit_spread_signal(
            BULL_PUT_SIGNAL, frozenset({"NIFTY"}), TEN_LAKH_BUDGET
        )
        assert not decision.approved
        assert RiskRejectionReason.UNDERLYING_IN_FO_BAN_LIST in decision.rejection_reasons

    def test_budget_too_small_for_one_lot_is_rejected_not_rounded_up(self):
        small_budget = RiskBudgetConfig(account_capital=500_000.0)  # 1% = 5,000 < 7,500
        decision = evaluate_credit_spread_signal(
            BULL_PUT_SIGNAL, frozenset(), small_budget
        )
        assert not decision.approved
        assert (
            RiskRejectionReason.RISK_BUDGET_TOO_SMALL_FOR_ONE_UNIT
            in decision.rejection_reasons
        )

    def test_ban_and_undefined_risk_reasons_accumulate(self):
        adversarial_signal = CreditSpreadSignal(
            underlying_symbol="KAYNES", bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD,
            short_leg=_put_leg(4000.0, OptionLegAction.SELL, lot_size=150),
            hedge_leg=_put_leg(3900.0, OptionLegAction.BUY, lot_size=75),
            short_leg_estimated_delta=0.25,
        )  # mismatched lot sizes -> net short exposure survives the lots check
        decision = evaluate_credit_spread_signal(
            adversarial_signal, frozenset({"KAYNES"}), TEN_LAKH_BUDGET
        )
        assert not decision.approved
        assert RiskRejectionReason.UNDERLYING_IN_FO_BAN_LIST in decision.rejection_reasons
        assert (
            RiskRejectionReason.UNDEFINED_RISK_COMBINATION in decision.rejection_reasons
        )
