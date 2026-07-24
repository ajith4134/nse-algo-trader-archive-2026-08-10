"""§9 prediction records for options (Rule I: options are first-class lab
experiments). Directional confidence rises WITH ADX (trend); credit-spread
confidence rises as ADX FALLS (range)."""

from datetime import date

from nse_algo_trader.paper_trading.prediction_lab.option_prediction_records import (
    build_credit_spread_prediction_record,
    build_directional_option_prediction_record,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictionLabeledTable,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

OPT = Instrument(
    instrument_token=7, trading_symbol="NIFTY26JUL23600CE",
    exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
    lot_size=75, tick_size=0.05, underlying_symbol="NIFTY", strike_price=23600.0,
    option_right=OptionRight.CALL, expiry_date=date(2026, 7, 30),
)
TODAY = date(2026, 7, 24)


class TestDirectionalConfidenceRisesWithAdx:
    def test_strong_trend_is_confident_win(self):
        rec = build_directional_option_prediction_record(OPT, "long", 40.0, TODAY, 2.0)
        assert rec.assigned_table is PredictionLabeledTable.CONFIDENT_WIN
        assert rec.win_probability > 0.6

    def test_weak_trend_is_confident_loss(self):
        rec = build_directional_option_prediction_record(OPT, "long", 12.0, TODAY, 2.0)
        assert rec.assigned_table is PredictionLabeledTable.CONFIDENT_LOSS
        assert rec.win_probability < 0.4


class TestCreditSpreadConfidenceRisesAsAdxFalls:
    def test_low_adx_range_is_confident_win(self):
        rec = build_credit_spread_prediction_record(OPT, "bull_put", 12.0, TODAY)
        assert rec.assigned_table is PredictionLabeledTable.CONFIDENT_WIN
        assert rec.strategy_tag == "credit_spread_v1"

    def test_high_adx_trending_is_confident_loss_for_a_spread(self):
        rec = build_credit_spread_prediction_record(OPT, "bear_call", 40.0, TODAY)
        assert rec.assigned_table is PredictionLabeledTable.CONFIDENT_LOSS

    def test_directional_and_spread_disagree_at_the_same_adx(self):
        adx = 40.0  # strongly trending
        directional = build_directional_option_prediction_record(OPT, "long", adx, TODAY, 2.0)
        spread = build_credit_spread_prediction_record(OPT, "bull_put", adx, TODAY)
        # trend is good for a long option, bad for a premium-selling spread
        assert directional.win_probability > 0.5
        assert spread.win_probability < 0.5
