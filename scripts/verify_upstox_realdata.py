"""Rule-F real-data verification for the Upstox v3 historical adapter (task #17/#22).

Uses the long-lived Analytics Token (UPSTOX_ANALYTICS_TOKEN in .env, gitignored) —
no daily login. Downloads the REAL Upstox NSE instrument master, resolves the
instrument_key, fetches REAL minute bars through the full adapter path, and asserts
they are non-empty, time-ordered, and OHLC-sane. Secrets are read from the
environment only and never printed.

Run:  python scripts/verify_upstox_realdata.py [YYYY-MM-DD] [SYMBOL]
      (date defaults to the most recent weekday; SYMBOL defaults to RELIANCE.)
"""

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
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


def _most_recent_weekday() -> date:
    day = date.today()
    while day.weekday() >= 5:  # Sat/Sun -> step back to Friday
        day -= timedelta(days=1)
    return day


def main() -> int:
    session_date = (
        date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else _most_recent_weekday()
    )
    symbol = sys.argv[2] if len(sys.argv) > 2 else "RELIANCE"

    load_env_file_into_environ()
    access_token = (
        os.environ.get("UPSTOX_ANALYTICS_TOKEN", "").strip()
        or os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    )
    if not access_token:
        print("UPSTOX_ANALYTICS_TOKEN (or UPSTOX_ACCESS_TOKEN) not set in .env.")
        return 2

    print("Downloading REAL Upstox NSE instrument master …")
    records = download_upstox_nse_instrument_master_records()
    resolver = UpstoxInstrumentKeyResolver.from_instrument_master_records(records)
    print(
        f"→ resolver: {resolver.cash_symbol_count()} cash symbols, "
        f"{resolver.option_contract_count()} option contracts"
    )

    instrument = Instrument(
        instrument_token=0, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )
    print(f"→ {symbol} instrument_key: {resolver.instrument_key_for(instrument)}")

    client = UpstoxRestHistoricalClient(access_token)
    source = UpstoxHistoricalBarSource(client, resolver)
    from_dt = datetime(session_date.year, session_date.month, session_date.day, tzinfo=IST)
    to_dt = from_dt + timedelta(days=1)

    print(f"Fetching REAL Upstox 1-minute bars: {symbol} {session_date} …")
    bars = source.fetch_historical_bars(instrument, BarInterval.MINUTE_1, from_dt, to_dt)

    print(f"→ {len(bars)} one-minute bars returned")
    if not bars:
        print("EMPTY — check the date is a trading day and the token is valid.")
        return 1
    for bar in bars[:3] + bars[-3:]:
        print(f"  {bar.timestamp}  O{bar.open_price} H{bar.high_price} "
              f"L{bar.low_price} C{bar.close_price} V{bar.volume}")

    timestamps = [b.timestamp for b in bars]
    assert timestamps == sorted(timestamps), "bars not time-ordered"
    assert len(timestamps) == len(set(timestamps)), "duplicate timestamps not de-duped"
    assert all(b.low_price <= b.open_price <= b.high_price for b in bars), "OHLC insane"
    assert all(b.low_price <= b.close_price <= b.high_price for b in bars), "OHLC insane"
    assert all(b.interval is BarInterval.MINUTE_1 for b in bars)
    print("✓ Rule-F PASS: real Upstox minute bars are non-empty, ordered, de-duped, OHLC-sane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
