"""§53 slice 4 P4b — live order-book depth recorder (hermetic, Rule J).
Real-session capture is an OPEN BLOCKER (needs an open market + live Kite session);
here the pipeline is verified end-to-end with fakes."""

from datetime import datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.market_data.kite_market_depth_source import KiteMarketDepthSource
from nse_algo_trader.market_data.market_depth_snapshot_store import (
    MarketDepthSnapshotStore,
)
from nse_algo_trader.market_data.market_depth_types import (
    MarketDepthLevel,
    MarketDepthSnapshot,
)
from nse_algo_trader.paper_trading.live_market_depth_recorder import (
    LiveMarketDepthRecorder,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _snapshot(token: int, at: datetime) -> MarketDepthSnapshot:
    return MarketDepthSnapshot(
        instrument_token=token, captured_at=at,
        bids=(MarketDepthLevel(100.0, 10, 2), MarketDepthLevel(99.95, 5, 1)),
        asks=(MarketDepthLevel(100.05, 8, 1),),
    )


def test_store_roundtrips_snapshots(tmp_path):
    store = MarketDepthSnapshotStore(tmp_path / "depth.sqlite3")
    at = datetime(2026, 7, 24, 10, 0, 5, tzinfo=IST)
    assert store.save_snapshots([_snapshot(738561, at)]) == 1
    loaded = store.load_snapshots(738561)
    assert len(loaded) == 1
    assert loaded[0].bids[0] == MarketDepthLevel(100.0, 10, 2)
    assert loaded[0].asks[0].price == 100.05
    assert loaded[0].captured_at == at
    assert store.snapshot_count() == 1


class _FakeKiteQuoteClient:
    def __init__(self):
        self.asked = None

    def quote(self, tokens):
        self.asked = tokens
        return {
            str(tokens[0]): {
                "depth": {
                    "buy": [{"price": 100.0, "quantity": 10, "orders": 2}],
                    "sell": [{"price": 100.5, "quantity": 8, "orders": 1}],
                }
            }
        }


def test_kite_depth_source_parses_quote_depth():
    client = _FakeKiteQuoteClient()
    source = KiteMarketDepthSource(
        client, now_provider=lambda: datetime(2026, 7, 24, 10, 0, tzinfo=IST)
    )
    snapshots = source.fetch_market_depth([738561])
    assert client.asked == [738561]
    snap = snapshots[738561]
    assert snap.bids[0] == MarketDepthLevel(100.0, 10, 2)
    assert snap.asks[0] == MarketDepthLevel(100.5, 8, 1)


class _FakeDepthSource:
    def fetch_market_depth(self, tokens):
        at = datetime(2026, 7, 24, 10, 0, tzinfo=IST)
        return {t: _snapshot(t, at) for t in tokens}


def test_recorder_persists_snapshots(tmp_path):
    store = MarketDepthSnapshotStore(tmp_path / "depth.sqlite3")
    recorder = LiveMarketDepthRecorder(_FakeDepthSource(), store)
    assert recorder.record_once([1, 2, 3]) == 3
    assert store.snapshot_count() == 3
    assert recorder.record_once([]) == 0  # empty focus -> no-op


class _RecordingRecorder:
    def __init__(self):
        self.calls = []

    def record_once(self, tokens):
        self.calls.append(list(tokens))
        return len(tokens)


def _cash(token: int) -> Instrument:
    return Instrument(
        instrument_token=token, trading_symbol=f"S{token}",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def test_service_records_depth_for_focus_when_enabled():
    recorder = _RecordingRecorder()
    service = LivePaperTradingService(
        object(), 1_000_000.0,
        record_live_market_depth=True, market_depth_focus_size=2,
        market_depth_recorder=recorder,
    )
    service._cash_universe = [_cash(1), _cash(2), _cash(3)]
    service._record_market_depth_best_effort()
    assert recorder.calls == [[1, 2]]  # focus capped to market_depth_focus_size


def test_service_skips_depth_recording_when_disabled():
    recorder = _RecordingRecorder()
    service = LivePaperTradingService(
        object(), 1_000_000.0, market_depth_recorder=recorder,  # flag defaults False
    )
    service._cash_universe = [_cash(1)]
    service._record_market_depth_best_effort()
    assert recorder.calls == []
