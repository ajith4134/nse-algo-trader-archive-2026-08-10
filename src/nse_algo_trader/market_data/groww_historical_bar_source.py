"""Groww implementation of HistoricalBarSource (task #19; research/80).

An interchangeable market-data source (PLAN §8a.12). Minute-and-coarser history
(back to 2020) — Groww has no sub-minute, so `SECOND_1` raises (Breeze is the 1s
source). Takes an already-authenticated client exposing `get_historical_candles(...)`
the way `growwapi.GrowwAPI` does — **injected, never constructed here, and this
module never imports `growwapi`** (heavy deps + its constructor does an unguarded
network call, so it is non-hermetic). Groww auth is a plain Bearer token, so
`GrowwRestHistoricalClient` below is a thin REST client that avoids the SDK entirely.

Groww caps a request at 30 days (1–5 min), 90 days (10–30 min), or 180 days (1h+),
so multi-window pulls are chunked and de-duplicated here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument, InstrumentKind

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

GROWW_CANDLE_INTERVAL_BY_BAR_INTERVAL: dict[BarInterval, str] = {
    BarInterval.MINUTE_1: "1minute",
    BarInterval.MINUTE_3: "3minute",
    BarInterval.MINUTE_5: "5minute",
    BarInterval.MINUTE_10: "10minute",
    BarInterval.MINUTE_15: "15minute",
    BarInterval.MINUTE_30: "30minute",
    BarInterval.MINUTE_60: "1hour",
    BarInterval.DAY_1: "1day",
}

# Groww per-request range caps (research/80).
_WINDOW_DAYS_BY_BAR_INTERVAL: dict[BarInterval, int] = {
    BarInterval.MINUTE_1: 30, BarInterval.MINUTE_3: 30, BarInterval.MINUTE_5: 30,
    BarInterval.MINUTE_10: 90, BarInterval.MINUTE_15: 90, BarInterval.MINUTE_30: 90,
    BarInterval.MINUTE_60: 180, BarInterval.DAY_1: 180,
}

_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)


def default_groww_symbol(instrument: Instrument) -> str:
    """Groww's `groww_symbol` for an instrument. Cash → `NSE-{SYMBOL}`. Options need
    Groww's instrument CSV (its own expiry/strike format) and raise here until that
    resolver is injected (research/80 follow-up)."""
    if instrument.kind in _OPTION_INSTRUMENT_KINDS:
        raise ValueError(
            f"{instrument.trading_symbol}: Groww option symbol needs the instrument-"
            "CSV resolver — inject groww_symbol_resolver (research/80)"
        )
    return f"NSE-{instrument.trading_symbol}"


class GrowwHistoricalBarSource:
    def __init__(
        self,
        authenticated_groww_client,
        groww_symbol_resolver: Callable[[Instrument], str] = default_groww_symbol,
    ) -> None:
        self._groww_client = authenticated_groww_client
        self._groww_symbol_resolver = groww_symbol_resolver

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        if bar_interval not in GROWW_CANDLE_INTERVAL_BY_BAR_INTERVAL:
            raise ValueError(
                f"Groww does not serve {bar_interval.value} candles "
                f"(supported: {sorted(i.value for i in GROWW_CANDLE_INTERVAL_BY_BAR_INTERVAL)}; "
                "use the Breeze source for 1-second)"
            )
        candle_interval = GROWW_CANDLE_INTERVAL_BY_BAR_INTERVAL[bar_interval]
        groww_symbol = self._groww_symbol_resolver(instrument)
        is_option = instrument.kind in _OPTION_INSTRUMENT_KINDS
        segment = "FNO" if is_option else "CASH"
        window = timedelta(days=_WINDOW_DAYS_BY_BAR_INTERVAL[bar_interval])

        bars_by_timestamp: dict[datetime, PriceBar] = {}
        chunk_start = from_datetime
        while chunk_start < to_datetime:
            chunk_end = min(chunk_start + window, to_datetime)
            response = self._groww_client.get_historical_candles(
                exchange="NSE",
                segment=segment,
                groww_symbol=groww_symbol,
                start_time=_to_groww_ist(chunk_start),
                end_time=_to_groww_ist(chunk_end),
                candle_interval=candle_interval,
            )
            for raw_candle in _candles_from_response(response):
                bar = _price_bar_from_groww_candle(
                    raw_candle, instrument.instrument_token, bar_interval
                )
                bars_by_timestamp[bar.timestamp] = bar
            chunk_start = chunk_end

        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]


def _to_groww_ist(moment: datetime) -> str:
    """Groww wants `yyyy-MM-dd HH:mm:ss` IST wall-clock."""
    ist = moment.astimezone(_INDIA_MARKET_TIMEZONE) if moment.tzinfo else moment
    return ist.strftime("%Y-%m-%d %H:%M:%S")


def _candles_from_response(response) -> list[list]:
    """The candle rows from Groww's response — tolerant of a bare
    `{"candles": [...]}` or a `{"payload": {"candles": [...]}}` wrapper."""
    if not isinstance(response, dict):
        return []
    if isinstance(response.get("candles"), list):
        return response["candles"]
    payload = response.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("candles"), list):
        return payload["candles"]
    return []


def _parse_groww_timestamp(raw_timestamp) -> datetime:
    if isinstance(raw_timestamp, (int, float)):
        return datetime.fromtimestamp(raw_timestamp, _INDIA_MARKET_TIMEZONE)
    text = str(raw_timestamp).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_INDIA_MARKET_TIMEZONE)
    return parsed


def _price_bar_from_groww_candle(
    raw_candle: list, instrument_token: int, bar_interval: BarInterval
) -> PriceBar:
    open_interest = (
        int(raw_candle[6])
        if len(raw_candle) > 6 and raw_candle[6] not in (None, "")
        else None
    )
    return PriceBar(
        instrument_token=instrument_token,
        timestamp=_parse_groww_timestamp(raw_candle[0]),
        interval=bar_interval,
        open_price=float(raw_candle[1]),
        high_price=float(raw_candle[2]),
        low_price=float(raw_candle[3]),
        close_price=float(raw_candle[4]),
        volume=int(float(raw_candle[5])),
        open_interest=open_interest,
    )


class GrowwRestHistoricalClient:
    """Thin Bearer-token REST client for Groww's historical-candles endpoint — avoids
    the heavy `growwapi` SDK (which also does non-hermetic construction). Network only
    when `get_historical_candles` is called; built at the composition root."""

    _HISTORICAL_CANDLES_URL = "https://api.groww.in/v1/historical/candles"

    def __init__(self, access_token: str, timeout_seconds: int = 30) -> None:
        self._access_token = access_token
        self._timeout_seconds = timeout_seconds

    def get_historical_candles(
        self, exchange, segment, groww_symbol, start_time, end_time, candle_interval,
        timeout=None,
    ):
        import requests

        response = requests.get(
            self._HISTORICAL_CANDLES_URL,
            params={
                "exchange": exchange, "segment": segment, "groww_symbol": groww_symbol,
                "start_time": start_time, "end_time": end_time,
                "candle_interval": candle_interval,
            },
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json", "x-api-version": "1.0",
            },
            timeout=timeout or self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
