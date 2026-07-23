from datetime import datetime

from nse_algo_trader.broker_oms import OrderSide
from nse_algo_trader.dashboard import (
    AlertLevel,
    TradingControlConfig,
    TradingMode,
    build_dashboard_snapshot,
    generate_dashboard_alerts,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard


def _levels(alerts):
    return {a.level for a in alerts}


def _cats(alerts):
    return {a.category for a in alerts}


class TestGenerateAlerts:
    def _flat_ledger(self):
        return PaperTradingLedger(1_000_000.0)

    def test_all_healthy_yields_single_info(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), self._flat_ledger(),
            PredictionTableScoreboard(), kite_access_token_valid=True,
            stored_bar_count=1650,
        )
        assert len(alerts) == 1
        assert alerts[0].level is AlertLevel.INFO

    def test_live_mode_warns(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(trading_mode=TradingMode.LIVE), self._flat_ledger(),
            PredictionTableScoreboard(), True, 1650,
        )
        assert "mode" in _cats(alerts)
        assert AlertLevel.WARNING in _levels(alerts)

    def test_open_position_is_critical(self):
        ledger = PaperTradingLedger(1_000_000.0)
        ledger.record_fill(1, OrderSide.BUY, 100, 100.0)  # left open
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), ledger, PredictionTableScoreboard(), True, 1650,
        )
        crit = [a for a in alerts if a.level is AlertLevel.CRITICAL]
        assert crit and crit[0].category == "position"

    def test_expired_token_warns(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), self._flat_ledger(),
            PredictionTableScoreboard(), kite_access_token_valid=False,
            stored_bar_count=1650,
        )
        assert "auth" in _cats(alerts)

    def test_no_bars_warns(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), self._flat_ledger(),
            PredictionTableScoreboard(), True, stored_bar_count=0,
        )
        assert "data" in _cats(alerts)


class TestSnapshotIncludesAlerts:
    def test_snapshot_has_alerts_field(self):
        snapshot = build_dashboard_snapshot(
            TradingControlConfig(), PaperTradingLedger(1_000_000.0),
            PredictionTableScoreboard(), datetime(2026, 7, 23, 12, 0),
            kite_access_token_valid=True, stored_bar_count=1650,
        )
        payload = snapshot.to_json_dict()
        assert "alerts" in payload and len(payload["alerts"]) >= 1
        assert payload["alerts"][0]["level"] == "info"
