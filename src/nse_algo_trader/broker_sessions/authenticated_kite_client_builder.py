"""Builds a live-authenticated KiteConnect client — the ONLY place outside `market_data` that touches
`kiteconnect` for a trading client, kept inside the broker seam (idea #10, `feedback_kite_decoupled_architecture`).

Kite is a bounded execution/live-feed adapter: nothing outside `broker_*`/`market_data` may import
`kiteconnect`. The dashboard + every analysis feature must run with NO Kite session; only the Live/Paper
trading module reaches for a broker client, and it does so through THIS function so the dependency stays
isolated (an architecture guard test enforces the boundary).

Returns None when there is no valid daily token — the caller then runs offline/stored-data mode. The
`kiteconnect` import is function-local so importing this module never forces the SDK to load.
"""

from __future__ import annotations

from typing import Any


def build_authenticated_kite_client_if_valid() -> Any | None:
    """A live-authenticated `KiteConnect`, or None if no valid daily token exists (→ caller degrades to
    offline/stored-data mode). Typed `Any` so callers/tests need not import the SDK to reference it."""
    from kiteconnect import KiteConnect

    from nse_algo_trader.broker_credentials import (
        BrokerName,
        load_broker_api_credentials,
        load_env_file_into_environ,
    )
    from nse_algo_trader.broker_sessions.kite_access_token_store import KiteAccessTokenFileStore

    load_env_file_into_environ()
    token_record = KiteAccessTokenFileStore().load_if_still_valid()
    if token_record is None:
        return None
    credentials = load_broker_api_credentials(BrokerName.ZERODHA_KITE)
    kite_client = KiteConnect(api_key=credentials.api_key)
    kite_client.set_access_token(token_record.access_token)
    return kite_client
