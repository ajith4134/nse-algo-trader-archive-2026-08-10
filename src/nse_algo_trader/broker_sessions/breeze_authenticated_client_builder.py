"""Builds an authenticated ICICI Breeze client from stored creds + a session token
(§53 slice 4 task #6a).

`breeze_connect` does network I/O at import (downloads the SecurityMaster), so this
module — a composition-root concern — is the ONLY place that imports it, and even
then lazily, behind an injectable factory so tests never touch the real SDK. The
Breeze historical adapter stays free of the import.
"""

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    BrokerApiCredentials,
    MissingBrokerCredentialsError,
)


def build_authenticated_breeze_client(
    api_credentials: BrokerApiCredentials,
    session_token: str,
    breeze_connect_factory=None,
):
    """Construct a BreezeConnect and generate its daily session. `breeze_connect_
    factory` defaults to the real `BreezeConnect` class (imported lazily so the
    network-heavy import only happens when actually building a live client); tests
    inject a fake factory. Returns the authenticated client."""
    if not api_credentials.api_secret:
        raise MissingBrokerCredentialsError(
            "ICICI_BREEZE_API_SECRET is required to generate a Breeze session"
        )
    if breeze_connect_factory is None:
        from breeze_connect import BreezeConnect  # network I/O at import — intended

        breeze_connect_factory = BreezeConnect
    client = breeze_connect_factory(api_key=api_credentials.api_key)
    client.generate_session(
        api_secret=api_credentials.api_secret, session_token=session_token
    )
    return client
