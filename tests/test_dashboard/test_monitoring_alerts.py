from datetime import datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard import (
    AlertLevel,
    TradingControlConfig,
    TradingMode,
    build_dashboard_snapshot,
    generate_dashboard_alerts,
)
from nse_algo_trader.dashboard.dashboard_read_model import (
    PaperTradingSummary,
    PredictionTableSummary,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard

IST = ZoneInfo("Asia/Kolkata")
MIDDAY = datetime(2026, 7, 24, 12, 0, tzinfo=IST)
AFTER_SQUARE_OFF = datetime(2026, 7, 24, 15, 20, tzinfo=IST)


def _levels(alerts):
    return {a.level for a in alerts}


def _cats(alerts):
    return {a.category for a in alerts}


def _flat_summary():
    return PaperTradingSummary(1_000_000.0, 0.0, 0, is_flat=True)


def _empty_tables():
    return [
        PredictionTableSummary(t, 0, None, None, None, None)
        for t in ("confident_win", "confident_loss", "uncertain")
    ]


class TestGenerateAlerts:
    def test_all_healthy_yields_single_info(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), _flat_summary(), _empty_tables(),
            kite_access_token_valid=True, stored_bar_count=1650,
            generated_at=MIDDAY, open_position_count=0,
        )
        assert len(alerts) == 1
        assert alerts[0].level is AlertLevel.INFO

    def test_live_mode_warns(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(trading_mode=TradingMode.LIVE), _flat_summary(),
            _empty_tables(), True, 1650, generated_at=MIDDAY,
        )
        assert "mode" in _cats(alerts)
        assert AlertLevel.WARNING in _levels(alerts)

    def test_open_position_midsession_is_info_not_critical(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), PaperTradingSummary(1_000_000.0, 0.0, 1, is_flat=False),
            _empty_tables(), True, 1650, generated_at=MIDDAY, open_position_count=45,
        )
        pos = [a for a in alerts if a.category == "position"]
        assert pos and pos[0].level is AlertLevel.INFO  # normal intraday, not overnight

    def test_open_position_after_square_off_is_critical(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), PaperTradingSummary(1_000_000.0, 0.0, 1, is_flat=False),
            _empty_tables(), True, 1650, generated_at=AFTER_SQUARE_OFF, open_position_count=3,
        )
        crit = [a for a in alerts if a.level is AlertLevel.CRITICAL]
        assert crit and crit[0].category == "position"

    def test_expired_token_warns(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), _flat_summary(), _empty_tables(),
            kite_access_token_valid=False, stored_bar_count=1650, generated_at=MIDDAY,
        )
        assert "auth" in _cats(alerts)

    def test_no_bars_warns(self):
        alerts = generate_dashboard_alerts(
            TradingControlConfig(), _flat_summary(), _empty_tables(),
            True, stored_bar_count=0, generated_at=MIDDAY,
        )
        assert "data" in _cats(alerts)


class TestSnapshotIncludesAlerts:
    def test_snapshot_has_alerts_field(self):
        snapshot = build_dashboard_snapshot(
            TradingControlConfig(), PaperTradingLedger(1_000_000.0),
            PredictionTableScoreboard(), MIDDAY,
            kite_access_token_valid=True, stored_bar_count=1650,
        )
        payload = snapshot.to_json_dict()
        assert "alerts" in payload and len(payload["alerts"]) >= 1
        assert payload["alerts"][0]["level"] == "info"
