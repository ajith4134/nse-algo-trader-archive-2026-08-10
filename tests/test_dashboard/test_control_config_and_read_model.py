from datetime import datetime
from pathlib import Path

import pytest

from nse_algo_trader.dashboard import (
    SelectableStrategy,
    TradableSegment,
    TradingControlConfig,
    TradingMode,
    build_dashboard_snapshot,
    load_trading_control_config,
    save_trading_control_config,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import (
    PredictionTableScoreboard,
    build_orb_prediction_record,
    grade_prediction,
)
from nse_algo_trader.strategy_engine import OpeningRangeBreakoutSignal, SignalDirection
from nse_algo_trader.broker_oms import OrderSide
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

INFY = Instrument(
    408065, "INFY", ExchangeSegment.NSE_CASH, InstrumentKind.CASH_EQUITY,
    1, 0.05, None, None, None, None,
)


class TestTradingControlConfig:
    def test_defaults_are_paper_all_segments_all_strategies_on(self):
        config = TradingControlConfig()
        assert config.trading_mode is TradingMode.PAPER
        assert all(config.segment_enabled.values())
        assert all(config.strategy_enabled.values())
        assert config.is_segment_enabled(TradableSegment.NSE_INDEX_OPTIONS)
        assert config.is_strategy_enabled(SelectableStrategy.CREDIT_SPREAD)

    def test_editable_paper_capital_and_min_per_trade(self):
        config = TradingControlConfig(
            account_virtual_capital=500_000.0, min_capital_per_trade=5_000.0
        )
        config.validate()
        assert config.account_virtual_capital == 500_000.0
        assert config.min_capital_per_trade == 5_000.0

    def test_segment_toggle_off(self):
        config = TradingControlConfig()
        config.segment_enabled[TradableSegment.NSE_STOCK_OPTIONS.value] = False
        assert not config.is_segment_enabled(TradableSegment.NSE_STOCK_OPTIONS)

    def test_invalid_capital_rejected(self):
        with pytest.raises(ValueError, match="account_virtual_capital"):
            TradingControlConfig(account_virtual_capital=-1).validate()

    def test_max_below_min_rejected(self):
        with pytest.raises(ValueError, match="max_capital_per_trade"):
            TradingControlConfig(
                min_capital_per_trade=100_000.0, max_capital_per_trade=10_000.0
            ).validate()

    def test_round_trips_through_json_and_file(self, tmp_path: Path):
        config = TradingControlConfig(
            trading_mode=TradingMode.PAPER, account_virtual_capital=750_000.0
        )
        config.segment_enabled[TradableSegment.NSE_STOCK_OPTIONS.value] = False
        path = tmp_path / "control.json"
        save_trading_control_config(config, path)
        reloaded = load_trading_control_config(path)
        assert reloaded.account_virtual_capital == 750_000.0
        assert not reloaded.is_segment_enabled(TradableSegment.NSE_STOCK_OPTIONS)

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        config = load_trading_control_config(tmp_path / "does_not_exist.json")
        assert config.account_virtual_capital == 1_000_000.0


class TestDashboardSnapshot:
    def _scoreboard_with_one_win(self):
        board = PredictionTableScoreboard()
        signal = OpeningRangeBreakoutSignal(
            instrument=INFY, direction=SignalDirection.LONG,
            triggered_at=datetime(2026, 7, 22, 9, 30),
            breakout_close_price=103.0, opening_range_high=102,
            opening_range_low=98, stop_loss_price=98.0, target_price=113.0,
        )
        record = build_orb_prediction_record(signal, 40.0, datetime(2026, 7, 22).date(), 2.0)
        board.add_graded_prediction(grade_prediction(record, 5000.0))
        return board

    def test_snapshot_includes_config_roadmap_tree_and_live_state(self):
        ledger = PaperTradingLedger(1_000_000.0)
        ledger.record_fill(408065, OrderSide.BUY, 100, 100.0)
        ledger.record_fill(408065, OrderSide.SELL, 100, 103.0)
        snapshot = build_dashboard_snapshot(
            TradingControlConfig(), ledger, self._scoreboard_with_one_win(),
            datetime(2026, 7, 23, 12, 0),
        )
        payload = snapshot.to_json_dict()
        # 11 layers, 16 trunks
        assert len(payload["layer_roadmap"]) == 11
        assert len(payload["concept_tree"]) == 16
        assert payload["concept_tree_counts"]["trunk_count"] == 16
        assert payload["concept_tree_counts"]["total_branch_count"] > 100
        # live paper state reflects the real ledger
        assert payload["paper_trading"]["realized_pnl"] == pytest.approx(300.0)
        assert payload["paper_trading"]["is_flat"] is True
        # config editable knobs present
        assert payload["control_config"]["account_virtual_capital"] == 1_000_000.0
        # lab scoreboard present
        win = next(t for t in payload["prediction_tables"] if t["table"] == "confident_win")
        assert win["trade_count"] == 1

    def test_snapshot_is_json_serializable(self):
        import json
        snapshot = build_dashboard_snapshot(
            TradingControlConfig(), PaperTradingLedger(1_000_000.0),
            PredictionTableScoreboard(), datetime(2026, 7, 23, 12, 0),
        )
        json.dumps(snapshot.to_json_dict())  # must not raise
