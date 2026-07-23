"""Kite Connect implementation of the HistoricalBarSource protocol.

Takes an already-authenticated Kite client (anything exposing
`historical_data(instrument_token, from_date, to_date, interval, oi=...)`
the way `kiteconnect.KiteConnect` does — injected, never constructed
here, so tests use a fake and live wiring stays in Layer 6).
"""

from datetime import datetime

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument, InstrumentKind

KITE_INTERVAL_NAME_BY_BAR_INTERVAL: dict[BarInterval, str] = {
    BarInterval.MINUTE_1: "minute",
    BarInterval.MINUTE_3: "3minute",
    BarInterval.MINUTE_5: "5minute",
    BarInterval.MINUTE_10: "10minute",
    BarInterval.MINUTE_15: "15minute",
    BarInterval.MINUTE_30: "30minute",
    BarInterval.MINUTE_60: "60minute",
    BarInterval.DAY_1: "day",
}

_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)


class KiteHistoricalBarSource:
    """Fetches historical candles from Kite and yields broker-neutral PriceBars.

    For option instruments the request always asks Kite for the OI series
    too (`oi=True`) — per `docs/research/13`, candle-level OI exists only
    when explicitly requested, and cash equities have none at all.
    """

    def __init__(self, authenticated_kite_client) -> None:
        self._kite_client = authenticated_kite_client

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        include_open_interest = instrument.kind in _OPTION_INSTRUMENT_KINDS
        raw_kite_candles = self._kite_client.historical_data(
            instrument.instrument_token,
            from_datetime,
            to_datetime,
            KITE_INTERVAL_NAME_BY_BAR_INTERVAL[bar_interval],
            oi=include_open_interest,
        )
        return [
            _price_bar_from_kite_candle(raw_candle, instrument.instrument_token, bar_interval)
            for raw_candle in raw_kite_candles
        ]


def _price_bar_from_kite_candle(
    raw_kite_candle: dict, instrument_token: int, bar_interval: BarInterval
) -> PriceBar:
    return PriceBar(
        instrument_token=instrument_token,
        timestamp=raw_kite_candle["date"],
        interval=bar_interval,
        open_price=float(raw_kite_candle["open"]),
        high_price=float(raw_kite_candle["high"]),
        low_price=float(raw_kite_candle["low"]),
        close_price=float(raw_kite_candle["close"]),
        volume=int(raw_kite_candle["volume"]),
        open_interest=(
            int(raw_kite_candle["oi"]) if "oi" in raw_kite_candle else None
        ),
    )
