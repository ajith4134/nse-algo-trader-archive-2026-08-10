"""task #20 — autonomous multi-broker MINUTE replay activation (hermetic, Rule J).
Injects a fake fleet builder (DI seam) so no broker/network is touched; asserts the
service self-selects a MINUTE_1 HighFidelityReplayConfig on the fleet, and degrades to
the store path when no fleet is available. Real fleet build is the Rule-F pass
(scripts/verify_multi_broker_replay_wiring_realdata.py)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _cash(symbol) -> Instrument:
    return Instrument(
        instrument_token=hash(symbol) % 10_000, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


class _FakeFleet:
    """Stands in for a MultiBrokerHistoricalBarSource — returns one bar per call."""

    def fetch_historical_bars(self, instrument, bar_interval, from_datetime, to_datetime):
        return [PriceBar(
            instrument_token=instrument.instrument_token,
            timestamp=from_datetime, interval=bar_interval,
            open_price=100.0, high_price=101.0, low_price=99.0, close_price=100.5,
            volume=10, open_interest=None,
        )]


def _service_with_fleet_builder(builder, focus_size=200) -> LivePaperTradingService:
    service = LivePaperTradingService(
        object(), 1_000_000.0,
        multi_broker_replay_source_builder=builder,
        multi_broker_replay_focus_size=focus_size,
    )
    # Minimal state the focus-candidate picker needs (no live universe fetch).
    service._cash_universe = [_cash("RELIANCE"), _cash("INFY")]
    service._tradable_universe = None  # -> candidates = cash list (graceful degrade)
    return service


def test_activation_sets_minute_config_on_the_fleet():
    fleet = _FakeFleet()
    service = _service_with_fleet_builder(lambda: fleet)

    service._maybe_activate_autonomous_multi_broker_replay()

    config = service._high_fidelity_replay
    assert config is not None
    assert config.bar_source is fleet
    assert config.bar_interval is BarInterval.MINUTE_1
    # both cash names are in the focus (their relative order is the liquidity
    # ranker's concern, tested separately and store-dependent — assert membership).
    assert {i.trading_symbol for i in config.focus_instruments} == {"RELIANCE", "INFY"}
    # session date is a weekday on-or-before yesterday
    yesterday = datetime.now(IST).date() - timedelta(days=1)
    assert config.session_date <= yesterday and config.session_date.weekday() < 5


def test_no_fleet_available_stays_on_store_path():
    service = _service_with_fleet_builder(lambda: None)
    service._maybe_activate_autonomous_multi_broker_replay()
    assert service._high_fidelity_replay is None  # -> store-5m path


def test_focus_size_truncates_candidates():
    service = _service_with_fleet_builder(lambda: _FakeFleet(), focus_size=1)
    service._maybe_activate_autonomous_multi_broker_replay()
    assert len(service._high_fidelity_replay.focus_instruments) == 1  # cash dropped first


def test_builder_exception_never_breaks_startup():
    def _boom():
        raise RuntimeError("broker down")

    service = _service_with_fleet_builder(_boom)
    service._maybe_activate_autonomous_multi_broker_replay()
    assert service._high_fidelity_replay is None  # swallowed -> store path
