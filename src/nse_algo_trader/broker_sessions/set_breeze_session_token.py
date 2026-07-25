"""CLI to store today's ICICI Breeze session token (§53 slice 4 task #6a).

Breeze has no headless login, so the daily token is obtained manually:
  1. Run with no args to print the login URL (built from ICICI_BREEZE_API_KEY).
  2. Open it, log in (TOTP), copy `apisession=…` from the redirect URL.
  3. Run:  python -m nse_algo_trader.broker_sessions.set_breeze_session_token <apisession>
This stores it (owner-only) so the service/adapter can build an authenticated
client without re-prompting until it expires (midnight / 24h).
"""

import sys
from datetime import datetime

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    BrokerName,
    load_broker_api_credentials,
    load_env_file_into_environ,
)
from nse_algo_trader.broker_sessions.breeze_session_token_store import (
    INDIA_MARKET_TIMEZONE,
    BreezeSessionTokenFileStore,
    BreezeSessionTokenRecord,
)

_LOGIN_URL_TEMPLATE = "https://api.icicidirect.com/apiuser/login?api_key={api_key}"


def main() -> int:
    load_env_file_into_environ()
    credentials = load_broker_api_credentials(BrokerName.ICICI_BREEZE)
    if len(sys.argv) < 2:
        print("Open this URL, log in (TOTP), then re-run with the apisession value:")
        print(_LOGIN_URL_TEMPLATE.format(api_key=credentials.api_key))
        return 2
    session_token = sys.argv[1].strip()
    store = BreezeSessionTokenFileStore()
    record = BreezeSessionTokenRecord(
        session_token=session_token,
        generated_at=datetime.now(INDIA_MARKET_TIMEZONE),
    )
    store.save(record)
    print(f"Stored Breeze session token — valid until {record.expires_at()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
