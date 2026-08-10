"""Regenerate the cached symbol→instrument_token map from the live Kite instrument dump (through the seam).

The segment-bot option adapters read this cache to resolve an underlying to its real ``instrument_token`` so
they can pull DEEP intraday history from the stored ``price_bars`` table (waking the regime + directional
engines). The cache is Kite-independent to READ; this script is the named consumer (Rule G) that refreshes
it through the broker-session seam — run it after a fresh Kite login / when new names list.

    python scripts/refresh_instrument_token_map.py
"""

from __future__ import annotations

from datetime import UTC, datetime

from nse_algo_trader.market_data.underlying_intraday_price_source import refresh_underlying_token_map


def main() -> int:
    count = refresh_underlying_token_map(now_iso=datetime.now(UTC).isoformat())
    if count == 0:
        print("no valid Kite session — kept the existing cache (adapters fall back to the daily series)")
        return 1
    print(f"refreshed instrument_token_map.json: {count} symbol→token entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
