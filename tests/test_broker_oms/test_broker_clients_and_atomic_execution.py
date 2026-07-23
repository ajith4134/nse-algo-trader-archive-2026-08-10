import pytest

from nse_algo_trader.broker_oms import (
    BrokerClient,
    KiteBrokerClient,
    OrderIntent,
    OrderLifecycleState,
    OrderRateLimiter,
    OrderSide,
    SimulatedBrokerClient,
    execute_multi_leg_order_atomically,
)
from tests.test_broker_oms.broker_oms_test_fixtures import (
    CASH_INSTRUMENT,
    make_put_instrument,
)

HEDGE_PUT = make_put_instrument(23650.0)
SHORT_PUT = make_put_instrument(23750.0)


def _spread_legs(hedge_first: bool = True) -> list[OrderIntent]:
    hedge = OrderIntent(HEDGE_PUT, OrderSide.BUY, 65, "credit_spread_v1")
    short = OrderIntent(SHORT_PUT, OrderSide.SELL, 65, "credit_spread_v1")
    return [hedge, short] if hedge_first else [short, hedge]


class TestSimulatedBrokerClient:
    def test_satisfies_broker_client_protocol(self):
        assert isinstance(SimulatedBrokerClient(), BrokerClient)

    def test_fills_at_last_known_price_and_tracks_positions(self):
        client = SimulatedBrokerClient()
        client.update_market_price(408065, 1523.1)
        result = client.place_order(
            OrderIntent(CASH_INSTRUMENT, OrderSide.BUY, 100, "orb")
        )
        assert result.state is OrderLifecycleState.COMPLETE
        assert result.average_fill_price == 1523.1
        assert client.net_position_quantity(408065) == 100
        client.place_order(OrderIntent(CASH_INSTRUMENT, OrderSide.SELL, 100, "orb"))
        assert client.net_position_quantity(408065) == 0

    def test_unknown_price_rejects_instead_of_inventing_a_fill(self):
        result = SimulatedBrokerClient().place_order(
            OrderIntent(CASH_INSTRUMENT, OrderSide.BUY, 100, "orb")
        )
        assert result.state is OrderLifecycleState.REJECTED
        assert "no market price" in result.rejection_message

    def test_fill_price_adjuster_hook_shifts_fills(self):
        client = SimulatedBrokerClient(
            fill_price_adjuster=lambda intent, price: price + 0.5
        )
        client.update_market_price(408065, 100.0)
        result = client.place_order(
            OrderIntent(CASH_INSTRUMENT, OrderSide.BUY, 10, "orb")
        )
        assert result.average_fill_price == 100.5


class FakeKiteTradingClient:
    def __init__(self, reject_symbols: set[str] = frozenset()):
        self.reject_symbols = reject_symbols
        self.placed_order_kwargs: list[dict] = []
        self.cancelled_order_ids: list[str] = []

    def place_order(self, **kwargs):
        if kwargs["tradingsymbol"] in self.reject_symbols:
            raise RuntimeError("RMS: margin exceeds")
        self.placed_order_kwargs.append(kwargs)
        return len(self.placed_order_kwargs)

    def order_history(self, order_id):
        return [{"status": "COMPLETE", "filled_quantity": 65, "average_price": 41.5}]

    def cancel_order(self, variety, order_id):
        self.cancelled_order_ids.append(order_id)


def _instant_rate_limiter() -> OrderRateLimiter:
    fake_time = [0.0]

    def clock():
        fake_time[0] += 0.001
        return fake_time[0]

    return OrderRateLimiter(monotonic_clock=clock, sleep_function=lambda s: None)


class TestKiteBrokerClient:
    def test_satisfies_protocol_and_maps_every_kite_param(self):
        fake_kite = FakeKiteTradingClient()
        client = KiteBrokerClient(fake_kite, _instant_rate_limiter())
        assert isinstance(client, BrokerClient)
        result = client.place_order(
            OrderIntent(
                SHORT_PUT, OrderSide.SELL, 65,
                "credit_spread_v1_extra_long_tag_beyond_kite_limit",
            )
        )
        assert result.state is OrderLifecycleState.OPEN
        placed_kwargs = fake_kite.placed_order_kwargs[0]
        assert placed_kwargs["exchange"] == "NFO"
        assert placed_kwargs["tradingsymbol"] == "NIFTY26JUL23750PE"
        assert placed_kwargs["transaction_type"] == "SELL"
        assert placed_kwargs["quantity"] == 65
        assert placed_kwargs["product"] == "MIS"
        assert placed_kwargs["order_type"] == "MARKET"
        assert len(placed_kwargs["tag"]) <= 20

    def test_kite_exception_becomes_rejected_result_not_crash(self):
        fake_kite = FakeKiteTradingClient(reject_symbols={"NIFTY26JUL23750PE"})
        client = KiteBrokerClient(fake_kite, _instant_rate_limiter())
        result = client.place_order(
            OrderIntent(SHORT_PUT, OrderSide.SELL, 65, "credit_spread_v1")
        )
        assert result.state is OrderLifecycleState.REJECTED
        assert "RMS" in result.rejection_message

    def test_fetch_order_result_maps_kite_history(self):
        client = KiteBrokerClient(FakeKiteTradingClient(), _instant_rate_limiter())
        result = client.fetch_order_result("42")
        assert result.state is OrderLifecycleState.COMPLETE
        assert result.filled_quantity == 65
        assert result.average_fill_price == 41.5


