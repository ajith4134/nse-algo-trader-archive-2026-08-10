"""CLI entry point for the daily Kite token refresh (run by cron pre-market).

Usage:  python -m nse_algo_trader.broker_sessions.refresh_kite_access_token
Skips the login entirely when the stored token is still valid; pass
--force to refresh regardless.
"""

import sys

from nse_algo_trader.broker_credentials import (
    BrokerName,
    load_broker_api_credentials,
    load_env_file_into_environ,
)
from nse_algo_trader.broker_credentials.kite_login_credentials_loader import (
    load_kite_login_credentials,
)
from nse_algo_trader.broker_sessions.kite_access_token_store import (
    KiteAccessTokenFileStore,
)
from nse_algo_trader.broker_sessions.kite_totp_auto_login import (
    generate_and_store_daily_kite_access_token,
)


def refresh_kite_access_token_if_needed(force_refresh: bool = False) -> None:
    load_env_file_into_environ()
    token_store = KiteAccessTokenFileStore()

    if not force_refresh:
        still_valid_record = token_store.load_if_still_valid()
        if still_valid_record is not None:
            print(
                f"Kite access token for {still_valid_record.kite_user_id} still "
                f"valid until {still_valid_record.expires_at():%Y-%m-%d %H:%M %Z} — "
                "skipping login"
            )
            return

    fresh_record = generate_and_store_daily_kite_access_token(
        kite_api_credentials=load_broker_api_credentials(BrokerName.ZERODHA_KITE),
        kite_login_credentials=load_kite_login_credentials(),
        token_store=token_store,
    )
    print(
        f"Fresh Kite access token stored for {fresh_record.kite_user_id}, "
        f"valid until {fresh_record.expires_at():%Y-%m-%d %H:%M %Z}"
    )


if __name__ == "__main__":
    refresh_kite_access_token_if_needed(force_refresh="--force" in sys.argv)
