"""Assembles the complete dashboard state — the read-model over the engine.

The dashboard OBSERVES; it never trades. This builds one JSON-serializable
`DashboardSnapshot` from (a) the static project data (layer roadmap,
concept tree) and (b) live engine objects (the paper ledger, the §9
prediction scoreboard). The FastAPI layer just serves what this returns,
so the read-model stays pure and testable against real engine state.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime

from nse_algo_trader.dashboard.project_status_data import (
    CONCEPT_TREE,
    LAYER_ROADMAP,
)
from nse_algo_trader.dashboard.monitoring_alerts import generate_dashboard_alerts
from nse_algo_trader.dashboard.trading_control_config import TradingControlConfig
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import (
    PredictionLabeledTable,
    PredictionTableScoreboard,
)


@dataclass(frozen=True)
class PaperTradingSummary:
    starting_virtual_cash: float
    realized_pnl: float
    fill_count: int
    is_flat: bool


@dataclass(frozen=True)
class PredictionTableSummary:
    table: str
    trade_count: int
    prediction_hit_rate: float | None
    mean_win_probability: float | None
    actual_win_rate: float | None
    brier_score: float | None
    mean_logarithmic_score: float | None = None


@dataclass(frozen=True)
class OpenPositionSummary:
    trading_symbol: str
    direction: str
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    last_price: float | None
    unrealized_pnl: float | None
    assigned_table: str
    segment: str = "cash"


@dataclass(frozen=True)
class LiveUniverseStatus:
    is_market_open: bool
    cash_universe_size: int
    seeded_count: int
    open_position_count: int
    closed_trade_count: int
    last_pass_at: str | None


@dataclass(frozen=True)
class StrategyReadinessSummary:
    """Per-strategy Deflated-Sharpe/CPCV promotion-gate verdict (research/41
    wiring). Informational in paper mode — a statistical readiness signal, not
    a live-capital gate yet."""

    strategy: str
    trade_count: int
    per_trade_sharpe_ratio: float | None
    deflated_sharpe_ratio: float | None
    outcome: str
    promoted: bool


@dataclass(frozen=True)
class ConceptTreeCounts:
    trunk_count: int
    total_branch_count: int


@dataclass(frozen=True)
class DashboardSnapshot:
    generated_at: str
    control_config: dict
    alerts: list[dict]
    layer_roadmap: list[dict]
    concept_tree: list[dict]
    concept_tree_counts: ConceptTreeCounts
    paper_trading: PaperTradingSummary
    prediction_tables: list[PredictionTableSummary]
    confident_win_beats_confident_loss: bool | None
    open_positions: list[OpenPositionSummary]
    live_universe_status: LiveUniverseStatus | None
    segment_boards: list[dict] = field(default_factory=list)
    closed_trades: list[dict] = field(default_factory=list)
    combined_realized_pnl: float = 0.0
    strategy_readiness: list[StrategyReadinessSummary] = field(default_factory=list)
    memory_experiment_count: int = 0
    reflection_board: list[dict] = field(default_factory=list)
    assumption_tripwires: list[dict] = field(default_factory=list)
    vetoed_mechanism_count: int = 0
    vetoed_entry_count: int = 0
    shadow_entry_count: int = 0
    opponent_ledger: dict | None = None
    positioning_deferred_count: int = 0
    information_diet: dict | None = None
    experiment_count_by_provenance: dict | None = None
    prequential_forecast_score: dict | None = None
    feature_surfaces: list[dict] = field(default_factory=list)  # task #13 (Rule N)

    def to_json_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "control_config": self.control_config,
            "alerts": self.alerts,
            "layer_roadmap": self.layer_roadmap,
            "concept_tree": self.concept_tree,
            "concept_tree_counts": asdict(self.concept_tree_counts),
            "paper_trading": asdict(self.paper_trading),
            "prediction_tables": [asdict(t) for t in self.prediction_tables],
            "confident_win_beats_confident_loss": (
                self.confident_win_beats_confident_loss
            ),
            "open_positions": [asdict(p) for p in self.open_positions],
            "live_universe_status": (
                asdict(self.live_universe_status)
                if self.live_universe_status is not None
                else None
            ),
            "segment_boards": self.segment_boards,
            "closed_trades": self.closed_trades,
            "combined_realized_pnl": self.combined_realized_pnl,
            "strategy_readiness": [asdict(r) for r in self.strategy_readiness],
            "memory_experiment_count": self.memory_experiment_count,
            "reflection_board": self.reflection_board,
            "assumption_tripwires": self.assumption_tripwires,
            "vetoed_mechanism_count": self.vetoed_mechanism_count,
            "vetoed_entry_count": self.vetoed_entry_count,
            "shadow_entry_count": self.shadow_entry_count,
            "opponent_ledger": self.opponent_ledger,
            "positioning_deferred_count": self.positioning_deferred_count,
            "information_diet": self.information_diet,
            "experiment_count_by_provenance": self.experiment_count_by_provenance,
            "prequential_forecast_score": self.prequential_forecast_score,
            "feature_surfaces": self.feature_surfaces,
        }


def build_dashboard_snapshot(
    control_config: TradingControlConfig,
    paper_ledger: PaperTradingLedger,
    prediction_scoreboard: PredictionTableScoreboard,
    generated_at: datetime,
    kite_access_token_valid: bool = True,
    stored_bar_count: int = 1,
    open_positions: list[OpenPositionSummary] | None = None,
    live_universe_status: LiveUniverseStatus | None = None,
    precomputed_paper_trading: PaperTradingSummary | None = None,
    precomputed_prediction_tables: list[PredictionTableSummary] | None = None,
    precomputed_confident_win_beats_confident_loss: bool | None = None,
    segment_boards: list[dict] | None = None,
    closed_trades: list[dict] | None = None,
    combined_realized_pnl: float = 0.0,
    strategy_readiness: list[StrategyReadinessSummary] | None = None,
    memory_experiment_count: int = 0,
    reflection_board: list[dict] | None = None,
    assumption_tripwires: list[dict] | None = None,
    vetoed_mechanism_count: int = 0,
    vetoed_entry_count: int = 0,
    shadow_entry_count: int = 0,
    opponent_ledger: dict | None = None,
    positioning_deferred_count: int = 0,
    information_diet: dict | None = None,
    experiment_count_by_provenance: dict | None = None,
    prequential_forecast_score: dict | None = None,
    feature_surfaces: list[dict] | None = None,
) -> DashboardSnapshot:
    """When `precomputed_*` summaries are supplied (by the live service's
    writer thread, which is the sole mutator of the ledger/scoreboard),
    they are used verbatim — the request thread never reads the mutating
    ledger/scoreboard objects, so there is no dictionary-changed-size race."""
    layer_roadmap = [
        {
            "number": layer.number,
            "name": layer.name,
            "status": layer.status.value,
            "note": layer.note,
        }
        for layer in LAYER_ROADMAP
    ]
    concept_tree = [
        {
            "roman_number": trunk.roman_number,
            "name": trunk.name,
            "essence": trunk.essence,
            "ignition": trunk.ignition.value,
            "is_gated": trunk.is_gated,
            "branch_count": trunk.branch_count,
            "branch_names": list(trunk.branch_names),
        }
        for trunk in CONCEPT_TREE
    ]
    concept_tree_counts = ConceptTreeCounts(
        trunk_count=len(CONCEPT_TREE),
        total_branch_count=sum(trunk.branch_count for trunk in CONCEPT_TREE),
    )
    if precomputed_paper_trading is not None:
        paper_trading = precomputed_paper_trading
    elif paper_ledger is not None:
        paper_trading = PaperTradingSummary(
            starting_virtual_cash=paper_ledger.starting_virtual_cash,
            realized_pnl=paper_ledger.realized_pnl,
            fill_count=len(paper_ledger.recorded_fills),
            is_flat=paper_ledger.is_flat(),
        )
    else:  # service present but first pass not yet published
        paper_trading = PaperTradingSummary(0.0, 0.0, 0, is_flat=True)
    if precomputed_prediction_tables is not None:
        prediction_tables = precomputed_prediction_tables
    elif prediction_scoreboard is not None:
        prediction_tables = [
            _summarize_table(prediction_scoreboard, table)
            for table in PredictionLabeledTable
        ]
    else:
        prediction_tables = [
            PredictionTableSummary(t.value, 0, None, None, None, None)
            for t in PredictionLabeledTable
        ]
    confident_win_beats_confident_loss = (
        precomputed_confident_win_beats_confident_loss
        if precomputed_prediction_tables is not None
        else prediction_scoreboard.confident_win_beats_confident_loss()
    )
    alerts = [
        {"level": a.level.value, "category": a.category, "message": a.message}
        for a in generate_dashboard_alerts(
            control_config, paper_trading, prediction_tables,
            kite_access_token_valid, stored_bar_count,
            generated_at=generated_at,
            open_position_count=(
                live_universe_status.open_position_count
                if live_universe_status is not None
                else 0
            ),
            assumption_tripwires=assumption_tripwires or [],
            information_diet=information_diet,
        )
    ]
    return DashboardSnapshot(
        generated_at=generated_at.isoformat(),
        control_config=control_config.to_json_dict(),
        alerts=alerts,
        layer_roadmap=layer_roadmap,
        concept_tree=concept_tree,
        concept_tree_counts=concept_tree_counts,
        paper_trading=paper_trading,
        prediction_tables=prediction_tables,
        confident_win_beats_confident_loss=confident_win_beats_confident_loss,
        open_positions=list(open_positions or []),
        live_universe_status=live_universe_status,
        segment_boards=list(segment_boards or []),
        closed_trades=list(closed_trades or []),
        combined_realized_pnl=combined_realized_pnl,
        strategy_readiness=list(strategy_readiness or []),
        memory_experiment_count=memory_experiment_count,
        reflection_board=list(reflection_board or []),
        assumption_tripwires=list(assumption_tripwires or []),
        vetoed_mechanism_count=vetoed_mechanism_count,
        vetoed_entry_count=vetoed_entry_count,
        shadow_entry_count=shadow_entry_count,
        opponent_ledger=opponent_ledger,
        positioning_deferred_count=positioning_deferred_count,
        information_diet=information_diet,
        experiment_count_by_provenance=experiment_count_by_provenance,
        prequential_forecast_score=prequential_forecast_score,
        feature_surfaces=feature_surfaces or [],
    )


def _summarize_table(
    scoreboard: PredictionTableScoreboard, table: PredictionLabeledTable
) -> PredictionTableSummary:
    score = scoreboard.score_for_table(table)
    if score is None:
        return PredictionTableSummary(table.value, 0, None, None, None, None)
    return PredictionTableSummary(
        table=table.value,
        trade_count=score.prediction_count,
        prediction_hit_rate=score.prediction_hit_rate,
        mean_win_probability=score.mean_win_probability,
        actual_win_rate=score.actual_win_rate,
        brier_score=score.brier_score,
        mean_logarithmic_score=score.mean_logarithmic_score,
    )
