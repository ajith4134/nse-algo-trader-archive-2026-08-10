"""Fyers implementation of HistoricalBarSource — the deep, free MINUTE-history
source (cash + F&O + OI, since ~Jul-2017; §53 slice 4, research/78).

Deeper than ICICI Breeze's ~3 years and free — Breeze stays the 1-second source
(Fyers' finest is 5-second, no 1s). Takes an already-authenticated Fyers client
(anything exposing `history(data=dict)` the way `fyers_apiv3.fyersModel.FyersModel`
does) — **injected, never constructed here, and this module never imports
`fyers_apiv3`** (which hard-pins requests/aiohttp and would risk a dependency
collision; construction is only done at the composition root for the real-data pass).

Fyers caps a minute request at ~100 days and a daily request at ~366 days, so
multi-year pulls are chunked and de-duplicated here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument, InstrumentKind

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

# Fyers resolution strings. Fyers' finest is 5-second (NO 1s) — so SECOND_1 is
# intentionally absent and raises; Breeze is the 1-second source (research/78).
FYERS_RESOLUTION_BY_BAR_INTERVAL: dict[BarInterval, str] = {
    BarInterval.MINUTE_1: "1",
    BarInterval.MINUTE_3: "3",
    BarInterval.MINUTE_5: "5",
    BarInterval.MINUTE_10: "10",
    BarInterval.MINUTE_15: "15",
    BarInterval.MINUTE_30: "30",
    BarInterval.MINUTE_60: "60",
    BarInterval.DAY_1: "D",
}

# Fyers per-request range caps: minute ≤100 days, daily ≤366 days (research/78).
_MINUTE_REQUEST_WINDOW = timedelta(days=100)
_DAILY_REQUEST_WINDOW = timedelta(days=366)

_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)


def default_fyers_symbol(instrument: Instrument) -> str:
    """The Fyers symbol for an instrument. Cash → `NSE:{SYMBOL}-EQ`. Options need
    the Fyers symbol master (monthly vs weekly month-code formatting) and raise here
    until that resolver is injected — deliberately, so a wrong option symbol is never
    silently sent (research/78 follow-up)."""
    if instrument.kind in _OPTION_INSTRUMENT_KINDS:
        raise ValueError(
            f"{instrument.trading_symbol}: Fyers option symbol formatting needs the "
            "symbol-master resolver — inject fyers_symbol_resolver (research/78)"
        )
    return f"NSE:{instrument.trading_symbol}-EQ"


class FyersHistoricalBarSource:
    def __init__(
        self,
        authenticated_fyers_client,
        fyers_symbol_resolver: Callable[[Instrument], str] = default_fyers_symbol,
    ) -> None:
        self._fyers_client = authenticated_fyers_client
        self._fyers_symbol_resolver = fyers_symbol_resolver

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        if bar_interval not in FYERS_RESOLUTION_BY_BAR_INTERVAL:
            raise ValueError(
                f"Fyers does not serve {bar_interval.value} candles "
                f"(supported: {sorted(i.value for i in FYERS_RESOLUTION_BY_BAR_INTERVAL)}; "
                "use the Breeze source for 1-second)"
            )
        resolution = FYERS_RESOLUTION_BY_BAR_INTERVAL[bar_interval]
        symbol = self._fyers_symbol_resolver(instrument)
        include_open_interest = instrument.kind in _OPTION_INSTRUMENT_KINDS
        window = (
            _DAILY_REQUEST_WINDOW
            if bar_interval is BarInterval.DAY_1
            else _MINUTE_REQUEST_WINDOW
        )

        bars_by_timestamp: dict[datetime, PriceBar] = {}
        chunk_start = from_datetime
        while chunk_start < to_datetime:
            chunk_end = min(chunk_start + window, to_datetime)
            response = self._fyers_client.history(
                data={
                    "symbol": symbol,
                    "resolution": resolution,
                    "date_format": "0",  # epoch seconds
                    "range_from": str(int(chunk_start.timestamp())),
                    "range_to": str(int(chunk_end.timestamp())),
                    "cont_flag": "0",
                    "oi_flag": "1" if include_open_interest else "0",
                }
            )
            for raw_candle in _successful_candles(response):
                bar = _price_bar_from_fyers_candle(
                    raw_candle, instrument.instrument_token, bar_interval
                )
                bars_by_timestamp[bar.timestamp] = bar
            chunk_start = chunk_end

        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]


def _successful_candles(response) -> list[list]:
    """Candle rows from a Fyers `{"s":"ok","candles":[[epoch,o,h,l,c,v(,oi)]]}`
    envelope. Anything other than an "ok" status yields no rows (best-effort)."""
    if not isinstance(response, dict) or response.get("s") != "ok":
        return []
    return response.get("candles") or []


def _price_bar_from_fyers_candle(
    raw_candle: list, instrument_token: int, bar_interval: BarInterval
) -> PriceBar:
    return PriceBar(
        instrument_token=instrument_token,
        timestamp=datetime.fromtimestamp(raw_candle[0], _INDIA_MARKET_TIMEZONE),
        interval=bar_interval,
        open_price=float(raw_candle[1]),
        high_price=float(raw_candle[2]),
        low_price=float(raw_candle[3]),
        close_price=float(raw_candle[4]),
        volume=int(raw_candle[5]),
        open_interest=int(raw_candle[6]) if len(raw_candle) > 6 else None,
    )
