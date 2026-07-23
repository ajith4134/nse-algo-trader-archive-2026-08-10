"""Shared instrument/signal builders for the broker OMS tests."""

from datetime import date, datetime

from nse_algo_trader.strategy_engine import OpeningRangeBreakoutSignal, SignalDirection
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

CASH_INSTRUMENT = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)


def make_put_instrument(strike: float, lot_size: int = 65) -> Instrument:
    return Instrument(
        instrument_token=int(strike * 10),
        trading_symbol=f"NIFTY26JUL{strike:.0f}PE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=lot_size, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=strike, option_right=OptionRight.PUT,
        expiry_date=date(2026, 7, 28),
    )


def make_orb_signal(entry: float, stop: float) -> OpeningRangeBreakoutSignal:
    return OpeningRangeBreakoutSignal(
        instrument=CASH_INSTRUMENT, direction=SignalDirection.LONG,
        triggered_at=datetime(2026, 7, 22, 9, 30), breakout_close_price=entry,
        opening_range_high=entry - 1, opening_range_low=stop,
        stop_loss_price=stop, target_price=entry + 2 * (entry - stop),
    )
