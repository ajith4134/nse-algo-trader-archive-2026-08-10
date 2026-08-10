"""Order-intent write-ahead log (WAL) — the durability spine of the L3 ops floor.

Every order intent is persisted to durable SQLite storage in state ``PENDING``
*before* the broker call is made, and its outcome (``PLACED`` / ``FILLED`` /
``REJECTED``) is recorded *after*. A crash or restart between the write and the
broker acknowledgement therefore never (a) loses an in-flight order — the row
survives and a restart can reconcile it — nor (b) double-sends one — the
deterministic ``client_order_id`` is already on disk, so ``state_of`` reports it
as seen and the placement is skipped.

Design (see ``docs/research/168``): this is a small *durable state machine*, not
an event-sourcing framework. The sourcing sweep (top of this module's design
note) rejected the event-sourcing / outbox libraries as wrong-shape and far
heavier than one embedded SQLite file needs. It follows the repo's SQLite store
convention (``sqlite_experience_memory.py``): a ``~/.nse_algo_trader/`` default
path (injectable for tests), WAL journal mode, a long-lived thread-safe
connection with short committed writes, and — critically for a component that
sits directly on the trading loop — it NEVER raises on a write. A WAL that
crashes the trading loop defeats its own purpose. But a *failed* write is not
swallowed silently (Rule O): it is logged and counted, and the count is surfaced
on ``summary()`` so the operator sees a degraded WAL.

State machine, keyed by ``client_order_id`` (a plain deterministic id supplied by
the caller — this module does not compute or import it):

    (unseen) --record_pending--> PENDING --mark_placed--> PLACED
                                    |                        |
                                    +------ mark_filled ------+--> FILLED   (terminal)
                                    |                        |
                                    +------ mark_rejected ----+--> REJECTED (terminal)

Monotonic by rank (PENDING < PLACED < {FILLED, REJECTED}): a transition only ever
advances the row, never regresses it. So a duplicate ``record_pending`` for an id
already ``PLACED``/``FILLED`` is a NO-OP that does not clobber the later state
(that is exactly how a duplicate send attempt is *detected* rather than losing
history), a late ``mark_placed`` arriving after a ``FILLED`` is ignored, and a
``mark_*`` for an id never recorded is a counted, logged no-op — never a crash.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_ORDER_INTENT_WAL_DB_PATH = Path(
    "~/.nse_algo_trader/order_intent_wal.sqlite3"
).expanduser()


class OrderIntentWalState(str, Enum):
    """The durable lifecycle states of a single order intent in the WAL.

    Written BEFORE the broker call (``PENDING``) and advanced by the outcome
    reported AFTER it. ``FILLED`` and ``REJECTED`` are terminal.
    """

    PENDING = "pending"  # persisted before the broker call; not yet acknowledged
    PLACED = "placed"  # broker accepted it and returned a broker_order_id
    FILLED = "filled"  # fully executed (terminal)
    REJECTED = "rejected"  # broker/exchange refused it (terminal)


# Monotonic advancement rank. A transition applies only when it strictly
# increases this rank, which is what makes every mark_* idempotent and
# regression-proof. FILLED and REJECTED share the top rank: both are terminal,
# so neither can overwrite the other or be reopened.
_STATE_RANK: dict[str, int] = {
    OrderIntentWalState.PENDING.value: 1,
    OrderIntentWalState.PLACED.value: 2,
    OrderIntentWalState.FILLED.value: 3,
    OrderIntentWalState.REJECTED.value: 3,
}

_NON_TERMINAL_STATES: tuple[str, ...] = (
    OrderIntentWalState.PENDING.value,
    OrderIntentWalState.PLACED.value,
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS order_intent_wal (
    client_order_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    intent_summary_json TEXT NOT NULL,
    broker_order_id TEXT,
    filled_quantity INTEGER,
    average_fill_price REAL,
    rejection_reason TEXT,
    recorded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_INDEXES = (
    # The restart-reconciliation query (pending_intents) filters on state; index it.
    "CREATE INDEX IF NOT EXISTS idx_order_intent_wal_state "
    "ON order_intent_wal(state)",
)


class OrderIntentWriteAheadLog:
    """SQLite-backed durable state machine for order intents (see module docstring).

    Thread-safe: reached from both the trading thread (record/mark) and a
    reconciliation/dashboard reader thread. A single ``threading.RLock``
    serialises every read-modify-write so the monotonic-advancement decision and
    its UPDATE are atomic; SQLite's own WAL journal handles durability.
    """

    def __init__(
        self,
        db_file_path: Path = DEFAULT_ORDER_INTENT_WAL_DB_PATH,
        now_provider=datetime.now,
    ) -> None:
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        # Shared across threads (check_same_thread=False) like the experience
        # store; every access is a short, immediately-committed statement guarded
        # by self._lock, which SQLite + WAL serialise safely.
        self._connection = sqlite3.connect(str(db_file_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        # If a concurrent writer holds the file lock, wait rather than raise
        # SQLITE_BUSY — the WAL must never throw at the trading loop.
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(_CREATE_TABLE)
        for index_statement in _INDEXES:
            self._connection.execute(index_statement)
        self._connection.commit()
        self._now_provider = now_provider
        self._lock = threading.RLock()
        # Rule O: writes never raise, but failures are counted + surfaced, never
        # silently swallowed. `mark_*` for an id we never recorded is a real
        # durability anomaly (an outcome for an order the WAL never saw placed) —
        # counted separately so it is visible on the dashboard.
        self._write_failure_count = 0
        self._unknown_id_mark_count = 0

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # -- write path: state machine ------------------------------------------

    def record_pending(
        self, client_order_id: str, intent_summary: dict, now: str
    ) -> None:
        """Persist an intent as ``PENDING`` BEFORE the broker call (the WAL write).

        Idempotent: if the id is already present in ANY state this is a no-op that
        does NOT overwrite a later state — so a duplicate send attempt is detected
        by ``state_of`` (which will report the existing state), never clobbered.
        Uses ``INSERT OR IGNORE`` so the primary-key conflict is resolved on disk
        atomically.
        """
        with self._lock:
            try:
                summary_json = self._encode_intent_summary(intent_summary)
                self._connection.execute(
                    "INSERT OR IGNORE INTO order_intent_wal "
                    "(client_order_id, state, intent_summary_json, "
                    " broker_order_id, filled_quantity, average_fill_price, "
                    " rejection_reason, recorded_at, updated_at) "
                    "VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)",
                    (
                        client_order_id,
                        OrderIntentWalState.PENDING.value,
                        summary_json,
                        now,
                        now,
                    ),
                )
                self._connection.commit()
            except Exception:  # noqa: BLE001 — WAL must never raise at the loop
                self._record_write_failure("record_pending", client_order_id)

    def mark_placed(
        self, client_order_id: str, broker_order_id: str, now: str
    ) -> None:
        """Record that the broker accepted the order → ``PLACED`` (advances PENDING)."""
        self._advance_state(
            client_order_id,
            OrderIntentWalState.PLACED,
            now,
            extra_columns={"broker_order_id": broker_order_id},
        )

    def mark_filled(
        self,
        client_order_id: str,
        filled_quantity: int,
        average_fill_price: float,
        now: str,
    ) -> None:
        """Record a full execution → ``FILLED`` (terminal; advances PENDING/PLACED)."""
        self._advance_state(
            client_order_id,
            OrderIntentWalState.FILLED,
            now,
            extra_columns={
                "filled_quantity": filled_quantity,
                "average_fill_price": average_fill_price,
            },
        )

    def mark_rejected(self, client_order_id: str, reason: str, now: str) -> None:
        """Record a broker/exchange rejection → ``REJECTED`` (terminal)."""
        self._advance_state(
            client_order_id,
            OrderIntentWalState.REJECTED,
            now,
            extra_columns={"rejection_reason": reason},
        )

    def _advance_state(
        self,
        client_order_id: str,
        target_state: OrderIntentWalState,
        now: str,
        extra_columns: dict[str, object],
    ) -> None:
        """Monotonic read-modify-write: apply ``target_state`` only if it strictly
        advances the row's rank. Unknown id → counted no-op. Never raises."""
        with self._lock:
            try:
                current = self._connection.execute(
                    "SELECT state FROM order_intent_wal WHERE client_order_id = ?",
                    (client_order_id,),
                ).fetchone()
                if current is None:
                    # An outcome for an intent the WAL never recorded pending — a
                    # durability anomaly. Surface it (counted), do not fabricate a row.
                    self._unknown_id_mark_count += 1
                    logger.warning(
                        "order_intent_wal: %s for unknown client_order_id=%s "
                        "(never recorded pending) — no-op",
                        target_state.value,
                        client_order_id,
                    )
                    return
                if _STATE_RANK[target_state.value] <= _STATE_RANK[current["state"]]:
                    # Equal or lower rank: no regression, no duplicate downgrade.
                    return
                set_fragments = ["state = ?", "updated_at = ?"]
                parameters: list[object] = [target_state.value, now]
                for column_name, value in extra_columns.items():
                    set_fragments.append(f"{column_name} = ?")
                    parameters.append(value)
                parameters.append(client_order_id)
                self._connection.execute(
                    f"UPDATE order_intent_wal SET {', '.join(set_fragments)} "
                    "WHERE client_order_id = ?",
                    parameters,
                )
                self._connection.commit()
            except Exception:  # noqa: BLE001 — WAL must never raise at the loop
                self._record_write_failure(target_state.value, client_order_id)

    @staticmethod
    def _encode_intent_summary(intent_summary: dict) -> str:
        # default=str keeps a non-JSON-native value (Enum, datetime, Decimal) from
        # ever turning a WAL write into an exception — durability beats fidelity.
        return json.dumps(intent_summary, sort_keys=True, default=str)

    def _record_write_failure(self, operation: str, client_order_id: str) -> None:
        self._write_failure_count += 1
        logger.exception(
            "order_intent_wal: write FAILED during %s for client_order_id=%s "
            "(failure #%d) — swallowed to protect the trading loop, surfaced on summary()",
            operation,
            client_order_id,
            self._write_failure_count,
        )

    # -- read path: idempotency probe + reconciliation + dashboard ----------

    def state_of(self, client_order_id: str) -> str | None:
        """The idempotency probe. ``None`` = never seen → safe to place. Any of
        ``pending``/``placed``/``filled``/``rejected`` = already known → do NOT
        re-place (a terminal state means it is done; a non-terminal one means it is
        already in flight)."""
        with self._lock:
            row = self._connection.execute(
                "SELECT state FROM order_intent_wal WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
        return row["state"] if row is not None else None

    def pending_intents(self) -> list[dict]:
        """Every intent still ``PENDING`` or ``PLACED`` (i.e. non-terminal) — exactly
        what a restart must reconcile/replay: a ``PENDING`` row may or may not have
        reached the broker (query the broker to find out); a ``PLACED`` row was
        accepted but never observed to fill/reject. Newest first."""
        with self._lock:
            cursor = self._connection.execute(
                "SELECT client_order_id, state, intent_summary_json, broker_order_id, "
                "recorded_at, updated_at "
                "FROM order_intent_wal "
                f"WHERE state IN ({', '.join('?' for _ in _NON_TERMINAL_STATES)}) "
                "ORDER BY recorded_at DESC, client_order_id DESC",
                _NON_TERMINAL_STATES,
            )
            rows = cursor.fetchall()
        return [self._row_to_intent_dict(row) for row in rows]

    def _row_to_intent_dict(self, row: sqlite3.Row) -> dict:
        return {
            "client_order_id": row["client_order_id"],
            "state": row["state"],
            "broker_order_id": row["broker_order_id"],
            "recorded_at": row["recorded_at"],
            "updated_at": row["updated_at"],
            "intent_summary": self._decode_intent_summary(row["intent_summary_json"]),
        }

    @staticmethod
    def _decode_intent_summary(intent_summary_json: str) -> dict:
        try:
            decoded = json.loads(intent_summary_json)
        except (ValueError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def summary(self) -> dict:
        """Counts per state + total + degradation counters — the dashboard surface.

        ``write_failure_count`` and ``unknown_id_mark_count`` are non-zero only when
        the WAL is degraded, so they make a silently-struggling durability spine
        visible (Rule O) rather than swallowed.
        """
        with self._lock:
            counts_by_state = {
                row["state"]: row["n"]
                for row in self._connection.execute(
                    "SELECT state, COUNT(*) AS n FROM order_intent_wal GROUP BY state"
                )
            }
            write_failure_count = self._write_failure_count
            unknown_id_mark_count = self._unknown_id_mark_count
        per_state = {
            state.value: counts_by_state.get(state.value, 0)
            for state in OrderIntentWalState
        }
        return {
            "counts_by_state": per_state,
            "total_intents": sum(per_state.values()),
            "pending_reconciliation_count": (
                per_state[OrderIntentWalState.PENDING.value]
                + per_state[OrderIntentWalState.PLACED.value]
            ),
            "write_failure_count": write_failure_count,
            "unknown_id_mark_count": unknown_id_mark_count,
        }
