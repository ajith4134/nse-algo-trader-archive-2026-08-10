"""Kite implementation of `MarketDepthSource` (§53 slice 4 P4b).

Takes an already-authenticated Kite client (anything exposing `quote(tokens)` the
way `kiteconnect.KiteConnect` does — injected, never constructed here). `quote()`
returns, per instrument, a 5-level book `depth: {buy:[{price,quantity,orders}],
sell:[...]}`, which this converts to broker-neutral `MarketDepthSnapshot`s.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_depth_types import (
    MarketDepthLevel,
    MarketDepthSnapshot,
)

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


class KiteMarketDepthSource:
    def __init__(self, authenticated_kite_client, now_provider=None) -> None:
        self._kite_client = authenticated_kite_client
        self._now_provider = now_provider or (
            lambda: datetime.now(_INDIA_MARKET_TIMEZONE)
        )

    def fetch_market_depth(
        self, instrument_tokens: list[int]
    ) -> dict[int, MarketDepthSnapshot]:
        if not instrument_tokens:
            return {}
        captured_at = self._now_provider()
        raw_quote = self._kite_client.quote(instrument_tokens)
        snapshots: dict[int, MarketDepthSnapshot] = {}
        for token in instrument_tokens:
            instrument_quote = raw_quote.get(str(token)) or raw_quote.get(token)
            depth = (instrument_quote or {}).get("depth")
            if not depth:
                continue
            snapshots[token] = MarketDepthSnapshot(
                instrument_token=token,
                captured_at=captured_at,
                bids=_levels(depth.get("buy")),
                asks=_levels(depth.get("sell")),
            )
        return snapshots


def _levels(raw_levels) -> tuple[MarketDepthLevel, ...]:
    return tuple(
        MarketDepthLevel(
            price=float(level["price"]),
            quantity=int(level["quantity"]),
            orders=int(level["orders"]),
        )
        for level in (raw_levels or [])
    )
