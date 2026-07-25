"""Upstox implementation of HistoricalBarSource (task #17; research/82).

An interchangeable market-data source (PLAN §8a.12). Minute-and-coarser candles via
the v3 historical API (`get_historical_candle_data(instrument_key, unit, interval,
to_date, from_date)`) — 1-minute+ (no sub-minute), OI present as the 7th field.
Takes an already-authenticated Upstox client (exposing `get_historical_candle_data`)
— injected, never constructed here (the adapter never imports `upstox_client`).
Upstox addresses instruments by `instrument_key` (`NSE_EQ|<ISIN>`, `NSE_FO|<token>`)
from its instrument master, so a key resolver is injected.

v3 per-call range caps (research/82): minutes 1–15 ≤1 month, minutes >15 & hours
≤1 quarter, days ≤1 decade — chunked here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

# BarInterval -> (unit, interval) for the v3 historical endpoint.
UPSTOX_UNIT_INTERVAL_BY_BAR_INTERVAL: dict[BarInterval, tuple[str, str]] = {
    BarInterval.MINUTE_1: ("minutes", "1"),
    BarInterval.MINUTE_3: ("minutes", "3"),
    BarInterval.MINUTE_5: ("minutes", "5"),
    BarInterval.MINUTE_10: ("minutes", "10"),
    BarInterval.MINUTE_15: ("minutes", "15"),
    BarInterval.MINUTE_30: ("minutes", "30"),
    BarInterval.MINUTE_60: ("hours", "1"),
    BarInterval.DAY_1: ("days", "1"),
}

_WINDOW_DAYS_BY_BAR_INTERVAL: dict[BarInterval, int] = {
    BarInterval.MINUTE_1: 30, BarInterval.MINUTE_3: 30, BarInterval.MINUTE_5: 30,
    BarInterval.MINUTE_10: 30, BarInterval.MINUTE_15: 30, BarInterval.MINUTE_30: 90,
    BarInterval.MINUTE_60: 90, BarInterval.DAY_1: 3650,
}


def _requires_upstox_key_resolver(instrument: Instrument) -> str:
    raise ValueError(
        f"{instrument.trading_symbol}: Upstox addresses instruments by instrument_key "
        "(NSE_EQ|ISIN, NSE_FO|token) — inject upstox_instrument_key_resolver backed by "
        "the Upstox instrument master (research/82)"
    )


class UpstoxHistoricalBarSource:
    def __init__(
        self,
        authenticated_upstox_history_client,
        upstox_instrument_key_resolver: Callable[[Instrument], str] = _requires_upstox_key_resolver,
    ) -> None:
        self._upstox_history_client = authenticated_upstox_history_client
        self._upstox_instrument_key_resolver = upstox_instrument_key_resolver

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        if bar_interval not in UPSTOX_UNIT_INTERVAL_BY_BAR_INTERVAL:
            raise ValueError(
                f"Upstox does not serve {bar_interval.value} candles "
                f"(supported: {sorted(i.value for i in UPSTOX_UNIT_INTERVAL_BY_BAR_INTERVAL)}; "
                "use the Breeze source for 1-second)"
            )
        unit, interval = UPSTOX_UNIT_INTERVAL_BY_BAR_INTERVAL[bar_interval]
        instrument_key = self._upstox_instrument_key_resolver(instrument)
        window = timedelta(days=_WINDOW_DAYS_BY_BAR_INTERVAL[bar_interval])

        bars_by_timestamp: dict[datetime, PriceBar] = {}
        chunk_start = from_datetime
        while chunk_start < to_datetime:
            chunk_end = min(chunk_start + window, to_datetime)
            response = self._upstox_history_client.get_historical_candle_data(
                instrument_key=instrument_key,
                unit=unit,
                interval=interval,
                to_date=_to_upstox_date(chunk_end),
                from_date=_to_upstox_date(chunk_start),
            )
            for raw_candle in _candles_from_response(response):
                bar = _price_bar_from_upstox_candle(
                    raw_candle, instrument.instrument_token, bar_interval
                )
                bars_by_timestamp[bar.timestamp] = bar
            chunk_start = chunk_end

        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]


def _to_upstox_date(moment: datetime) -> str:
    ist = moment.astimezone(_INDIA_MARKET_TIMEZONE) if moment.tzinfo else moment
    return ist.strftime("%Y-%m-%d")


def _candles_from_response(response) -> list[list]:
    """Rows from Upstox v3 `{"data": {"candles": [[ts,o,h,l,c,v,oi], …]}}` — tolerant
    of both a dict and the SDK's response object (`response.data.candles`)."""
    data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
    if data is None:
        return []
    candles = data.get("candles") if isinstance(data, dict) else getattr(data, "candles", None)
    return candles if isinstance(candles, list) else []


def _price_bar_from_upstox_candle(
    raw_candle: list, instrument_token: int, bar_interval: BarInterval
) -> PriceBar:
    open_interest = (
        int(raw_candle[6])
        if len(raw_candle) > 6 and raw_candle[6] not in (None, "")
        else None
    )
    return PriceBar(
        instrument_token=instrument_token,
        timestamp=datetime.fromisoformat(str(raw_candle[0])),
        interval=bar_interval,
        open_price=float(raw_candle[1]),
        high_price=float(raw_candle[2]),
        low_price=float(raw_candle[3]),
        close_price=float(raw_candle[4]),
        volume=int(float(raw_candle[5])),
        open_interest=open_interest,
    )
