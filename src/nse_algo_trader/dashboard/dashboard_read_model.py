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


@dataclass(frozen=True)
class ConceptTreeCounts:
    trunk_count: int
    total_branch_count: int


@dataclass(frozen=True)
class DashboardSnapshot:
    generated_at: str
    control_config: dict
    layer_roadmap: list[dict]
    concept_tree: list[dict]
    concept_tree_counts: ConceptTreeCounts
    paper_trading: PaperTradingSummary
    prediction_tables: list[PredictionTableSummary]
    confident_win_beats_confident_loss: bool | None

    def to_json_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "control_config": self.control_config,
            "layer_roadmap": self.layer_roadmap,
            "concept_tree": self.concept_tree,
            "concept_tree_counts": asdict(self.concept_tree_counts),
            "paper_trading": asdict(self.paper_trading),
            "prediction_tables": [asdict(t) for t in self.prediction_tables],
            "confident_win_beats_confident_loss": (
                self.confident_win_beats_confident_loss
            ),
        }


def build_dashboard_snapshot(
    control_config: TradingControlConfig,
    paper_ledger: PaperTradingLedger,
    prediction_scoreboard: PredictionTableScoreboard,
    generated_at: datetime,
) -> DashboardSnapshot:
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
    paper_trading = PaperTradingSummary(
        starting_virtual_cash=paper_ledger.starting_virtual_cash,
        realized_pnl=paper_ledger.realized_pnl,
        fill_count=len(paper_ledger.recorded_fills),
        is_flat=paper_ledger.is_flat(),
    )
    prediction_tables = [
        _summarize_table(prediction_scoreboard, table)
        for table in PredictionLabeledTable
    ]
    return DashboardSnapshot(
        generated_at=generated_at.isoformat(),
        control_config=control_config.to_json_dict(),
        layer_roadmap=layer_roadmap,
        concept_tree=concept_tree,
        concept_tree_counts=concept_tree_counts,
        paper_trading=paper_trading,
        prediction_tables=prediction_tables,
        confident_win_beats_confident_loss=(
            prediction_scoreboard.confident_win_beats_confident_loss()
        ),
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
    )
