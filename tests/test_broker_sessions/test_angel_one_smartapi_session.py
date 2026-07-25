"""task #18 — Angel One SmartAPI session (hermetic, Rule J). The login + candle
network calls go through `requests.post`, monkeypatched here so no real network is
touched; the real-data pass (verify_angel_one_realdata.py) covers the live path."""

import pytest

from nse_algo_trader.broker_sessions import angel_one_smartapi_session as session_module
from nse_algo_trader.broker_sessions.angel_one_smartapi_session import (
    AngelOneSmartApiLoginError,
    build_angel_one_authenticated_historical_client,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_login_success_builds_client_that_sends_bearer_and_privatekey(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        if "loginByPassword" in url:
            return _FakeResponse({"status": True, "data": {"jwtToken": "JWT123"}})
        return _FakeResponse({"status": True, "data": [["2026-07-24T09:15:00+05:30", 1, 2, 0, 1, 5]]})

    monkeypatch.setattr(session_module.requests, "post", fake_post)
    client = build_angel_one_authenticated_historical_client(
        "APIKEY", "CLIENT1", "1234", "BASE32SECRET234567"
    )
    result = client.getCandleData({"exchange": "NSE", "symboltoken": "2885"})

    assert result["data"][0][4] == 1  # candle passed through
    assert captured["headers"]["Authorization"] == "Bearer JWT123"
    assert captured["headers"]["X-PrivateKey"] == "APIKEY"


def test_login_without_jwt_raises_login_error(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse({"status": False, "message": "Invalid totp", "data": None})

    monkeypatch.setattr(session_module.requests, "post", fake_post)
    with pytest.raises(AngelOneSmartApiLoginError, match="no jwtToken"):
        build_angel_one_authenticated_historical_client(
            "APIKEY", "CLIENT1", "1234", "BASE32SECRET234567"
        )
