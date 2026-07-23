from datetime import datetime

from nse_algo_trader.market_data import (
    KiteLiveTickStreamSource,
    LiveTickStreamSource,
    parse_kite_ticker_payload,
)

SAMPLE_KITE_FULL_MODE_TICK = {
    "tradable": True,
    "mode": "full",
    "instrument_token": 408065,
    "last_price": 1523.1,
    "last_traded_quantity": 25,
    "average_traded_price": 1521.8,
    "volume_traded": 1834230,
    "oi": 0,
    "exchange_timestamp": datetime(2026, 7, 22, 14, 5, 3),
}

SAMPLE_KITE_LTP_MODE_TICK = {
    "tradable": True,
    "mode": "ltp",
    "instrument_token": 9604354,
    "last_price": 110.2,
}


class FakeKiteTickerClient:
    """Stands in for kiteconnect.KiteTicker; records subscribe/connect calls."""

    def __init__(self):
        self.on_ticks = None
        self.on_connect = None
        self.subscribed_tokens = []
        self.connect_called = False
        self.close_called = False
        self._connected = False

    def is_connected(self):
        return self._connected

    def subscribe(self, instrument_tokens):
        self.subscribed_tokens.extend(instrument_tokens)

    def connect(self, threaded=False):
        self.connect_called = True
        self._connected = True
        self.on_connect(self, {})

    def close(self):
        self.close_called = True
        self._connected = False


def test_full_mode_payload_parses_every_field():
    market_tick = parse_kite_ticker_payload(SAMPLE_KITE_FULL_MODE_TICK)
    assert market_tick.instrument_token == 408065
    assert market_tick.last_price == 1523.1
    assert market_tick.last_traded_quantity == 25
    assert market_tick.cumulative_day_volume == 1834230
    assert market_tick.average_traded_price == 1521.8
    assert market_tick.open_interest == 0
    assert market_tick.exchange_timestamp == datetime(2026, 7, 22, 14, 5, 3)


def test_ltp_mode_payload_parses_with_none_for_absent_fields():
    market_tick = parse_kite_ticker_payload(SAMPLE_KITE_LTP_MODE_TICK)
    assert market_tick.instrument_token == 9604354
    assert market_tick.last_price == 110.2
    assert market_tick.last_traded_quantity is None
    assert market_tick.cumulative_day_volume is None
    assert market_tick.exchange_timestamp is None


def test_satisfies_live_tick_stream_source_protocol():
    stream_source = KiteLiveTickStreamSource(FakeKiteTickerClient())
    assert isinstance(stream_source, LiveTickStreamSource)


def test_tokens_subscribed_before_connect_are_sent_on_connect():
    fake_ticker_client = FakeKiteTickerClient()
    stream_source = KiteLiveTickStreamSource(fake_ticker_client)
    stream_source.subscribe_instrument_tokens([408065, 9604354])
    assert fake_ticker_client.subscribed_tokens == []  # not connected yet
    stream_source.start_streaming()
    assert fake_ticker_client.connect_called is True
    assert fake_ticker_client.subscribed_tokens == [408065, 9604354]


def test_registered_callbacks_receive_parsed_market_ticks():
    fake_ticker_client = FakeKiteTickerClient()
    stream_source = KiteLiveTickStreamSource(fake_ticker_client)
    received_market_ticks = []
    stream_source.register_tick_callback(received_market_ticks.append)
    fake_ticker_client.on_ticks(
        fake_ticker_client, [SAMPLE_KITE_FULL_MODE_TICK, SAMPLE_KITE_LTP_MODE_TICK]
    )
    assert [tick.instrument_token for tick in received_market_ticks] == [
        408065,
        9604354,
    ]


def test_stop_streaming_closes_the_websocket():
    fake_ticker_client = FakeKiteTickerClient()
    stream_source = KiteLiveTickStreamSource(fake_ticker_client)
    stream_source.stop_streaming()
    assert fake_ticker_client.close_called is True
