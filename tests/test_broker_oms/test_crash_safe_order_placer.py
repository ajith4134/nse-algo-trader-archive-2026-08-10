"""L3 ops floor — the crash-safe order placer binds idempotency + WAL + reconciliation onto the broker.

Hermetic (Rule J): a fake broker behind the `place_order` protocol proves double-place suppression +
durability + restart reconciliation. The real-data pass is a LIVE Kite session (open blocker, BACKLOG).
"""

from datetime import date, datetime

from nse_algo_trader.broker_oms.broker_state_reconciler import PositionSnapshot
from nse_algo_trader.broker_oms.crash_safe_order_placer import CrashSafeOrderPlacer
from nse_algo_trader.broker_oms.order_intent_write_ahead_log import OrderIntentWriteAheadLog
from nse_algo_trader.broker_oms.order_types import (
    OrderExecutionResult,
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

_SESSION = date(2026, 8, 3)


def _instrument() -> Instrument:
    return Instrument(
        instrument_token=408065, trading_symbol="INFY",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _intent(quantity: int = 10) -> OrderIntent:
    return OrderIntent(
        instrument=_instrument(), side=OrderSide.BUY, quantity=quantity, strategy_tag="orb_v1",
    )


class _FakeBroker:
    """Counts real placements + returns a filled result, so a duplicate send is observable as a call."""

    def __init__(self) -> None:
        self.place_calls = 0

    def place_order(self, intent: OrderIntent) -> OrderExecutionResult:
        self.place_calls += 1
        return OrderExecutionResult(
            broker_order_id=f"BROKER-{self.place_calls}", state=OrderLifecycleState.COMPLETE,
            filled_quantity=intent.quantity, average_fill_price=100.0,
        )


class _RaisingBroker:
    def place_order(self, intent: OrderIntent) -> OrderExecutionResult:
        raise RuntimeError("broker down")


def _placer(tmp_path, broker):
    wal = OrderIntentWriteAheadLog(db_file_path=tmp_path / "wal.sqlite3")
    return CrashSafeOrderPlacer(broker, write_ahead_log=wal, session_date=_SESSION), wal


def test_first_placement_is_sent_and_recorded(tmp_path):
    broker = _FakeBroker()
    placer, wal = _placer(tmp_path, broker)
    outcome = placer.place_order_crash_safe(_intent())
    assert broker.place_calls == 1
    assert not outcome.was_duplicate_suppressed
    assert outcome.result.broker_order_id == "BROKER-1"
    assert wal.state_of(outcome.client_order_id) == "filled"


def test_duplicate_same_intent_is_suppressed_not_resent(tmp_path):
    broker = _FakeBroker()
    placer, _ = _placer(tmp_path, broker)
    first = placer.place_order_crash_safe(_intent())
    second = placer.place_order_crash_safe(_intent())  # identical intent → same client id
    assert broker.place_calls == 1  # the broker was NOT hit a second time
    assert second.was_duplicate_suppressed
    assert second.result.broker_order_id == first.result.broker_order_id  # original id echoed


def test_a_different_intent_is_a_different_order(tmp_path):
    broker = _FakeBroker()
    placer, _ = _placer(tmp_path, broker)
    placer.place_order_crash_safe(_intent(quantity=10))
    placer.place_order_crash_safe(_intent(quantity=25))  # different quantity → different id
    assert broker.place_calls == 2


def test_duplicate_survives_a_simulated_restart(tmp_path):
    # Place, then "crash": a fresh placer + fresh WAL instance on the SAME db must still suppress the resend.
    broker1 = _FakeBroker()
    placer1, _ = _placer(tmp_path, broker1)
    placer1.place_order_crash_safe(_intent())
    assert broker1.place_calls == 1

    broker2 = _FakeBroker()  # new process, new broker connection
    wal2 = OrderIntentWriteAheadLog(db_file_path=tmp_path / "wal.sqlite3")  # reopen same durable log
    placer2 = CrashSafeOrderPlacer(broker2, write_ahead_log=wal2, session_date=_SESSION)
    outcome = placer2.place_order_crash_safe(_intent())
    assert broker2.place_calls == 0  # durable idempotency: the restart does NOT re-place
    assert outcome.was_duplicate_suppressed


def test_broker_failure_is_recorded_and_reraised(tmp_path):
    placer, wal = _placer(tmp_path, _RaisingBroker())
    intent = _intent()
    try:
        placer.place_order_crash_safe(intent)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    # The intent was durably recorded then marked rejected — never a silent loss.
    from nse_algo_trader.broker_oms.idempotent_order_identity import client_order_identity, session_key_for_date
    cid = client_order_identity(intent, session_key_for_date(_SESSION)).full_hex_id
    assert wal.state_of(cid) == "rejected"


def test_reconcile_against_broker_flags_unknown_broker_position(tmp_path):
    placer, _ = _placer(tmp_path, _FakeBroker())
    report = placer.reconcile_against_broker(
        local_positions=[PositionSnapshot(instrument_token=1, net_quantity=100)],
        broker_positions=[
            PositionSnapshot(instrument_token=1, net_quantity=100),   # matched
            PositionSnapshot(instrument_token=2, net_quantity=-50),   # unknown at the broker
        ],
    )
    assert not report.is_clean
    assert len(report.unknown_broker) == 1
    assert report.requires_human_attention  # unknown broker position → ALERT_HUMAN


def test_now_provider_is_injectable(tmp_path):
    broker = _FakeBroker()
    wal = OrderIntentWriteAheadLog(db_file_path=tmp_path / "wal.sqlite3")
    placer = CrashSafeOrderPlacer(
        broker, write_ahead_log=wal, session_date=_SESSION,
        now_provider=lambda: datetime(2026, 8, 3, 10, 0, 0),
    )
    outcome = placer.place_order_crash_safe(_intent())
    assert outcome.result.broker_order_id == "BROKER-1"
