"""Rule-F real-data verification for the multi-broker failover source (task #20).

Uses the two LIVE adapters verified this session — Upstox (Analytics Token) and Angel
One (generateSession) — to prove failover on REAL data:
  A. [Upstox, Angel]         → primary Upstox serves real bars (secondary untouched).
  B. [BROKEN, Angel]         → primary raises → fails over → Angel serves real bars.
  C. [Angel, Upstox]         → reversed priority: Angel serves (order is respected).

Secrets are read from the environment only and never printed.
Run:  python scripts/verify_multi_broker_failover_realdata.py [YYYY-MM-DD] [SYMBOL]
"""

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.broker_sessions.angel_one_smartapi_session import (
    build_angel_one_authenticated_historical_client,
)
from nse_algo_trader.market_data.angel_one_historical_bar_source import (
    AngelOneHistoricalBarSource,
)
from nse_algo_trader.market_data.angel_one_symbol_token_resolver import (
    AngelOneSymbolTokenResolver,
    download_angel_one_scrip_master_records,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.market_data.multi_broker_historical_bar_source import (
    MultiBrokerHistoricalBarSource,
    NamedHistoricalBarSource,
)
from nse_algo_trader.market_data.upstox_historical_bar_source import (
    UpstoxHistoricalBarSource,
    UpstoxRestHistoricalClient,
)
from nse_algo_trader.market_data.upstox_instrument_key_resolver import (
    UpstoxInstrumentKeyResolver,
    download_upstox_nse_instrument_master_records,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


class _AlwaysBrokenSource:
    """Stands in for a broker mid-outage / rate-limited — always raises."""

    def fetch_historical_bars(self, *_args, **_kwargs):
        raise RuntimeError("simulated broker outage / rate-limit")


def _most_recent_weekday() -> date:
    day = date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _build_upstox_source() -> UpstoxHistoricalBarSource:
    token = (
        os.environ.get("UPSTOX_ANALYTICS_TOKEN", "").strip()
        or os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    )
    resolver = UpstoxInstrumentKeyResolver.from_instrument_master_records(
        download_upstox_nse_instrument_master_records()
    )
    return UpstoxHistoricalBarSource(UpstoxRestHistoricalClient(token), resolver)


def _build_angel_source() -> AngelOneHistoricalBarSource:
    resolver = AngelOneSymbolTokenResolver.from_scrip_master_records(
        download_angel_one_scrip_master_records()
    )
    client = build_angel_one_authenticated_historical_client(
        os.environ["ANGEL_ONE_API_KEY"].strip(),
        os.environ["ANGEL_ONE_CLIENT_CODE"].strip(),
        os.environ["ANGEL_ONE_PIN"].strip(),
        os.environ["ANGEL_ONE_TOTP_SECRET"].strip(),
    )
    return AngelOneHistoricalBarSource(client, resolver)


def main() -> int:
    session_date = (
        date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else _most_recent_weekday()
    )
    symbol = sys.argv[2] if len(sys.argv) > 2 else "RELIANCE"

    load_env_file_into_environ()
    print("Building the two LIVE sources (Upstox + Angel One) …")
    upstox = NamedHistoricalBarSource("upstox", _build_upstox_source())
    angel = NamedHistoricalBarSource("angel_one", _build_angel_source())
    broken = NamedHistoricalBarSource("broken_broker", _AlwaysBrokenSource())

    instrument = Instrument(
        instrument_token=0, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )
    from_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 15, tzinfo=IST)
    to_dt = from_dt + timedelta(hours=6, minutes=15)

    def run(label, ordered, expected_server):
        attempts = []
        multi = MultiBrokerHistoricalBarSource(ordered, on_source_attempt=attempts.append)
        bars = multi.fetch_historical_bars(instrument, BarInterval.MINUTE_1, from_dt, to_dt)
        trail = " -> ".join(f"{a.source_name}:{a.outcome}({a.bar_count})" for a in attempts)
        server = next((a.source_name for a in attempts if a.outcome == "served"), None)
        print(f"\n[{label}] {trail}")
        print(f"    → {len(bars)} real bars, served by {server!r}")
        assert bars, f"{label}: expected real bars"
        assert server == expected_server, f"{label}: expected {expected_server}, got {server}"
        ts = [b.timestamp for b in bars]
        assert ts == sorted(ts) and len(ts) == len(set(ts)), f"{label}: bars unordered/dup"
        assert all(b.low_price <= b.open_price <= b.high_price for b in bars), f"{label}: OHLC"
        return bars

    run("A primary-serves [upstox, angel]", [upstox, angel], "upstox")
    run("B error-failover [BROKEN, angel]", [broken, angel], "angel_one")
    run("C reversed-order [angel, upstox]", [angel, upstox], "angel_one")

    print("\n✓ Rule-F PASS: real multi-broker failover — primary serves, a broken "
          "primary fails over to a live secondary, and priority order is respected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
