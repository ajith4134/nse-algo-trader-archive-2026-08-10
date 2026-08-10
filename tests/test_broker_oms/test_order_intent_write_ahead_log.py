"""Tests for the order-intent write-ahead log — the durability spine of the ops floor.

Covers: the state machine (PENDING → PLACED → FILLED / REJECTED), the idempotency
probe, monotonic no-regression under duplicate/late/out-of-order transitions,
crash-simulation persistence across two WAL instances on one db file,
unknown-id no-ops, the dashboard summary, a never-raise-on-write property, and
concurrent writes that must not corrupt the log.
"""

from __future__ import annotations

import threading
from itertools import count
from pathlib import Path

import pytest

from nse_algo_trader.broker_oms.order_intent_write_ahead_log import (
    OrderIntentWalState,
    OrderIntentWriteAheadLog,
)

# A deterministic monotonically-increasing ISO clock so recorded_at/updated_at
# ordering in assertions is stable and independent of wall time.
_CLOCK = count(1)


def _next_now() -> str:
    return f"2026-08-03T09:{next(_CLOCK):02d}:00+05:30"


def _intent_summary(symbol: str = "INFY", side: str = "buy", qty: int = 10) -> dict:
    return {
        "trading_symbol": symbol,
        "side": side,
        "quantity": qty,
        "order_type": "market",
        "strategy_tag": "orb",
    }


@pytest.fixture
def wal(tmp_path: Path) -> OrderIntentWriteAheadLog:
    return OrderIntentWriteAheadLog(db_file_path=tmp_path / "order_intent_wal.sqlite3")


