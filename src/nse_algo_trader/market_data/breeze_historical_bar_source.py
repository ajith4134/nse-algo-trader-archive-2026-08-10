"""ICICI Direct **Breeze** implementation of the HistoricalBarSource protocol —
the 1-second fidelity climb above the BASE bar-only replay (§53 slice 4, P4a;
research/66).

Takes an already-authenticated Breeze client (anything exposing
`get_historical_data_v2(interval, from_date, to_date, stock_code, exchange_code,
product_type, expiry_date, right, strike_price)` the way
`breeze_connect.BreezeConnect` does) — **injected, never constructed here**. This
is deliberate and load-bearing: `import breeze_connect` fires an unconditional
network download (the SecurityMaster zip) and pulls socketio at module import, so
importing it inside this adapter would make the module non-hermetic and
network-coupled. Construction + `generate_session(...)` happen at the composition
root / the real-data verification script; tests inject an in-memory fake.

1-second candles exist only in Breeze's **v2** endpoint, capped at ~1000 candles
per request, so multi-window pulls are **chunked** and de-duplicated here. The
adapter yields broker-neutral `PriceBar`s, identical in shape to the Kite source.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument, InstrumentKind, OptionRight

# Breeze v2 interprets from_date/to_date as IST WALL-CLOCK (the trailing 'Z' is
# cosmetic — it does NOT mean UTC; verified live 2026-07-25). So all times sent to
# Breeze are formatted in this zone, and Breeze returns IST datetimes too.
_BREEZE_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

# Breeze v2 supports only this subset of interval names (research/66). Anything
# else (3m/10m/15m/60m) has no Breeze equivalent → a clear error, not a KeyError.
BREEZE_V2_INTERVAL_NAME_BY_BAR_INTERVAL: dict[BarInterval, str] = {
    BarInterval.SECOND_1: "1second",
    BarInterval.MINUTE_1: "1minute",
    BarInterval.MINUTE_5: "5minute",
    BarInterval.MINUTE_30: "30minute",
    BarInterval.DAY_1: "1day",
}

_SECONDS_PER_BAR_INTERVAL: dict[BarInterval, int] = {
    BarInterval.SECOND_1: 1,
    BarInterval.MINUTE_1: 60,
    BarInterval.MINUTE_5: 300,
    BarInterval.MINUTE_30: 1_800,
    BarInterval.DAY_1: 86_400,
}

# Breeze v2 caps a single historical request at ~1000 candles (research/66).
_MAX_CANDLES_PER_BREEZE_REQUEST = 1000

_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)

_BREEZE_RIGHT_BY_OPTION_RIGHT: dict[OptionRight, str] = {
    OptionRight.CALL: "call",
    OptionRight.PUT: "put",
}


def default_breeze_stock_code(instrument: Instrument) -> str:
    """The Breeze `stock_code` for an instrument. Defaults to the underlying
    symbol for options and the trading symbol for cash. ICICI's own stock codes
    can differ from NSE symbols for some names — inject a custom resolver (backed
    by the SecurityMaster mapping) if the real-data pass surfaces mismatches."""
    if instrument.kind in _OPTION_INSTRUMENT_KINDS:
        return instrument.underlying_symbol  # required-non-None for options
    return instrument.trading_symbol


class BreezeHistoricalBarSource:
    """Fetches historical candles from ICICI Breeze (v2) and yields broker-neutral
    PriceBars, chunking any request beyond Breeze's ~1000-candle cap."""

    def __init__(
        self,
        authenticated_breeze_client,
        stock_code_resolver: Callable[[Instrument], str] = default_breeze_stock_code,
    ) -> None:
        self._breeze_client = authenticated_breeze_client
        self._stock_code_resolver = stock_code_resolver

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        if bar_interval not in BREEZE_V2_INTERVAL_NAME_BY_BAR_INTERVAL:
            raise ValueError(
                f"ICICI Breeze does not serve {bar_interval.value} candles "
                f"(supported: {sorted(i.value for i in BREEZE_V2_INTERVAL_NAME_BY_BAR_INTERVAL)})"
            )
        breeze_interval = BREEZE_V2_INTERVAL_NAME_BY_BAR_INTERVAL[bar_interval]
        addressing = self._breeze_addressing_for(instrument)
        window = timedelta(
            seconds=_MAX_CANDLES_PER_BREEZE_REQUEST * _SECONDS_PER_BAR_INTERVAL[bar_interval]
        )

        # Chunk [from, to] into <=1000-candle windows; de-dupe on timestamp so an
        # inclusive-boundary candle shared by two windows is only kept once.
        bars_by_timestamp: dict[datetime, PriceBar] = {}
        chunk_start = from_datetime
        while chunk_start < to_datetime:
            chunk_end = min(chunk_start + window, to_datetime)
            raw_response = self._breeze_client.get_historical_data_v2(
                interval=breeze_interval,
                from_date=_to_breeze_ist_iso(chunk_start),
                to_date=_to_breeze_ist_iso(chunk_end),
                **addressing,
            )
            for raw_candle in _successful_candles(raw_response):
                bar = _price_bar_from_breeze_candle(
                    raw_candle, instrument.instrument_token, bar_interval
                )
                bars_by_timestamp[bar.timestamp] = bar
            chunk_start = chunk_end

        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]

    def _breeze_addressing_for(self, instrument: Instrument) -> dict:
        """The Breeze v2 addressing kwargs for one instrument (cash vs option)."""
        stock_code = self._stock_code_resolver(instrument)
        if instrument.kind in _OPTION_INSTRUMENT_KINDS:
            return {
                "stock_code": stock_code,
                "exchange_code": "NFO",
                "product_type": "options",
                "expiry_date": _to_breeze_ist_iso(
                    datetime(
                        instrument.expiry_date.year,
                        instrument.expiry_date.month,
                        instrument.expiry_date.day,
                    )
                ),
                "right": _BREEZE_RIGHT_BY_OPTION_RIGHT[instrument.option_right],
                "strike_price": str(instrument.strike_price),
            }
        return {
            "stock_code": stock_code,
            "exchange_code": "NSE",
            "product_type": "cash",
        }


