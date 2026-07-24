"""SQLite backend for `ExperienceMemory` (research/43 v1 recommendation).

Embeddable, zero-config, one `.db` file alongside the market store — no new
service dependency. The categorical edges (strategy / mechanism / regime /
instrument-kind / table) are flattened onto the experiment row with indexes,
so the three query patterns are indexed group-by/filters. A real temporal
knowledge graph (Graphiti/Neo4j) is the documented swap-up for multi-hop /
semantic retrieval — it would implement the same `ExperienceMemory` protocol.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from nse_algo_trader.memory_reflection.experience_memory import (
    CalibrationBoardRow,
    CalibrationSummary,
    ClosedExperiment,
    PriorOutcomeSummary,
    ReflectionDiffRow,
)

DEFAULT_EXPERIENCE_MEMORY_DB_PATH = Path(
    "~/.nse_algo_trader/experience_memory.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS experience_nodes (
    experiment_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    session_date TEXT NOT NULL,
    strategy_tag TEXT NOT NULL,
    mechanism_name TEXT NOT NULL,
    regime_context TEXT NOT NULL,
    instrument_token INTEGER NOT NULL,
    instrument_kind TEXT NOT NULL,
    assigned_table TEXT NOT NULL,
    direction TEXT NOT NULL,
    predicted_outcome TEXT NOT NULL,
    win_probability REAL NOT NULL,
    actual_outcome TEXT NOT NULL,
    prediction_was_correct INTEGER NOT NULL,
    brier_contribution REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    realized_return_fraction REAL NOT NULL,
    predicted_exit_cause TEXT NOT NULL,
    actual_exit_cause TEXT NOT NULL,
    kill_criteria TEXT NOT NULL
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_experience_strategy_regime "
    "ON experience_nodes(strategy_tag, regime_context)",
    "CREATE INDEX IF NOT EXISTS idx_experience_prior "
    "ON experience_nodes(strategy_tag, mechanism_name, regime_context, instrument_kind)",
    "CREATE INDEX IF NOT EXISTS idx_experience_occurred "
    "ON experience_nodes(occurred_at)",
)


class SqliteExperienceMemory:
    def __init__(
        self,
        db_file_path: Path = DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
        now_provider=datetime.now,
    ) -> None:
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_file_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(_CREATE_TABLE)
        for index_statement in _INDEXES:
            self._connection.execute(index_statement)
        self._connection.commit()
        self._now_provider = now_provider

    def close(self) -> None:
        self._connection.close()

    def record_closed_experiment(self, experiment: ClosedExperiment) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO experience_nodes VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                experiment.experiment_id,
                experiment.occurred_at.isoformat(),
                self._now_provider().isoformat(),
                experiment.session_date.isoformat(),
                experiment.strategy_tag,
                experiment.mechanism_name,
                experiment.regime_context,
                experiment.instrument_token,
                experiment.instrument_kind,
                experiment.assigned_table,
                experiment.direction,
                experiment.predicted_outcome,
                experiment.win_probability,
                experiment.actual_outcome,
                int(experiment.prediction_was_correct),
                experiment.brier_contribution,
                experiment.realized_pnl,
                experiment.realized_return_fraction,
                experiment.predicted_exit_cause,
                experiment.actual_exit_cause,
                experiment.kill_criteria,
            ),
        )
        self._connection.commit()

    def experiment_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) AS n FROM experience_nodes"
        ).fetchone()["n"]

    def calibration_for(
        self, strategy_tag: str, regime_context: str
    ) -> CalibrationSummary:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n, AVG(prediction_was_correct) AS hit, "
            "AVG(brier_contribution) AS brier, "
            "AVG(realized_return_fraction) AS ret "
            "FROM experience_nodes WHERE strategy_tag=? AND regime_context=?",
            (strategy_tag, regime_context),
        ).fetchone()
        count = row["n"] or 0
        return CalibrationSummary(
            strategy_tag=strategy_tag,
            regime_context=regime_context,
            experiment_count=count,
            hit_rate=row["hit"] if count else None,
            mean_brier=row["brier"] if count else None,
            mean_return_fraction=row["ret"] if count else None,
        )

    def prior_outcomes_for(
        self,
        strategy_tag: str,
        mechanism_name: str,
        regime_context: str,
        instrument_kind: str,
    ) -> PriorOutcomeSummary:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n, "
            "AVG(CASE WHEN actual_outcome='win' THEN 1.0 ELSE 0.0 END) AS wr, "
            "AVG(realized_return_fraction) AS ret, AVG(brier_contribution) AS brier "
            "FROM experience_nodes WHERE strategy_tag=? AND mechanism_name=? "
            "AND regime_context=? AND instrument_kind=?",
            (strategy_tag, mechanism_name, regime_context, instrument_kind),
        ).fetchone()
        count = row["n"] or 0
        return PriorOutcomeSummary(
            experiment_count=count,
            win_rate=row["wr"] if count else None,
            mean_return_fraction=row["ret"] if count else None,
            mean_brier=row["brier"] if count else None,
        )

    def reflection_diff(
        self, recent_window_start: datetime
    ) -> list[ReflectionDiffRow]:
        """Per (strategy × mechanism × regime): metrics for experiments in the
        recent window vs the baseline before it — the nightly reflection
        signal (what got better/worse)."""
        boundary = recent_window_start.isoformat()
        recent = self._aggregate_cohorts("occurred_at >= ?", (boundary,))
        baseline = self._aggregate_cohorts("occurred_at < ?", (boundary,))
        rows: list[ReflectionDiffRow] = []
        for key, r in recent.items():
            b = baseline.get(key)
            hit_delta = (
                r["hit"] - b["hit"] if b is not None and r["hit"] is not None
                and b["hit"] is not None else None
            )
            rows.append(
                ReflectionDiffRow(
                    strategy_tag=key[0], mechanism_name=key[1], regime_context=key[2],
                    recent_count=r["n"], baseline_count=b["n"] if b else 0,
                    recent_hit_rate=r["hit"],
                    baseline_hit_rate=b["hit"] if b else None,
                    hit_rate_delta=hit_delta,
                    recent_mean_brier=r["brier"],
                    baseline_mean_brier=b["brier"] if b else None,
                )
            )
        rows.sort(key=lambda row: (row.hit_rate_delta is None, row.hit_rate_delta or 0))
        return rows

    def calibration_board(
        self,
        minimum_experiments: int = 1,
        limit: int = 20,
        recency_window: int | None = None,
    ) -> list[CalibrationBoardRow]:
        """Per (strategy × mechanism): predicted vs actual win-rate + Brier —
        the reflection surface. Ordered by the calibration gap (predicted −
        actual) descending, so the most over-confident theses surface first.

        `recency_window` (slice 4): when set, aggregate only each mechanism's
        LAST N experiments (by occurred_at) — so fresh shadow-probe evidence can
        lift a veto (recovery). None = all-time (the Reflection display)."""
        if recency_window is None:
            source = "experience_nodes"
            params: tuple = (minimum_experiments, limit)
        else:
            source = (
                "(SELECT *, ROW_NUMBER() OVER (PARTITION BY mechanism_name "
                "ORDER BY occurred_at DESC) AS rn FROM experience_nodes) "
                "WHERE rn <= ?"
            )
            params = (recency_window, minimum_experiments, limit)
        cursor = self._connection.execute(
            "SELECT strategy_tag, mechanism_name, COUNT(*) AS n, "
            "AVG(win_probability) AS pred, "
            "AVG(CASE WHEN actual_outcome='win' THEN 1.0 ELSE 0.0 END) AS act, "
            "AVG(brier_contribution) AS brier, "
            "AVG(realized_return_fraction) AS ret "
            f"FROM {source} GROUP BY strategy_tag, mechanism_name "
            "HAVING n >= ? ORDER BY (pred - act) DESC LIMIT ?",
            params,
        )
        return [
            CalibrationBoardRow(
                strategy_tag=row["strategy_tag"],
                mechanism_name=row["mechanism_name"],
                experiment_count=row["n"],
                predicted_win_rate=row["pred"],
                actual_win_rate=row["act"],
                mean_brier=row["brier"],
                mean_return_fraction=row["ret"],
            )
            for row in cursor.fetchall()
        ]

    def _aggregate_cohorts(self, where_clause: str, params: tuple) -> dict:
        cursor = self._connection.execute(
            "SELECT strategy_tag, mechanism_name, regime_context, COUNT(*) AS n, "
            "AVG(prediction_was_correct) AS hit, AVG(brier_contribution) AS brier "
            f"FROM experience_nodes WHERE {where_clause} "
            "GROUP BY strategy_tag, mechanism_name, regime_context",
            params,
        )
        return {
            (row["strategy_tag"], row["mechanism_name"], row["regime_context"]): {
                "n": row["n"], "hit": row["hit"], "brier": row["brier"],
            }
            for row in cursor.fetchall()
        }
