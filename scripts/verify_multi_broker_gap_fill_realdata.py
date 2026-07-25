"""Rule-F real-data verification for GAP_FILL aggregation (task #20 slice-2).

Proves gap-fill completes a primary's mid-session gap from a real secondary. To create
a genuine gap on REAL data, the primary is the live Upstox source TRUNCATED to the
morning (a thin wrapper that returns only Upstox's real bars before 12:00 IST —
simulating a mid-day broker outage); the secondary is the live full-day Angel source.
GAP_FILL must then serve morning bars from Upstox and afternoon bars from Angel, all
REAL. Secrets are read from the environment only and never printed.

Run:  python scripts/verify_multi_broker_gap_fill_realdata.py [YYYY-MM-DD] [SYMBOL]
"""

import os
import sys
from datetime import date, datetime, time, timedelta
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
    SourceCombinationPolicy,
    SourceAttempt,
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
_NOON = time(12, 0)


class _MorningOnlyRealSource:
    """Delegates to a REAL source but drops bars at/after 12:00 IST — a deterministic
    mid-session gap over genuine data (stands in for a broker that went down at noon)."""

    def __init__(self, real_source):
        self._real_source = real_source

    def fetch_historical_bars(self, instrument, bar_interval, from_datetime, to_datetime):
        real_bars = self._real_source.fetch_historical_bars(
            instrument, bar_interval, from_datetime, to_datetime
        )
        return [b for b in real_bars if b.timestamp.timetz().replace(tzinfo=None) < _NOON]


def _most_recent_weekday() -> date:
    day = date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def main() -> int:
    session_date = (
        date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else _most_recent_weekday()
    )
    symbol = sys.argv[2] if len(sys.argv) > 2 else "RELIANCE"
    load_env_file_into_environ()

    upstox_token = (
        os.environ.get("UPSTOX_ANALYTICS_TOKEN", "").strip()
        or os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    )
    upstox_resolver = UpstoxInstrumentKeyResolver.from_instrument_master_records(
        download_upstox_nse_instrument_master_records()
    )
    upstox = UpstoxHistoricalBarSource(UpstoxRestHistoricalClient(upstox_token), upstox_resolver)

    angel_resolver = AngelOneSymbolTokenResolver.from_scrip_master_records(
        download_angel_one_scrip_master_records()
    )
    angel_client = build_angel_one_authenticated_historical_client(
        os.environ["ANGEL_ONE_API_KEY"].strip(),
        os.environ["ANGEL_ONE_CLIENT_CODE"].strip(),
        os.environ["ANGEL_ONE_PIN"].strip(),
        os.environ["ANGEL_ONE_TOTP_SECRET"].strip(),
    )
    angel = AngelOneHistoricalBarSource(angel_client, angel_resolver)

    attempts: list[SourceAttempt] = []
    gap_filled = MultiBrokerHistoricalBarSource(
        [
            NamedHistoricalBarSource("upstox_morning_only", _MorningOnlyRealSource(upstox)),
            NamedHistoricalBarSource("angel_full_day", angel),
        ],
        on_source_attempt=attempts.append,
        combination_policy=SourceCombinationPolicy.GAP_FILL,
    )

    instrument = Instrument(
        instrument_token=0, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )
    from_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 15, tzinfo=IST)
    to_dt = from_dt + timedelta(hours=6, minutes=15)

    print(f"GAP_FILL real pass: {symbol} {session_date} "
          f"(primary=Upstox truncated to <12:00, secondary=Angel full day) …")
    bars = gap_filled.fetch_historical_bars(instrument, BarInterval.MINUTE_1, from_dt, to_dt)

    morning = [b for b in bars if b.timestamp.timetz().replace(tzinfo=None) < _NOON]
    afternoon = [b for b in bars if b.timestamp.timetz().replace(tzinfo=None) >= _NOON]
    for a in attempts:
        print(f"    {a.source_name}: {a.outcome} contributed {a.bar_count}")
    print(f"→ {len(bars)} bars total = {len(morning)} morning + {len(afternoon)} afternoon")

    assert morning and afternoon, "expected both a morning and an afternoon segment"
    # Upstox (primary) contributed the morning; Angel filled the afternoon gap.
    upstox_contrib = next(a.bar_count for a in attempts if a.source_name == "upstox_morning_only")
    angel_contrib = next(a.bar_count for a in attempts if a.source_name == "angel_full_day")
    assert upstox_contrib == len(morning), "morning should come from the primary"
    assert angel_contrib == len(afternoon), "afternoon gap should be filled by the secondary"
    ts = [b.timestamp for b in bars]
    assert ts == sorted(ts) and len(ts) == len(set(ts)), "not sorted/deduped"
    assert all(b.low_price <= b.open_price <= b.high_price for b in bars), "OHLC insane"
    print("\n✓ Rule-F PASS: GAP_FILL completed a real mid-session gap — morning from the "
          "primary (Upstox), afternoon filled from the secondary (Angel), contiguous & sane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
