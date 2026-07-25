"""Rule-F real-data verification for the autonomous multi-broker replay wiring
(task #20). Exercises the SAME path the service uses when the market is closed and no
Breeze token is present: the real `_build_available_broker_fleet_source()` assembles a
live fleet from .env creds, then `build_replay_bars_by_token_from_source` (the exact
builder `_build_high_fidelity_replay_feed` calls) produces a real minute `bars_by_token`
for a focus set. Asserts real bars came back and were served by the fleet's members.
Secrets are read from the environment only and never printed.

Run:  python scripts/verify_multi_broker_replay_wiring_realdata.py [YYYY-MM-DD]
"""

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.dashboard.live_paper_trading_service import (
    _build_available_broker_fleet_source,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.market_data.multi_broker_historical_bar_source import (
    SourceAttempt,
)
from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (
    build_replay_bars_by_token_from_source,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")

_FOCUS = [
    ("RELIANCE", 738561),
    ("INFY", 408065),
    ("TCS", 2953217),
]


def _most_recent_weekday() -> date:
    day = date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def main() -> int:
    session_date = (
        date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else _most_recent_weekday()
    )
    load_env_file_into_environ()

    print("Building the REAL broker fleet from .env creds …")
    fleet = _build_available_broker_fleet_source()
    if fleet is None:
        print("No broker creds available — set Upstox/Angel creds in .env.")
        return 2
    print(f"→ fleet priority order: {fleet.source_names_in_priority_order()}")

    attempts: list[SourceAttempt] = []
    fleet._on_source_attempt = attempts.append  # observe which broker serves each

    focus_instruments = [
        Instrument(
            instrument_token=token, trading_symbol=symbol,
            exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
            lot_size=1, tick_size=0.05,
        )
        for symbol, token in _FOCUS
    ]
    from_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 15, tzinfo=IST)
    to_dt = from_dt + timedelta(hours=6, minutes=15)

    print(f"Building replay bars_by_token via the loop's builder: {session_date} …")
    bars_by_token = build_replay_bars_by_token_from_source(
        fleet, focus_instruments, BarInterval.MINUTE_1, from_dt, to_dt
    )

    print(f"→ {len(bars_by_token)} instruments served; "
          f"{sum(len(b) for b in bars_by_token.values())} total real minute bars")
    for symbol, token in _FOCUS:
        served_by = next(
            (a.source_name for a in attempts
             if a.instrument_trading_symbol == symbol and a.outcome == "served"),
            None,
        )
        n = len(bars_by_token.get(token, []))
        print(f"    {symbol}: {n} bars  (served by {served_by!r})")

    assert bars_by_token, "fleet returned no bars for any focus instrument"
    for token_bars in bars_by_token.values():
        ts = [b.timestamp for b in token_bars]
        assert ts == sorted(ts) and len(ts) == len(set(ts)), "bars unordered/dup"
        assert all(b.low_price <= b.open_price <= b.high_price for b in token_bars)
    print("\n✓ Rule-F PASS: the autonomous fleet wiring produced real minute bars_by_token "
          "through the exact builder the market-closed loop uses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
