"""Rule-F real-data verification for the Angel One SmartAPI historical adapter
(task #18/#22). Fully automatic — no manual browser step: it logs in via
`generateSession` (client code + PIN + TOTP from .env, gitignored), resolves the
symboltoken from the REAL OpenAPIScripMaster, fetches REAL bars through the full
adapter path, and asserts they are non-empty, time-ordered, and OHLC-sane. Secrets
are read from the environment only and never printed.

Run:  python scripts/verify_angel_one_realdata.py [YYYY-MM-DD] [SYMBOL]
      (date defaults to the most recent weekday; SYMBOL defaults to RELIANCE.)
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
    api_key = os.environ.get("ANGEL_ONE_API_KEY", "").strip()
    client_code = os.environ.get("ANGEL_ONE_CLIENT_CODE", "").strip()
    pin = os.environ.get("ANGEL_ONE_PIN", "").strip()
    totp_secret = os.environ.get("ANGEL_ONE_TOTP_SECRET", "").strip()
    if not all((api_key, client_code, pin, totp_secret)):
        print("Missing ANGEL_ONE_{API_KEY,CLIENT_CODE,PIN,TOTP_SECRET} in .env.")
        return 2

    print("Downloading REAL Angel One OpenAPIScripMaster …")
    records = download_angel_one_scrip_master_records()
    resolver = AngelOneSymbolTokenResolver.from_scrip_master_records(records)
    print(
        f"→ resolver: {resolver.cash_symbol_count()} cash symbols, "
        f"{resolver.option_contract_count()} option contracts"
    )

    instrument = Instrument(
        instrument_token=0, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )
    print(f"→ {symbol} symboltoken: {resolver.symbol_token_for(instrument)}")

    print("Logging in via generateSession (client code + PIN + TOTP) …")
    client = build_angel_one_authenticated_historical_client(
        api_key, client_code, pin, totp_secret
    )
    source = AngelOneHistoricalBarSource(client, resolver)
    from_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 15, tzinfo=IST)
    to_dt = from_dt + timedelta(hours=6, minutes=15)  # 09:15–15:30

    print(f"Fetching REAL Angel One 1-minute bars: {symbol} {session_date} …")
    bars = source.fetch_historical_bars(instrument, BarInterval.MINUTE_1, from_dt, to_dt)

    print(f"→ {len(bars)} one-minute bars returned")
    if not bars:
        print("EMPTY — check the date is a trading day and the session is valid.")
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
    assert all(b.open_interest is None for b in bars), "Angel historical carries no OI"
    print("✓ Rule-F PASS: real Angel One minute bars are non-empty, ordered, de-duped, OHLC-sane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
