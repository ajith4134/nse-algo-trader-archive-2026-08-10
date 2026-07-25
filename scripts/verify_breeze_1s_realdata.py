"""Rule-F real-data verification for the Breeze 1-second historical adapter
(§53 slice 4 P4a). Run this YOURSELF — it needs a daily Breeze session token that
only a manual browser login (with TOTP) can produce; there is no headless login.

Steps:
  1. Ensure .env has ICICI_BREEZE_API_KEY and ICICI_BREEZE_API_SECRET (gitignored).
  2. Open (in a browser):  https://api.icicidirect.com/apiuser/login?api_key=<API_KEY>
     Log in (TOTP happens here). After login the redirect URL contains apisession=XXXX.
  3. Run:  python scripts/verify_breeze_1s_realdata.py <apisession> [YYYY-MM-DD] [SYMBOL]
     (date defaults to the most recent weekday; SYMBOL defaults to RELIANCE.)

Prints the real 1-second bars fetched for the session's first ~10 minutes and
asserts they are non-empty, time-ordered, and OHLC-sane. Secrets are read from the
environment only and never printed.
"""

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    BrokerName,
    load_broker_api_credentials,
    load_env_file_into_environ,
)
from nse_algo_trader.market_data.breeze_historical_bar_source import (
    BreezeHistoricalBarSource,
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
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    session_token = sys.argv[1].strip()
    session_date = (
        date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else _most_recent_weekday()
    )
    # Default to ITC: its ICICI stock_code == NSE symbol, so it works without the
    # stock-code map. Many names (e.g. Reliance = "RELIND") differ — see task #6.
    symbol = sys.argv[3] if len(sys.argv) > 3 else "ITC"

    load_env_file_into_environ()
    credentials = load_broker_api_credentials(BrokerName.ICICI_BREEZE)
    if not credentials.api_secret:
        print("ICICI_BREEZE_API_SECRET is not set in .env — cannot generate session.")
        return 2

    from breeze_connect import BreezeConnect  # network I/O at import — intended here

    breeze = BreezeConnect(api_key=credentials.api_key)
    breeze.generate_session(api_secret=credentials.api_secret, session_token=session_token)

    instrument = Instrument(
        instrument_token=0, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )
    source = BreezeHistoricalBarSource(breeze)
    from_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 15, tzinfo=IST)
    to_dt = from_dt + timedelta(minutes=10)

    print(f"Fetching REAL Breeze 1-second bars: {symbol} {session_date} 09:15–09:25 IST …")
    bars = source.fetch_historical_bars(instrument, BarInterval.SECOND_1, from_dt, to_dt)

    print(f"→ {len(bars)} one-second bars returned")
    if not bars:
        print("EMPTY — check the date is a trading day, the session token is fresh, "
              "and the ICICI stock_code matches (Success:[] is ambiguous).")
        return 1
    for bar in bars[:3] + bars[-3:]:
        print(f"  {bar.timestamp}  O{bar.open_price} H{bar.high_price} "
              f"L{bar.low_price} C{bar.close_price} V{bar.volume}")

    timestamps = [b.timestamp for b in bars]
    assert timestamps == sorted(timestamps), "bars not time-ordered"
    assert all(b.low_price <= b.open_price <= b.high_price for b in bars), "OHLC insane"
    assert all(b.low_price <= b.close_price <= b.high_price for b in bars), "OHLC insane"
    assert all(b.interval is BarInterval.SECOND_1 for b in bars)
    print("✓ Rule-F PASS: real 1-second bars are non-empty, time-ordered, OHLC-sane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
