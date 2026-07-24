"""Tests for the live paper service publish path + read-model open positions.

The threaded loop's live behavior is Rule-F verified against the running
server (45 open positions on the dashboard, 2026-07-24); here we pin the
non-threaded publish + serialization with a fake feed.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.dashboard_read_model import (
    LiveUniverseStatus,
    OpenPositionSummary,
    build_dashboard_snapshot,
)
from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.dashboard.trading_control_config import TradingControlConfig
from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")
STOCK = Instrument(
    instrument_token=111, trading_symbol="TESTCO",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05,
)


def _bar(ts, o, h, low, c):
    return PriceBar(STOCK.instrument_token, ts, BarInterval.MINUTE_5, o, h, low, c, 10000)


def _bars_long_breakout_open():
    bars = []
    base = datetime(2026, 7, 20, 9, 15, tzinfo=IST)
    price = 80.0
    for day in range(4):
        for i in range(8):
            price += 0.5
            bars.append(_bar(base.replace(day=20 + day) + timedelta(minutes=5 * i),
                             price, price + 1, price - 1, price))
    t = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
    bars.append(_bar(t, 97, 100, 95, 98))
    bars.append(_bar(t + timedelta(minutes=5), 98, 100, 96, 99))
    bars.append(_bar(t + timedelta(minutes=10), 99, 100, 97, 99))
    bars.append(_bar(t + timedelta(minutes=15), 100, 101.5, 99.5, 101))
    for i in range(4):
        bars.append(_bar(t + timedelta(minutes=20 + 5 * i), 101, 102, 100.5, 101.5))
    return bars


class _FakeFeed:
    def latest_price_by_token(self, instruments):
        return {STOCK.instrument_token: 101.5}

    def recent_intraday_bars(self, instrument, as_of, lookback_calendar_days=7,
                             bar_interval=BarInterval.MINUTE_5):
        return _bars_long_breakout_open()


def _service_with_fake_feed():
    service = LivePaperTradingService(object(), 1_000_000.0)
    service._cash_universe = [STOCK]
    service._feed = _FakeFeed()
    return service


class TestServicePublish:
    def test_advance_then_publish_exposes_open_position(self):
        service = _service_with_fake_feed()
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        service._advance_one_pass(now)
        service._publish(now)
        published = service.published_snapshot()
        assert published.open_position_count == 1
        view = published.open_positions[0]
        assert view.trading_symbol == "TESTCO"
        assert view.direction == "long"
        assert view.last_price == 101.5
        assert view.unrealized_pnl is not None
        assert published.cash_universe_size == 1

    def test_publish_without_prices_still_lists_positions(self):
        service = _service_with_fake_feed()
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        service._advance_one_pass(now)
        service._publish(now, price_open_positions=False)
        published = service.published_snapshot()
        assert published.open_position_count == 1
        assert published.open_positions[0].last_price is None


class TestReadModelOpenPositions:
    def test_open_positions_and_status_serialize(self):
        snapshot = build_dashboard_snapshot(
            TradingControlConfig(),
            PaperTradingLedger(1_000_000.0),
            PredictionTableScoreboard(),
            datetime(2026, 7, 24, 11, 0, tzinfo=IST),
            open_positions=[
                OpenPositionSummary("TESTCO", "long", 10, 100.0, 95.0, 110.0,
                                    101.5, 15.0, "confident_win"),
            ],
            live_universe_status=LiveUniverseStatus(
                is_market_open=True, cash_universe_size=9272, seeded_count=80,
                open_position_count=1, closed_trade_count=7, last_pass_at=None,
            ),
        )
        as_json = snapshot.to_json_dict()
        assert len(as_json["open_positions"]) == 1
        assert as_json["open_positions"][0]["trading_symbol"] == "TESTCO"
        assert as_json["live_universe_status"]["cash_universe_size"] == 9272
