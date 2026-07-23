from datetime import datetime, timedelta

import pytest

from nse_algo_trader.broker_oms import OrderSide, SimulatedBrokerClient
from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.paper_trading import (
    INDIA_MARKET_TIMEZONE,
    PaperSessionOutcome,
    PaperTradingLedger,
    group_bars_into_sessions,
    run_opening_range_breakout_paper_session,
)
from nse_algo_trader.risk_management import RiskBudgetConfig
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

INFY = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)
TEN_LAKH = RiskBudgetConfig(account_capital=1_000_000.0)
SESSION_START = datetime(2026, 7, 22, 9, 15, tzinfo=INDIA_MARKET_TIMEZONE)


def _session(ohlc) -> list[PriceBar]:
    return [
        PriceBar(
            instrument_token=408065,
            timestamp=SESSION_START + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5,
            open_price=o, high_price=h, low_price=l, close_price=c, volume=1000,
        )
        for i, (o, h, l, c) in enumerate(ohlc)
    ]


# Opening range (first 3 bars): high 102, low 98.
OPENING_RANGE = [(100, 101, 98, 100), (100, 102, 99, 101), (101, 102, 99, 100)]


class TestPaperTradingLedger:
    def test_long_round_trip_realizes_pnl(self):
        ledger = PaperTradingLedger(1_000_000.0)
        ledger.record_fill(1, OrderSide.BUY, 100, 100.0)
        assert ledger.net_quantity(1) == 100
        fill = ledger.record_fill(1, OrderSide.SELL, 100, 103.0)
        assert fill.realized_pnl_from_this_fill == pytest.approx(300.0)
        assert ledger.realized_pnl == pytest.approx(300.0)
        assert ledger.is_flat()

    def test_short_round_trip_realizes_pnl(self):
        ledger = PaperTradingLedger(1_000_000.0)
        ledger.record_fill(1, OrderSide.SELL, 50, 200.0)
        ledger.record_fill(1, OrderSide.BUY, 50, 195.0)  # covered lower -> profit
        assert ledger.realized_pnl == pytest.approx(250.0)
        assert ledger.is_flat()

    def test_average_cost_on_scaling_in(self):
        ledger = PaperTradingLedger(1_000_000.0)
        ledger.record_fill(1, OrderSide.BUY, 100, 100.0)
        ledger.record_fill(1, OrderSide.BUY, 100, 110.0)  # avg 105
        ledger.record_fill(1, OrderSide.SELL, 200, 108.0)
        assert ledger.realized_pnl == pytest.approx((108 - 105) * 200)

    def test_unrealized_and_total_pnl(self):
        ledger = PaperTradingLedger(1_000_000.0)
        ledger.record_fill(1, OrderSide.BUY, 100, 100.0)
        assert ledger.unrealized_pnl({1: 104.0}) == pytest.approx(400.0)
        assert ledger.total_pnl({1: 104.0}) == pytest.approx(400.0)


class TestOpeningRangeBreakoutPaperSession:
    def _run(self, ohlc):
        broker = SimulatedBrokerClient()
        ledger = PaperTradingLedger(1_000_000.0)
        result = run_opening_range_breakout_paper_session(
            _session(ohlc), INFY, broker, TEN_LAKH, ledger
        )
        return result, ledger

    def test_no_breakout_is_no_signal_and_flat(self):
        result, ledger = self._run(OPENING_RANGE + [(100, 101.5, 98.5, 100)] * 3)
        assert result.outcome is PaperSessionOutcome.NO_SIGNAL
        assert ledger.is_flat()

    def test_long_breakout_hits_target(self):
        # breakout close 103 (stop 98, target 103 + 2*(103-98)=113); later bar prints 113
        ohlc = OPENING_RANGE + [(101, 104, 100, 103.0), (103, 114, 103, 113.5)]
        result, ledger = self._run(ohlc)
        assert result.outcome is PaperSessionOutcome.EXITED_TARGET
        assert result.exit_price == pytest.approx(113.0)
        assert result.realized_pnl > 0
        assert ledger.is_flat()  # squared off — no overnight

    def test_long_breakout_hits_stop(self):
        ohlc = OPENING_RANGE + [(101, 104, 100, 103.0), (103, 103, 97, 98.0)]  # low 97 < stop 98
        result, ledger = self._run(ohlc)
        assert result.outcome is PaperSessionOutcome.EXITED_STOP
        assert result.exit_price == pytest.approx(98.0)
        assert result.realized_pnl < 0
        assert ledger.is_flat()

    def test_no_stop_or_target_squares_off_at_close(self):
        ohlc = OPENING_RANGE + [(101, 104, 100, 103.0), (103, 104, 102, 103.5)]
        result, ledger = self._run(ohlc)
        assert result.outcome is PaperSessionOutcome.SQUARED_OFF_AT_CLOSE
        assert result.exit_price == pytest.approx(103.5)
        assert ledger.is_flat()  # never left open overnight

    def test_group_bars_into_sessions_splits_by_date(self):
        day1 = _session(OPENING_RANGE)
        day2_start = datetime(2026, 7, 23, 9, 15, tzinfo=INDIA_MARKET_TIMEZONE)
        day2 = [
            PriceBar(408065, day2_start, BarInterval.MINUTE_5, 1, 1, 1, 1, 10)
        ]
        sessions = group_bars_into_sessions(day1 + day2)
        assert len(sessions) == 2
