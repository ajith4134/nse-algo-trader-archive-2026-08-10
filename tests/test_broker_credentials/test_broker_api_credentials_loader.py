import pytest

from nse_algo_trader.broker_credentials import (
    BrokerName,
    MissingBrokerCredentialsError,
    load_broker_api_credentials,
)

FAKE_ENVIRON_WITH_KITE_AND_ANGEL = {
    "ZERODHA_KITE_API_KEY": "fake_kite_key",
    "ZERODHA_KITE_API_SECRET": "fake_kite_secret",
    "ANGEL_ONE_API_KEY": "fake_angel_key",  # deliberately no secret
}


def test_loads_key_and_secret_when_both_present():
    kite_credentials = load_broker_api_credentials(
        BrokerName.ZERODHA_KITE, FAKE_ENVIRON_WITH_KITE_AND_ANGEL
    )
    assert kite_credentials.api_key == "fake_kite_key"
    assert kite_credentials.api_secret == "fake_kite_secret"


def test_missing_secret_becomes_none_not_empty_string():
    angel_credentials = load_broker_api_credentials(
        BrokerName.ANGEL_ONE, FAKE_ENVIRON_WITH_KITE_AND_ANGEL
    )
    assert angel_credentials.api_key == "fake_angel_key"
    assert angel_credentials.api_secret is None


def test_missing_api_key_raises_with_env_var_name_in_message():
    with pytest.raises(MissingBrokerCredentialsError, match="UPSTOX_API_KEY"):
        load_broker_api_credentials(
            BrokerName.UPSTOX, FAKE_ENVIRON_WITH_KITE_AND_ANGEL
        )


def test_repr_never_exposes_secret_values():
    kite_credentials = load_broker_api_credentials(
        BrokerName.ZERODHA_KITE, FAKE_ENVIRON_WITH_KITE_AND_ANGEL
    )
    credentials_repr = repr(kite_credentials)
    assert "fake_kite_key" not in credentials_repr
    assert "fake_kite_secret" not in credentials_repr
    assert "***" in credentials_repr
