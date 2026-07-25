"""Angel One SmartAPI daily session: api_key + client code + PIN + TOTP → jwtToken,
and a thin authenticated historical client (task #18; research/83).

SmartAPI login is NOT OAuth — it is a direct `generateSession(clientcode, pin, totp)`
POST (`loginByPassword`) that returns a `jwtToken`. The session hard-expires at
midnight IST, so this runs once daily. We avoid the `smartapi-python` SDK and speak
the REST endpoints directly (requests + pyotp, both already project deps), returning
an object exposing `getCandleData(param)` — exactly the shape
`AngelOneHistoricalBarSource` consumes (injected at the composition root; the adapter
never imports this).
"""

from __future__ import annotations

import pyotp
import requests

_LOGIN_URL = (
    "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
)
_CANDLE_DATA_URL = (
    "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
)


def _smartapi_headers(api_key: str) -> dict[str, str]:
    """The mandatory SmartAPI request headers (IPs/MAC are cosmetic for a script)."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00",
        "X-PrivateKey": api_key,
    }


class AngelOneSmartApiLoginError(Exception):
    """Raised when `generateSession` (loginByPassword) does not return a jwtToken."""


class AngelOneAuthenticatedHistoricalClient:
    """Holds a live jwtToken and exposes `getCandleData(param)` — the shape
    `AngelOneHistoricalBarSource` expects. Network only when called."""

    def __init__(self, api_key: str, jwt_token: str, timeout_seconds: int = 30) -> None:
        self._api_key = api_key
        self._jwt_token = jwt_token
        self._timeout_seconds = timeout_seconds

    def getCandleData(self, param: dict, timeout=None):  # noqa: N802 (SmartAPI name)
        headers = _smartapi_headers(self._api_key)
        headers["Authorization"] = f"Bearer {self._jwt_token}"
        response = requests.post(
            _CANDLE_DATA_URL, headers=headers, json=param,
            timeout=timeout or self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


def build_angel_one_authenticated_historical_client(
    api_key: str,
    client_code: str,
    pin: str,
    totp_secret: str,
    timeout_seconds: int = 30,
) -> AngelOneAuthenticatedHistoricalClient:
    """Log in via `generateSession` (current TOTP from `totp_secret`) and return an
    authenticated historical client. Network I/O — call at the composition root."""
    login_response = requests.post(
        _LOGIN_URL,
        headers=_smartapi_headers(api_key),
        json={
            "clientcode": client_code,
            "password": pin,
            "totp": pyotp.TOTP(totp_secret).now(),
        },
        timeout=timeout_seconds,
    )
    login_response.raise_for_status()
    body = login_response.json()
    jwt_token = (body.get("data") or {}).get("jwtToken")
    if not jwt_token:
        raise AngelOneSmartApiLoginError(
            f"Angel One login returned no jwtToken (message: {body.get('message')!r})"
        )
    return AngelOneAuthenticatedHistoricalClient(api_key, jwt_token, timeout_seconds)
