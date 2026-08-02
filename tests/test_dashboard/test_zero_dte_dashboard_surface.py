"""B34 Slice B (hermetic, Rule J): open + closed 0-DTE structures reach the dashboard.

Closes B32 item 8 — the 0-DTE engine opened real positions (44 on 2026-07-28) but they were
LOG-ONLY: nothing surfaced them into the open-position views, the segment boards, or the combined
realised P&L, so the Index/Stock Options tiles read 0 even while options traded. These pin that:
- an OPEN 0-DTE index structure renders as an `index_option` row (and a stock one as `stock_option`),
- CLOSED 0-DTE realised P&L is included in the combined headline.

The Rule-F pass on a real expiry day (next NIFTY 0-DTE = 2026-08-04) stays an open blocker (BACKLOG B34).
"""

from datetime import date, datetime
from types import SimpleNamespace

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.paper_trading.zero_dte_expiry_day_live_path import (
    ClosedZeroDtePosition,
    OpenZeroDtePosition,
    _EnteredLeg,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    OptionLegAction,
    OptionLegIntent,
)
from nse_algo_trader.strategy_engine.zero_dte_regime_router import ZeroDteStructure
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

LOT = 50


def _opt(token, underlying, strike, right, kind):
    return Instrument(
        instrument_token=token, trading_symbol=f"{underlying}{int(strike)}{right.value}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=kind, lot_size=LOT, tick_size=0.05,
        underlying_symbol=underlying, strike_price=strike, option_right=right,
        expiry_date=date(2026, 8, 4),
    )


def _short_premium_spread(underlying, kind, base_token):
    """A defined-risk short-premium spread: SELL a near leg (credit), BUY a far hedge (debit)."""
    short = _opt(base_token, underlying, 23000, OptionRight.CALL, kind)
    hedge = _opt(base_token + 1, underlying, 23200, OptionRight.CALL, kind)
    return OpenZeroDtePosition(
        position_id=f"{underlying}|0dte",
        underlying_symbol=underlying,
        structure=ZeroDteStructure.SHORT_PREMIUM_SPREAD,
        entered_legs=[
            _EnteredLeg(leg=OptionLegIntent(short, OptionLegAction.SELL, 1), entry_premium=80.0),
            _EnteredLeg(leg=OptionLegIntent(hedge, OptionLegAction.BUY, 1), entry_premium=30.0),
        ],
        lots=1, lot_size=LOT, defined_risk_per_lot=200.0 * LOT,
        opened_at=datetime(2026, 8, 4, 10, 0), strategy_tag="zero_dte",
        assigned_table="uncertain",
    )


class _Feed:
    def __init__(self, marks):
        self._marks = marks

    def latest_price_by_token(self, instruments):
        return {i.instrument_token: self._marks[i.instrument_token] for i in instruments
                if i.instrument_token in self._marks}


def _service_with(open_positions=None, closed=None, marks=None):
    state = SimpleNamespace(
        open_zero_dte_positions=open_positions or {},
        closed_zero_dte_positions=closed or [],
    )
    return SimpleNamespace(
        _state=state,
        _feed=_Feed(marks or {}),
        _INDEX_UNDERLYINGS=LivePaperTradingService._INDEX_UNDERLYINGS,
    )


def test_open_index_zero_dte_renders_as_index_option_row():
    pos = _short_premium_spread("NIFTY", InstrumentKind.INDEX_OPTION, 1000)
    # net entry credit/unit = +80 (sold) − 30 (hedge) = +50; mark it to +40 (spread decayed = profit)
    marks = {1000: 70.0, 1001: 30.0}  # net mark = 70 − 30 = 40
    svc = _service_with(open_positions={pos.position_id: pos}, marks=marks)
    rows = LivePaperTradingService._zero_dte_views(svc, price=True)
    assert len(rows) == 1
    row = rows[0]
    assert row.segment == "index_option"
    assert "NIFTY" in row.trading_symbol and "0DTE" in row.trading_symbol
    assert row.entry_price == 50.0  # net credit per unit
    assert row.last_price == 40.0   # net mark per unit
    assert row.unrealized_pnl is not None


def test_open_stock_zero_dte_renders_as_stock_option_row():
    pos = _short_premium_spread("RELIANCE", InstrumentKind.STOCK_OPTION, 2000)
    svc = _service_with(open_positions={pos.position_id: pos}, marks={2000: 75.0, 2001: 28.0})
    rows = LivePaperTradingService._zero_dte_views(svc, price=True)
    assert rows[0].segment == "stock_option"


def test_no_open_zero_dte_positions_yields_no_rows():
    assert LivePaperTradingService._zero_dte_views(_service_with(), price=True) == []


def test_closed_zero_dte_realized_pnl_is_summed_for_the_headline():
    closed = [
        ClosedZeroDtePosition(
            position=_short_premium_spread("NIFTY", InstrumentKind.INDEX_OPTION, 1),
            realized_pnl=1234.5, closed_at=datetime(2026, 8, 4, 15, 0), exit_reason="time_stop",
        ),
        ClosedZeroDtePosition(
            position=_short_premium_spread("RELIANCE", InstrumentKind.STOCK_OPTION, 3),
            realized_pnl=-200.0, closed_at=datetime(2026, 8, 4, 15, 0), exit_reason="stop",
        ),
    ]
    svc = _service_with(closed=closed)
    assert LivePaperTradingService._zero_dte_realized_pnl(svc) == 1034.5