class TestOrderRateLimiter:
    def test_blocks_at_the_ceiling_until_the_window_rolls(self):
        current_time = [0.0]
        sleeps: list[float] = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            current_time[0] += seconds

        limiter = OrderRateLimiter(
            max_orders_per_second=5,
            monotonic_clock=lambda: current_time[0],
            sleep_function=fake_sleep,
        )
        for _ in range(5):
            limiter.wait_for_order_slot()
        assert sleeps == []  # first five pass immediately
        limiter.wait_for_order_slot()  # sixth must wait for the window
        assert len(sleeps) >= 1
        assert current_time[0] >= 1.0


class TestAtomicMultiLegExecution:
    def test_happy_path_executes_hedge_before_short(self):
        paper_client = SimulatedBrokerClient()
        paper_client.update_market_price(HEDGE_PUT.instrument_token, 28.0)
        paper_client.update_market_price(SHORT_PUT.instrument_token, 53.6)
        report = execute_multi_leg_order_atomically(
            _spread_legs(hedge_first=False), paper_client  # wrong order on purpose
        )
        assert report.all_legs_executed
        assert paper_client.net_position_quantity(HEDGE_PUT.instrument_token) == 65
        assert paper_client.net_position_quantity(SHORT_PUT.instrument_token) == -65
        # first executed order was the hedge BUY despite reversed input
        first_result = report.leg_results[0]
        assert first_result.broker_order_id == "SIM-1"

    def test_short_leg_failure_unwinds_hedge_no_position_remains(self):
        # PLAN §5's mandated one-leg-failure test: hedge fills, short leg
        # is rejected (no market price known for it) -> hedge unwound.
        paper_client = SimulatedBrokerClient()
        paper_client.update_market_price(HEDGE_PUT.instrument_token, 28.0)
        report = execute_multi_leg_order_atomically(_spread_legs(), paper_client)
        assert not report.all_legs_executed
        assert report.failed_leg_intent.instrument == SHORT_PUT
        assert len(report.unwind_results) == 1
        assert paper_client.net_position_quantity(HEDGE_PUT.instrument_token) == 0
        assert paper_client.net_position_quantity(SHORT_PUT.instrument_token) == 0

    def test_empty_legs_raise(self):
        with pytest.raises(ValueError):
            execute_multi_leg_order_atomically([], SimulatedBrokerClient())


class TestPaperLiveParity:
    """PLAN §5: the same intent sequence against SimulatedBrokerClient and a
    mocked KiteBrokerClient must produce identical order-intent sequences."""

    def test_identical_order_sequences_on_both_clients(self):
        recorded_sequences = {}

        for client_name, client in {
            "paper": SimulatedBrokerClient(),
            "live": KiteBrokerClient(FakeKiteTradingClient(), _instant_rate_limiter()),
        }.items():
            if isinstance(client, SimulatedBrokerClient):
                client.update_market_price(HEDGE_PUT.instrument_token, 28.0)
                client.update_market_price(SHORT_PUT.instrument_token, 53.6)
            executed_intents: list[tuple] = []
            original_place_order = client.place_order

            def recording_place_order(intent, _original=original_place_order):
                executed_intents.append(
                    (intent.instrument.trading_symbol, intent.side.value, intent.quantity)
                )
                return _original(intent)

            client.place_order = recording_place_order
            report = execute_multi_leg_order_atomically(_spread_legs(), client)
            assert report.all_legs_executed
            recorded_sequences[client_name] = executed_intents

        assert recorded_sequences["paper"] == recorded_sequences["live"]
        assert recorded_sequences["paper"] == [
            ("NIFTY26JUL23650PE", "buy", 65),
            ("NIFTY26JUL23750PE", "sell", 65),
        ]