class TestStateMachineHappyPath:
    def test_record_pending_puts_intent_in_pending_state(self, wal):
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.PENDING.value

    def test_full_lifecycle_pending_placed_filled(self, wal):
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        wal.mark_placed("coid-1", broker_order_id="BRK-99", now=_next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.PLACED.value
        wal.mark_filled("coid-1", filled_quantity=10, average_fill_price=101.25, now=_next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.FILLED.value

    def test_pending_can_be_rejected(self, wal):
        wal.record_pending("coid-2", _intent_summary(), _next_now())
        wal.mark_rejected("coid-2", reason="insufficient margin", now=_next_now())
        assert wal.state_of("coid-2") == OrderIntentWalState.REJECTED.value

    def test_mark_filled_directly_from_pending_is_allowed(self, wal):
        # A fill notification can arrive without a separate placed marker.
        wal.record_pending("coid-3", _intent_summary(), _next_now())
        wal.mark_filled("coid-3", filled_quantity=5, average_fill_price=50.0, now=_next_now())
        assert wal.state_of("coid-3") == OrderIntentWalState.FILLED.value

    def test_placed_row_carries_broker_order_id_and_fill_fields(self, wal):
        wal.record_pending("coid-4", _intent_summary(), _next_now())
        wal.mark_placed("coid-4", broker_order_id="BRK-4", now=_next_now())
        [row] = wal.pending_intents()
        assert row["client_order_id"] == "coid-4"
        assert row["broker_order_id"] == "BRK-4"
        assert row["intent_summary"]["trading_symbol"] == "INFY"


class TestIdempotencyProbe:
    def test_state_of_unknown_id_is_none(self, wal):
        assert wal.state_of("never-seen") is None

    def test_duplicate_record_pending_does_not_regress_placed(self, wal):
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        wal.mark_placed("coid-1", broker_order_id="BRK-1", now=_next_now())
        # A duplicate send attempt calls record_pending again — must NOT clobber PLACED.
        wal.record_pending("coid-1", _intent_summary(qty=999), _next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.PLACED.value
        # And the original intent summary is preserved (not overwritten by the dup).
        [row] = wal.pending_intents()
        assert row["intent_summary"]["quantity"] == 10

    def test_duplicate_record_pending_does_not_regress_filled(self, wal):
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        wal.mark_filled("coid-1", filled_quantity=10, average_fill_price=100.0, now=_next_now())
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.FILLED.value


class TestMonotonicNoRegression:
    def test_late_mark_placed_after_filled_is_ignored(self, wal):
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        wal.mark_filled("coid-1", filled_quantity=10, average_fill_price=100.0, now=_next_now())
        wal.mark_placed("coid-1", broker_order_id="BRK-late", now=_next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.FILLED.value

    def test_terminal_state_is_not_reopened_by_the_other_terminal(self, wal):
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        wal.mark_filled("coid-1", filled_quantity=10, average_fill_price=100.0, now=_next_now())
        wal.mark_rejected("coid-1", reason="too late", now=_next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.FILLED.value

    def test_placed_can_still_advance_to_rejected(self, wal):
        # A placed order can be rejected by the exchange after acceptance.
        wal.record_pending("coid-1", _intent_summary(), _next_now())
        wal.mark_placed("coid-1", broker_order_id="BRK-1", now=_next_now())
        wal.mark_rejected("coid-1", reason="exchange reject", now=_next_now())
        assert wal.state_of("coid-1") == OrderIntentWalState.REJECTED.value


class TestUnknownIdMarksAreSafeNoOps:
    def test_mark_placed_on_unknown_id_is_a_no_op(self, wal):
        wal.mark_placed("ghost", broker_order_id="BRK-x", now=_next_now())
        assert wal.state_of("ghost") is None
        assert wal.summary()["unknown_id_mark_count"] == 1

    def test_all_marks_on_unknown_id_are_counted_no_ops(self, wal):
        wal.mark_placed("g1", broker_order_id="x", now=_next_now())
        wal.mark_filled("g2", filled_quantity=1, average_fill_price=1.0, now=_next_now())
        wal.mark_rejected("g3", reason="x", now=_next_now())
        assert wal.summary()["unknown_id_mark_count"] == 3
        assert wal.summary()["total_intents"] == 0


class TestPendingIntentsReconciliationView:
    def test_pending_intents_returns_pending_and_placed_but_not_terminal(self, wal):
        wal.record_pending("still-pending", _intent_summary(), _next_now())
        wal.record_pending("now-placed", _intent_summary(), _next_now())
        wal.mark_placed("now-placed", broker_order_id="BRK-2", now=_next_now())
        wal.record_pending("now-filled", _intent_summary(), _next_now())
        wal.mark_filled("now-filled", filled_quantity=1, average_fill_price=1.0, now=_next_now())
        wal.record_pending("now-rejected", _intent_summary(), _next_now())
        wal.mark_rejected("now-rejected", reason="x", now=_next_now())

        ids = {row["client_order_id"] for row in wal.pending_intents()}
        assert ids == {"still-pending", "now-placed"}

    def test_empty_wal_has_no_pending_intents(self, wal):
        assert wal.pending_intents() == []


class TestCrashSimulationPersistence:
    def test_pending_intent_survives_a_restart(self, tmp_path):
        db_file = tmp_path / "order_intent_wal.sqlite3"
        # Write the intent, then "crash" before the broker ever confirms.
        first = OrderIntentWriteAheadLog(db_file_path=db_file)
        first.record_pending("coid-crash", _intent_summary(), _next_now())
        first.close()

        # Restart: a brand-new instance on the same file must still see it as
        # pending reconciliation — the durability guarantee.
        second = OrderIntentWriteAheadLog(db_file_path=db_file)
        assert second.state_of("coid-crash") == OrderIntentWalState.PENDING.value
        pending_ids = {row["client_order_id"] for row in second.pending_intents()}
        assert "coid-crash" in pending_ids
        second.close()

    def test_terminal_outcome_survives_a_restart_and_is_not_reconciled(self, tmp_path):
        db_file = tmp_path / "order_intent_wal.sqlite3"
        first = OrderIntentWriteAheadLog(db_file_path=db_file)
        first.record_pending("coid-done", _intent_summary(), _next_now())
        first.mark_filled("coid-done", filled_quantity=10, average_fill_price=100.0, now=_next_now())
        first.close()

        second = OrderIntentWriteAheadLog(db_file_path=db_file)
        assert second.state_of("coid-done") == OrderIntentWalState.FILLED.value
        assert second.pending_intents() == []  # terminal → nothing to reconcile
        second.close()

    def test_duplicate_send_is_detected_after_restart(self, tmp_path):
        # The core anti-double-send guarantee across a crash: the id is on disk,
        # so a fresh instance's probe reports it as seen.
        db_file = tmp_path / "order_intent_wal.sqlite3"
        first = OrderIntentWriteAheadLog(db_file_path=db_file)
        first.record_pending("coid-1", _intent_summary(), _next_now())
        first.mark_placed("coid-1", broker_order_id="BRK-1", now=_next_now())
        first.close()

        restarted = OrderIntentWriteAheadLog(db_file_path=db_file)
        # A restart considering a resend must find it and skip placement.
        assert restarted.state_of("coid-1") is not None
        restarted.close()


class TestSummary:
    def test_summary_counts_per_state(self, wal):
        wal.record_pending("a", _intent_summary(), _next_now())
        wal.record_pending("b", _intent_summary(), _next_now())
        wal.mark_placed("b", broker_order_id="BRK-b", now=_next_now())
        wal.record_pending("c", _intent_summary(), _next_now())
        wal.mark_filled("c", filled_quantity=1, average_fill_price=1.0, now=_next_now())
        wal.record_pending("d", _intent_summary(), _next_now())
        wal.mark_rejected("d", reason="x", now=_next_now())

        summary = wal.summary()
        assert summary["counts_by_state"] == {
            OrderIntentWalState.PENDING.value: 1,
            OrderIntentWalState.PLACED.value: 1,
            OrderIntentWalState.FILLED.value: 1,
            OrderIntentWalState.REJECTED.value: 1,
        }
        assert summary["total_intents"] == 4
        assert summary["pending_reconciliation_count"] == 2  # pending + placed
        assert summary["write_failure_count"] == 0
        assert summary["unknown_id_mark_count"] == 0

    def test_summary_on_empty_wal_is_all_zero(self, wal):
        summary = wal.summary()
        assert summary["total_intents"] == 0
        assert all(v == 0 for v in summary["counts_by_state"].values())


class TestNeverRaisesOnWrite:
    def test_write_failure_is_counted_not_raised(self, tmp_path):
        import sqlite3

        wal = OrderIntentWriteAheadLog(db_file_path=tmp_path / "wal.sqlite3")
        real_connection = wal._connection

        class RaisingConnection:
            """Stub whose every statement fails, simulating a disk/db error mid-write."""

            def execute(self, *_args, **_kwargs):
                raise sqlite3.OperationalError("simulated disk failure")

            def commit(self):
                raise sqlite3.OperationalError("simulated disk failure")

        # The WAL must swallow-and-count, never raise at the trading loop (Rule O).
        wal._connection = RaisingConnection()  # type: ignore[assignment]
        wal.record_pending("coid-1", _intent_summary(), _next_now())  # must not raise
        wal._connection = real_connection

        assert wal.summary()["write_failure_count"] == 1
        # The failed write left no phantom row.
        assert wal.state_of("coid-1") is None

    def test_record_pending_never_raises_on_encode_failure(self, wal):
        # A summary that json can't natively encode must not turn a WAL write into
        # an exception (default=str handles it); the row is still written.
        class Unserializable:
            def __repr__(self) -> str:
                return "Unserializable()"

        wal.record_pending("coid-weird", {"obj": Unserializable()}, _next_now())
        assert wal.state_of("coid-weird") == OrderIntentWalState.PENDING.value


class TestConcurrentWritesDoNotCorrupt:
    def test_many_threads_recording_and_marking(self, wal):
        intent_count = 200

        def worker(index: int) -> None:
            coid = f"coid-{index}"
            wal.record_pending(coid, _intent_summary(qty=index + 1), f"2026-08-03T10:00:{index % 60:02d}+05:30")
            wal.mark_placed(coid, broker_order_id=f"BRK-{index}", now="2026-08-03T10:01:00+05:30")
            if index % 2 == 0:
                wal.mark_filled(coid, filled_quantity=index + 1, average_fill_price=100.0,
                                now="2026-08-03T10:02:00+05:30")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(intent_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        summary = wal.summary()
        assert summary["total_intents"] == intent_count
        assert summary["write_failure_count"] == 0
        assert summary["unknown_id_mark_count"] == 0
        # Even indices reached FILLED (terminal); odd indices remain PLACED.
        assert summary["counts_by_state"][OrderIntentWalState.FILLED.value] == intent_count // 2
        assert summary["counts_by_state"][OrderIntentWalState.PLACED.value] == intent_count // 2
