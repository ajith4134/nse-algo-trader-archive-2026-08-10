"""Kite Connect implementation of the LiveTickStreamSource protocol.

Wraps an injected `kiteconnect.KiteTicker`-shaped object (anything with
`on_ticks` / `subscribe` / `connect` / `close`). The parsing of Kite's
raw tick dicts into broker-neutral `MarketTick`s lives in a standalone
function so it is testable without any WebSocket at all; actually
constructing an authenticated KiteTicker belongs to Layer 6.
"""

from collections.abc import Callable

from nse_algo_trader.market_data.market_data_types import MarketTick


def parse_kite_ticker_payload(raw_kite_tick: dict) -> MarketTick:
    """One raw Kite ticker dict in, one broker-neutral MarketTick out.

    Kite's "ltp" mode sends only token + last price; "quote"/"full" modes
    add volume/OI/timestamps. Absent fields become None, matching the
    MarketTick contract.
    """
    return MarketTick(
        instrument_token=raw_kite_tick["instrument_token"],
        last_price=float(raw_kite_tick["last_price"]),
        exchange_timestamp=raw_kite_tick.get("exchange_timestamp"),
        last_traded_quantity=raw_kite_tick.get("last_traded_quantity"),
        cumulative_day_volume=raw_kite_tick.get("volume_traded"),
        average_traded_price=raw_kite_tick.get("average_traded_price"),
        open_interest=raw_kite_tick.get("oi"),
    )


class KiteLiveTickStreamSource:
    """Adapts a KiteTicker-shaped WebSocket client to LiveTickStreamSource."""

    def __init__(self, kite_ticker_client) -> None:
        self._kite_ticker_client = kite_ticker_client
        self._tick_callbacks: list[Callable[[MarketTick], None]] = []
        self._pending_subscription_tokens: list[int] = []
        kite_ticker_client.on_ticks = self._dispatch_raw_kite_ticks
        kite_ticker_client.on_connect = self._subscribe_pending_tokens_on_connect

    def register_tick_callback(
        self, on_market_tick: Callable[[MarketTick], None]
    ) -> None:
        self._tick_callbacks.append(on_market_tick)

    def subscribe_instrument_tokens(self, instrument_tokens: list[int]) -> None:
        self._pending_subscription_tokens.extend(instrument_tokens)
        if getattr(self._kite_ticker_client, "is_connected", lambda: False)():
            self._kite_ticker_client.subscribe(instrument_tokens)

    def start_streaming(self) -> None:
        self._kite_ticker_client.connect(threaded=True)

    def stop_streaming(self) -> None:
        self._kite_ticker_client.close()

    def _dispatch_raw_kite_ticks(self, _websocket, raw_kite_ticks: list[dict]) -> None:
        for raw_kite_tick in raw_kite_ticks:
            market_tick = parse_kite_ticker_payload(raw_kite_tick)
            for tick_callback in self._tick_callbacks:
                tick_callback(market_tick)

    def _subscribe_pending_tokens_on_connect(self, _websocket, _response) -> None:
        if self._pending_subscription_tokens:
            self._kite_ticker_client.subscribe(self._pending_subscription_tokens)
