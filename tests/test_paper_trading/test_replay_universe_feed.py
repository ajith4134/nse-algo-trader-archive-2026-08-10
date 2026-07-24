"""The market-CLOSED replay half of the 24/7 router (PLAN §1.4, research/41).

Proves the loop runs unchanged on the ReplayUniverseFeed: stepping the replay
clock through a stored session opens an ORB position and squares it off at the
replayed 15:15 — paper never idles when the market is shut.
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
from nse_algo_trader.paper_trading.replay_universe_feed import ReplayUniverseFeed
from nse_algo_trader.risk_management import RiskBudgetConfig
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")
STOCK = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05,
)
RISK = RiskBudgetConfig(account_capital=1_000_000.0)


def _bar(ts, o, h, low, c):
    return PriceBar(STOCK.instrument_token, ts, BarInterval.MINUTE_5, o, h, low, c, 10000)


def _one_stored_session():
    """Prior-day filler (warms ADX) + a session with a clean upside breakout
    that then runs to target well before 15:15."""
    bars = []
    base = datetime(2026, 7, 20, 9, 15, tzinfo=IST)
    price = 80.0
    for day in range(4):
        for i in range(8):
            price += 0.5
            bars.append(_bar(base.replace(day=20 + day) + timedelta(minutes=5 * i),
                             price, price + 1, price - 1, price))
    t = datetime(2026, 7, 24, 9, 15, tzinfo=IST)  # a Friday
    bars.append(_bar(t, 97, 100, 95, 98))
    bars.append(_bar(t + timedelta(minutes=5), 98, 100, 96, 99))
    bars.append(_bar(t + timedelta(minutes=10), 99, 100, 97, 99))
    bars.append(_bar(t + timedelta(minutes=15), 100, 101.5, 99.5, 101))  # breakout
    # bars through the day to 15:25
    for m in range(20, 6 * 60 + 10, 5):
        bars.append(_bar(t + timedelta(minutes=m), 101, 101.5, 100.5, 101))
    return bars


class TestReplayFeed:
    def test_recent_bars_respect_the_replay_clock(self):
        feed = ReplayUniverseFeed({STOCK.instrument_token: _one_stored_session()})
        as_of = datetime(2026, 7, 24, 10, 0, tzinfo=IST)
        bars = feed.recent_intraday_bars(STOCK, as_of)
        assert bars and all(b.timestamp <= as_of for b in bars)

    def test_latest_price_is_the_bar_at_or_before_the_clock(self):
        feed = ReplayUniverseFeed({STOCK.instrument_token: _one_stored_session()})
        feed.set_replay_as_of(datetime(2026, 7, 24, 9, 30, tzinfo=IST))
        prices = feed.latest_price_by_token([STOCK])
        assert prices.get(STOCK.instrument_token) is not None


class TestLoopRunsOnReplay:
    def test_replaying_a_session_opens_then_squares_off(self):
        feed = ReplayUniverseFeed({STOCK.instrument_token: _one_stored_session()})
        state = LiveUniversePaperState(
            ledger=PaperTradingLedger(1_000_000.0),
            scoreboard=PredictionTableScoreboard(),
        )
        clock = NseMarketClock()
        opened_any = False
        # Step the replay clock through the stored session, exactly as the
        # service's _advance_replay_pass would.
        for replay_now in feed.stored_session_timestamps():
            if replay_now.date() != date(2026, 7, 24):
                continue  # only replay the target session
            feed.set_replay_as_of(replay_now)
            run_live_universe_scan_pass(
                state, [STOCK], feed, RISK, replay_now,
                max_new_cash_seeds_per_pass=5, market_clock=clock,
            )
            if state.open_position_count() > 0:
                opened_any = True
        assert opened_any  # a position was opened during the replayed session
        # After replaying past 15:15, the position is squared off -> flat.
        assert state.open_position_count() == 0
        assert state.ledger.is_flat()
