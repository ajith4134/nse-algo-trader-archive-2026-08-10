"""Layer 10 — Experience Memory: the episodic substrate of Memory & Reflection.

One **closed §9 experiment** (a graded prediction joined to its closed paper
trade) becomes one memory node. Per research/43, the substrate is a swappable
`ExperienceMemory` interface — strategy/reflection code depends on this
protocol, never a concrete backend — so the v1 embeddable SQLite store can be
swapped for a Graphiti/Neo4j temporal knowledge graph later (for the semantic /
multi-hop tier) without a rewrite, exactly as the broker/data layers are
swappable.

The three query patterns this must serve (all categorical filters +
aggregations, NOT multi-hop traversal — which is why SQLite fits v1):
1. calibration-by-regime — hit rate / mean Brier / mean return for a strategy
   in a regime.
2. prior-outcomes (entry-time pre-mortem) — the outcome distribution of past
   experiments matching a signal's (strategy, mechanism, regime, kind).
3. reflection diff — how those metrics moved between two time windows.

The categorical keys (strategy, mechanism, regime, instrument-kind, table) are
the graph's typed edges, flattened onto the node for v1; explicit node/edge
tables (or a real KG) are the documented swap-up when multi-hop traversal is
needed (Rule G named future consumer).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class ClosedExperiment:
    """One memory node: a graded §9 prediction joined to its closed trade."""

    experiment_id: str
    occurred_at: datetime
    session_date: date
    # categorical keys (the typed edges, flattened for v1)
    strategy_tag: str
    mechanism_name: str
    regime_context: str
    instrument_token: int
    instrument_kind: str  # cash_equity | index_option | stock_option
    assigned_table: str  # confident_win | confident_loss | uncertain
    direction: str
    # prediction vs realized outcome
    predicted_outcome: str
    win_probability: float
    actual_outcome: str  # win | loss
    prediction_was_correct: bool
    brier_contribution: float
    realized_pnl: float
    realized_return_fraction: float
    predicted_exit_cause: str
    actual_exit_cause: str
    kill_criteria: str


@dataclass(frozen=True)
class CalibrationSummary:
    strategy_tag: str
    regime_context: str
    experiment_count: int
    hit_rate: float | None  # fraction of predictions that were correct
    mean_brier: float | None
    mean_return_fraction: float | None


@dataclass(frozen=True)
class PriorOutcomeSummary:
    experiment_count: int
    win_rate: float | None  # fraction that actually won
    mean_return_fraction: float | None
    mean_brier: float | None


@dataclass(frozen=True)
class CalibrationBoardRow:
    """One (strategy × mechanism) cohort's calibration: what it PREDICTED vs
    what actually happened — the core reflection surface. A big gap between
    `predicted_win_rate` and `actual_win_rate` is a miscalibrated thesis."""

    strategy_tag: str
    mechanism_name: str
    experiment_count: int
    predicted_win_rate: float  # mean predicted win-probability
    actual_win_rate: float  # fraction that actually won
    mean_brier: float
    mean_return_fraction: float


@dataclass(frozen=True)
class ReflectionDiffRow:
    """How one (strategy × mechanism × regime) cohort moved between a recent
    window and the baseline before it — the nightly reflection signal."""

    strategy_tag: str
    mechanism_name: str
    regime_context: str
    recent_count: int
    baseline_count: int
    recent_hit_rate: float | None
    baseline_hit_rate: float | None
    hit_rate_delta: float | None
    recent_mean_brier: float | None
    baseline_mean_brier: float | None


class ExperienceMemory(Protocol):
    """The swappable substrate boundary (research/43). A SQLite backend today;
    a Graphiti/Neo4j temporal KG is the named future consumer for the
    semantic/multi-hop tier."""

    def record_closed_experiment(self, experiment: ClosedExperiment) -> None: ...

    def experiment_count(self) -> int: ...

    def calibration_for(
        self, strategy_tag: str, regime_context: str
    ) -> CalibrationSummary: ...

    def prior_outcomes_for(
        self,
        strategy_tag: str,
        mechanism_name: str,
        regime_context: str,
        instrument_kind: str,
    ) -> PriorOutcomeSummary: ...

    def reflection_diff(
        self, recent_window_start: datetime
    ) -> list[ReflectionDiffRow]: ...

    def calibration_board(
        self,
        minimum_experiments: int = 1,
        limit: int = 20,
        recency_window: int | None = None,
    ) -> list[CalibrationBoardRow]: ...


def build_closed_experiment(
    graded_prediction,
    closed_trade,
    instrument_kind: str,
) -> ClosedExperiment:
    """Assemble a memory node from a §9 `GradedPrediction` + its
    `ClosedPaperTrade`. Kept free of any backend so it is reused across
    substrates (Rule C names, research/43)."""
    record = graded_prediction.record
    notional = abs(closed_trade.entry_price * closed_trade.quantity)
    return ClosedExperiment(
        experiment_id=(
            f"{record.strategy_tag}:{record.instrument_token}:"
            f"{closed_trade.closed_at.isoformat()}"
        ),
        occurred_at=closed_trade.closed_at,
        session_date=record.session_date,
        strategy_tag=record.strategy_tag,
        mechanism_name=record.mechanism_name,
        regime_context=record.calendar_context,
        instrument_token=record.instrument_token,
        instrument_kind=instrument_kind,
        assigned_table=record.assigned_table.value,
        direction=record.direction.value,
        predicted_outcome=record.predicted_outcome.value,
        win_probability=record.win_probability,
        actual_outcome=graded_prediction.actual_outcome.value,
        prediction_was_correct=graded_prediction.prediction_was_correct,
        brier_contribution=graded_prediction.brier_contribution,
        realized_pnl=closed_trade.realized_pnl,
        realized_return_fraction=(
            closed_trade.realized_pnl / notional if notional > 0 else 0.0
        ),
        predicted_exit_cause=record.predicted_exit_cause,
        actual_exit_cause=closed_trade.outcome.value,
        kill_criteria=record.kill_criteria,
    )
