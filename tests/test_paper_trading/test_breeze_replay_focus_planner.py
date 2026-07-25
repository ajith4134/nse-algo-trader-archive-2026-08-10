"""§53 slice 4 task #7 — rate-limit-aware focus planner + service self-activation
(hermetic, Rule J). No network, no real breeze_connect."""

from datetime import datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.paper_trading.breeze_replay_focus_planner import (
    chunks_per_instrument_for,
    plan_breeze_replay_focus,
)
from nse_algo_trader.broker_sessions.breeze_session_token_store import (
    BreezeSessionTokenRecord,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _instruments(n: int) -> list[Instrument]:
    return [
        Instrument(
            instrument_token=1000 + i, trading_symbol=f"SYM{i}",
            exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
            lot_size=1, tick_size=0.05,
        )
        for i in range(n)
    ]


def test_chunks_per_instrument_for_one_second_session():
    # 22,500s session / (1000 candles x 1s) = 22.5 -> 23 chunked calls.
    assert chunks_per_instrument_for(BarInterval.SECOND_1) == 23
    assert chunks_per_instrument_for(BarInterval.MINUTE_1) == 1  # coarse -> 1 call


def test_focus_capped_to_daily_call_budget():
    focus = plan_breeze_replay_focus(_instruments(500), 5000, BarInterval.SECOND_1)
    assert len(focus) == 5000 // 23  # 217 affordable instrument-sessions
    assert focus == _instruments(500)[:217]  # order preserved (caller ranks)


def test_tiny_budget_and_empty_candidates_yield_empty_focus():
    assert plan_breeze_replay_focus(_instruments(10), 10, BarInterval.SECOND_1) == []
    assert plan_breeze_replay_focus([], 5000, BarInterval.SECOND_1) == []


class _FakeTokenStore:
    def __init__(self, record):
        self._record = record

    def load_if_still_valid(self, now=None):
        return self._record


class _FakeSource:
    def fetch_historical_bars(self, *a, **k):
        return []


def test_service_self_activates_when_a_valid_token_is_stored():
    built_with = {}

    def fake_source_builder(session_token):
        built_with["token"] = session_token
        return _FakeSource()

    record = BreezeSessionTokenRecord(
        session_token="tok-999", generated_at=datetime(2026, 7, 24, 10, 0, tzinfo=IST)
    )
    service = LivePaperTradingService(
        object(), 1_000_000.0,
        breeze_session_token_store=_FakeTokenStore(record),
        breeze_historical_source_builder=fake_source_builder,
    )
    service._cash_universe = _instruments(3)
    service._maybe_activate_autonomous_breeze_replay()

    assert built_with["token"] == "tok-999"
    config = service._high_fidelity_replay
    assert config is not None
    assert config.bar_interval is BarInterval.SECOND_1
    assert config.focus_instruments == _instruments(3)  # all 3 fit the budget


def test_service_stays_on_store_path_without_a_valid_token():
    def fail_builder(session_token):  # must never be called
        raise AssertionError("should not build a source without a token")

    service = LivePaperTradingService(
        object(), 1_000_000.0,
        breeze_session_token_store=_FakeTokenStore(None),  # no valid token
        breeze_historical_source_builder=fail_builder,
    )
    service._cash_universe = _instruments(3)
    service._maybe_activate_autonomous_breeze_replay()
    assert service._high_fidelity_replay is None  # falls back to store-5m replay
