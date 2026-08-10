"""Persistent strategy-trial registry — the honest cumulative trial count `N`
that the Deflated Sharpe Ratio needs (PLAN §5; L2 validation engine,
docs/research/166).

The Deflated Sharpe Ratio deflates a strategy's Sharpe against the *number of
independent configurations ever tried* (multiple-testing correction). Computing
that number from only the current tournament batch
(`champion_challenger_orb_evaluator.py:94` — `number_of_trials =
len(all_scorecards)`) is optimistic: it forgets every config tried on previous
days / previous process starts, so the DSR bar is set too low and overfit
configs leak through the promotion gate.

This registry records EVERY (strategy_family, config_hash) trial ever run —
across restarts — in an embeddable SQLite log (mirroring
`memory_reflection/sqlite_experience_memory.py`: one `.db` file under the same
`~/.nse_algo_trader/` directory convention, no service dependency). It answers
two questions the DSR machinery consumes:

* `cumulative_trial_count()` → the honest `N` (distinct configs ever trialed),
* `sharpe_std_across_trials()` → the dispersion of trial Sharpes that
  `estimate_deflated_sharpe_benchmark(sharpe_std_across_trials, N)` scales by.

Dedup is essential: a re-run of an *identical* config is not a new independent
trial. Re-registering the same `config_hash` UPDATES its row rather than adding
a second one, so `N` is not inflated (which would over-deflate the DSR and
reject good strategies).

Instrumentation must never break a trading pass, so `register_trial` never
raises — a failed write is logged and swallowed, and the trading loop proceeds.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
import statistics
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Same directory convention as the experience-memory store (one embeddable
# `.db` alongside it — no new service dependency).
DEFAULT_STRATEGY_TRIAL_REGISTRY_DB_PATH = Path(
    "~/.nse_algo_trader/strategy_trial_registry.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS strategy_trials (
    strategy_family TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    trial_sharpe REAL,
    observation_count INTEGER NOT NULL,
    kept INTEGER NOT NULL,
    provenance TEXT NOT NULL DEFAULT 'live',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (strategy_family, config_hash)
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_strategy_trials_family "
    "ON strategy_trials(strategy_family)",
)

# Non-finite Sharpe (NaN / ±inf) is stored as SQL NULL: the config WAS trialed
# (so it still counts toward the honest `N`), but its Sharpe is unknown and is
# excluded from the std / mean / list reads rather than poisoning them to NaN.
_TRIAL_SHARPE_NULL = None


def stable_config_hash(config: dict[str, Any]) -> str:
    """Deterministic, order-independent SHA-256 hex digest of a config dict.

    Two dicts with the SAME key/value content hash identically regardless of
    insertion order (`{"a": 1, "b": 2}` == `{"b": 2, "a": 1}`), so a re-run of
    an identical configuration dedups to one trial row. Nested dicts are sorted
    recursively via `sort_keys`; non-JSON values fall back to their `repr` so
    hashing never raises on an exotic config value.
    """
    canonical_json = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class StrategyTrialRegistry:
    """SQLite-backed log of every strategy configuration ever trialed.

    Thread-safe: reached from both the trading-pass thread (which registers
    trials) and the promotion-gate reader. A single process-wide lock serialises
    access and every operation uses a short-lived connection (opened, committed,
    closed) exactly like the experience-memory store, so there is no cross-thread
    connection sharing to reason about.
    """

    def __init__(
        self,
        db_file_path: Path = DEFAULT_STRATEGY_TRIAL_REGISTRY_DB_PATH,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._db_file_path = db_file_path
        self._now_provider = now_provider
        self._lock = threading.Lock()
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(_CREATE_TABLE)
                for index_statement in _INDEXES:
                    connection.execute(index_statement)
                connection.commit()
            finally:
                connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._db_file_path))
        connection.row_factory = sqlite3.Row
        return connection

    # ----- write -----------------------------------------------------------

    def register_trial(
        self,
        strategy_family: str,
        config_hash: str,
        trial_sharpe: float,
        observation_count: int,
        kept: bool,
        provenance: str = "live",
        created_at: str | None = None,
    ) -> None:
        """Record (or update) one trial of a configuration. NEVER raises.

        One row per `(strategy_family, config_hash)`. Re-registering the SAME
        `config_hash` UPDATES the existing row (an identical re-run is not a new
        independent trial) — `trial_sharpe`, `observation_count`, `kept` and
        `provenance` are refreshed while the original `created_at` is preserved,
        so the distinct-trial count never inflates.

        Robustness: a non-finite `trial_sharpe` (NaN / ±inf) is stored as NULL
        (the trial still counts, its Sharpe is treated as unknown); a negative
        `observation_count` is clamped to 0. Any storage failure is logged and
        swallowed so a trading pass is never broken by instrumentation.
        """
        try:
            sanitized_sharpe = (
                float(trial_sharpe)
                if math.isfinite(trial_sharpe)
                else _TRIAL_SHARPE_NULL
            )
            sanitized_observation_count = max(0, int(observation_count))
            timestamp = created_at or self._now_provider().isoformat()
            with self._lock:
                connection = self._connect()
                try:
                    connection.execute(
                        "INSERT INTO strategy_trials "
                        "(strategy_family, config_hash, trial_sharpe, "
                        " observation_count, kept, provenance, created_at, "
                        " updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(strategy_family, config_hash) DO UPDATE SET "
                        " trial_sharpe=excluded.trial_sharpe, "
                        " observation_count=excluded.observation_count, "
                        " kept=excluded.kept, "
                        " provenance=excluded.provenance, "
                        " updated_at=excluded.updated_at",
                        (
                            strategy_family,
                            config_hash,
                            sanitized_sharpe,
                            sanitized_observation_count,
                            int(bool(kept)),
                            provenance,
                            timestamp,
                            timestamp,
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()
        except Exception:
            # Instrumentation must not break a trading pass (Rule O: never
            # swallow SILENTLY — this is logged and surfaced).
            _LOGGER.exception(
                "strategy_trial_registry: failed to register trial "
                "family=%s config_hash=%s",
                strategy_family,
                config_hash,
            )

    # ----- read ------------------------------------------------------------

    def cumulative_trial_count(self, strategy_family: str | None = None) -> int:
        """The honest `N`: DISTINCT config trials ever recorded (each row is one
        distinct `(family, config_hash)`), optionally scoped to a family
        (None = all families). This is what feeds the DSR trial count in place
        of the current-batch-only `len(all_scorecards)`.
        """
        where, params = self._family_filter(strategy_family)
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    f"SELECT COUNT(*) AS n FROM strategy_trials{where}", params
                ).fetchone()
            finally:
                connection.close()
        return int(row["n"]) if row is not None else 0

    def all_trial_sharpes(
        self, strategy_family: str | None = None
    ) -> list[float]:
        """Every recorded FINITE trial Sharpe (non-finite ones excluded),
        optionally scoped to a family — the raw dispersion sample the DSR
        benchmark is estimated from."""
        where, params = self._family_filter(strategy_family)
        finite_clause = (
            f"{where} AND trial_sharpe IS NOT NULL"
            if where
            else " WHERE trial_sharpe IS NOT NULL"
        )
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    f"SELECT trial_sharpe FROM strategy_trials{finite_clause}",
                    params,
                ).fetchall()
            finally:
                connection.close()
        return [
            float(row["trial_sharpe"])
            for row in rows
            if row["trial_sharpe"] is not None
            and math.isfinite(row["trial_sharpe"])
        ]

    def sharpe_std_across_trials(
        self, strategy_family: str | None = None
    ) -> float:
        """Population standard deviation of recorded trial Sharpes — the value
        `estimate_deflated_sharpe_benchmark(sharpe_std_across_trials, N)`
        scales the expected-maximum-Sharpe bar by. Returns 0.0 when fewer than
        two finite Sharpes exist (dispersion undefined → no deflation, matching
        the promotion gate's `number_of_trials < 2` guard).
        """
        sharpes = self.all_trial_sharpes(strategy_family)
        if len(sharpes) < 2:
            return 0.0
        return statistics.pstdev(sharpes)

    def trial_summary(
        self, strategy_family: str | None = None
    ) -> dict[str, float]:
        """One-shot dashboard summary of the trial registry (durable, every
        session): distinct-trial `count`, `kept_count`, `discarded_count`,
        `sharpe_std` and `mean_sharpe`. `count` includes trials whose Sharpe was
        non-finite (they were still tried); `sharpe_std` / `mean_sharpe` are over
        the finite Sharpes only, and are 0.0 when there are too few finite
        values.
        """
        where, params = self._family_filter(strategy_family)
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT COUNT(*) AS n, "
                    "SUM(CASE WHEN kept = 1 THEN 1 ELSE 0 END) AS kept_n "
                    f"FROM strategy_trials{where}",
                    params,
                ).fetchone()
            finally:
                connection.close()
        total = int(row["n"]) if row is not None else 0
        kept_count = int(row["kept_n"] or 0) if row is not None else 0
        sharpes = self.all_trial_sharpes(strategy_family)
        return {
            "count": total,
            "kept_count": kept_count,
            "discarded_count": total - kept_count,
            "sharpe_std": (
                statistics.pstdev(sharpes) if len(sharpes) >= 2 else 0.0
            ),
            "mean_sharpe": statistics.fmean(sharpes) if sharpes else 0.0,
        }

    @staticmethod
    def _family_filter(
        strategy_family: str | None,
    ) -> tuple[str, tuple[str, ...]]:
        if strategy_family is None:
            return "", ()
        return " WHERE strategy_family = ?", (strategy_family,)
