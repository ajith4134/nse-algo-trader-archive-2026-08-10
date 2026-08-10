"""Assembles the complete dashboard state — the read-model over the engine.

The dashboard OBSERVES; it never trades. This builds one JSON-serializable
`DashboardSnapshot` from (a) the static project data (layer roadmap,
concept tree) and (b) live engine objects (the paper ledger, the §9
prediction scoreboard). The FastAPI layer just serves what this returns,
so the read-model stays pure and testable against real engine state.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from nse_algo_trader.dashboard.project_status_data import (
    CONCEPT_TREE,
    LAYER_ROADMAP,
    atlas_coverage,
    branch_build_status,
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
    # B23: the best and worst this OPEN trade has looked since it opened (rupees), and the
    # ratcheting profit lock (None until the trail arms). These are the operator-requested
    # max-profit / max-loss columns.
    maximum_favourable_profit: float = 0.0
    maximum_adverse_profit: float = 0.0
    profit_locked: float | None = None


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
    # AI-atlas build coverage (build-to-100% program) — shown on the dashboard concept tree.
    built_branch_count: int = 0
    partial_branch_count: int = 0
    built_pct: float = 0.0


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
    # B25b: structured capture-ratio rows so the dashboard can CHART them. The exit_efficiency
    # surface carries the same numbers only as formatted strings, which cannot be plotted.
    exit_efficiency_rows: list[dict] = field(default_factory=list)
    segment_boards: list[dict] = field(default_factory=list)
    closed_trades: list[dict] = field(default_factory=list)
    combined_realized_pnl: float = 0.0  # B33: GROSS incl. confident_loss probes — kept for continuity
    #: B33: the bot's REAL realized P&L (confident_win + uncertain only); confident_loss probes are
    #: reported separately and scored by prediction accuracy, never summed into real money.
    real_realized_pnl: float = 0.0
    confident_loss_probe_realized_pnl: float = 0.0
    confident_loss_prediction_accuracy: float | None = None
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
    option_entry_reason_counts: dict = field(default_factory=dict)  # B34 task #4
    option_index_entry_outcomes: dict = field(default_factory=dict)  # B34 task #4

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
            "exit_efficiency_rows": self.exit_efficiency_rows,
            "segment_boards": self.segment_boards,
            "closed_trades": self.closed_trades,
            "combined_realized_pnl": self.combined_realized_pnl,
            "real_realized_pnl": self.real_realized_pnl,
            "confident_loss_probe_realized_pnl": self.confident_loss_probe_realized_pnl,
            "confident_loss_prediction_accuracy": self.confident_loss_prediction_accuracy,
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
            "option_entry_reason_counts": self.option_entry_reason_counts,
            "option_index_entry_outcomes": self.option_index_entry_outcomes,
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
    exit_efficiency_rows: list[dict] | None = None,
    segment_boards: list[dict] | None = None,
    closed_trades: list[dict] | None = None,
    combined_realized_pnl: float = 0.0,
    real_realized_pnl: float = 0.0,
    confident_loss_probe_realized_pnl: float = 0.0,
    confident_loss_prediction_accuracy: float | None = None,
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
    option_entry_reason_counts: dict | None = None,
    option_index_entry_outcomes: dict | None = None,
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
            # per-branch build status (build-to-100% program) — the concept-tree chip colours.
            "branches": [
                {"name": b, "status": branch_build_status(b)} for b in trunk.branch_names
            ],
            "built_branch_count": sum(
                1 for b in trunk.branch_names if branch_build_status(b) == "built"
            ),
        }
        for trunk in CONCEPT_TREE
    ]
    _coverage = atlas_coverage()
    concept_tree_counts = ConceptTreeCounts(
        trunk_count=len(CONCEPT_TREE),
        total_branch_count=_coverage["total"],
        built_branch_count=_coverage["built"],
        partial_branch_count=_coverage["partial"],
        built_pct=_coverage["built_pct"],
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
    # The 3 segment-bot pod trades open in the POD (a separate process from the live paper service that
    # publishes these boards), so surface the pod's OPEN OPTION positions into the Index/Stock-Option tables +
    # their open-counts — otherwise the user sees "0 open" though the bots are trading (Rule N visibility).
    _pod_positions, _pod_boards = _with_pod_option_positions(
        list(open_positions or []), list(segment_boards or []))
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
        open_positions=_pod_positions,
        live_universe_status=live_universe_status,
        exit_efficiency_rows=list(exit_efficiency_rows or []),
        segment_boards=_pod_boards,
        closed_trades=list(closed_trades or []),
        combined_realized_pnl=combined_realized_pnl,
        real_realized_pnl=real_realized_pnl,
        confident_loss_probe_realized_pnl=confident_loss_probe_realized_pnl,
        confident_loss_prediction_accuracy=confident_loss_prediction_accuracy,
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
        feature_surfaces=_with_segment_bot_surfaces(feature_surfaces or []),
        option_entry_reason_counts=option_entry_reason_counts or {},
        option_index_entry_outcomes=option_index_entry_outcomes or {},
    )


def _with_segment_bot_surfaces(feature_surfaces: list[dict]) -> list[dict]:
    """Append the 3 segment bots + 2 directional AI surfaces (measured from code + disk, Rule N/R).

    These run in the pod, not the dashboard's live service, so they are probed here — always-on, with or
    without live auth. Robust by construction: a probe failure never breaks the snapshot (Rule O).
    """
    try:
        from nse_algo_trader.dashboard.segment_bot_surface_prober import probe_segment_bot_surfaces

        # The live service only emits "not yet surfaced" placeholders for the bot keys (it doesn't hold the
        # pod), so the prober is authoritative for those keys — it REPLACES the placeholder in place, keeping
        # manifest order, and any bot key not already present (the no-live path) is appended.
        probed = {s.key: s.to_json_dict() for s in probe_segment_bot_surfaces()}
        merged = [probed.pop(str(s.get("key")), s) for s in feature_surfaces]
        merged.extend(probed.values())
        return merged
    except Exception:  # noqa: BLE001 — surfacing must never take down the whole dashboard snapshot
        import logging

        logging.getLogger(__name__).exception("segment-bot surface probe failed")
        return feature_surfaces


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _expiry_label(iso: str) -> str:
    """2026-08-06 → '06Aug' for a compact real-contract label."""
    try:
        y, m, d = str(iso)[:10].split("-")
        return f"{int(d):02d}{_MONTHS[int(m) - 1]}"
    except (ValueError, IndexError):
        return ""


def _pod_option_rows(r: dict, seg: str) -> list:
    """Expand a pod option position into ONE ROW PER REAL LEG (strike · CE/PE · expiry · live premium).

    So the Option-Index / Option-Stocks tables show the actual contracts the bot is trading (e.g.
    'NIFTY 06Aug 24500CE  SELL  entry 34.5  LTP 28.0'), not just the underlying. A position with no synthesized
    legs (a directional single leg / cash) falls back to one underlying row.
    """
    underlying = str(r.get("underlying", "?"))
    legs = r.get("legs") or []
    exp = _expiry_label(r.get("expiry", ""))
    qty = int(r.get("quantity", 0))
    # the "Table" badge on a pod option row carries no §9 confidence table (that concept is cash/live-only) —
    # so repurpose it to show WHICH PROFIT ENGINE's edge this trade is on (Θ/Δ/ν/Γ/RV): the inline evidence.
    raw_feats = r.get("features")
    feats = raw_feats if isinstance(raw_feats, dict) else {}
    engine_badge = f"engine_{feats.get('engine')}" if feats.get("engine") else "uncertain"
    if not legs:
        return [OpenPositionSummary(
            trading_symbol=underlying, direction=str(r.get("side", "neutral")), quantity=qty,
            entry_price=round(float(r.get("entry_price", 0.0)), 2),
            stop_loss_price=round(float(r.get("stop_price", 0.0)), 2),
            target_price=round(float(r.get("target_price", 0.0)), 2),
            last_price=r.get("last_mark"), unrealized_pnl=r.get("unrealized_pnl"),
            assigned_table=engine_badge, segment=seg,
            maximum_favourable_profit=float(r.get("max_favourable", 0.0) or 0.0),
            maximum_adverse_profit=float(r.get("max_adverse", 0.0) or 0.0))]
    rows = []
    for leg in legs:
        strike = int(float(leg.get("strike", 0)))
        right = str(leg.get("right", ""))
        side = str(leg.get("side", ""))
        entry = round(float(leg.get("entry_price", 0.0)), 2)
        cur = leg.get("current_price")
        # buy leg reads BUY, sell reads SELL in the table (renderer maps long→BUY / short→SELL)
        rows.append(OpenPositionSummary(
            trading_symbol=f"{underlying} {exp} {strike}{right}".strip(),
            direction="long" if side == "buy" else "short",
            quantity=qty,
            entry_price=entry,
            stop_loss_price=0.0,
            target_price=0.0,
            last_price=(round(float(cur), 2) if cur is not None else None),
            unrealized_pnl=(round((entry - float(cur)) * (1 if side == "sell" else -1) * max(qty, 1), 2)
                            if cur is not None else None),
            assigned_table=engine_badge,  # profit-engine badge (Θ/Δ/ν/Γ/RV) — which edge this leg's trade is on
            segment=seg))
    return rows


def _with_pod_option_positions(
    open_positions: list, segment_boards: list[dict]
) -> tuple[list, list[dict]]:
    """Merge the segment-bot pod's OPEN option positions into the Index/Stock-Option tables + open-counts.

    The pod (3 AI bots) trades in a different process from the live paper service that fills these boards, so
    without this the Option-Index / Option-Stocks tables read "0 open" while the bots are actually trading.
    Robust: a read failure never breaks the snapshot (Rule O).
    """
    try:
        from pathlib import Path

        store = Path.home() / ".nse_algo_trader" / "segment_bot_pod" / "lifecycle" / "pod_open_positions.json"
        if not store.exists():
            return open_positions, segment_boards
        rows = json.loads(store.read_text())
        option_rows = [r for r in rows if r.get("segment") in ("index_option", "stock_option")]
        if not option_rows:
            return open_positions, segment_boards

        positions = list(open_positions)
        counts: dict[str, int] = {}
        for r in option_rows:
            seg = r["segment"]
            counts[seg] = counts.get(seg, 0) + 1
            positions.extend(_pod_option_rows(r, seg))  # per-leg rows: real contracts (strike/CE-PE/expiry)

        boards = [dict(b) for b in segment_boards]
        seen = {b.get("segment") for b in boards}
        for board in boards:
            seg = board.get("segment")
            if seg in counts:
                board["open_count"] = int(board.get("open_count", 0)) + counts[seg]
        for seg, n in counts.items():
            if seg not in seen:
                boards.append({"segment": seg, "open_count": n, "unrealized_pnl": 0.0, "realised_fees": 0.0})
        return positions, boards
    except Exception:  # noqa: BLE001 — surfacing must never take down the snapshot
        import logging

        logging.getLogger(__name__).exception("pod option-position surfacing failed")
        return open_positions, segment_boards


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
