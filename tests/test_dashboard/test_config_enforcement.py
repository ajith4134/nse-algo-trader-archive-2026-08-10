from datetime import datetime, timedelta

from nse_algo_trader.dashboard import (
    TradableSegment,
    TradingControlConfig,
    clamp_quantity_to_capital_limits,
    is_orb_cash_trading_enabled,
    map_control_config_to_risk_budget,
    run_config_enforced_orb_paper_lab,
)
from nse_algo_trader.dashboard.trading_control_config import SelectableStrategy
from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.paper_trading import INDIA_MARKET_TIMEZONE, PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

INFY = Instrument(
    408065, "INFY", ExchangeSegment.NSE_CASH, InstrumentKind.CASH_EQUITY,
    1, 0.05, None, None, None, None,
)


def _breakout_session():
    start = datetime(2026, 7, 22, 9, 15, tzinfo=INDIA_MARKET_TIMEZONE)
    ohlc = [(100, 101, 98, 100), (100, 102, 99, 101), (101, 102, 99, 100),
            (101, 104, 100, 103.0), (103, 114, 103, 113.5)]
    return [
        PriceBar(408065, start + timedelta(minutes=5 * i), BarInterval.MINUTE_5,
                 o, h, l, c, 1000)
        for i, (o, h, l, c) in enumerate(ohlc)
    ]


class TestConfigToRiskBudget:
    def test_capital_and_risk_flow_into_budget(self):
        budget = map_control_config_to_risk_budget(
            TradingControlConfig(account_virtual_capital=500_000.0,
                                 max_risk_per_trade_fraction=0.02)
        )
        assert budget.account_capital == 500_000.0
        assert budget.max_risk_per_trade_fraction == 0.02

    def test_max_capital_per_trade_caps_margin_fraction(self):
        budget = map_control_config_to_risk_budget(
            TradingControlConfig(account_virtual_capital=1_000_000.0,
                                 max_capital_per_trade=100_000.0)
        )
        # 100k notional * 0.25 margin / 1M capital = 0.025
        assert budget.max_margin_per_position_fraction < 0.05


class TestSegmentStrategyGate:
    def test_all_on_is_enabled(self):
        assert is_orb_cash_trading_enabled(TradingControlConfig())

    def test_cash_segment_off_disables(self):
        config = TradingControlConfig()
        config.segment_enabled[TradableSegment.NSE_CASH_EQUITY.value] = False
        assert not is_orb_cash_trading_enabled(config)

    def test_orb_strategy_off_disables(self):
        config = TradingControlConfig()
        config.strategy_enabled[SelectableStrategy.OPENING_RANGE_BREAKOUT.value] = False
        assert not is_orb_cash_trading_enabled(config)


class TestCapitalPerTradeClamp:
    def test_clamps_down_to_max_capital(self):
        # entry 100, want 5000 shares (500k), but max/trade 100k -> 1000 shares
        assert clamp_quantity_to_capital_limits(100.0, 5000, TradingControlConfig(
            max_capital_per_trade=100_000.0, min_capital_per_trade=1000.0)) == 1000

    def test_rejects_below_min_capital(self):
        # entry 100, 5 shares = 500 notional, min 10k -> skip (0)
        assert clamp_quantity_to_capital_limits(100.0, 5, TradingControlConfig(
            min_capital_per_trade=10_000.0)) == 0

    def test_zero_inputs_safe(self):
        assert clamp_quantity_to_capital_limits(0.0, 100, TradingControlConfig()) == 0
        assert clamp_quantity_to_capital_limits(100.0, 0, TradingControlConfig()) == 0


class TestConfigEnforcedRun:
    def _run(self, config):
        ledger = PaperTradingLedger(config.account_virtual_capital)
        board = PredictionTableScoreboard()
        run_config_enforced_orb_paper_lab(config, _breakout_session(), INFY, ledger, board)
        return ledger, board

    def test_enabled_config_trades(self):
        ledger, board = self._run(TradingControlConfig())
        assert len(ledger.recorded_fills) > 0

    def test_segment_off_trades_nothing(self):
        config = TradingControlConfig()
        config.segment_enabled[TradableSegment.NSE_CASH_EQUITY.value] = False
        ledger, board = self._run(config)
        assert ledger.recorded_fills == []
        assert board.overall_score() is None

    def test_strategy_off_trades_nothing(self):
        config = TradingControlConfig()
        config.strategy_enabled[SelectableStrategy.OPENING_RANGE_BREAKOUT.value] = False
        ledger, board = self._run(config)
        assert ledger.recorded_fills == []
