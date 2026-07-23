import json
from pathlib import Path

import pyotp
import pytest

from nse_algo_trader.broker_credentials import BrokerApiCredentials, BrokerName
from nse_algo_trader.broker_credentials.kite_login_credentials_loader import (
    KiteLoginCredentials,
    load_kite_login_credentials,
)
from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    MissingBrokerCredentialsError,
)
from nse_algo_trader.broker_sessions import (
    KiteAccessTokenFileStore,
    KiteAutoLoginError,
    fetch_kite_request_token_via_totp_login,
    generate_and_store_daily_kite_access_token,
)

FAKE_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # standard test-vector base32 secret

FAKE_LOGIN_CREDENTIALS = KiteLoginCredentials(
    kite_user_id="HZV381",
    kite_password="fake_password",
    kite_totp_secret=FAKE_TOTP_SECRET,
)

FAKE_KITE_API_CREDENTIALS = BrokerApiCredentials(
    broker_name=BrokerName.ZERODHA_KITE,
    api_key="fake_api_key",
    api_secret="fake_api_secret",
)


class FakeHttpResponse:
    def __init__(self, status_code=200, json_payload=None, headers=None):
        self.status_code = status_code
        self._json_payload = json_payload or {}
        self.headers = headers or {}

    def json(self):
        return self._json_payload


class FakeKiteWebSession:
    """Replays Kite's login endpoint sequence, validating each step's inputs."""

    def __init__(self, wrong_password=False):
        self.wrong_password = wrong_password
        self.posted_forms = []

    def get(self, url, allow_redirects=True, timeout=None):
        if "connect/login" in url and "skip_session" not in url:
            return FakeHttpResponse()  # cookie-seeding page load
        if "skip_session=true" in url:
            return FakeHttpResponse(
                302,
                headers={"location": "https://kite.zerodha.com/connect/finish?x=1"},
            )
        if "connect/finish" in url:
            return FakeHttpResponse(
                302,
                headers={
                    "location": "http://127.0.0.1/kite/callback"
                    "?status=success&request_token=fake_request_token_123"
                },
            )
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, data=None, timeout=None):
        self.posted_forms.append((url, data))
        if url.endswith("/api/login"):
            if self.wrong_password:
                return FakeHttpResponse(403, {"message": "Invalid password"})
            assert data == {"user_id": "HZV381", "password": "fake_password"}
            return FakeHttpResponse(200, {"data": {"request_id": "fake_request_id"}})
        if url.endswith("/api/twofa"):
            assert data["request_id"] == "fake_request_id"
            assert data["twofa_type"] == "totp"
            assert pyotp.TOTP(FAKE_TOTP_SECRET).verify(data["twofa_value"])
            return FakeHttpResponse(200, {"data": {}})
        raise AssertionError(f"unexpected POST {url}")


def test_full_login_chain_yields_request_token_without_visiting_redirect_url():
    request_token = fetch_kite_request_token_via_totp_login(
        "fake_api_key", FAKE_LOGIN_CREDENTIALS, FakeKiteWebSession()
    )
    assert request_token == "fake_request_token_123"


def test_wrong_password_raises_with_kite_error_message():
    with pytest.raises(KiteAutoLoginError, match="Invalid password"):
        fetch_kite_request_token_via_totp_login(
            "fake_api_key", FAKE_LOGIN_CREDENTIALS, FakeKiteWebSession(wrong_password=True)
        )


def test_daily_refresh_exchanges_token_and_persists_record(tmp_path: Path):
    token_store = KiteAccessTokenFileStore(tmp_path / "kite_access_token.json")

    def fake_session_generator(request_token, api_secret):
        assert request_token == "fake_request_token_123"
        assert api_secret == "fake_api_secret"
        return {"access_token": "fake_daily_access_token", "user_id": "HZV381"}

    stored_record = generate_and_store_daily_kite_access_token(
        FAKE_KITE_API_CREDENTIALS,
        FAKE_LOGIN_CREDENTIALS,
        token_store,
        authenticated_session_generator=fake_session_generator,
        http_session=FakeKiteWebSession(),
    )
    assert stored_record.access_token == "fake_daily_access_token"
    persisted_fields = json.loads((tmp_path / "kite_access_token.json").read_text())
    assert persisted_fields["access_token"] == "fake_daily_access_token"
    assert persisted_fields["kite_user_id"] == "HZV381"


def test_login_credentials_loader_lists_every_missing_env_var():
    with pytest.raises(MissingBrokerCredentialsError) as raised:
        load_kite_login_credentials({"ZERODHA_KITE_USER_ID": "HZV381"})
    assert "ZERODHA_KITE_PASSWORD" in str(raised.value)
    assert "ZERODHA_KITE_TOTP_SECRET" in str(raised.value)
