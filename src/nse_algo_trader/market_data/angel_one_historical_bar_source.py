"""Angel One SmartAPI implementation of HistoricalBarSource (task #18; research/81).

An interchangeable market-data source (PLAN §8a.12). Minute-and-coarser candles
(`getCandleData`, ONE_MINUTE…ONE_DAY — no sub-minute, and NO historical OI). Takes
an already-authenticated SmartConnect client (exposing `getCandleData(param)`) —
injected, never constructed here (the adapter never imports SmartApi). Angel
addresses instruments by a numeric `symboltoken` (from its OpenAPIScripMaster, not
our Kite token), so a token resolver is injected.

Per-interval range caps (research/81): ONE_MINUTE ≤30d, THREE_MINUTE ≤60d,
FIVE/TEN ≤100d, FIFTEEN/THIRTY ≤200d, ONE_HOUR ≤400d, ONE_DAY ≤2000d — chunked here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument, InstrumentKind

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

ANGEL_INTERVAL_BY_BAR_INTERVAL: dict[BarInterval, str] = {
    BarInterval.MINUTE_1: "ONE_MINUTE",
    BarInterval.MINUTE_3: "THREE_MINUTE",
    BarInterval.MINUTE_5: "FIVE_MINUTE",
    BarInterval.MINUTE_10: "TEN_MINUTE",
    BarInterval.MINUTE_15: "FIFTEEN_MINUTE",
    BarInterval.MINUTE_30: "THIRTY_MINUTE",
    BarInterval.MINUTE_60: "ONE_HOUR",
    BarInterval.DAY_1: "ONE_DAY",
}

_WINDOW_DAYS_BY_BAR_INTERVAL: dict[BarInterval, int] = {
    BarInterval.MINUTE_1: 30, BarInterval.MINUTE_3: 60, BarInterval.MINUTE_5: 100,
    BarInterval.MINUTE_10: 100, BarInterval.MINUTE_15: 200, BarInterval.MINUTE_30: 200,
    BarInterval.MINUTE_60: 400, BarInterval.DAY_1: 2000,
}

_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)


def _requires_angel_token_resolver(instrument: Instrument) -> str:
    raise ValueError(
        f"{instrument.trading_symbol}: Angel addresses instruments by symboltoken — "
        "inject angel_symbol_token_resolver backed by OpenAPIScripMaster (research/81)"
    )


class AngelOneHistoricalBarSource:
    def __init__(
        self,
        authenticated_smartapi_client,
        angel_symbol_token_resolver: Callable[[Instrument], str] = _requires_angel_token_resolver,
    ) -> None:
        self._smartapi_client = authenticated_smartapi_client
        self._angel_symbol_token_resolver = angel_symbol_token_resolver

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        if bar_interval not in ANGEL_INTERVAL_BY_BAR_INTERVAL:
            raise ValueError(
                f"Angel One does not serve {bar_interval.value} candles "
                f"(supported: {sorted(i.value for i in ANGEL_INTERVAL_BY_BAR_INTERVAL)}; "
                "use the Breeze source for 1-second)"
            )
        interval = ANGEL_INTERVAL_BY_BAR_INTERVAL[bar_interval]
        symbol_token = self._angel_symbol_token_resolver(instrument)
        exchange = "NFO" if instrument.kind in _OPTION_INSTRUMENT_KINDS else "NSE"
        window = timedelta(days=_WINDOW_DAYS_BY_BAR_INTERVAL[bar_interval])

        bars_by_timestamp: dict[datetime, PriceBar] = {}
        chunk_start = from_datetime
        while chunk_start < to_datetime:
            chunk_end = min(chunk_start + window, to_datetime)
            response = self._smartapi_client.getCandleData(
                {
                    "exchange": exchange,
                    "symboltoken": symbol_token,
                    "interval": interval,
                    "fromdate": _to_angel_ist(chunk_start),
                    "todate": _to_angel_ist(chunk_end),
                }
            )
            for raw_candle in _candles_from_response(response):
                bar = _price_bar_from_angel_candle(
                    raw_candle, instrument.instrument_token, bar_interval
                )
                bars_by_timestamp[bar.timestamp] = bar
            chunk_start = chunk_end

        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]


def _to_angel_ist(moment: datetime) -> str:
    """Angel wants `yyyy-MM-dd HH:mm` IST (no seconds)."""
    ist = moment.astimezone(_INDIA_MARKET_TIMEZONE) if moment.tzinfo else moment
    return ist.strftime("%Y-%m-%d %H:%M")


def _candles_from_response(response) -> list[list]:
    """Rows from Angel's `{"status":true,"data":[[ts,o,h,l,c,v], …]}` envelope."""
    if not isinstance(response, dict):
        return []
    data = response.get("data")
    return data if isinstance(data, list) else []


def _price_bar_from_angel_candle(
    raw_candle: list, instrument_token: int, bar_interval: BarInterval
) -> PriceBar:
    return PriceBar(
        instrument_token=instrument_token,
        timestamp=datetime.fromisoformat(str(raw_candle[0])),
        interval=bar_interval,
        open_price=float(raw_candle[1]),
        high_price=float(raw_candle[2]),
        low_price=float(raw_candle[3]),
        close_price=float(raw_candle[4]),
        volume=int(float(raw_candle[5])),
        open_interest=None,  # Angel's historical candles carry no OI (research/81)
    )
