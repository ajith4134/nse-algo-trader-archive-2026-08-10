"""§53 slice 4 task #6a — Breeze session-token store + authenticated-client builder
(hermetic, Rule J). No network, no real breeze_connect import."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    BrokerApiCredentials,
    BrokerName,
    MissingBrokerCredentialsError,
)
from nse_algo_trader.broker_sessions.breeze_authenticated_client_builder import (
    build_authenticated_breeze_client,
)
from nse_algo_trader.broker_sessions.breeze_session_token_store import (
    BreezeSessionTokenFileStore,
    BreezeSessionTokenRecord,
)

IST = ZoneInfo("Asia/Kolkata")


def _record(hour: int) -> BreezeSessionTokenRecord:
    return BreezeSessionTokenRecord(
        session_token="sess-123",
        generated_at=datetime(2026, 7, 24, hour, 0, tzinfo=IST),
    )


def test_token_valid_same_day_expired_after_midnight():
    record = _record(10)  # generated 10:00 IST
    assert record.is_still_valid(datetime(2026, 7, 24, 15, 0, tzinfo=IST))
    assert not record.is_still_valid(datetime(2026, 7, 25, 0, 1, tzinfo=IST))
    # expiry is the next IST midnight (earlier than +24h for a daytime token)
    assert record.expires_at() == datetime(2026, 7, 25, 0, 0, tzinfo=IST)


def test_save_load_roundtrip_and_valid_gate(tmp_path):
    store = BreezeSessionTokenFileStore(tmp_path / "breeze_session_token.json")
    assert store.load() is None
    record = _record(10)
    store.save(record)
    loaded = store.load()
    assert loaded.session_token == "sess-123"
    assert loaded.generated_at == record.generated_at
    # valid gate honours expiry
    assert store.load_if_still_valid(datetime(2026, 7, 24, 12, 0, tzinfo=IST)) is not None
    assert store.load_if_still_valid(datetime(2026, 7, 25, 1, 0, tzinfo=IST)) is None


def test_record_repr_masks_the_token():
    assert "sess-123" not in repr(_record(10))
    assert "***" in repr(_record(10))


class _FakeBreezeConnect:
    def __init__(self, api_key):
        self.api_key = api_key
        self.generated_with = None

    def generate_session(self, api_secret, session_token):
        self.generated_with = (api_secret, session_token)


def test_builder_constructs_and_generates_session_via_injected_factory():
    created = {}

    def factory(api_key):
        client = _FakeBreezeConnect(api_key)
        created["client"] = client
        return client

    credentials = BrokerApiCredentials(
        broker_name=BrokerName.ICICI_BREEZE, api_key="app-key", api_secret="app-secret"
    )
    client = build_authenticated_breeze_client(
        credentials, "sess-xyz", breeze_connect_factory=factory
    )
    assert client is created["client"]
    assert client.api_key == "app-key"
    assert client.generated_with == ("app-secret", "sess-xyz")


def test_builder_requires_api_secret():
    credentials = BrokerApiCredentials(
        broker_name=BrokerName.ICICI_BREEZE, api_key="app-key", api_secret=None
    )
    with pytest.raises(MissingBrokerCredentialsError):
        build_authenticated_breeze_client(
            credentials, "sess-xyz", breeze_connect_factory=_FakeBreezeConnect
        )