def _to_breeze_ist_iso(moment: datetime) -> str:
    """Breeze v2 wants the time as IST WALL-CLOCK in an ISO string with a cosmetic
    trailing 'Z' (e.g. 2026-07-24T09:15:00.000Z means 09:15 IST, NOT UTC — verified
    live). A tz-aware input is converted to IST; a naive input is taken as already
    IST wall-clock."""
    ist = moment.astimezone(_BREEZE_MARKET_TIMEZONE) if moment.tzinfo else moment
    return ist.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _successful_candles(raw_response) -> list[dict]:
    """The candle rows from a Breeze v2 envelope `{Success, Error, Status}`. An
    empty `Success` is ambiguous (bad request vs genuinely no data, research/66) —
    treated as no rows here; callers should not read it as authoritative."""
    if not isinstance(raw_response, dict):
        return []
    return raw_response.get("Success") or []


def _parse_breeze_datetime(raw_datetime: str) -> datetime:
    """Parse Breeze's candle datetime — tolerant of ISO ('2023-01-02T09:15:00')
    and the space-separated form ('2023-01-02 09:15:00')."""
    text = raw_datetime.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _optional_open_interest(raw_candle: dict) -> int | None:
    raw_open_interest = raw_candle.get("open_interest")
    if raw_open_interest in (None, ""):
        return None
    return int(float(raw_open_interest))


def _price_bar_from_breeze_candle(
    raw_candle: dict, instrument_token: int, bar_interval: BarInterval
) -> PriceBar:
    return PriceBar(
        instrument_token=instrument_token,
        timestamp=_parse_breeze_datetime(raw_candle["datetime"]),
        interval=bar_interval,
        open_price=float(raw_candle["open"]),
        high_price=float(raw_candle["high"]),
        low_price=float(raw_candle["low"]),
        close_price=float(raw_candle["close"]),
        volume=int(float(raw_candle["volume"])),
        open_interest=_optional_open_interest(raw_candle),
    )
