"""L3 ops floor — the crash-safe order placer that binds the three durability parts into the order path.

Wraps any `BrokerClientProtocol` so that every placement is:
  1. **idempotent** — a deterministic client-order-id (`idempotent_order_identity`) is computed and the
     write-ahead log is probed FIRST; an intent already PLACED/FILLED is NOT sent again (a retry or a
     crash-restart can never double-place);
  2. **durable** — the intent is written to the WAL (`order_intent_write_ahead_log`) BEFORE the broker
     call and its outcome recorded after, so an in-flight order is never lost across a crash;
  3. **reconcilable** — `pending_intents()` + `reconcile_against_broker()` expose the unresolved state and
     the diff vs broker truth on restart.

This lives on the LIVE broker seam only (paper's `SimulatedBrokerClient` cannot crash-lose an order). The
real-data pass — driving this from a live Kite session with real acknowledgements + a real restart
reconciliation — is the one permissible open blocker (Rule K), logged in docs/BACKLOG.md; the engine is
hermetically verified through the broker protocol with a fake (Rule J).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from nse_algo_trader.broker_oms.broker_state_reconciler import (
    PositionSnapshot,
    ReconciliationReport,
    reconcile,
)
from nse_algo_trader.broker_oms.idempotent_order_identity import (
    client_order_identity,
    session_key_for_date,
)
from nse_algo_trader.broker_oms.order_intent_write_ahead_log import (
    OrderIntentWalState,
    OrderIntentWriteAheadLog,
)
from nse_algo_trader.broker_oms.order_types import (
    OrderExecutionResult,
    OrderIntent,
    OrderLifecycleState,
)


@dataclass(frozen=True)
class PlacementOutcome:
    """The result of a crash-safe placement + WHETHER it was actually sent or suppressed as a duplicate."""

    result: OrderExecutionResult
    client_order_id: str
    was_duplicate_suppressed: bool


def _intent_summary(intent: OrderIntent, client_order_id: str) -> dict:
    """A JSON-safe snapshot of the intent for the WAL (audit + restart context), never the live object."""
    instrument = getattr(intent, "instrument", None)
    return {
        "client_order_id": client_order_id,
        "instrument_token": getattr(instrument, "instrument_token", None),
        "trading_symbol": getattr(instrument, "trading_symbol", None),
        "side": getattr(getattr(intent, "side", None), "value", str(getattr(intent, "side", ""))),
        "quantity": getattr(intent, "quantity", None),
        "order_type": getattr(getattr(intent, "order_type", None), "value", None),
        "limit_price": getattr(intent, "limit_price", None),
        "trigger_price": getattr(intent, "trigger_price", None),
        "strategy_tag": getattr(intent, "strategy_tag", None),
    }


class CrashSafeOrderPlacer:
    """Idempotent, durable order placement over any broker client. Same signature shape as the broker so
    it drops into the live execution path; paper keeps using the raw simulated broker."""

    def __init__(
        self,
        broker_client,
        write_ahead_log: OrderIntentWriteAheadLog | None = None,
        session_date: date | None = None,
        now_provider=datetime.now,
    ) -> None:
        self._broker = broker_client
        self._wal = write_ahead_log if write_ahead_log is not None else OrderIntentWriteAheadLog()
        self._now = now_provider
        # session_date scopes the id: the same setup on two days is two orders, a retry within a day is one.
        # None is resolved lazily per placement so a long-running process rolls to the new day correctly.
        self._session_date = session_date
        # In-process echo of results so a same-process duplicate returns the ORIGINAL broker id, not a stub.
        self._results_by_client_id: dict[str, OrderExecutionResult] = {}

    def _session_key(self) -> str:
        return session_key_for_date(self._session_date or self._now().date())

    def place_order_crash_safe(self, intent: OrderIntent) -> PlacementOutcome:
        identity = client_order_identity(intent, self._session_key())
        client_id = identity.full_hex_id
        now_iso = self._now().isoformat()

        prior_state = self._wal.state_of(client_id)
        if prior_state in (OrderIntentWalState.PLACED.value, OrderIntentWalState.FILLED.value):
            # Idempotency: this exact intent was already sent — do NOT place again.
            cached = self._results_by_client_id.get(client_id)
            result = cached if cached is not None else OrderExecutionResult(
                broker_order_id="", state=OrderLifecycleState.OPEN, filled_quantity=0,
                average_fill_price=None,
                rejection_message=f"duplicate suppressed (already {prior_state}); reconcile from broker",
            )
            return PlacementOutcome(result=result, client_order_id=client_id, was_duplicate_suppressed=True)

        # Durability: record the intent BEFORE the broker ever sees it.
        self._wal.record_pending(client_id, _intent_summary(intent, client_id), now_iso)
        try:
            result = self._broker.place_order(intent)
        except Exception as broker_error:  # noqa: BLE001 — record the failure durably, then re-raise
            self._wal.mark_rejected(client_id, f"broker raised: {broker_error!r}", self._now().isoformat())
            raise

        if result.rejection_message:
            self._wal.mark_rejected(client_id, result.rejection_message, self._now().isoformat())
        else:
            self._wal.mark_placed(client_id, result.broker_order_id, self._now().isoformat())
            if result.filled_quantity > 0:
                self._wal.mark_filled(
                    client_id, result.filled_quantity, result.average_fill_price or 0.0,
                    self._now().isoformat(),
                )
        self._results_by_client_id[client_id] = result
        return PlacementOutcome(result=result, client_order_id=client_id, was_duplicate_suppressed=False)

    def place_order(self, intent: OrderIntent) -> OrderExecutionResult:
        """Broker-protocol-compatible entry point (returns just the result), for drop-in on the live seam."""
        return self.place_order_crash_safe(intent).result

    def pending_intents(self) -> list[dict]:
        """Intents still PENDING/PLACED (not terminal) — what a restart must reconcile."""
        return self._wal.pending_intents()

    def reconcile_against_broker(
        self, local_positions: list[PositionSnapshot], broker_positions: list[PositionSnapshot]
    ) -> ReconciliationReport:
        """On restart: diff the bot's belief vs broker truth, carrying the WAL's unresolved intents."""
        pending_ids = [row.get("client_order_id", "") for row in self._wal.pending_intents()]
        return reconcile(local_positions, broker_positions, pending_intent_ids=pending_ids)

    def wal_summary(self) -> dict:
        """WAL counts per state (for the dashboard surface, Rule N)."""
        return self._wal.summary()
