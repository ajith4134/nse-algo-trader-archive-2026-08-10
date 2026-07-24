"""Deterministic tests for the live universe paper loop (fake feed).

Live Rule-F coverage (29 open positions held across the universe, tables
spread confident_win/loss/uncertain, 2026-07-24) is recorded in the
flowchart note; these fixtures pin the open/hold/exit/square-off logic.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.paper_trading.live_universe_paper_loop import (
    LiveUniversePaperState,
    run_live_universe_scan_pass,
)
from nse_algo_trader.risk_management import RiskBudgetConfig
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")
TODAY = date(2026, 7, 24)  # a Friday (trading day)

STOCK = Instrument(
    instrument_token=111, trading_symbol="TESTCO",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05,
)


def _bar(ts, o, h, low, c):
    return PriceBar(STOCK.instrument_token, ts, BarInterval.MINUTE_5, o, h, low, c, 10000)


def _bars_with_long_breakout_still_open():
    """Prior-day filler to warm ADX + today's opening range then an upside
    breakout that does NOT hit stop/target (stays open)."""
    bars = []
    # 4 prior days x 8 bars of gently trending filler (warms ADX)
    base = datetime(2026, 7, 20, 9, 15, tzinfo=IST)
    price = 80.0
    for day in range(4):
        for i in range(8):
            ts = base.replace(day=20 + day) + timedelta(minutes=5 * i)
            price += 0.5
            bars.append(_bar(ts, price, price + 1, price - 1, price))
    # today: opening range 95-100 (3 bars), then breakout to 101 close
    t = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
    bars.append(_bar(t, 97, 100, 95, 98))
    bars.append(_bar(t + timedelta(minutes=5), 98, 100, 96, 99))
    bars.append(_bar(t + timedelta(minutes=10), 99, 100, 97, 99))
    bars.append(_bar(t + timedelta(minutes=15), 100, 101.5, 99.5, 101))  # breakout > 100
    # subsequent bars stay between stop and target -> position stays OPEN
    for i in range(4):
        ts = t + timedelta(minutes=20 + 5 * i)
        bars.append(_bar(ts, 101, 102, 100.5, 101.5))
    return bars


class _FakeFeed:
    def __init__(self, recent_bars, price_by_token):
        self._recent_bars = recent_bars
        self._price_by_token = price_by_token

    def latest_price_by_token(self, instruments):
        return dict(self._price_by_token)

    def recent_intraday_bars(self, instrument, as_of, lookback_calendar_days=7,
                             bar_interval=BarInterval.MINUTE_5):
        return list(self._recent_bars)


def _fresh_state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0),
        scoreboard=PredictionTableScoreboard(),
    )


RISK = RiskBudgetConfig(account_capital=1_000_000.0)


class TestOpenAndHold:
    def test_breakout_opens_a_held_position(self):
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        report = run_live_universe_scan_pass(state, [STOCK], feed, RISK, now,
                                             market_clock=NseMarketClock())
        assert report.newly_opened_count == 1
        assert state.open_position_count() == 1
        assert STOCK.instrument_token in state.open_positions

    def test_seeded_instrument_is_not_reseeded_next_pass(self):
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        run_live_universe_scan_pass(state, [STOCK], feed, RISK, now, market_clock=NseMarketClock())
        second = run_live_universe_scan_pass(state, [STOCK], feed, RISK, now, market_clock=NseMarketClock())
        assert second.newly_seeded_count == 0  # already seeded


class TestLivePriceManagement:
    def test_open_position_exits_when_live_price_hits_target(self):
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        run_live_universe_scan_pass(state, [STOCK], feed, RISK, now, market_clock=NseMarketClock())
        target = state.open_positions[STOCK.instrument_token].target_price
        # next pass: live price jumps to the target
        feed._price_by_token = {STOCK.instrument_token: target + 1}
        report = run_live_universe_scan_pass(state, [STOCK], feed, RISK,
                                             now + timedelta(minutes=5), market_clock=NseMarketClock())
        assert report.closed_this_pass_count == 1
        assert state.open_position_count() == 0
        assert len(state.closed_trades) == 1
        assert state.closed_trades[0].realized_pnl > 0


def _bars_no_breakout_inside_range():
    """Prior-day filler (warms ADX) + today's opening range with NO breakout
    (price stays inside the 95-100 range all session)."""
    bars = []
    base = datetime(2026, 7, 20, 9, 15, tzinfo=IST)
    price = 80.0
    for day in range(4):
        for i in range(8):
            price += 0.5
            bars.append(_bar(base.replace(day=20 + day) + timedelta(minutes=5 * i),
                             price, price + 1, price - 1, price))
    t = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
    for i in range(8):  # opening range + rest of session, all inside 95..100
        bars.append(_bar(t + timedelta(minutes=5 * i), 97, 100, 95, 98))
    return bars


class TestPostSeedBreakoutWatch:
    def test_seeded_no_signal_name_is_watched_then_opens_on_live_breakout(self):
        feed = _FakeFeed(_bars_no_breakout_inside_range(), {STOCK.instrument_token: 98.0})
        state = _fresh_state()
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        report = run_live_universe_scan_pass(state, [STOCK], feed, RISK, now,
                                             market_clock=NseMarketClock())
        assert report.newly_opened_count == 0
        assert STOCK.instrument_token in state.watched_opening_ranges  # now watched
        # next pass: live LTP breaks above the opening-range high (100)
        feed._price_by_token = {STOCK.instrument_token: 101.0}
        run_live_universe_scan_pass(state, [STOCK], feed, RISK,
                                    now + timedelta(minutes=5), market_clock=NseMarketClock())
        assert STOCK.instrument_token in state.open_positions  # opened on live breakout
        assert state.open_positions[STOCK.instrument_token].direction.value == "long"


class TestForcedSquareOff:
    def test_all_open_positions_flatten_via_layer8_at_1515(self):
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()
        open_now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        run_live_universe_scan_pass(state, [STOCK], feed, RISK, open_now, market_clock=NseMarketClock())
        assert state.open_position_count() == 1
        # a scan pass inside the 15:15 square-off window
        at_close = datetime(2026, 7, 24, 15, 20, tzinfo=IST)
        report = run_live_universe_scan_pass(state, [STOCK], feed, RISK, at_close,
                                             market_clock=NseMarketClock())
        assert report.squared_off_at_close
        assert state.open_position_count() == 0  # no overnight carry, ever
        assert state.ledger.is_flat()

    def test_unflattened_leg_is_surfaced_not_silently_booked(self):
        # A broker that always REJECTS -> Layer 8 cannot flatten -> the loop
        # must surface it, never book it closed (Rule: never a silent drop).
        from nse_algo_trader.broker_oms import OrderExecutionResult, OrderLifecycleState
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()

        class _AlwaysRejectBroker:
            def update_market_price(self, token, price):
                pass
            def place_order(self, intent):
                return OrderExecutionResult("", OrderLifecycleState.REJECTED, 0, None, "RMS")
        state.simulated_broker = _AlwaysRejectBroker()

        open_now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        # open a position first (with a normal fill path via a fresh state feed)
        state2 = _fresh_state()
        run_live_universe_scan_pass(state2, [STOCK], feed, RISK, open_now, market_clock=NseMarketClock())
        # move its open position into the reject-broker state
        state.open_positions = state2.open_positions
        at_close = datetime(2026, 7, 24, 15, 20, tzinfo=IST)
        run_live_universe_scan_pass(state, [STOCK], feed, RISK, at_close, market_clock=NseMarketClock())
        assert len(state.unflattened_square_off_positions) == 1  # surfaced
        assert not state.closed_trades  # NOT silently booked closed


class TestCapitalPerTradeClamp:
    def test_clamps_to_max_and_skips_below_min(self):
        state = _fresh_state()
        state.max_capital_per_trade = 100_000.0
        state.min_capital_per_trade = 20_000.0
        assert state.capital_clamped_quantity(100.0, 500) == 500       # 50k, within
        assert state.capital_clamped_quantity(100.0, 2000) == 1000     # 200k -> cap 100k
        assert state.capital_clamped_quantity(100.0, 100) == 0         # 10k < 20k -> skip

    def test_no_limits_is_a_noop(self):
        state = _fresh_state()  # limits default None
        assert state.capital_clamped_quantity(100.0, 500) == 500


class TestAntibodyVeto:
    def test_a_vetoed_mechanism_does_not_open(self):
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()
        # veto the exact mechanism this breakout would trade
        state.vetoed_mechanisms = {"post-breakout trend continuation (ADX trending)"}
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        report = run_live_universe_scan_pass(state, [STOCK], feed, RISK, now,
                                             market_clock=NseMarketClock())
        assert report.newly_opened_count == 0        # vetoed -> no position
        assert state.open_position_count() == 0
        assert state.vetoed_entry_count == 1         # veto counted

    def test_without_veto_the_same_setup_opens(self):
        feed = _FakeFeed(_bars_with_long_breakout_still_open(), {STOCK.instrument_token: 101.5})
        state = _fresh_state()  # no veto
        now = datetime(2026, 7, 24, 11, 0, tzinfo=IST)
        report = run_live_universe_scan_pass(state, [STOCK], feed, RISK, now,
                                             market_clock=NseMarketClock())
        assert report.newly_opened_count == 1        # control: it does open
