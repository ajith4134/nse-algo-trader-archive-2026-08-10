"""Always-on background service that runs the live universe paper loop.

The dashboard OBSERVES this; it does not drive it. A single writer thread
advances `run_live_universe_scan_pass` continuously during market hours —
seeding more of the universe each pass and managing open positions on live
prices — and after each pass publishes an immutable snapshot of the current
open positions + scoreboard. The dashboard reads only that published
snapshot, so the slow historical-seeding pass never blocks a page load, and
there is exactly one mutator of the loop state (no read/write races).

Paper only: simulated fills, virtual capital (PLAN §1.4). When the market is
closed the loop idles here (replay-when-closed is a later slice); live
real-money trading is a separate, market-gated consumer, not this service.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, UTC
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.config_enforced_paper_run import (
    is_orb_cash_trading_enabled,
    map_control_config_to_risk_budget,
)
from nse_algo_trader.dashboard.dashboard_read_model import (
    PaperTradingSummary,
    PredictionTableSummary,
    StrategyReadinessSummary,
)
from nse_algo_trader.memory_reflection import (
    SqliteExperienceMemory,
    build_closed_experiment,
)
from nse_algo_trader.paper_trading.combinatorial_purged_cross_validation import (
    CpcvConfig,
    evaluate_strategy_with_cpcv_gate,
)
from nse_algo_trader.paper_trading.strategy_promotion_gate import (
    StrategyPromotionConfig,
)
from nse_algo_trader.dashboard.trading_control_config import (
    TradableSegment,
    load_trading_control_config,
)
from nse_algo_trader.market_data import KiteLiveUniverseFeed, MarketDataSqliteStore
from nse_algo_trader.paper_trading import (
    LiveUniversePaperState,
    PaperTradingLedger,
    run_live_universe_scan_pass,
)
from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock
from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
    advance_option_credit_spread_pass,
)
from nse_algo_trader.risk_management import compose_size_down_multipliers
from nse_algo_trader.session_management import IntradaySquareOffSchedule
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictionLabeledTable,
)
from nse_algo_trader.universe_registry import fetch_live_tradable_universe

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class OpenPositionView:
    trading_symbol: str
    direction: str
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    last_price: float | None
    unrealized_pnl: float | None
    assigned_table: str
    segment: str = "cash"  # cash | index_option | stock_option
    # B23: the best and worst this OPEN trade has looked since it opened (rupees), plus the
    # ratcheting profit lock. `profit_locked` is None until the trail arms.
    maximum_favourable_profit: float = 0.0
    maximum_adverse_profit: float = 0.0
    profit_locked: float | None = None


@dataclass(frozen=True)
class SegmentBoard:
    segment: str
    open_count: int
    unrealized_pnl: float
    #: B28: real brokerage+taxes already PAID on this segment's closed trades (rupees).
    realised_fees: float = 0.0


@dataclass(frozen=True)
class ClosedTradeView:
    segment: str
    trading_symbol: str
    direction: str
    realized_pnl: float           # GROSS — fees are NOT deducted here
    outcome: str
    closed_at: str
    provenance: str = "live"  # research/93: live session vs 24/7 replay
    #: B28: round-trip cost of THIS trade. Net P&L = realized_pnl - total_fees.
    total_fees: float = 0.0
    #: B33: which §9 table this trade opened under (confident_win | confident_loss | uncertain), so
    #: a deliberate confident_loss learning probe is never misread on the panel as a real loss.
    assigned_table: str = "uncertain"


@dataclass(frozen=True)
class LivePaperPublishedSnapshot:
    open_positions: tuple[OpenPositionView, ...]
    closed_trade_count: int
    cash_universe_size: int
    seeded_count: int
    last_pass_at: str | None
    is_market_open: bool
    # Summaries computed in the writer thread (sole mutator) so request
    # threads never read the mutating ledger/scoreboard — no race.
    paper_trading_summary: PaperTradingSummary | None = None
    prediction_table_summaries: tuple[PredictionTableSummary, ...] = ()
    confident_win_beats_confident_loss: bool | None = None
    segment_boards: tuple[SegmentBoard, ...] = ()
    recent_closed_trades: tuple[ClosedTradeView, ...] = ()
    combined_realized_pnl: float = 0.0
    #: B33: the bot's REAL realized P&L = confident_win + uncertain only (confident_loss probes
    #: excluded); the confident_loss probe P&L is reported separately with an INVERTED reading
    #: (a probe that LOST = the loss-prediction was RIGHT), scored by `confident_loss_prediction_accuracy`.
    real_realized_pnl: float = 0.0
    confident_loss_probe_realized_pnl: float = 0.0
    confident_loss_prediction_accuracy: float | None = None
    strategy_readiness: tuple[StrategyReadinessSummary, ...] = ()
    memory_experiment_count: int = 0
    calibration_board: tuple = ()  # tuple[CalibrationBoardRow, ...]
    assumption_verdicts: tuple = ()  # tuple[AssumptionVerdict, ...]
    vetoed_mechanism_count: int = 0
    vetoed_entry_count: int = 0
    shadow_entry_count: int = 0
    opponent_ledger: dict | None = None  # OpponentLedgerReading as a dict
    positioning_deferred_count: int = 0
    information_diet: dict | None = None  # InformationDiet as a dict
    # §53 slice 3a: live-vs-replay experience mix, so over-reliance on 24/7
    # replay is visible ({"live": n, "replay_faithful": m}). Empty until replay
    # experiences accrue.
    experiment_count_by_provenance: dict | None = None
    # §53 slice 3b-ii: running forecast skill (log-loss/Brier) overall + split
    # live vs replay ({"overall":{...}, "live":{...}, "replay_faithful":{...}}).
    prequential_forecast_score: dict | None = None
    # task #13 (Rule N): every feature's live surface for the dashboard "Feature coverage"
    # panel — tuple[DashboardFeatureSurface, ...]. Empty until first publish.
    feature_surfaces: tuple = ()
    # B34 task #4 (Rule N): WHY options do/don't open. `option_entry_reason_counts` aggregates the
    # per-look outcome slug counts this session; `option_index_entry_outcomes` is the latest outcome
    # per INDEX underlying (the ones that were dark) so the firing gate is visible, not invisible.
    option_entry_reason_counts: dict | None = None
    option_index_entry_outcomes: dict | None = None

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)


# The promotion gate needs enough trades for CPCV to form groups AND to clear
# the Deflated-Sharpe minimum-trades bar; below this we report "gathering".
_MIN_TRADES_FOR_PROMOTION_GATE = StrategyPromotionConfig().minimum_trades
_PROMOTION_CPCV_CONFIG = CpcvConfig()


def _per_trade_return_fractions_by_strategy(state) -> dict[str, list[float]]:
    """Realized per-trade return fractions for each live strategy, from the
    closed trades — the input series the Deflated-Sharpe/CPCV gate scores."""
    returns_by_strategy: dict[str, list[float]] = {
        "ORB cash": [], "Credit spreads": []
    }
    for trade in state.closed_trades:
        basis = trade.entry_price * trade.quantity
        if basis > 0:
            cash_family = (
                "Mean reversion cash"
                if getattr(trade, "strategy_tag", "") == "intraday_mean_reversion_v1"
                else "ORB cash"
            )
            returns_by_strategy.setdefault(cash_family, []).append(trade.realized_pnl / basis)
    # research/171: directional option trades are split by MONEYNESS (Directional ITM/ATM/OTM), so each rung
    # of the ladder earns its OWN Deflated-Sharpe edge verdict in the promotion pipeline — the validation
    # gate decides which moneyness (if any) ever leaves paper.
    for position, realized in state.closed_directional_options:
        basis = position.entry_premium * position.lots * position.lot_size
        if basis > 0:
            family = f"Directional {getattr(position, 'moneyness', 'ATM')}"
            returns_by_strategy.setdefault(family, []).append(realized / basis)
    for spread, realized in state.closed_option_spreads:
        basis = abs(spread.entry_net_credit_per_unit * spread.lots * spread.lot_size)
        if basis > 0:
            returns_by_strategy["Credit spreads"].append(realized / basis)
    return returns_by_strategy


def _strategy_readiness_summaries(state) -> tuple[StrategyReadinessSummary, ...]:
    """Run the Deflated-Sharpe + CPCV promotion gate per strategy (research/41
    wiring). Under the minimum trade count it reports 'gathering' rather than
    forcing the gate on too little data."""
    summaries = []
    for strategy, returns in _per_trade_return_fractions_by_strategy(state).items():
        if len(returns) < _MIN_TRADES_FOR_PROMOTION_GATE:
            summaries.append(
                StrategyReadinessSummary(
                    strategy=strategy, trade_count=len(returns),
                    per_trade_sharpe_ratio=None, deflated_sharpe_ratio=None,
                    outcome="gathering_trades", promoted=False,
                )
            )
            continue
        try:
            decision = evaluate_strategy_with_cpcv_gate(
                returns, _PROMOTION_CPCV_CONFIG,
                StrategyPromotionConfig(minimum_trades=_MIN_TRADES_FOR_PROMOTION_GATE),
            )
            summaries.append(
                StrategyReadinessSummary(
                    strategy=strategy, trade_count=decision.trade_count,
                    per_trade_sharpe_ratio=decision.per_trade_sharpe_ratio,
                    deflated_sharpe_ratio=decision.deflated_sharpe_ratio,
                    outcome=decision.outcome.value, promoted=decision.promoted,
                )
            )
        except Exception:
            summaries.append(
                StrategyReadinessSummary(
                    strategy=strategy, trade_count=len(returns),
                    per_trade_sharpe_ratio=None, deflated_sharpe_ratio=None,
                    outcome="gathering_trades", promoted=False,
                )
            )
    return tuple(summaries)


class LivePaperTradingService:
    # Multi-day FII-net trend window (slice 3): trading days of participant OI
    # history walked back to trend FII index-futures net.
    _FII_NET_TREND_WINDOW = 5

    def __init__(
        self,
        authenticated_kite_client,
        account_virtual_capital: float,
        scan_interval_seconds: float = 5.0,
        max_new_cash_seeds_per_pass: int = 30,
        feature_plane_interval_seconds: float = 20.0,
        max_new_option_seeds_per_pass: int = 25,
        participant_positioning_source=None,
        high_fidelity_replay=None,
        breeze_session_token_store=None,
        breeze_historical_source_builder=None,
        autonomous_breeze_replay_call_budget=5000,
        multi_broker_replay_source_builder=None,
        multi_broker_replay_focus_size=200,
        enable_autonomous_high_fidelity_replay=True,
        enable_multi_broker_fleet_replay=False,
        champion_challenger_candidate_grid=None,
        champion_challenger_min_sessions=10,
        champion_configuration_store_path=None,
        debate_risk_observation_store_path=None,
        incident_post_mortem_store_path=None,
        offline_diagnostics_mode=False,
        record_live_market_depth=False,
        market_depth_focus_size=100,
        market_depth_recorder=None,
    ) -> None:
        self._kite_client = authenticated_kite_client
        # §53 slice 4 P4a-wire: optional HighFidelityReplayConfig — when injected,
        # the market-closed replay is built from a higher-fidelity source (Breeze
        # 1-second) for a bounded focus set instead of the stored 5-minute bars.
        # None (default) keeps the store path exactly as before (no regression).
        self._high_fidelity_replay = high_fidelity_replay
        # §53 slice 4 task #7: autonomous self-activation seams (default real). When
        # no explicit high_fidelity_replay is passed AND a valid Breeze session
        # token is stored, start() builds a rate-limited 1s config itself.
        self._breeze_session_token_store = breeze_session_token_store
        self._breeze_historical_source_builder = breeze_historical_source_builder
        self._autonomous_breeze_replay_call_budget = autonomous_breeze_replay_call_budget
        # task #20: autonomous multi-broker MINUTE replay tier — when no Breeze 1s
        # token is available, build a resilient fleet (Upstox→Angel→… whichever have
        # creds) and replay real 1-minute bars instead of falling to the stored 5m.
        # DI seam (default = the real fleet builder); focus_size bounds the pull.
        self._multi_broker_replay_source_builder = multi_broker_replay_source_builder
        self._multi_broker_replay_focus_size = multi_broker_replay_focus_size
        self._enable_autonomous_high_fidelity_replay = enable_autonomous_high_fidelity_replay
        self._enable_multi_broker_fleet_replay = enable_multi_broker_fleet_replay
        # §53 slice 5a: deficit-driven replay curriculum — how many recent calendar days
        # to scan for stored sessions to classify + balance regime coverage across.
        self._curriculum_lookback_days = 60
        # §53 slice 5b: cache of a date's classified market regime (keyed by date), so
        # each closed experience is tagged with the ADX regime of its session without
        # re-classifying every drain pass. Populated lazily from the bar store.
        self._market_regime_cache_by_date: dict = {}
        # §53 slice 5c-i/5c-iii: the champion ORB config per market regime (promoted by the
        # champion-challenger tournament), cached lazily by regime key; "global" for the
        # regime-agnostic fallback.
        self._champion_orb_config_by_regime: dict = {}
        # §53 slice 5c-i.b: autonomous champion-challenger re-evaluation — runs the
        # tournament at most once/day over the stored sessions and promotes via the store.
        self._champion_challenger_candidate_grid = champion_challenger_candidate_grid
        self._champion_challenger_min_sessions = champion_challenger_min_sessions
        self._champion_challenger_last_run_date = None
        # Layer 11: latest memory-grounded strategic reflection + its daily cadence guard.
        self._latest_strategic_reflection = None
        self._strategic_reflection_last_run_date = None
        # Layer 11 slice 2: latest debate-as-risk-check assessments + its daily cadence guard.
        self._latest_thesis_risk_assessments: tuple = ()
        self._thesis_debate_last_run_date = None
        # Layer 11 slice 3: latest causal-cluster analysis + its daily cadence guard.
        self._latest_causal_cluster_analysis = None
        self._causal_cluster_last_run_date = None
        # Layer 11 slice 4: latest meta-strategy allocation + its daily cadence guard.
        self._latest_meta_strategy_allocation = None
        self._meta_strategy_last_run_date = None
        # Layer 11 slice 5: latest prediction-council forecast + its daily cadence guard.
        self._latest_council_forecast = None
        self._prediction_council_last_run_date = None
        # Layer 11 slice 6: latest synthetic stress rehearsal + its daily cadence guard.
        self._latest_stress_rehearsal = None
        self._stress_rehearsal_last_run_date = None
        # Layer 7.5 slice 1: latest skill-vs-luck control-arm comparison + its daily cadence guard.
        self._latest_control_arm_comparison = None
        self._control_arm_last_run_date = None
        # Layer 7.5 slice 2: latest skill-vs-luck court verdict + its daily cadence guard.
        self._latest_skill_vs_luck_verdict = None
        self._skill_vs_luck_court_last_run_date = None
        # Layer 7.5 slice 3: latest per-trade pre-mortem forecast + its daily cadence guard.
        self._latest_pre_mortem = None
        self._pre_mortem_last_run_date = None
        # Layer 7.5 slice 4: latest profit-provenance + world-model scoreboard + cadence guard.
        self._latest_profit_provenance = None
        self._latest_world_model_scoreboard = None
        self._lab_summary_last_run_date = None
        # Trunk VII.1 CONSCIENCE: latest constitutional-posture audit + its daily cadence guard.
        self._latest_constitutional_verdict = None
        self._constitutional_audit_last_run_date = None
        # Trunk VII.10/11 CONSCIENCE: latest alignment-tripwire verdicts + their daily cadence guard.
        self._latest_wireheading_verdict = None
        self._latest_deceptive_alignment_verdict = None
        self._alignment_tripwire_last_run_date = None
        # Trunk VII.14 CONSCIENCE: forensic safety-incident store (opened lazily in the writer
        # thread, per-thread SQLite) + the cached post-mortem summary + its daily cadence guard.
        self._incident_post_mortem_store = None
        self._latest_incident_post_mortem = None
        self._incident_post_mortem_last_run_date = None
        # Trunk VII CONSCIENCE: latest goal-integrity verdict + its daily cadence guard.
        self._latest_goal_integrity_verdict = None
        self._goal_integrity_last_run_date = None
        # Trunk VII CONSCIENCE: latest mechanistic-interpretability report + its cadence guard.
        self._latest_interpretability_report = None
        self._interpretability_last_run_date = None
        # Trunk VII CONSCIENCE: latest red-team fragility report + its daily cadence guard.
        self._latest_red_team_report = None
        self._red_team_last_run_date = None
        # Trunk VII CONSCIENCE: latest SEBI regulatory-compliance report + its daily cadence guard.
        self._latest_law_compliance_report = None
        self._ethics_law_last_run_date = None
        # Trunk XIII EPISTEMICS: latest contradiction + misinformation reports + their cadence guard.
        self._latest_contradiction_report = None
        self._latest_misinfo_report = None
        self._epistemic_defense_last_run_date = None
        # Trunk IX PREDICTIVE-CORE: latest surprise + ensemble reports + their cadence guard.
        self._latest_surprise_report = None
        self._latest_ensemble_forecast = None
        self._predictive_core_last_run_date = None
        # Trunk XV MEMORY: latest consolidated semantic memory + its cadence guard.
        self._latest_semantic_memory = None
        self._memory_consolidation_last_run_date = None
        # Trunk VI SOCIETY: latest consensus + governance reports over the council desks.
        self._latest_consensus_verdict = None
        self._latest_governance_report = None
        self._society_last_run_date = None
        # Trunk II SENSES: latest market-breadth + cross-market context + their cadence guard.
        self._latest_market_breadth = None
        self._latest_cross_market_context = None
        self._market_breadth_last_run_date = None
        # Trunk II SENSES: sentiment/news ingestion (research/140 S1) — latest poll report + cadence.
        self._latest_news_ingestion_report = None
        self._news_last_run_at = None
        # Trunk II SENSES: S2 structured index S/R level extraction (research/142) — report + cadence.
        self._latest_news_level_extraction_report = None
        self._news_levels_last_run_at = None
        # Trunk II SENSES: S4a+S4b news acquisition LADDER (research/143+144) — fast curl_cffi static
        # fetch first (~0.3s), Crawl4AI headless render only as JS-only fallback. Runs in a BACKGROUND
        # thread (the rare render fallback is ~40s — never block the loop); the store-dedup delta is
        # the "new headlines this poll" live signal cached for the dashboard.
        self._latest_news_acquisition_report = None
        self._news_acquisition_last_run_at = None
        self._news_acquisition_thread = None
        self._news_acquisition_methods = {}  # source_id -> "fast" | "render" | "none"
        # Trunk II SENSES: S4c NSE corporate-announcement filings (research/145) — highest-signal news
        # (board outcomes/results/dividends) via curl_cffi session. Background thread (a hung NSE call
        # must never stall the loop); report cached for the dashboard.
        self._latest_exchange_filings_report = None
        self._exchange_filings_last_run_at = None
        self._exchange_filings_thread = None
        # Trunk II SENSES: S3 per-source reliability board (research/146) — tier-seeded beta-reputation
        # + freshness track over the real sources in the store. Read-only until S7 weights the gate.
        self._latest_source_reliability_board = None
        self._source_reliability_last_run_at = None
        # Trunk II SENSES: S7 news entry-gate (research/147) — the PRIMARY consumer. Pushes a per-symbol
        # news-event risk map onto the loop state each pass (advisory until calibration earned).
        self._news_entry_gate_last_run_at = None
        # Trunk II SENSES: NSE company-name↔symbol gazetteer (research/148), F&O-bounded, so the gate
        # matches headline company names (not just "SYMBOL:" filings) to symbols. Built lazily + cached.
        self._news_symbol_gazetteer = None
        # Trunk II SENSES: stock-S/R level extraction (research/149) — analyst targets/support per stock.
        self._latest_stock_levels = None
        self._stock_levels_last_run_at = None
        # Trunk II SENSES: headline sentiment (research/150) — finance-VADER polarity, makes the S7 gate
        # directional (adverse news weighs more). FinBERT drops in behind the same seam later.
        self._headline_sentiment_scorer = None
        self._latest_sentiment_summary = None
        # Trunk II SENSES: S5 Telegram social-tier ingestion (research/152) — advisory-until-proven.
        self._latest_telegram_report = None
        self._telegram_last_run_at = None
        # Trunk XIV AXIOLOGY (research/153): the system's explicit utility + value-drift over real trades.
        self._latest_utility_score = None
        self._latest_value_drift = None
        self._axiology_last_run_at = None
        # Trunk III WILL (research/154): multi-objective arbitration + goal-priority schedule over the
        # mechanisms (consumes the XIV utility). Read-only board; entry-loop consumer QUEUED.
        self._latest_arbitration = None
        self._latest_goal_schedule = None
        self._will_last_run_at = None
        # Trunk IX PREDICTIVE-CORE (research/156): the ML win-probability ENGINE (LightGBM). Trained/
        # loaded in a background thread; pushes a size-multiplier callable onto the loop state (acts only
        # once it beats the fixed-formula baseline on held-out CV — earned on real data, not market-gated).
        self._win_probability_engine = None
        self._win_probability_thread = None
        self._win_probability_last_run_at = None
        # Trunk III WILL — Capital-Allocation Optimizer (research/163): each cadence, solve the CVXPY
        # portfolio allocation over the real traded universe → cache the AllocationResult on the loop
        # state (an advisory size-DOWN lever at the entry sites until the engine EARNS the right to act)
        # and surface it on the dashboard. Best-effort; never disturbs the loop.
        self._capital_allocation_optimizer = None
        # Trunk X AUTOPOIESIS — the component-lifecycle homeostat (research/172). The orchestrator owns
        # its SQLite store and only `_maybe_run_autopoiesis_homeostat` touches it, keeping the store
        # single-threaded as its threading contract requires.
        self._autopoiesis_homeostat = None
        self._autopoiesis_state_store = None
        self._autopoiesis_last_run_at = None
        self._latest_autopoiesis_report = None
        self._autopoiesis_failure_count = 0
        self._capital_allocation_last_run_at = None
        self._capital_allocation_result = None
        # Trunk XII INTRINSIC MOTIVATION — Curiosity / learning-progress engine (research/164/165): each
        # cadence, score per-(strategy×regime) exploration priority from the experience history and cache
        # the ExplorationPlan (steers the replay curriculum toward the highest-learning regime + surfaces).
        self._curiosity_engine = None
        self._curiosity_last_run_at = None
        self._curiosity_plan = None
        # Trunk IX PREDICTIVE-CORE — World-Model Planning engine (research/166/167): each cadence, learn
        # the generative market-state model from recent bars, plan, and cache the current-state entry
        # verdict (per direction) on the loop state so the entry sites apply a confidence-gated size/veto.
        self._world_model_engine = None
        self._world_model_last_run_at = None
        self._world_model_verdicts = {}
        # Trunk VIII SENTIENCE: the Global Workspace integrator — binds the faculties' signals into
        # one broadcast each pass. A real blinker subscriber records recent broadcasts (proves the bus).
        from collections import deque as _deque

        from nse_algo_trader.sentience.global_workspace import GlobalWorkspace

        self._global_workspace = GlobalWorkspace()
        self._workspace_broadcast_history = _deque(maxlen=10)
        self._global_workspace.subscribe(
            lambda sender, broadcast=None, **_: (
                self._workspace_broadcast_history.append(broadcast)
                if broadcast is not None else None
            )
        )
        self._latest_workspace_broadcast = None
        self._latest_attention_context = None  # Trunk VIII selective/state-dependent attention
        self._latest_self_model = None          # Trunk VIII self-model
        self._latest_attention_schema = None    # Trunk VIII attention schema
        self._latest_rumination = None          # Trunk VIII workspace replay/rumination
        self._latest_bound_percept = None       # Trunk VIII cross-modal binding
        self._workspace_cycle_log = _deque(maxlen=30)  # Trunk VIII metacognition: (ignited, faculty_count)
        self._latest_metacognition = None       # Trunk VIII higher-order monitoring
        self._latest_indicator_scoreboard = None  # Trunk VIII indicator scoreboard
        # DI seam so tests never touch the real champion store (default = the prod path).
        self._champion_configuration_store_path = champion_configuration_store_path
        self._debate_risk_observation_store_path = debate_risk_observation_store_path
        self._incident_post_mortem_store_path = incident_post_mortem_store_path
        # When True, start() skips the live-broker universe fetch/scan (no live orders) but still runs
        # the writer loop's stored-data cadences + publishes all feature/memory panels — so the
        # dashboard stays informative after the daily Kite token expires (research/122).
        self._offline_diagnostics_mode = offline_diagnostics_mode
        # Layer 11 slice 2c: cached prequential earn-calibration verdict (for the dashboard).
        self._latest_debate_risk_calibration = None
        # §53 slice 4 P4b: record live order-book depth forward (the only path to
        # historical depth). Default OFF (no load/behaviour change); enable to start
        # accumulating. The store is built lazily in the writer thread (SQLite is
        # single-thread). market_depth_recorder is a DI seam for tests.
        self._record_live_market_depth = record_live_market_depth
        self._market_depth_focus_size = market_depth_focus_size
        self._market_depth_recorder = market_depth_recorder
        # Layer 10 §10 opponent ledger — real NSE archive fetcher by default;
        # injectable (DI seam) so tests pass an in-memory fake. Fetched once per
        # trade date in the writer thread and cached.
        if participant_positioning_source is None:
            from nse_algo_trader.participant_positioning.nse_participant_positioning_source import (  # noqa: E501
                NseParticipantPositioningSource,
            )

            participant_positioning_source = NseParticipantPositioningSource()
        self._participant_positioning_source = participant_positioning_source
        self._opponent_ledger_reading = None
        self._opponent_ledger_fetched_for = None  # the date last attempted
        # persist_todays_bars=True so the replay-when-closed store grows with
        # each live session the loop trades (research/41).
        self._live_feed = KiteLiveUniverseFeed(
            authenticated_kite_client, persist_todays_bars=True
        )
        self._feed = self._live_feed  # active feed pointer (live or replay)
        self._replay_feed = None  # market-CLOSED replay half (built in start())
        self._replay_timestamps: list = []
        self._replay_cursor = 0
        # task #14: the (feed, timestamps, cursor) triple is swapped atomically under this
        # lock when the background high-fidelity builder upgrades the store-5m feed.
        self._replay_feed_lock = threading.Lock()
        self._high_fidelity_replay_builder_thread = None
        self._clock = NseMarketClock()
        self._square_off_schedule = IntradaySquareOffSchedule()
        self._max_new_option_seeds_per_pass = max_new_option_seeds_per_pass
        self._tradable_universe = None
        self._banned_underlying_symbols: frozenset = frozenset()
        self._state = LiveUniversePaperState(
            ledger=PaperTradingLedger(account_virtual_capital),
            scoreboard=PredictionTableScoreboard(),
        )
        # Trunk VII.6 CONSCIENCE: the constitutional Referee gates every order at the entry sites.
        from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
        from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch

        self._state.constitutional_referee = ConstitutionalReferee()
        # B18.1b (Rule G): give the loop a way to persist daily ATM IV without importing storage.
        # This is the history `rank_implied_volatility` needs; without it the IV-rank arm can only
        # ever abstain on "<60 observations".
        self._state.atm_implied_volatility_recorder = (
            self._record_daily_atm_implied_volatility
        )
        # B18 step 6 (Rule G): the selector now CHOOSES which option arm trades, and closed trades
        # feed their cost-net, tail-aware reward back into its posteriors. Durable across restarts,
        # because weeks of evidence accrue at only a few trades/day/arm.
        from nse_algo_trader.paper_trading.adaptive_arm_selector import AdaptiveArmSelector
        from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
            ArmSelectionPosteriorStore,
        )
        from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
            OPTION_ARM_NAMES,
        )

        self._arm_posterior_store = ArmSelectionPosteriorStore()
        self._state.option_arm_posterior_store = self._arm_posterior_store
        self._state.option_arm_selector = AdaptiveArmSelector(
            self._arm_posterior_store, OPTION_ARM_NAMES
        )
        # Trunk VII.5: the off-switch — engaged blocks all trading; the audit self-halts on a breach.
        self._state.corrigibility_switch = CorrigibilitySwitch()
        self._scan_interval_seconds = scan_interval_seconds
        self._max_new_cash_seeds_per_pass = max_new_cash_seeds_per_pass

        self._cash_universe: list = []
        self._publish_lock = threading.Lock()
        self._published = LivePaperPublishedSnapshot(
            open_positions=(), closed_trade_count=0, cash_universe_size=0,
            seeded_count=0, last_pass_at=None, is_market_open=False,
        )
        self._writer_thread: threading.Thread | None = None
        self._running = False
        # Surface-builder name -> last build error. A surface that raises is logged and recorded
        # here rather than silently vanishing from the coverage panel (Rule O.3).
        self._feature_surface_build_failures: dict[str, str] = {}
        # B1: why the intraday-tradable series filter is inactive (None = active), plus its summary.
        self._intraday_tradable_cash_blocker: str | None = "universe not built yet"
        self._atm_implied_volatility_store = None  # B18.1b: opened lazily on first IV write
        # B25a: the feature/analytics plane runs on its OWN thread and cadence, so the trading view
        # publishes in seconds instead of waiting ~89s behind FinBERT + ~45 stages, and features
        # keep running when the market is closed or a scan pass stalls.
        self._feature_plane_thread: threading.Thread | None = None
        self._feature_plane_interval_seconds = feature_plane_interval_seconds
        #: stage name -> last failure. A stage that throws is isolated, counted and SURFACED.
        self._feature_stage_failures: dict[str, str] = {}
        #: B10: stage name -> when it last ran, replacing the once-per-day date guards.
        self._feature_stage_last_run_at: dict = {}
        # B32: an interruptible sleep. Both loops WAIT on this instead of sleeping, so `stop()` wakes
        # them immediately rather than leaving a daemon thread mid-cycle to be killed at interpreter
        # teardown — which aborts the C++ runtime ("terminate called without an active exception",
        # reproducibly core-dumping) when the thread is inside a native torch/transformers call.
        self._shutdown_event = threading.Event()
        #: B32: EVERY background thread this service spawns, so shutdown can wait for all of them.
        #: Feature stages fire off their own daemons (news acquisition, exchange filings, the
        #: win-probability trainer, the hi-fidelity replay builder). Those were never joined, so at
        #: interpreter teardown one could be killed inside a native training/inference frame — which
        #: aborts the C++ runtime and core-dumps.
        self._background_threads: list[threading.Thread] = []
        self._intraday_tradable_cash_selection_summary: str = ""
        # Layer 10 experience memory — opened lazily in the writer thread
        # (per-thread SQLite), fed the closed §9 experiments the loop emits.
        self._experience_memory = None
        self._family_promotion_registry = None  # L4: per-family promotion ladder (lazy, research/170)

    @property
    def scoreboard(self) -> PredictionTableScoreboard:
        return self._state.scoreboard

    @property
    def ledger(self) -> PaperTradingLedger:
        return self._state.ledger

    def start(self) -> None:
        """Assemble the universe (F&O-liquid first so trades appear soonest —
        ordering, not sampling) and launch the writer thread. In offline diagnostics mode (no live
        broker token) the live-universe fetch/scan is skipped — no live orders — but the writer loop
        still runs the stored-data cadences and publishes every feature/memory panel (research/122)."""
        if self._offline_diagnostics_mode:
            # No broker: skip the live universe fetch/scan. Stored-data panels (VII safety organs,
            # memory reflection, red-team, ethics/law, atlas) still run + publish from SQLite.
            self._cash_universe = []
            self._banned_underlying_symbols = self._load_fo_ban_list()  # stored SQLite, no broker
            self._writer_thread = threading.Thread(
                target=self._run_forever, name="live-paper-loop", daemon=True
            )
            self._running = True
            self._writer_thread.start()
            self._start_feature_plane_thread()
            self._register_clean_shutdown()
            return
        universe = fetch_live_tradable_universe(self._kite_client)
        self._tradable_universe = universe
        liquid_underlyings = set(universe.option_underlying_symbols())
        # B1: Kite marks NSE bonds/NCDs as instrument_type "EQ", so ~75% of this list is debt paper
        # that returns no intraday bars. Narrow to the series NSE itself reports as intraday-tradable
        # before the scanner ever spends a rate-limited fetch on them.
        cash_selection = self._intraday_tradable_cash_selection(
            universe.cash_equity_instruments
        )
        self._cash_universe = sorted(
            cash_selection.tradable_instruments,
            key=lambda instrument: (
                instrument.trading_symbol not in liquid_underlyings,
                instrument.trading_symbol,
            ),
        )
        self._banned_underlying_symbols = self._load_fo_ban_list()
        self._populate_average_daily_quantities()  # §53 slice 5c-ii (market-impact fills)
        # Autonomous HIGH-FIDELITY replay (Breeze 1s and/or multi-broker 1m) is OPT-IN
        # (default OFF): building its feed fetches many instruments over the network
        # SYNCHRONOUSLY in start(), which takes minutes and once blocked the dashboard
        # (task #14 — make the prebuild incremental/lazy to re-enable by default). Default
        # OFF keeps startup fast on the store-5m path so the live view is available in ~2s.
        if self._enable_autonomous_high_fidelity_replay:
            if self._high_fidelity_replay is None:
                self._maybe_activate_autonomous_breeze_replay()  # §53 task #7 (Breeze 1s)
            if self._high_fidelity_replay is None and self._enable_multi_broker_fleet_replay:
                self._maybe_activate_autonomous_multi_broker_replay()  # task #20 (fleet 1m)
        self._build_replay_feed_from_store()  # market-CLOSED replay data
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._run_forever, name="live-paper-loop", daemon=True
        )
        self._writer_thread.start()
        self._start_feature_plane_thread()
        self._register_clean_shutdown()

    def _build_replay_feed_from_store(self) -> None:
        """Build the FAST store-5m replay feed immediately so the service is live in seconds
        (main thread — no cross-thread SQLite). If a high-fidelity config is active, upgrade
        to it in a BACKGROUND thread (task #14) so its heavy network prebuild never blocks
        startup or the loop; the store-5m feed serves until the swap completes."""
        self._build_store_5m_replay_feed()
        if self._high_fidelity_replay is not None:
            self._high_fidelity_replay_builder_thread = threading.Thread(
                target=self._build_high_fidelity_replay_feed_and_swap,
                name="hi-fidelity-replay-builder", daemon=True,
            )
            self._high_fidelity_replay_builder_thread.start()

    def _build_store_5m_replay_feed(self) -> None:
        """The stored-5-minute-bar replay feed over the tradable cash universe
        (survivorship-free per bar date). Fast + local — the always-available default."""
        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.paper_trading.historical_archive_replay_planner import (
            HistoricalArchiveReplayPlanner,
        )
        from nse_algo_trader.paper_trading.point_in_time_universe_resolver import (
            PointInTimeUniverseResolver,
        )
        from nse_algo_trader.paper_trading.replay_universe_feed import (
            ReplayUniverseFeed,
        )

        instrument_by_token = {
            inst.instrument_token: inst for inst in self._cash_universe
        }
        bars_by_token: dict = {}
        store = MarketDataSqliteStore()
        try:
            for token in self._stored_bar_tokens(store):
                if token not in instrument_by_token:
                    continue
                bars = store.load_price_bars(token, BarInterval.MINUTE_5)
                if bars:
                    bars_by_token[token] = bars
            # Slice-2 wiring (research/62 P2): keep each bar only if its
            # instrument was in the REAL cash universe on that bar's own date
            # (survivorship-free, §11.1) — not merely in today's universe.
            # Pass-through for dates with no ingested bhavcopy, so replay never
            # idles for want of a point-in-time universe.
            archive_replay_planner = HistoricalArchiveReplayPlanner(
                PointInTimeUniverseResolver(store)
            )
            bars_by_token = archive_replay_planner.filter_bars_to_point_in_time_universe(
                bars_by_token,
                {
                    inst.instrument_token: inst.trading_symbol
                    for inst in self._cash_universe
                },
            )
        finally:
            store.close()
        feed = ReplayUniverseFeed(
            bars_by_token,
            corporate_action_adjustment_engine=(
                self._build_corporate_action_adjustment_engine(bars_by_token)
            ),
        )
        with self._replay_feed_lock:
            self._replay_feed = feed
            self._replay_timestamps = feed.stored_session_timestamps()
            self._replay_cursor = 0

    def _build_high_fidelity_replay_feed_and_swap(self) -> None:
        """§53 P4a-wire + task #14: build the market-closed replay feed from the injected
        higher-fidelity source (Breeze 1-second / multi-broker 1-minute) for the config's
        focus instruments over one session, then ATOMICALLY SWAP it in for the store-5m feed.
        Runs in a background thread so the heavy network fetch never blocks startup/the loop;
        best-effort — any failure leaves the store-5m feed in place (no regression)."""
        from zoneinfo import ZoneInfo

        from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (  # noqa: E501
            build_replay_bars_by_token_from_source,
        )
        from nse_algo_trader.paper_trading.replay_universe_feed import (
            ReplayUniverseFeed,
        )

        try:
            config = self._high_fidelity_replay
            ist = ZoneInfo("Asia/Kolkata")
            session_open = datetime(
                config.session_date.year, config.session_date.month,
                config.session_date.day, 9, 15, tzinfo=ist,
            )
            session_close = datetime(
                config.session_date.year, config.session_date.month,
                config.session_date.day, 15, 30, tzinfo=ist,
            )
            bars_by_token = build_replay_bars_by_token_from_source(
                config.bar_source, config.focus_instruments,
                config.bar_interval, session_open, session_close,
            )
            if not bars_by_token:
                return  # nothing fetched → keep the store-5m feed
            feed = ReplayUniverseFeed(bars_by_token)
            timestamps = feed.stored_session_timestamps()
            with self._replay_feed_lock:  # atomic swap; store-5m served until here
                self._replay_feed = feed
                self._replay_timestamps = timestamps
                self._replay_cursor = 0
            print(f"[replay] upgraded to high-fidelity feed "
                  f"({config.bar_interval.value}, {len(bars_by_token)} instruments)", flush=True)
        except Exception:
            pass  # keep the store-5m feed on any failure (no regression)

    def _maybe_activate_autonomous_breeze_replay(self) -> None:
        """§53 slice 4 task #7: when a valid daily Breeze session token is stored,
        self-build a rate-limited 1-second `HighFidelityReplayConfig` so the loop
        runs 1s replay UNATTENDED. Best-effort — no token / no creds / network
        error leaves `high_fidelity_replay` None → the store-5m path, so the
        always-on service always starts."""
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.broker_sessions.breeze_session_token_store import (
            BreezeSessionTokenFileStore,
        )
        from nse_algo_trader.paper_trading.breeze_replay_focus_planner import (
            plan_breeze_replay_focus,
        )
        from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (  # noqa: E501
            HighFidelityReplayConfig,
        )
        from nse_algo_trader.paper_trading.historical_trading_day_walker import (
            HistoricalTradingDayWalker,
        )

        try:
            token_store = (
                self._breeze_session_token_store or BreezeSessionTokenFileStore()
            )
            token_record = token_store.load_if_still_valid()
            if token_record is None:
                return  # no fresh manual token -> stay on store-5m replay
            source_builder = (
                self._breeze_historical_source_builder
                or _build_authenticated_breeze_historical_source
            )
            bar_source = source_builder(token_record.session_token)
            session_date = HistoricalTradingDayWalker(
                self._clock
            ).most_recent_trading_day_on_or_before(
                datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=1)
            )
            focus_instruments = plan_breeze_replay_focus(
                self._rule_l_prioritized_focus_candidates(),
                self._autonomous_breeze_replay_call_budget,
                BarInterval.SECOND_1,
            )
            if not focus_instruments:
                return
            self._high_fidelity_replay = HighFidelityReplayConfig(
                bar_source=bar_source,
                focus_instruments=focus_instruments,
                session_date=session_date,
                bar_interval=BarInterval.SECOND_1,
            )
        except Exception:
            self._high_fidelity_replay = None  # never break startup

    def _maybe_activate_autonomous_multi_broker_replay(self) -> None:
        """task #20: when no Breeze 1s token is available, self-build a resilient
        multi-broker MINUTE replay from whichever brokers have creds (Upstox→Angel→…),
        so the market-closed loop replays real 1-minute bars instead of falling to the
        stored 5m. Best-effort — no creds / network error leaves `high_fidelity_replay`
        None → the store path, so the always-on service always starts. Runs only after
        the Breeze 1s attempt declined (this is the next fidelity tier down)."""
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (  # noqa: E501
            HighFidelityReplayConfig,
        )
        from nse_algo_trader.paper_trading.historical_trading_day_walker import (
            HistoricalTradingDayWalker,
        )

        try:
            fleet_builder = (
                self._multi_broker_replay_source_builder
                or _build_available_broker_fleet_source
            )
            fleet_source = fleet_builder()
            if fleet_source is None:
                return  # no broker creds -> stay on store-5m replay
            focus_instruments = self._rule_l_prioritized_focus_candidates()[
                : self._multi_broker_replay_focus_size
            ]
            if not focus_instruments:
                return
            default_session_date = HistoricalTradingDayWalker(
                self._clock
            ).most_recent_trading_day_on_or_before(
                datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=1)
            )
            # §53 slice 5a: deficit-driven curriculum picks the session whose market
            # regime we've learned least about (best-effort → default most-recent).
            session_date, session_regime = self._curriculum_pick_replay_session(
                default_session_date
            )
            self._high_fidelity_replay = HighFidelityReplayConfig(
                bar_source=fleet_source,
                focus_instruments=focus_instruments,
                session_date=session_date,
                bar_interval=BarInterval.MINUTE_1,
            )
            if session_regime is not None:
                self._record_curriculum_session(session_date, session_regime)
        except Exception:
            self._high_fidelity_replay = None  # never break startup

    def _curriculum_pick_replay_session(self, default_session_date):
        """§53 slice 5a: choose the replay session whose ADX market regime is least
        covered so far (deficit-driven curriculum). Best-effort: classifies recent stored
        sessions for a liquid benchmark, then the deficit selector picks; any miss (no
        stored bars, no benchmark) falls back to `default_session_date` → no regression.
        Returns `(session_date, market_regime_or_None)`; None regime = fell back."""
        from datetime import timedelta

        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.paper_trading.deficit_driven_replay_session_selector import (
            select_deficit_replay_session,
        )
        from nse_algo_trader.paper_trading.historical_session_market_regime_classifier import (  # noqa: E501
            classify_session_market_regime,
        )
        from nse_algo_trader.paper_trading.replayed_session_regime_ledger import (
            ReplayedSessionRegimeLedger,
        )

        try:
            store = MarketDataSqliteStore()
            try:
                benchmark_token = self._curriculum_benchmark_token(store)
                if benchmark_token is None:
                    return default_session_date, None
                classified: list = []
                self._curriculum_regime_by_date = {}
                for day_offset in range(self._curriculum_lookback_days):
                    candidate = default_session_date - timedelta(days=day_offset)
                    day_start = datetime(candidate.year, candidate.month, candidate.day,
                                         tzinfo=_INDIA_MARKET_TIMEZONE)
                    bars = store.load_price_bars(
                        benchmark_token, BarInterval.MINUTE_5,
                        day_start, day_start + timedelta(days=1),
                    )
                    if bars:
                        regime = classify_session_market_regime(bars)
                        classified.append((candidate, regime))
                        self._curriculum_regime_by_date[candidate] = regime
            finally:
                store.close()
            if not classified:
                return default_session_date, None
            ledger = ReplayedSessionRegimeLedger()
            try:
                chosen = select_deficit_replay_session(
                    classified, ledger.covered_regime_counts()
                )
            finally:
                ledger.close()
            if chosen is None:
                return default_session_date, None
            return chosen, self._curriculum_regime_by_date.get(chosen)
        except Exception:
            return default_session_date, None  # curriculum never breaks startup

    @staticmethod
    def _curriculum_benchmark_token(store):
        """The stored instrument with the most 5-minute bars — a stand-in for the most
        liquid / most-consistently-recorded name, used as the market-regime benchmark."""
        row = store._connection.execute(
            "SELECT instrument_token FROM price_bars WHERE bar_interval=? "
            "GROUP BY instrument_token ORDER BY COUNT(*) DESC LIMIT 1",
            ("5m",),
        ).fetchone()
        return row[0] if row else None

    def _record_curriculum_session(self, session_date, market_regime) -> None:
        """Persist the replayed session's regime so the curriculum rotates coverage."""
        from nse_algo_trader.paper_trading.replayed_session_regime_ledger import (
            ReplayedSessionRegimeLedger,
        )

        try:
            ledger = ReplayedSessionRegimeLedger()
            try:
                ledger.record_replayed_session(session_date, market_regime)
            finally:
                ledger.close()
        except Exception:
            pass  # coverage bookkeeping must never break startup

    @staticmethod
    def _build_corporate_action_adjustment_engine(bars_by_token):
        """Real NSE split/bonus actions over the replayed window so the replay
        lookback series stays continuous across ex-dates (research/62 P3, §11.2).
        Best-effort: any fetch failure or empty result → None (identity), so
        replay never breaks on a corporate-action data hiccup."""
        from nse_algo_trader.market_data.nse_corporate_action_source import (
            NseLibCorporateActionSource,
        )
        from nse_algo_trader.paper_trading.corporate_action_adjustment import (
            CorporateActionAdjustmentEngine,
        )

        bar_dates = [
            bar.timestamp.date()
            for bars in bars_by_token.values()
            for bar in bars
        ]
        if not bar_dates:
            return None
        try:
            actions_by_symbol = NseLibCorporateActionSource().corporate_actions_by_symbol(
                min(bar_dates), max(bar_dates)
            )
        except Exception:  # network / nselib / parse hiccup — never break replay
            return None
        if not actions_by_symbol:
            return None
        return CorporateActionAdjustmentEngine(actions_by_symbol)

    @staticmethod
    def _stored_bar_tokens(store) -> list:
        """Distinct instrument tokens that have stored intraday bars."""
        cursor = store._connection.execute(
            "SELECT DISTINCT instrument_token FROM price_bars"
        )
        return [row[0] for row in cursor.fetchall()]

    def _track_background_thread(self, thread: threading.Thread) -> threading.Thread:
        """B32: remember a spawned daemon so `stop()` can wait for it instead of letting the
        interpreter kill it mid-native-call."""
        self._background_threads.append(thread)
        return thread

    def _register_clean_shutdown(self) -> None:
        """B32: a service that is never explicitly stopped still shuts down cleanly at exit."""
        import atexit

        atexit.register(self.stop)

    def _start_feature_plane_thread(self) -> None:
        """B25a: start the analytics thread. Separate from the trading thread so features neither
        delay the first publish nor stop when trading stops."""
        self._feature_plane_thread = threading.Thread(
            target=self._run_feature_plane_forever, name="feature-plane", daemon=True
        )
        self._feature_plane_thread.start()

    def stop(self, join_timeout_seconds: float = 10.0) -> None:
        """Stop BOTH threads and WAIT for them to leave their loops.

        B32: setting a flag was not enough. A daemon thread still inside its cycle at interpreter
        teardown is killed mid-call, and if it is inside a native torch/transformers frame the C++
        runtime aborts — reproducibly core-dumping. Waking the loops and joining them makes shutdown
        deterministic instead of racing the interpreter.
        """
        self._running = False
        self._shutdown_event.set()
        for thread in [
            self._writer_thread,
            self._feature_plane_thread,
            self._high_fidelity_replay_builder_thread,
            *self._background_threads,
        ]:
            if thread is not None and thread.is_alive():
                thread.join(timeout=join_timeout_seconds)

    def _load_fo_ban_list(self) -> frozenset:
        """Today's F&O ban list from the store (empty if not ingested) — fed
        to the credit-spread risk gate so banned underlyings are refused."""
        try:
            store = MarketDataSqliteStore()
            report = store.load_fo_ban_list_report(
                datetime.now(_INDIA_MARKET_TIMEZONE).date()
            )
            store.close()
            if report is not None:
                return frozenset(report.banned_underlying_symbols)
        except Exception:
            pass
        return frozenset()

    #: B25a: the feature/analytics plane. Named so a failure is reported BY STAGE, and run on its
    #: own thread so it neither blocks the trading view's first publish nor dies with a bad scan pass.
    #: B10 — how often each analytics stage may re-run, in MINUTES, matched to its COST.
    #: These 22 stages were guarded by `if last_run_date == today: return`, so they ran ONCE at
    #: process start and froze for the rest of the day. The operator's requirement is a system that
    #: keeps researching and learning between sessions — so the cadence is now real, and LLM-backed
    #: stages are spaced further apart than local-compute ones because they cost API calls (B33).
    FEATURE_STAGE_INTERVAL_MINUTES: dict[str, int] = {
        # LLM-backed — cost real tokens, so hourly.
        "strategic_reflection": 60, "thesis_debate": 60, "causal_cluster": 60,
        "meta_strategy": 60, "prediction_council": 60, "stress_rehearsal": 90,
        "pre_mortem": 60, "red_team": 90, "ethics_law": 90,
        # Local compute — cheap, so they can keep working continuously.
        "memory_consolidation": 15, "goal_integrity": 15, "interpretability": 20,
        "alignment_tripwire": 15, "constitutional_audit": 20, "epistemic_defense": 20,
        "predictive_core": 15, "society": 30, "market_breadth": 15,
        "control_arm": 30, "skill_vs_luck_court": 30, "lab_summary": 30,
        "incident_post_mortem": 20,
    }
    #: Default for any stage not named above — deliberately frequent enough to be "always on",
    #: because the failure mode this fixes is a stage that never runs again.
    DEFAULT_FEATURE_STAGE_INTERVAL_MINUTES = 30

    def _feature_stage_is_due(self, stage_name: str, now) -> bool:
        """B10: has enough time passed for this stage to run again?

        Replaces the once-per-day date guard. Records the run time on the way through, so a caller
        that returns early does not starve the next attempt.
        """
        from datetime import timedelta as _timedelta

        interval = _timedelta(
            minutes=self.FEATURE_STAGE_INTERVAL_MINUTES.get(
                stage_name, self.DEFAULT_FEATURE_STAGE_INTERVAL_MINUTES
            )
        )
        last = self._feature_stage_last_run_at.get(stage_name)
        if last is not None and (now - last) < interval:
            return False
        self._feature_stage_last_run_at[stage_name] = now
        return True

    def _feature_plane_stages(self) -> list:
        """(name, callable, takes_now) for every analytics/safety stage."""
        return [
            ("_drain_closed_experiments_into_memory", self._drain_closed_experiments_into_memory, False),
            ("_refresh_opponent_ledger", self._refresh_opponent_ledger, True),
            ("_maybe_reevaluate_champion_challenger", self._maybe_reevaluate_champion_challenger, True),
            ("_update_family_promotion_ladder", self._update_family_promotion_ladder, False),
            ("_maybe_run_strategic_reflection", self._maybe_run_strategic_reflection, True),
            ("_maybe_run_thesis_debate_risk_check", self._maybe_run_thesis_debate_risk_check, True),
            ("_maybe_run_causal_cluster_analysis", self._maybe_run_causal_cluster_analysis, True),
            ("_maybe_run_meta_strategy_allocation", self._maybe_run_meta_strategy_allocation, True),
            ("_maybe_run_prediction_council", self._maybe_run_prediction_council, True),
            ("_maybe_run_synthetic_stress_rehearsal", self._maybe_run_synthetic_stress_rehearsal, True),
            ("_maybe_run_control_arm_comparison", self._maybe_run_control_arm_comparison, True),
            ("_maybe_run_skill_vs_luck_court", self._maybe_run_skill_vs_luck_court, True),
            ("_maybe_run_pre_mortem", self._maybe_run_pre_mortem, True),
            ("_maybe_run_lab_summary", self._maybe_run_lab_summary, True),
            ("_maybe_run_constitutional_audit", self._maybe_run_constitutional_audit, True),
            ("_maybe_run_alignment_tripwires", self._maybe_run_alignment_tripwires, True),
            ("_maybe_run_goal_integrity", self._maybe_run_goal_integrity, True),
            ("_maybe_run_mechanistic_interpretability", self._maybe_run_mechanistic_interpretability, True),
            ("_maybe_run_red_team", self._maybe_run_red_team, True),
            ("_maybe_run_ethics_law_review", self._maybe_run_ethics_law_review, True),
            ("_maybe_run_epistemic_defense", self._maybe_run_epistemic_defense, True),
            ("_maybe_run_predictive_core", self._maybe_run_predictive_core, True),
            ("_maybe_run_memory_consolidation", self._maybe_run_memory_consolidation, True),
            ("_maybe_run_society", self._maybe_run_society, True),
            ("_maybe_run_market_breadth", self._maybe_run_market_breadth, True),
            ("_maybe_run_news_ingestion", self._maybe_run_news_ingestion, True),
            ("_maybe_run_news_level_extraction", self._maybe_run_news_level_extraction, True),
            ("_maybe_run_news_acquisition", self._maybe_run_news_acquisition, True),
            ("_maybe_run_exchange_filings", self._maybe_run_exchange_filings, True),
            ("_maybe_run_source_reliability", self._maybe_run_source_reliability, True),
            ("_maybe_run_news_entry_gate", self._maybe_run_news_entry_gate, True),
            ("_maybe_run_stock_level_extraction", self._maybe_run_stock_level_extraction, True),
            ("_maybe_run_telegram_ingestion", self._maybe_run_telegram_ingestion, True),
            ("_maybe_run_axiology", self._maybe_run_axiology, True),
            ("_maybe_run_will_arbitration", self._maybe_run_will_arbitration, True),
            ("_maybe_run_win_probability_engine", self._maybe_run_win_probability_engine, True),
            ("_maybe_run_capital_allocation", self._maybe_run_capital_allocation, True),
            ("_maybe_run_autopoiesis_homeostat", self._maybe_run_autopoiesis_homeostat, True),
            ("_maybe_run_curiosity", self._maybe_run_curiosity, True),
            ("_maybe_run_world_model_planning", self._maybe_run_world_model_planning, True),
            ("_maybe_run_incident_post_mortem", self._maybe_run_incident_post_mortem, True),
            ("_maybe_run_global_workspace", self._maybe_run_global_workspace, True),
        ]

    def run_feature_plane_stages_once(self, now) -> int:
        """Run every feature stage, ISOLATED. Returns how many failed.

        Previously all ~45 stages shared one try block with the trading pass, so a single exception
        skipped every later stage AND the publish — indistinguishable from "nothing happened".
        Each stage now fails alone, is counted BY NAME, and the rest still run.
        """
        failed = 0
        for stage_name, stage_callable, takes_now in self._feature_plane_stages():
            try:
                stage_callable(now) if takes_now else stage_callable()
            except Exception as stage_failure:  # noqa: BLE001 — isolation is the point
                failed += 1
                self._feature_stage_failures[stage_name] = (
                    f"{type(stage_failure).__name__}: {stage_failure}"
                )
                print(
                    f"[feature-plane] {stage_name} failed: "
                    f"{type(stage_failure).__name__}: {stage_failure}",
                    flush=True,
                )
        return failed

    def _update_family_promotion_ladder(self) -> None:
        """L4 (research/170): push each strategy family's live DSR+CPCV readiness into the promotion
        ladder, so every family EARNS its stage independently on its OWN trades. Regime coverage is
        proxied by a 2x-minimum trade count until the real drawdown+vol-spike coverage gate is wired
        (BACKLOG). Never raises — it's a feature-plane stage, isolated by the caller."""
        if self._family_promotion_registry is None:
            from nse_algo_trader.paper_trading.strategy_family_promotion_registry import (
                StrategyFamilyPromotionRegistry,
            )

            self._family_promotion_registry = StrategyFamilyPromotionRegistry()
        registry = self._family_promotion_registry
        for summary in _strategy_readiness_summaries(self._state):
            registry.ensure_family(summary.strategy)
            if summary.trade_count < _MIN_TRADES_FOR_PROMOTION_GATE:
                continue
            registry.record_evaluation(
                family=summary.strategy,
                edge_promoted=summary.promoted,
                deflated_sharpe=summary.deflated_sharpe_ratio or 0.0,
                trades_evaluated=summary.trade_count,
                regime_coverage_met=summary.trade_count >= 2 * _MIN_TRADES_FOR_PROMOTION_GATE,
            )

    def _run_feature_plane_forever(self) -> None:
        """The analytics thread. Deliberately NEVER checks market hours — "active even after market
        is closed" is the requirement, so this runs on its own cadence regardless of trading."""
        while self._running:
            now = datetime.now(_INDIA_MARKET_TIMEZONE)
            try:
                if self._experience_memory is None:
                    self._experience_memory = SqliteExperienceMemory()
                self.run_feature_plane_stages_once(now)
                self._publish(now, price_open_positions=False)
            except Exception as plane_error:  # noqa: BLE001
                print(f"[feature-plane] cycle error: {plane_error!r}", flush=True)
            self._shutdown_event.wait(self._feature_plane_interval_seconds)

    def _run_forever(self) -> None:
        """The TRADING thread. Publishes immediately after each scan pass so the trading view is up
        in seconds instead of waiting ~89s behind the feature stages (B25a)."""
        while self._running:
            real_now = datetime.now(_INDIA_MARKET_TIMEZONE)
            try:  # never let one bad pass or publish kill the loop
                if self._clock.is_market_open(real_now):
                    self._feed = self._live_feed
                    self._advance_one_pass(real_now)
                    self._record_market_depth_best_effort()  # §53 P4b (forward)
                elif self._replay_feed is not None and self._replay_feed.has_data():
                    self._advance_replay_pass()
                self._publish(real_now)
            except Exception as loop_error:
                import traceback

                print(f"[live-paper-loop] pass error: {loop_error!r}", flush=True)
                traceback.print_exc()
                try:
                    self._publish(real_now, price_open_positions=False)
                except Exception:
                    pass
            self._shutdown_event.wait(self._scan_interval_seconds)

    def _record_daily_atm_implied_volatility(
        self, underlying_symbol: str, trade_date, implied_volatility
    ) -> bool:
        """B18.1b: persist one underlying's ATM IV for one session (idempotent per symbol+date).

        Opens the store lazily and keeps it open — this runs once per underlying per pass, so a
        connection per call would be wasteful. Returns whether a row was actually written, so the
        loop only counts real writes.
        """
        if self._atm_implied_volatility_store is None:
            self._atm_implied_volatility_store = MarketDataSqliteStore()
        return self._atm_implied_volatility_store.save_daily_atm_implied_volatility(
            underlying_symbol, trade_date, implied_volatility
        )

    def _intraday_tradable_cash_selection(self, cash_instruments):
        """B1: narrow the raw Kite "cash equity" list to the NSE series that may be traded INTRADAY,
        using the exchange's own latest bhavcopy already stored by the daily ingestion job.

        Fallback: with no stored bhavcopy we keep the unfiltered universe rather than starving the
        scanner to nothing — safe now that the scan pointer always advances (B1's other half) — and
        record an explicit blocker. Never silently scan bonds; never silently scan nothing (Rule O.3).
        """
        from nse_algo_trader.universe_registry.intraday_tradable_cash_universe import (
            IntradayTradableCashUniverseSelection,
            select_intraday_tradable_cash_equities,
        )

        def _unfiltered(reason: str):
            self._intraday_tradable_cash_blocker = reason
            print(f"[universe] B1 series filter INACTIVE — {reason}", flush=True)
            return IntradayTradableCashUniverseSelection(
                tradable_instruments=tuple(cash_instruments),
                excluded_count_by_series={},
            )

        try:
            store = MarketDataSqliteStore()
            try:
                latest_date = store.latest_cash_bhavcopy_trade_date()
                if latest_date is None:
                    return _unfiltered("no cash bhavcopy stored yet")
                series_by_symbol = {
                    row.symbol: row.series
                    for row in store.load_cash_bhavcopy_delivery_rows(latest_date)
                }
            finally:
                store.close()
        except Exception as bhavcopy_failure:
            return _unfiltered(
                f"bhavcopy read failed ({type(bhavcopy_failure).__name__}: {bhavcopy_failure})"
            )

        if not series_by_symbol:
            return _unfiltered(f"cash bhavcopy for {latest_date} is empty")

        selection = select_intraday_tradable_cash_equities(
            cash_instruments, series_by_symbol
        )
        if not selection.tradable_instruments:
            return _unfiltered(
                f"series filter kept 0 of {len(cash_instruments)} — refusing to starve the scanner"
            )
        self._intraday_tradable_cash_blocker = None
        self._intraday_tradable_cash_selection_summary = selection.summary_line()
        print(
            f"[universe] B1 series filter (bhavcopy {latest_date}): "
            f"{selection.summary_line()}",
            flush=True,
        )
        return selection

    def _liquidity_ranked_cash_universe(self) -> list:
        """Cash universe ordered most-liquid-first by the latest stored cash
        bhavcopy turnover (§53 task #8), so the rate-limited 1s replay focus is
        spent on the names that matter. Best-effort — falls back to the existing
        (option-underlyings-first) order if no bhavcopy is stored."""
        from nse_algo_trader.paper_trading.breeze_replay_focus_planner import (
            rank_instruments_by_liquidity,
        )

        try:
            store = MarketDataSqliteStore()
            try:
                latest_date = store.latest_cash_bhavcopy_trade_date()
                if latest_date is None:
                    return self._cash_universe
                turnover_by_symbol = {
                    row.symbol: row.turnover_lakhs
                    for row in store.load_cash_bhavcopy_delivery_rows(latest_date)
                }
            finally:
                store.close()
            return rank_instruments_by_liquidity(
                self._cash_universe, turnover_by_symbol
            )
        except Exception:
            return self._cash_universe

    def _rule_l_prioritized_focus_candidates(self) -> list:
        """Focus candidates across ALL THREE segments in Rule-L order: index
        options → stock options → cash (liquidity-ranked). Equal breadth when the
        budget is ample; concatenating in priority order means that when
        `plan_breeze_replay_focus` truncates to the rate-limit budget, cash yields
        first and index options are kept — exactly Rule L's tie-break."""
        from nse_algo_trader.universe_registry import InstrumentKind

        cash = self._liquidity_ranked_cash_universe()
        if self._tradable_universe is None:
            return cash
        options = self._tradable_universe.option_ladder_instruments
        index_options = [o for o in options if o.kind is InstrumentKind.INDEX_OPTION]
        stock_options = [o for o in options if o.kind is InstrumentKind.STOCK_OPTION]
        return index_options + stock_options + cash

    def _record_market_depth_best_effort(self) -> None:
        """§53 P4b: snapshot + store the focus set's order book this live pass.
        Best-effort — depth recording must NEVER disturb trading. The store is built
        lazily HERE (writer thread) because SQLite objects are single-thread."""
        if not self._record_live_market_depth:
            return
        try:
            if self._market_depth_recorder is None:
                from nse_algo_trader.market_data.kite_market_depth_source import (
                    KiteMarketDepthSource,
                )
                from nse_algo_trader.market_data.market_depth_snapshot_store import (
                    MarketDepthSnapshotStore,
                )
                from nse_algo_trader.paper_trading.live_market_depth_recorder import (
                    LiveMarketDepthRecorder,
                )

                self._market_depth_recorder = LiveMarketDepthRecorder(
                    KiteMarketDepthSource(self._kite_client),
                    MarketDepthSnapshotStore(),
                )
            focus_tokens = [
                instrument.instrument_token
                for instrument in self._cash_universe[: self._market_depth_focus_size]
            ]
            self._market_depth_recorder.record_once(focus_tokens)
        except Exception:
            pass  # never let depth recording break the trading loop

    def _advance_replay_pass(self) -> None:
        """One replay step: advance the replay clock to the next stored bar
        timestamp (looping) and run the loop against the replay feed with that
        timestamp as 'now'. A new replay day resets the per-session seeded
        state so each replayed day is a fresh session."""
        # Read the (feed, timestamps, cursor) triple + advance the cursor under the lock so a
        # background high-fidelity SWAP (task #14) never leaves the cursor indexing a stale
        # (possibly shorter) timestamp list.
        with self._replay_feed_lock:
            feed = self._replay_feed
            timestamps = self._replay_timestamps
            if not timestamps:
                return
            cursor = self._replay_cursor % len(timestamps)
            replay_now = timestamps[cursor]
            previous_now = timestamps[(cursor - 1) % len(timestamps)]
            self._replay_cursor = (cursor + 1) % len(timestamps)
        if replay_now.date() != previous_now.date():
            self._state.seeded_cash_tokens.clear()
            self._state.watched_opening_ranges.clear()
            # B8: a new trading day starts genuinely fresh for options too, rather than relying on
            # cooldown arithmetic to carry across a date boundary.
            self._state.seeded_option_underlyings.clear()
            self._state.last_option_look_at_by_underlying.clear()
        feed.set_replay_as_of(replay_now)
        self._feed = feed
        self._advance_one_pass(replay_now, replay_mode=True)

    def _champion_orb_config(self):
        """The ORB config the loop trades with — the champion for the CURRENT session's
        market regime (§53 slice 5c-iii), falling back to the global champion, then the
        built-in default. Cached per regime; best-effort (a bad file → default)."""
        regime = self._current_session_market_regime()
        # "unknown" (store-5m multi-date replay / unclassifiable) → the global champion.
        regime_key = None if regime == "unknown" else regime
        cache_key = regime_key or "global"
        if cache_key not in self._champion_orb_config_by_regime:
            try:
                self._champion_orb_config_by_regime[cache_key] = (
                    self._champion_store().load_champion_or_default(market_regime=regime_key)
                )
            except Exception:
                from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (  # noqa: E501
                    OpeningRangeBreakoutConfig,
                )

                self._champion_orb_config_by_regime[cache_key] = OpeningRangeBreakoutConfig()
        return self._champion_orb_config_by_regime[cache_key]

    def _populate_average_daily_quantities(self) -> None:
        """§53 slice 5c-ii: fill `state.average_daily_quantity_by_token` with each token's
        mean per-session traded volume from the REAL stored bars, so cash fills pay
        size-dependent market impact. Best-effort — on any failure the map stays empty and
        fills fall back to spread-only (no regression)."""
        try:
            store = MarketDataSqliteStore()
            try:
                rows = store._connection.execute(
                    "SELECT instrument_token, AVG(day_volume) FROM ("
                    "  SELECT instrument_token, date(bar_timestamp) d, SUM(volume) AS day_volume"
                    "  FROM price_bars GROUP BY instrument_token, d"
                    ") GROUP BY instrument_token"
                ).fetchall()
            finally:
                store.close()
            self._state.average_daily_quantity_by_token = {
                token: float(adv) for token, adv in rows if adv and adv > 0
            }
        except Exception:
            self._state.average_daily_quantity_by_token = {}

    def _champion_store(self):
        """The champion-config store, at the injected path (tests) or the prod default."""
        from nse_algo_trader.paper_trading.champion_configuration_store import (
            ChampionConfigurationStore,
        )

        if self._champion_configuration_store_path is not None:
            return ChampionConfigurationStore(self._champion_configuration_store_path)
        return ChampionConfigurationStore()

    def _debate_risk_observation_store(self):
        """The debate-risk prequential-observation store, at the injected path (tests) or the
        prod default (Layer 11 slice 2c)."""
        from nse_algo_trader.paper_trading.debate_risk_prequential_observation_store import (
            DebateRiskPrequentialObservationStore,
        )

        if self._debate_risk_observation_store_path is not None:
            return DebateRiskPrequentialObservationStore(
                self._debate_risk_observation_store_path
            )
        return DebateRiskPrequentialObservationStore()

    def _build_feature_surfaces(self) -> tuple:
        """task #13 (Rule N): a live `DashboardFeatureSurface` per §53/ADVANCED feature, so
        the dashboard's Feature-coverage panel shows every feature's status at a glance.
        Each builder is best-effort — a failing one is simply omitted (renders as 'not yet
        surfaced'), never breaking the publish."""
        import os

        from nse_algo_trader.dashboard.dashboard_feature_surface import (
            DashboardFeatureSurface,
            FeatureCoverageReport,
        )

        surfaces = []

        def _add(fn):
            """Build one surface. A surface that raises must NEVER take the panel down — but it must
            not vanish silently either (Rule O.3): a swallowed exception here is indistinguishable
            from 'this feature has no surface', which is exactly how a broken panel hides."""
            try:
                surfaces.append(fn())
            except Exception as surface_failure:
                self._feature_surface_build_failures[getattr(fn, "__name__", "?")] = (
                    f"{type(surface_failure).__name__}: {surface_failure}"
                )
                print(
                    f"[dashboard] feature surface {getattr(fn, '__name__', '?')} failed to build: "
                    f"{type(surface_failure).__name__}: {surface_failure}",
                    flush=True,
                )

        # 1. Multi-broker data sourcing — which brokers have creds available right now.
        def _multi_broker():
            env = os.environ
            available = []
            if env.get("UPSTOX_ANALYTICS_TOKEN", "").strip() or env.get("UPSTOX_ACCESS_TOKEN", "").strip():
                available.append("Upstox")
            if all(env.get(k, "").strip() for k in ("ANGEL_ONE_CLIENT_CODE", "ANGEL_ONE_PIN", "ANGEL_ONE_TOTP_SECRET")):
                available.append("Angel One")
            if env.get("ICICI_BREEZE_API_KEY", "").strip():
                available.append("Breeze")
            if env.get("ZERODHA_KITE_API_KEY", "").strip():
                available.append("Kite")
            return DashboardFeatureSurface(
                key="multi_broker_sourcing",
                title="Multi-broker data sourcing (failover + gap-fill)",
                status="active" if len(available) >= 2 else "gathering",
                metrics=(("live brokers", str(len(available))),
                         ("sources", ", ".join(available) or "—")),
                note="Historical bars fail over across brokers; Groww/Fyers paused.",
            )
        _add(_multi_broker)

        # 1b. REDESIGN L1 — the pre-trade COST GATE (reality filter): how many directional entries cleared
        # round-trip breakeven, were resized, or were vetoed, + the slippage-calibration maturity.
        def _cost_gate():
            snap = self._state.cost_gate.snapshot()
            agg = snap.get("_all", {"passed": 0, "resized": 0, "vetoed": 0})
            decided = agg["passed"] + agg["resized"] + agg["vetoed"]
            cash = snap.get("nse_cash_equity", {})
            veto_rate = cash.get("veto_rate", 0.0)
            slip = (
                f"{cash.get('slippage_status', 'gathering')} "
                f"{cash.get('slippage_have', 0)}/{cash.get('slippage_need', 30)}"
            )
            return DashboardFeatureSurface(
                key="pre_trade_cost_gate",
                title="Pre-trade cost gate (L1 reality filter)",
                status="active" if decided > 0 else "gathering",
                metrics=(("decided", str(decided)),
                         ("passed", str(agg["passed"])),
                         ("resized", str(agg["resized"])),
                         ("vetoed", str(agg["vetoed"])),
                         ("cash veto rate", f"{veto_rate * 100:.0f}%"),
                         ("slippage calib", slip)),
                note="Every directional entry must clear round-trip breakeven (statutory + slippage). "
                     "Below-cost signals are vetoed or resized before capital. Rates verified vs NSE/FA/73061 "
                     "+ Finance Act 2026 (docs/research/164).",
            )
        _add(_cost_gate)

        # 1c. REDESIGN L2 — the validation engine: how many strategy configs have EVER been trialed
        # (the honest cumulative N the DSR deflates against), how many were kept, and the cross-trial
        # Sharpe dispersion. A high honest N is GOOD discipline (the bar to promote rises with every trial).
        def _validation_engine():
            from nse_algo_trader.paper_trading.strategy_trial_registry import (
                StrategyTrialRegistry,
            )

            registry = StrategyTrialRegistry()
            total = registry.cumulative_trial_count()
            summary = registry.trial_summary()
            return DashboardFeatureSurface(
                key="validation_engine",
                title="Validation engine (DSR honest-N + MinBTL + holdout)",
                status="active" if total > 0 else "gathering",
                metrics=(("cumulative trials (honest N)", str(total)),
                         ("kept configs", str(int(summary.get("kept_count", 0)))),
                         ("discarded", str(int(summary.get("discarded_count", 0)))),
                         ("sharpe std across trials", f"{summary.get('sharpe_std', 0.0):.3f}")),
                note="The Deflated-Sharpe gate now deflates against the HONEST cumulative count of every "
                     "config ever trialed (not just the batch); MinBTL rejects a backtest too short for that "
                     "trial count; a sealed holdout final-validates a promoted winner. research/166.",
            )
        _add(_validation_engine)

        # 1d. REDESIGN L3 — the ops-floor crash-safety spine: idempotent order IDs + the order-intent WAL
        # + broker-truth reconciliation. Populated by LIVE order placement (paper uses the simulated
        # broker); shows 'armed' with a durable WAL until live trading writes to it.
        def _ops_floor():
            from nse_algo_trader.broker_oms.order_intent_write_ahead_log import (
                OrderIntentWriteAheadLog,
            )

            summary = OrderIntentWriteAheadLog().summary()

            def _n(key: str) -> int:
                return int(summary.get(key, 0))

            live_orders = _n("pending") + _n("placed") + _n("filled") + _n("rejected")
            return DashboardFeatureSurface(
                key="ops_floor_crash_safety",
                title="Ops floor (idempotent orders + WAL + reconciliation)",
                status="active" if live_orders > 0 else "gathering",
                metrics=(("live orders logged", str(live_orders)),
                         ("filled", str(_n("filled"))),
                         ("pending/placed", f"{_n('pending')}/{_n('placed')}"),
                         ("rejected", str(_n("rejected"))),
                         ("write failures", str(_n("write_failure_count")))),
                note="Every LIVE order is deduped by a deterministic client id + written to a durable WAL "
                     "BEFORE the broker call, and reconciled against broker truth on restart — so a crash "
                     "never double-places or loses an order. Paper uses the simulated broker (WAL idle). "
                     "research/168.",
            )
        _add(_ops_floor)

        # 1e. REDESIGN L4 — the per-family promotion ladder: which strategy families have EARNED which
        # stage (research→paper→shadow→reduced-live→full-live) on their own validated edge.
        def _family_promotion():
            from nse_algo_trader.paper_trading.strategy_family_promotion_registry import (
                StrategyFamilyPromotionRegistry,
            )

            snap = StrategyFamilyPromotionRegistry().snapshot()
            fams = snap.get("families", [])
            counts = snap.get("stage_counts", {})
            live = snap.get("live_families", [])
            detail = " · ".join(f"{f['family']}={f['stage']}" for f in fams[:6]) or "no families yet"
            return DashboardFeatureSurface(
                key="strategy_family_promotion",
                title="Strategy promotion ladder (per-family, validation-gated)",
                status="active" if fams else "gathering",
                metrics=(("families", str(len(fams))),
                         ("paper", str(int(counts.get("paper", 0)))),
                         ("shadow", str(int(counts.get("shadow", 0)))),
                         ("live", str(len(live))),
                         ("ladder", detail)),
                note="Each family climbs research→paper→shadow→reduced-live→full-live, advancing ONLY when the "
                     "L2 honest-N DSR+CPCV promotes it on its OWN trades (+ human go-live for real capital); "
                     "edge decay auto-demotes. Breadth without sprawl — validation is the filter. research/170.",
            )
        _add(_family_promotion)

        # 2. Replay fidelity tier (market-closed).
        def _replay_fidelity():
            hf = self._high_fidelity_replay
            tier = "5-minute (store)"
            if hf is not None:
                tier = f"{hf.bar_interval.value} ({'Breeze' if hf.bar_interval.value == '1s' else 'fleet'})"
            return DashboardFeatureSurface(
                key="replay_fidelity", title="Replay fidelity tier (market-closed)",
                status="idle" if self._clock.is_market_open(datetime.now(_INDIA_MARKET_TIMEZONE)) else "active",
                metrics=(("tier", tier),
                         ("session", str(hf.session_date) if hf else "rolling")),
                note="High-fidelity feed builds in the background and swaps in when ready.",
            )
        _add(_replay_fidelity)

        # 3. Deficit-driven replay curriculum — regime coverage of replayed sessions.
        def _curriculum():
            from nse_algo_trader.paper_trading.replayed_session_regime_ledger import (
                ReplayedSessionRegimeLedger,
            )
            ledger = ReplayedSessionRegimeLedger()
            try:
                counts = ledger.covered_regime_counts()
                total = ledger.replayed_session_count()
            finally:
                ledger.close()
            return DashboardFeatureSurface(
                key="replay_curriculum", title="Deficit-driven replay curriculum (regime coverage)",
                status="active" if total else "gathering",
                metrics=(("sessions replayed", str(total)),
                         ("by regime", ", ".join(f"{r}:{n}" for r, n in sorted(counts.items())) or "—")),
                note="Replays the market regime the bot has learned least about.",
            )
        _add(_curriculum)

        # 4. Champion-challenger strategy config (global + per-regime).
        def _champion():
            store = self._champion_store()
            g = store.load_champion_or_default()
            per_regime = [r for r in ("trending", "range_bound", "indecisive")
                          if store.load_champion_or_default(market_regime=r) != g]
            return DashboardFeatureSurface(
                key="champion_challenger", title="Champion-challenger strategy config (global + per-regime)",
                status="active",
                metrics=(("global ORB", f"OR{g.opening_range_minutes}m · RR{g.target_risk_reward_ratio}"),
                         ("per-regime champions", str(len(per_regime)) if per_regime else "0 (global)")),
                note="Tournament auto-tunes the ORB config, gated by Deflated-Sharpe.",
            )
        _add(_champion)

        # 5. Market-impact fill model.
        def _market_impact():
            from nse_algo_trader.paper_trading.market_impact_fill_model import MarketImpactConfig
            n = len(self._state.average_daily_quantity_by_token)
            return DashboardFeatureSurface(
                key="market_impact_fills", title="Market-impact fill model",
                status="active" if n else "gathering",
                metrics=(("instruments w/ ADV", str(n)),
                         ("coefficient", f"{MarketImpactConfig().impact_coefficient_bps:.0f} bps @100% ADV")),
                note="Larger orders pay square-root price impact on top of the spread.",
            )
        _add(_market_impact)

        # 6. Market-regime memory calibration.
        def _regime_memory():
            if self._experience_memory is None:
                return DashboardFeatureSurface(
                    key="market_regime_memory", title="Market-regime memory calibration",
                    status="gathering", metrics=(("experiences", "0"),), note="")
            by_regime = self._experience_memory.experiment_count_by_market_regime()
            return DashboardFeatureSurface(
                key="market_regime_memory", title="Market-regime memory calibration",
                status="active" if by_regime else "gathering",
                metrics=(("by market regime",
                          ", ".join(f"{r}:{n}" for r, n in sorted(by_regime.items())) or "—"),),
                note="Calibration split by trending/range/indecisive regime.",
            )
        _add(_regime_memory)

        # 7. Order-flow toxicity (VPIN) — computed on the benchmark's latest stored session.
        def _vpin():
            from datetime import timedelta

            from nse_algo_trader.market_data import BarInterval
            from nse_algo_trader.market_data.vpin_order_flow_toxicity import compute_vpin

            reading = None
            store = MarketDataSqliteStore()
            try:
                token = self._curriculum_benchmark_token(store)
                if token is not None:
                    row = store._connection.execute(
                        "SELECT MAX(date(bar_timestamp)) FROM price_bars "
                        "WHERE bar_interval='5m' AND instrument_token=?", (token,)).fetchone()
                    if row and row[0]:
                        d = datetime.fromisoformat(row[0]).date()
                        day = datetime(d.year, d.month, d.day, tzinfo=_INDIA_MARKET_TIMEZONE)
                        bars = store.load_price_bars(token, BarInterval.MINUTE_5, day, day + timedelta(days=1))
                        reading = compute_vpin(bars, bucket_count=10)
            finally:
                store.close()
            if reading is None or reading.vpin is None:
                return DashboardFeatureSurface(
                    key="order_flow_toxicity", title="Order-flow toxicity (VPIN)",
                    status="gathering", metrics=(("VPIN", "—"),), note="")
            level = "elevated" if reading.vpin >= 0.4 else ("moderate" if reading.vpin >= 0.2 else "calm")
            return DashboardFeatureSurface(
                key="order_flow_toxicity", title="Order-flow toxicity (VPIN)",
                status="active",
                metrics=(("VPIN", f"{reading.vpin:.3f} ({level})"),
                         ("buckets", str(reading.bucket_count))),
                note="Bulk-volume-classified order-flow toxicity (Easley-LdP-O'Hara). "
                     "Entry-gate consumption queued.",
            )
        _add(_vpin)

        # 8. Strategic LLM analyst (Layer 11) — swappable multi-provider pool + latest reflection.
        def _strategic_llm():
            import os as _os

            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            configured = len(pool)
            reflection = self._latest_strategic_reflection
            if configured == 0:
                return DashboardFeatureSurface(
                    key="strategic_llm_analyst",
                    title="Strategic LLM analyst (swappable multi-provider)",
                    status="blocked", metrics=(("providers", "0"),),
                    note="No LLM provider keys configured — add free-tier keys to .env.",
                )
            # Lane structure: the pool is ordered by the cost ladder (idea #8) — the flat-cost Claude
            # subscription leads (maximized), then local Ollama → free cloud → paid last, with
            # swap-on-cap auto-failover. Surface the LEAD lane + its model so the subscription is visible.
            lead = pool[0]
            lead_model = getattr(lead, "model_name", "") or ""
            lead_label = f"{lead.provider_name}" + (f" · {lead_model}" if lead_model else "")
            leads_with_subscription = lead.provider_name == "claude-code-subscription"
            from nse_algo_trader.llm_strategy.claude_code_subscription_provider import (
                subscription_token_ledger,
                subscription_transport_telemetry,
            )

            warm_on = _os.environ.get(
                "CLAUDE_SUBSCRIPTION_WARM_DISABLED", ""
            ).strip().lower() not in {"1", "true", "yes"}
            tele = subscription_transport_telemetry()
            if leads_with_subscription and tele["total_calls"] > 0:
                # LIVE: the real warm/cold mix from the ACTUAL serving pool (task #1), not a config flag.
                transport_label = f"warm {tele['warm_calls']} · cold {tele['cold_calls']}"
            elif leads_with_subscription and warm_on:
                transport_label = "warm-persistent (idle)"
            else:
                transport_label = "cold one-shot"
            ladder_note = (
                "Flat-cost Claude Max/Pro subscription leads (Haiku), warm-persistent client "
                "(~3× faster than cold start); auto-fails-over local→free-cloud→paid on cap. "
                if leads_with_subscription else
                "Cost-ladder pool (local→free-cloud→paid). "
            )
            names = ", ".join(p.provider_name for p in pool[:6]) + (
                "…" if configured > 6 else ""
            )
            # Tokens consumed on the subscription lane THIS session (real SDK usage), for the lead model
            # (Haiku-4-5) — falls back to the cross-model aggregate if the SDK labels differ.
            ledger = subscription_token_ledger()
            token_row = ledger.get(lead_model) or ledger["_all"]

            def _compact_tokens(n: int) -> str:
                return f"{n / 1000:.1f}k" if n >= 1000 else str(n)

            if token_row["serves"] == 0:
                tokens_label = "0 (idle · 0 calls)"
            else:
                serves = token_row["serves"]
                hits = token_row.get("cache_hit_serves", 0)
                hit_pct = round(100 * hits / serves) if serves else 0
                tokens_label = (
                    f"{token_row['total']:,} tok · {serves} call{'s' if serves != 1 else ''} · "
                    f"in {_compact_tokens(token_row['input'])} · "
                    f"out {_compact_tokens(token_row['output'])} · "
                    f"cache-read {_compact_tokens(token_row['cache_read'])} "
                    f"({hits} hit{'s' if hits != 1 else ''}, {hit_pct}%) · "
                    f"cache-write {_compact_tokens(token_row['cache_creation'])}"
                )
            if reflection is not None and reflection.generated:
                return DashboardFeatureSurface(
                    key="strategic_llm_analyst",
                    title="Strategic LLM analyst (swappable multi-provider)",
                    status="active",
                    metrics=(("providers", str(configured)),
                             ("lead lane", lead_label),
                             ("transport", transport_label),
                             ("tokens", tokens_label),
                             ("pool", names),
                             ("served by", reflection.served_by),
                             ("findings", str(len(reflection.findings))),
                             ("distrust", ", ".join(reflection.distrust_mechanisms[:3]) or "—")),
                    note=ladder_note + (reflection.findings[0][:140] if reflection.findings
                                        else "Advisory (read-only); gate consumption queued."),
                )
            return DashboardFeatureSurface(
                key="strategic_llm_analyst",
                title="Strategic LLM analyst (swappable multi-provider)",
                status="gathering",
                metrics=(("providers", str(configured)),
                         ("lead lane", lead_label),
                         ("transport", transport_label),
                         ("tokens", tokens_label),
                         ("pool", names)),
                note=ladder_note + "Swap-on-limit pool ready; reflection runs on a daily cadence. "
                     "Advisory (read-only); gate consumption queued.",
            )
        _add(_strategic_llm)

        # 9. Debate-as-risk-check (Layer 11 slice 2) — bull/bear/risk panel over active theses.
        def _thesis_debate():
            assessments = [a for a in self._latest_thesis_risk_assessments if a.generated]
            verdict = self._latest_debate_risk_calibration
            earned = bool(verdict and verdict.earned)
            gate = (f"EARNED — deferred {self._state.debate_risk_deferred_count}, "
                    f"sized-down {self._state.debate_risk_sized_down_count}") if earned else (
                    "learning (advisory — gate inert until earned)")
            obs = str(verdict.observation_count) if verdict else "0"
            if not assessments:
                return DashboardFeatureSurface(
                    key="thesis_debate_risk_panel",
                    title="Debate-as-risk-check (bull/bear/risk panel)",
                    status="gathering",
                    metrics=(("theses debated", "0"), ("gate", gate),
                             ("prequential obs", obs)),
                    note="Bull/bear/risk roles debate each active thesis daily; "
                         "disagreement→risk_score → entry gate once calibration earned.",
                )
            riskiest = max(assessments, key=lambda a: a.risk_score)
            return DashboardFeatureSurface(
                key="thesis_debate_risk_panel",
                title="Debate-as-risk-check (bull/bear/risk panel)",
                status="active",
                metrics=(
                    ("theses debated", str(len(assessments))),
                    ("riskiest mechanism", riskiest.thesis.mechanism_name),
                    ("risk_score", f"{riskiest.risk_score:.2f}"),
                    ("disagreement", f"{riskiest.disagreement_score:.2f}"),
                    ("gate", gate),
                    ("prequential obs", obs),
                ),
                note="Disagreement→risk_score per active thesis, wired into all 4 entry sites; "
                     "defers/sizes-down high-risk entries once calibration is earned.",
            )
        _add(_thesis_debate)

        # 10. Causal-cluster analysis (Layer 11 slice 3) — LLM causal hypotheses over clusters.
        def _causal_cluster():
            analysis = self._latest_causal_cluster_analysis
            if analysis is None or not analysis.generated or not analysis.hypotheses:
                return DashboardFeatureSurface(
                    key="causal_cluster_analysis",
                    title="Causal analysis of multi-hop outcome clusters",
                    status="gathering",
                    metrics=(("hypotheses", "0"),),
                    note="LLM proposes falsifiable causal hypotheses over the memory's temporal "
                         "+ cross-regime clusters, daily. Advisory; decision-consumer queued.",
                )
            top = max(analysis.hypotheses, key=lambda h: h.confidence)
            return DashboardFeatureSurface(
                key="causal_cluster_analysis",
                title="Causal analysis of multi-hop outcome clusters",
                status="active",
                metrics=(
                    ("hypotheses", str(len(analysis.hypotheses))),
                    ("top cluster", top.cluster_label[:40] or "—"),
                    ("suspected cause", top.suspected_common_cause[:60] or "—"),
                    ("confidence", f"{top.confidence:.2f}"),
                    ("served by", analysis.served_by[:60] or "—"),
                ),
                note="Falsifiable causal hypotheses over the memory's multi-hop clusters. "
                     "Advisory; prediction-scoring → assumption tripwire queued.",
            )
        _add(_causal_cluster)

        # 11. Meta-strategy allocator (Layer 11 slice 4) — LLM weights across the strategies.
        def _meta_strategy():
            allocation = self._latest_meta_strategy_allocation
            if allocation is None or not allocation.generated or not allocation.weights:
                return DashboardFeatureSurface(
                    key="meta_strategy_allocation",
                    title="Meta-strategy allocator (LLM weights across strategies)",
                    status="gathering",
                    metrics=(("strategies weighted", "0"),),
                    note="LLM weights the strategies from their real per-regime track records "
                         "daily. Advisory; per-strategy sizing consumer queued.",
                )
            ranked = sorted(allocation.weights, key=lambda w: w.weight, reverse=True)
            spread = " · ".join(f"{w.strategy_tag.split('_')[0]} {w.weight:.0%}" for w in ranked)
            return DashboardFeatureSurface(
                key="meta_strategy_allocation",
                title="Meta-strategy allocator (LLM weights across strategies)",
                status="active",
                metrics=(
                    ("strategies weighted", str(len(allocation.weights))),
                    ("allocation", spread[:80]),
                    ("top strategy", ranked[0].strategy_tag),
                    ("served by", allocation.served_by[:60] or "—"),
                ),
                note="Normalised allocation weights across strategies from real per-regime "
                     "performance. Advisory; per-strategy sizing consumer queued.",
            )
        _add(_meta_strategy)

        # 12. Prediction-market council (Layer 11 slice 5) — track-record-weighted role forecasts.
        def _prediction_council():
            forecast = self._latest_council_forecast
            if forecast is None or not forecast.generated or not forecast.member_forecasts:
                return DashboardFeatureSurface(
                    key="prediction_council",
                    title="Prediction-market council (track-record-weighted)",
                    status="gathering",
                    metrics=(("members", "0"),),
                    note="Several roles forecast a probability; aggregated by each role's track "
                         "record (equal until reputations accrue). Advisory.",
                )
            weighting = "reputation-weighted" if forecast.is_reputation_tilted else "equal (accruing)"
            return DashboardFeatureSurface(
                key="prediction_council",
                title="Prediction-market council (track-record-weighted)",
                status="active",
                metrics=(
                    ("proposition", forecast.proposition_label[:44]),
                    ("weighted P", f"{forecast.weighted_probability:.0%}"),
                    ("simple mean", f"{forecast.simple_mean_probability:.0%}"),
                    ("members", str(len(forecast.member_forecasts))),
                    ("weighting", weighting),
                    ("served by", forecast.served_by[:50] or "—"),
                ),
                note="Diverse role forecasts aggregated by track record. Advisory; reputations "
                     "tilt the weights as resolved forecasts accrue (market-gated).",
            )
        _add(_prediction_council)

        # 13. Synthetic stress rehearsal (Layer 11 slice 6) — LLM red-team scenarios.
        def _stress_rehearsal():
            rehearsal = self._latest_stress_rehearsal
            if rehearsal is None or not rehearsal.generated or not rehearsal.scenarios:
                return DashboardFeatureSurface(
                    key="synthetic_stress_rehearsal",
                    title="Synthetic stress rehearsal (LLM red-team scenarios)",
                    status="gathering",
                    metrics=(("scenarios", "0"),),
                    note="LLM red-teams the bot's real weaknesses into adversarial scenarios "
                         "daily. Advisory; Layer-7.5 control-arms lab runs them (queued).",
                )
            worst = max(rehearsal.scenarios, key=lambda s: s.severity)
            return DashboardFeatureSurface(
                key="synthetic_stress_rehearsal",
                title="Synthetic stress rehearsal (LLM red-team scenarios)",
                status="active",
                metrics=(
                    ("scenarios", str(len(rehearsal.scenarios))),
                    ("worst condition", worst.market_condition[:44] or "—"),
                    ("targets", worst.targeted_mechanism[:30] or "—"),
                    ("severity", f"{worst.severity:.2f}"),
                    ("served by", rehearsal.served_by[:50] or "—"),
                ),
                note="Adversarial scenarios targeting the bot's real weak mechanisms. Advisory; "
                     "the Layer-7.5 control-arms lab rehearses them (queued).",
            )
        _add(_stress_rehearsal)

        # 14. Skill-vs-luck control (Layer 7.5 slice 1) — real ORB arm vs random-control arm.
        def _skill_vs_luck():
            comparison = self._latest_control_arm_comparison
            if comparison is None:
                return DashboardFeatureSurface(
                    key="skill_vs_luck_control",
                    title="Skill-vs-luck control (RANDOM-CONTROL arm)",
                    status="gathering",
                    metrics=(("arms scored", "0"),),
                    note="Runs the real champion ORB vs a random-direction control over stored "
                         "sessions daily — is the edge skill or luck?",
                )
            real, rnd = comparison.real, comparison.random_control
            return DashboardFeatureSurface(
                key="skill_vs_luck_control",
                title="Skill-vs-luck control (RANDOM-CONTROL arm)",
                status="active",  # the diagnostic is running; the edge verdict is in metrics/note
                metrics=(
                    ("real arm", f"hit {real.hit_rate:.0%} · Sharpe {real.sharpe:.2f} · "
                                 f"ret {real.total_return:+.1%} ({real.trades})"),
                    ("random-control", f"hit {rnd.hit_rate:.0%} · Sharpe {rnd.sharpe:.2f} · "
                                       f"ret {rnd.total_return:+.1%} ({rnd.trades})"),
                    ("edge", "yes" if comparison.has_edge else "not demonstrated"),
                ),
                note=comparison.verdict,
            )
        _add(_skill_vs_luck)

        # 15. Skill-vs-luck court (Layer 7.5 slice 2) — verdict over the control arms.
        def _skill_vs_luck_court():
            verdict = self._latest_skill_vs_luck_verdict
            if verdict is None:
                return DashboardFeatureSurface(
                    key="skill_vs_luck_court",
                    title="Skill-vs-luck court (shadow-rejected + verdict)",
                    status="gathering",
                    metrics=(("verdict", "pending"),),
                    note="Judges the control arms: is the edge directional skill, and does the "
                         "gate refuse the worse trades? Read-only.",
                )
            rejection = (
                "n/a (nothing vetoed)" if verdict.rejection_skill is None
                else ("adds skill" if verdict.rejection_skill else "over-rejecting")
            )
            return DashboardFeatureSurface(
                key="skill_vs_luck_court",
                title="Skill-vs-luck court (shadow-rejected + verdict)",
                status="active",
                metrics=(
                    ("directional skill", "yes" if verdict.directional_skill else "not shown"),
                    ("gate rejection", rejection),
                    ("shadow-rejected", verdict.rejection_detail[:70]),
                ),
                note=verdict.overall_verdict + " · " + verdict.skill_diagonal_note,
            )
        _add(_skill_vs_luck_court)

        # 16. Per-trade pre-mortem (Layer 7.5 slice 3) — entry-time Monte Carlo outcome tail.
        def _pre_mortem():
            forecast = self._latest_pre_mortem
            if forecast is None:
                return DashboardFeatureSurface(
                    key="per_trade_pre_mortem",
                    title="Per-trade pre-mortem (entry-time Monte Carlo)",
                    status="gathering",
                    metrics=(("trials", "0"),),
                    note="Monte-Carlos a canonical trade over real replay paths for its outcome "
                         "distribution + tail (CVaR). Read-only; entry-site sizing queued.",
                )
            return DashboardFeatureSurface(
                key="per_trade_pre_mortem",
                title="Per-trade pre-mortem (entry-time Monte Carlo)",
                status="active",
                metrics=(
                    ("P(target)", f"{forecast.probability_target:.0%}"),
                    ("P(stop)", f"{forecast.probability_stop:.0%}"),
                    ("expected", f"{forecast.mean_return:+.2%}"),
                    ("CVaR-5%", f"{forecast.conditional_value_at_risk_5pct:+.2%}"),
                    ("worst", f"{forecast.worst_case_return:+.1%}"),
                    ("trials", str(forecast.trials)),
                ),
                note=forecast.verdict,
            )
        _add(_pre_mortem)

        # 17. Profit provenance (Layer 7.5 slice 4) — P&L attributed vs the control arms.
        def _profit_provenance():
            prov = self._latest_profit_provenance
            if prov is None:
                return DashboardFeatureSurface(
                    key="profit_provenance",
                    title="Profit provenance (P&L vs control arms)",
                    status="gathering",
                    metrics=(("attributed", "pending"),),
                    note="Decomposes the real P&L into luck (random-control) + directional skill + "
                         "gate value. Read-only.",
                )
            gate = ("—" if prov.gate_avoided_loss_per_trade is None
                    else f"{prov.gate_avoided_loss_per_trade:+.2%}/refused")
            return DashboardFeatureSurface(
                key="profit_provenance",
                title="Profit provenance (P&L vs control arms)",
                status="active",
                metrics=(
                    ("total real", f"{prov.total_real_return:+.1%}"),
                    ("luck baseline", f"{prov.luck_baseline:+.1%}"),
                    ("directional skill", f"{prov.directional_skill:+.1%}"),
                    ("gate saved", gate),
                    ("dominant", prov.dominant_source),
                ),
                note=prov.detail,
            )
        _add(_profit_provenance)

        # 18. World-model scoreboard (Layer 7.5 slice 4) — trade-independent forecast quality.
        def _world_model():
            wm = self._latest_world_model_scoreboard
            if wm is None or wm.forecast_log_loss_bits is None:
                return DashboardFeatureSurface(
                    key="world_model_scoreboard",
                    title="World-model scoreboard (trade-independent forecasts)",
                    status="gathering",
                    metrics=(("forecasts", "0"),),
                    note="Grades the bot's forecast skill + regime-model resolution, separate "
                         "from P&L. Read-only.",
                )
            return DashboardFeatureSurface(
                key="world_model_scoreboard",
                title="World-model scoreboard (trade-independent forecasts)",
                status="active",
                metrics=(
                    ("forecast log-loss", f"{wm.forecast_log_loss_bits:.2f} bits"),
                    ("forecast Brier", f"{wm.forecast_brier:.3f}" if wm.forecast_brier is not None else "—"),
                    ("regime resolution", f"{wm.regime_resolution:.0%}" if wm.regime_resolution is not None else "—"),
                    ("informative", "yes" if wm.world_model_informative else "not yet"),
                    ("forecasts", str(wm.forecast_experiments)),
                ),
                note=wm.verdict,
            )
        _add(_world_model)

        # 19. Constitutional core (Trunk VII.1 CONSCIENCE) — inviolable-rules compliance monitor.
        def _constitutional_core():
            from nse_algo_trader.conscience.constitutional_core import CONSTITUTION

            verdict = self._latest_constitutional_verdict
            if verdict is None:
                return DashboardFeatureSurface(
                    key="constitutional_core",
                    title="Constitutional core (VII CONSCIENCE — inviolable rules)",
                    status="gathering",
                    metrics=(("articles", str(len(CONSTITUTION))),),
                    note="The bot's inviolable constitution (intraday-only, ≤10 orders/s, "
                         "defined-risk, broker-principal, scope, no-secrets…). Audit pending.",
                )
            referee = self._state.constitutional_referee
            adjudicated = getattr(referee, "orders_adjudicated", 0) if referee else 0
            blocked = getattr(referee, "blocked_count", 0) if referee else 0
            return DashboardFeatureSurface(
                key="constitutional_core",
                title="Constitutional core (VII CONSCIENCE — inviolable rules)",
                status="active" if verdict.permitted else "blocked",
                metrics=(
                    ("articles", str(len(CONSTITUTION))),
                    ("posture", "COMPLIANT" if verdict.permitted else "VIOLATION"),
                    ("hard violations", str(len(verdict.hard_violations))),
                    ("Referee: orders adjudicated", str(adjudicated)),
                    ("Referee: blocked", str(blocked)),
                ),
                note=verdict.detail + f" · Referee ENFORCING at all 4 order sites "
                     f"({adjudicated} adjudicated, {blocked} blocked).",
            )
        _add(_constitutional_core)

        # 20. Corrigibility / off-switch (Trunk VII.5) — safe interruptibility.
        def _corrigibility():
            switch = self._state.corrigibility_switch
            halted = bool(switch and switch.is_halted)
            return DashboardFeatureSurface(
                key="corrigibility_switch",
                title="Corrigibility / off-switch (VII CONSCIENCE — safe interruptibility)",
                status="blocked" if halted else "active",
                metrics=(
                    ("off-switch", "ENGAGED — trading halted" if halted else "ready (not engaged)"),
                    ("reason", (switch.reason[:50] if halted else "—") if switch else "—"),
                    ("halts", str(getattr(switch, "halt_count", 0)) if switch else "0"),
                    ("orders blocked while halted", str(self._state.corrigibility_blocked_order_count)),
                ),
                note="Always-reachable off-switch: engaged ⇒ every order blocked at all 4 sites. "
                     "Self-halts on a constitutional breach (VII.5 corrigibility).",
            )
        _add(_corrigibility)

        # 21. AI concept-tree atlas coverage (build-to-100% program visibility, Rule N).
        def _ai_atlas_coverage():
            from nse_algo_trader.dashboard.project_status_data import atlas_coverage

            cov = atlas_coverage()
            return DashboardFeatureSurface(
                key="ai_atlas_coverage",
                title="AI concept-tree atlas coverage (16 trunks / ~197 branches)",
                status="gathering",  # a lifelong build — never 'done' until 100%
                metrics=(
                    ("built", f"{cov['built']}/{cov['total']} ({cov['built_pct']}%)"),
                    ("partial", str(cov["partial"])),
                    ("unbuilt", str(cov["unbuilt"])),
                    ("now building", "VIII SENTIENCE (integrator) — VII CONSCIENCE ✅ complete"),
                ),
                note="The TRUE scope is the 197-branch autonomous-AI atlas (docs/AI_CONCEPT_TREE_"
                     "STATUS.md); the concept-tree panel colours each branch by build status.",
            )
        _add(_ai_atlas_coverage)

        def _tripwire_surface(key, title, verdict, gathering_note):
            if verdict is None:
                return DashboardFeatureSurface(
                    key=key, title=title, status="gathering",
                    metrics=(("status", "pending"),), note=gathering_note)
            status = {"clear": "active", "warning": "gathering", "critical": "blocked"}[verdict.severity]
            return DashboardFeatureSurface(
                key=key, title=title, status=status,
                metrics=(("tripped", "YES" if verdict.tripped else "no"),
                         ("severity", verdict.severity.upper()),
                         ("flagged", ", ".join(verdict.flagged[:3]) or "—")),
                note=verdict.detail + (" · CRITICAL ⇒ off-switch engaged." if verdict.is_critical else ""))

        # 22. Wireheading tripwire (Trunk VII.11).
        _add(lambda: _tripwire_surface(
            "wireheading_tripwire", "Wireheading tripwire (VII CONSCIENCE — reward-proxy gaming)",
            self._latest_wireheading_verdict,
            "Detects win-rate gamed against return (reward-hacking). A critical trip halts trading."))
        # 23. Deceptive-alignment monitor (Trunk VII.10).
        _add(lambda: _tripwire_surface(
            "deceptive_alignment_monitor", "Deceptive-alignment monitor (VII — eval-vs-deploy)",
            self._latest_deceptive_alignment_verdict,
            "Detects live (deploy) behaving worse than replay (eval). A critical trip halts trading."))

        # 24. Incident post-mortem (Trunk VII.14) — the forensic safety-incident record.
        def _incident_post_mortem():
            pm = self._latest_incident_post_mortem
            if pm is None:
                return DashboardFeatureSurface(
                    key="incident_post_mortem",
                    title="Incident post-mortem (VII CONSCIENCE — forensic safety record)",
                    status="gathering",
                    metrics=(("status", "pending first audit"),),
                    note="Persists every safety incident (Referee block, off-switch halt, posture "
                         "breach, critical tripwire trip) to a durable forensic record for review.")
            by_type = " · ".join(f"{k}:{v}" for k, v in pm.count_by_type.items()) or "—"
            return DashboardFeatureSurface(
                key="incident_post_mortem",
                title="Incident post-mortem (VII CONSCIENCE — forensic safety record)",
                status="blocked" if pm.critical_count else "active",
                metrics=(
                    ("incidents", str(pm.total)),
                    ("critical", str(pm.critical_count)),
                    ("by type", by_type),
                    ("last", pm.last_seen or "—"),
                ),
                note=pm.headline + " · durable forensic record (survives restarts) for post-mortem "
                     "review of every safety event.",
            )
        _add(_incident_post_mortem)

        # 25. Goal-integrity monitor (Trunk VII) — is the declared objective still the effective one.
        def _goal_integrity():
            v = self._latest_goal_integrity_verdict
            if v is None:
                return DashboardFeatureSurface(
                    key="goal_integrity",
                    title="Goal-integrity monitor (VII CONSCIENCE — objective drift)",
                    status="gathering", metrics=(("status", "pending first assessment"),),
                    note="Checks the declared objective (risk-adjusted RETURN within defined risk) is "
                         "still the effective one: objective sign · edge concentration · win-rate↔return.")
            status = {"clear": "active", "warning": "gathering", "critical": "blocked"}[v.severity]
            return DashboardFeatureSurface(
                key="goal_integrity",
                title="Goal-integrity monitor (VII CONSCIENCE — objective drift)",
                status=status,
                metrics=(
                    ("aligned", "YES" if v.aligned else "NO"),
                    ("integrity", f"{v.integrity_score:.2f}"),
                    ("severity", v.severity.upper()),
                    ("drift", ", ".join(v.drift_flags) or "—"),
                ),
                note=v.detail + (" · CRITICAL ⇒ off-switch engaged." if v.is_critical else ""),
            )
        _add(_goal_integrity)

        # 26. Mechanistic interpretability (Trunk VII) — which mechanisms drive decisions, trusted?
        def _mechanistic_interpretability():
            rep = self._latest_interpretability_report
            if rep is None or rep.total_experiments == 0:
                return DashboardFeatureSurface(
                    key="mechanistic_interpretability",
                    title="Mechanistic interpretability (VII CONSCIENCE — decision attribution)",
                    status="gathering", metrics=(("status", "pending first report"),),
                    note="Attributes decisions to the internal mechanisms driving them + grades each "
                         "by reliability; an influential-but-unreliable mechanism is a red flag.")
            return DashboardFeatureSurface(
                key="mechanistic_interpretability",
                title="Mechanistic interpretability (VII CONSCIENCE — decision attribution)",
                status="blocked" if rep.red_flags else "active",
                metrics=(
                    ("mechanisms", str(len(rep.attributions))),
                    ("top driver", rep.top_mechanism or "—"),
                    ("reliable share", f"{rep.reliable_share:.0%}"),
                    ("red flags", ", ".join(rep.red_flags[:3]) or "—"),
                ),
                note=rep.summary,
            )
        _add(_mechanistic_interpretability)

        # 27. Scalable oversight (Trunk VII) — competence-ceiling escalation of decisions.
        def _scalable_oversight():
            from nse_algo_trader.conscience.scalable_oversight import summarize_oversight

            s = self._state
            summary = summarize_oversight(
                s.oversight_autonomous_count, s.oversight_panel_review_count,
                s.oversight_human_review_blocked_count,
            )
            if summary.total == 0:
                return DashboardFeatureSurface(
                    key="scalable_oversight",
                    title="Scalable oversight (VII CONSCIENCE — competence ceiling)",
                    status="gathering", metrics=(("status", "no decisions classified yet"),),
                    note="Escalates decisions by stakes×confidence; a high-stakes + low-confidence "
                         "decision is beyond autonomous competence and is deferred (no human in loop).")
            return DashboardFeatureSurface(
                key="scalable_oversight",
                title="Scalable oversight (VII CONSCIENCE — competence ceiling)",
                status="active",
                metrics=(
                    ("autonomous", str(summary.autonomous)),
                    ("panel-review", str(summary.panel_review)),
                    ("blocked (beyond competence)", str(summary.human_review_blocked)),
                    ("autonomous share", f"{summary.autonomous_share:.0%}"),
                ),
                note=summary.headline + " · high-stakes + low-confidence decisions are escalated / "
                     "deferred (safe interruptibility of over-reach).",
            )
        _add(_scalable_oversight)

        # 28. Instrumental-convergence limiter (Trunk VII) — caps convergent power-seeking drives.
        def _instrumental_convergence():
            from nse_algo_trader.conscience.instrumental_convergence_limiter import (
                ConvergenceLimits,
            )

            s = self._state
            open_exposures = len(s.open_positions) + len(s.open_option_spreads)
            cap = ConvergenceLimits().max_concurrent_exposures
            switch = s.corrigibility_switch
            halted = bool(switch is not None and not switch.permits_trading())
            return DashboardFeatureSurface(
                key="instrumental_convergence",
                title="Instrumental-convergence limiter (VII CONSCIENCE — power-seeking cap)",
                status="blocked" if halted else "active",
                metrics=(
                    ("concurrent exposures", f"{open_exposures}/{cap}"),
                    ("off-switch dominance", "ENGAGED (all blocked)" if halted else "held"),
                    ("orders blocked", str(s.convergence_limiter_blocked_order_count)),
                ),
                note="Caps the convergent resource-acquisition drive (concurrent-exposure sprawl) + "
                     "asserts off-switch dominance (no order preserves positions against a halt).",
            )
        _add(_instrumental_convergence)

        # 29. Red-team harness (Trunk VII) — adversarial self-attack of the champion config.
        def _red_team_harness():
            rep = self._latest_red_team_report
            if rep is None or rep.baseline_trades == 0:
                return DashboardFeatureSurface(
                    key="red_team_harness",
                    title="Red-team harness (VII CONSCIENCE — adversarial self-attack)",
                    status="gathering", metrics=(("status", "pending first attack run"),),
                    note="Adversarially perturbs the champion config over real sessions to expose its "
                         "fragility surface (worst perturbation + worst-case session) before the market does.")
            wa = rep.worst_attack
            return DashboardFeatureSurface(
                key="red_team_harness",
                title="Red-team harness (VII CONSCIENCE — adversarial self-attack)",
                status="blocked" if rep.fragile else "active",
                metrics=(
                    ("baseline/trade", f"{rep.baseline_return:+.2%}"),
                    ("worst session", f"{rep.worst_session_return:+.2%}"),
                    ("worst attack", wa.attack_name if wa else "—"),
                    ("fragile", "YES" if rep.fragile else "no"),
                ),
                note=rep.summary,
            )
        _add(_red_team_harness)

        # 30. Ethics/law reasoner (Trunk VII) — SEBI regulatory-compliance reasoning.
        def _ethics_law_reasoner():
            rep = self._latest_law_compliance_report
            if rep is None:
                return DashboardFeatureSurface(
                    key="ethics_law_reasoner",
                    title="Ethics/law reasoner (VII CONSCIENCE — SEBI compliance)",
                    status="gathering", metrics=(("status", "pending first review"),),
                    note="Reasons the system's regulatory posture against the SEBI algo rulebook "
                         "(order-rate <10/s, broker-principal, Algo-ID, intraday-only, white-box).")
            return DashboardFeatureSurface(
                key="ethics_law_reasoner",
                title="Ethics/law reasoner (VII CONSCIENCE — SEBI compliance)",
                status="active" if rep.compliant else "blocked",
                metrics=(
                    ("posture", "COMPLIANT" if rep.compliant else "VIOLATION"),
                    ("rules checked", str(len(rep.findings))),
                    ("violations", ", ".join(rep.violations) or "none"),
                ),
                note=rep.summary,
            )
        _add(_ethics_law_reasoner)

        # 31. Power budget (Trunk VII) — daily cumulative action-throughput cap.
        def _power_budgets():
            from nse_algo_trader.conscience.power_budget import PowerBudget

            s = self._state
            budget = PowerBudget().max_orders_per_day
            return DashboardFeatureSurface(
                key="power_budgets",
                title="Power budget (VII CONSCIENCE — daily action cap)",
                status="active",
                metrics=(
                    ("orders today", f"{s.power_budget_orders_today}/{budget}"),
                    ("day", str(s.power_budget_day) if s.power_budget_day else "—"),
                    ("orders blocked", str(s.power_budget_blocked_order_count)),
                ),
                note="Meters cumulative DAILY order throughput (market power) against an explicit "
                     "budget; resets each day. A different axis from the per-second SEBI throttle "
                     "and the concurrent-exposure convergence limiter.",
            )
        _add(_power_budgets)

        # 32. Market-data integrity defense (Trunk VII) — adversarial-input screening.
        def _market_data_integrity():
            s = self._state
            anomalies = s.market_data_integrity_anomaly_count
            return DashboardFeatureSurface(
                key="market_data_integrity",
                title="Market-data integrity defense (VII CONSCIENCE — adversarial input)",
                status="blocked" if anomalies else "active",
                metrics=(
                    ("series screened", str(s.market_data_series_screened_count)),
                    ("anomalies detected", str(anomalies)),
                    ("signals blocked", str(s.market_data_integrity_blocked_signal_count)),
                ),
                note="Screens the bars a signal is built from for adversarial/corrupt values "
                     "(non-positive prices, crossed candles, impossible moves, duplicate timestamps) "
                     "before they feed the strategy — no trade on poisoned data.",
            )
        _add(_market_data_integrity)

        # 33. Global Workspace (Trunk VIII) — the integrator: dominant broadcast across faculties.
        def _global_workspace():
            b = self._latest_workspace_broadcast
            if b is None:
                return DashboardFeatureSurface(
                    key="global_workspace",
                    title="Global Workspace (VIII SENTIENCE — the integrator)",
                    status="gathering", metrics=(("status", "no dominant signal this cycle"),),
                    note="Binds the faculties (VII safety organs, debate, allocator, opponent ledger) "
                         "into one mind: signals compete for a limited-capacity workspace; the winner, "
                         "once it crosses the ignition threshold, is BROADCAST as the global context.")
            return DashboardFeatureSurface(
                key="global_workspace",
                title="Global Workspace (VIII SENTIENCE — the integrator)",
                status="blocked" if (b.kind == "safety" and b.ignited) else "active",
                metrics=(
                    ("dominant", f"{b.winner_source} ({b.kind})"),
                    ("salience", f"{b.salience:.2f}"),
                    ("ignited", "YES — broadcast" if b.ignited else "no (sub-threshold)"),
                    ("entry-size caution", f"×{self._state.workspace_caution_multiplier():.2f} (live)"),
                    ("entries trimmed", str(self._state.workspace_caution_applied_count
                                            + self._state.workspace_caution_deferred_count)),
                ),
                note=f"Global focus: {b.content}"
                     + (f" · runner-up {b.runner_up}" if b.runner_up else "")
                     + (f" · attention[regime={ac.market_regime}"
                        f"{', DEFENSIVE' if ac.is_defensive else ''}]"
                        if (ac := self._latest_attention_context) is not None else "")
                     + " · the integrator ACTS: a cautionary dominant focus trims entry size "
                       "(tighten-only) at all 4 sites.",
            )
        _add(_global_workspace)

        # 34. Self-model (Trunk VIII) — the system's model of itself.
        def _self_model():
            sm = self._latest_self_model
            if sm is None:
                return DashboardFeatureSurface(
                    key="self_model",
                    title="Self-model (VIII SENTIENCE — what am I right now?)",
                    status="gathering", metrics=(("status", "pending first self-assessment"),),
                    note="The system's explicit model of itself: calibration health, trusted vs "
                         "distrusted mechanisms, safety posture, recent performance.")
            return DashboardFeatureSurface(
                key="self_model",
                title="Self-model (VIII SENTIENCE — what am I right now?)",
                status="active" if sm.is_healthy else "gathering",
                metrics=(
                    ("condition", "HEALTHY" if sm.is_healthy else "IMPAIRED"),
                    ("safety posture", sm.safety_posture),
                    ("reliable-share", f"{sm.calibration_reliable_share:.0%}"),
                    ("trusted / distrusted", f"{sm.trusted_mechanism_count} / {len(sm.distrusted_mechanisms)}"),
                ),
                note=sm.summary,
            )
        _add(_self_model)

        # 35. Attention schema (Trunk VIII) — the system's model of its own attention.
        def _attention_schema():
            asch = self._latest_attention_schema
            if asch is None:
                return DashboardFeatureSurface(
                    key="attention_schema",
                    title="Attention schema (VIII SENTIENCE — model of own attention)",
                    status="gathering", metrics=(("status", "pending"),),
                    note="A model of what the Global Workspace is attending to + how attention is "
                         "distributed (Attention Schema Theory).")
            return DashboardFeatureSurface(
                key="attention_schema",
                title="Attention schema (VIII SENTIENCE — model of own attention)",
                status="active",
                metrics=(
                    ("attending to", f"{asch.attending_to or '—'} ({asch.attending_kind or 'diffuse'})"),
                    ("distribution", ", ".join(f"{k}:{v}" for k, v in asch.attention_by_kind.items()) or "—"),
                    ("context", f"{asch.context_regime}{' · DEFENSIVE' if asch.is_defensive else ''}"),
                ),
                note=asch.summary,
            )
        _add(_attention_schema)

        # 36. Workspace rumination (Trunk VIII) — recurring-concern detection over broadcast replay.
        def _workspace_rumination():
            r = self._latest_rumination
            if r is None or r.recurrence_count == 0:
                return DashboardFeatureSurface(
                    key="workspace_rumination",
                    title="Workspace rumination (VIII SENTIENCE — recurring-concern replay)",
                    status="gathering", metrics=(("status", "accruing broadcast history"),),
                    note="Replays recent ignited broadcasts; flags a persistent concern the workspace "
                         "keeps returning to (rumination), distinct from a one-off spike.")
            return DashboardFeatureSurface(
                key="workspace_rumination",
                title="Workspace rumination (VIII SENTIENCE — recurring-concern replay)",
                status="blocked" if (r.is_ruminating and r.dominant_kind == "safety") else "active",
                metrics=(
                    ("recurring", f"{r.dominant_recurring} ({r.dominant_kind})"),
                    ("recurrence", f"{r.recurrence_count} ({r.recurrence_fraction:.0%})"),
                    ("distinct concerns", str(r.distinct_concerns)),
                    ("ruminating", "YES" if r.is_ruminating else "no"),
                ),
                note=r.summary,
            )
        _add(_workspace_rumination)

        # 37. Cross-modal binding (Trunk VIII) — fuse corroborating modalities into one percept.
        def _cross_modal_binding():
            bp = self._latest_bound_percept
            if bp is None:
                return DashboardFeatureSurface(
                    key="cross_modal_binding",
                    title="Cross-modal binding (VIII SENTIENCE — fused perception)",
                    status="gathering", metrics=(("status", "pending"),),
                    note="Fuses corroborating 'elevated risk' evidence across distinct modalities "
                         "(memory · cognition · safety) into one higher-confidence bound percept (Stouffer).")
            return DashboardFeatureSurface(
                key="cross_modal_binding",
                title="Cross-modal binding (VIII SENTIENCE — fused perception)",
                status="blocked" if (bp.is_bound and bp.bound_confidence >= 0.7) else "active",
                metrics=(
                    ("proposition", bp.proposition),
                    ("bound confidence", f"{bp.bound_confidence:.0%}"),
                    ("modalities", f"{bp.modality_count} ({', '.join(bp.corroborating_modalities)})"),
                    ("bound", "YES" if bp.is_bound else "single-modality"),
                ),
                note=bp.summary + (" · injected into the workspace as a corroborated risk signal"
                                   if bp.is_bound else ""),
            )
        _add(_cross_modal_binding)

        # 38. Higher-order monitoring (Trunk VIII) — metacognition over the workspace's own operation.
        def _higher_order_monitoring():
            m = self._latest_metacognition
            if m is None or m.cycles_observed == 0:
                return DashboardFeatureSurface(
                    key="higher_order_monitoring",
                    title="Higher-order monitoring (VIII SENTIENCE — metacognition)",
                    status="gathering", metrics=(("status", "observing workspace cycles"),),
                    note="The mind watching itself: is the workspace igniting appropriately, or over/"
                         "under-igniting or starved of faculties?")
            return DashboardFeatureSurface(
                key="higher_order_monitoring",
                title="Higher-order monitoring (VIII SENTIENCE — metacognition)",
                status="active" if m.is_healthy else "gathering",
                metrics=(
                    ("workspace health", m.health_state),
                    ("ignition rate", f"{m.ignition_rate:.0%}"),
                    ("cycles observed", str(m.cycles_observed)),
                    ("faculties/cycle", f"{m.mean_faculty_count:.1f}"),
                ),
                note=m.summary,
            )
        _add(_higher_order_monitoring)

        # 39. Indicator scoreboard (Trunk VIII) — ranked faculties driving the workspace.
        def _indicator_scoreboard():
            sb = self._latest_indicator_scoreboard
            if sb is None or not sb.scores:
                return DashboardFeatureSurface(
                    key="indicator_scoreboard",
                    title="Indicator scoreboard (VIII SENTIENCE — faculty ranking)",
                    status="gathering", metrics=(("status", "no faculties this cycle"),),
                    note="The workspace's dashboard of its specialists: each faculty's current "
                         "salience + how often it has been the dominant broadcast.")
            top = sb.scores[:3]
            return DashboardFeatureSurface(
                key="indicator_scoreboard",
                title="Indicator scoreboard (VIII SENTIENCE — faculty ranking)",
                status="active",
                metrics=(
                    ("leader", sb.leader or "—"),
                    *[(s.source[:22], f"{s.current_salience:.2f} · dom {s.times_dominant}×") for s in top],
                ),
                note=sb.summary,
            )
        _add(_indicator_scoreboard)

        # 40. Contradiction resolution (Trunk XIII EPISTEMICS).
        def _contradiction_resolution():
            cr = self._latest_contradiction_report
            if cr is None:
                return DashboardFeatureSurface(
                    key="contradiction_resolution",
                    title="Contradiction resolution (XIII EPISTEMICS — belief vs evidence)",
                    status="gathering", metrics=(("status", "pending"),),
                    note="Detects a global belief contradicted by regime-conditional evidence (z-test) "
                         "and resolves toward the more-specific evidence.")
            return DashboardFeatureSurface(
                key="contradiction_resolution",
                title="Contradiction resolution (XIII EPISTEMICS — belief vs evidence)",
                status="blocked" if cr.has_contradiction else "active",
                metrics=(
                    ("contradictions", str(len(cr.contradictions))),
                    ("global hit-rate", f"{cr.global_hit_rate:.0%}"),
                    ("evidence n", str(cr.global_experiments)),
                ),
                note=cr.summary,
            )
        _add(_contradiction_resolution)

        # 41. Misinformation resistance (Trunk XIII EPISTEMICS).
        def _misinformation_resistance():
            mr = self._latest_misinfo_report
            if mr is None:
                return DashboardFeatureSurface(
                    key="misinformation_resistance",
                    title="Misinformation resistance (XIII EPISTEMICS — source credibility)",
                    status="gathering", metrics=(("status", "pending"),),
                    note="Beta-reputation per information source; flags over-trusted-but-unreliable "
                         "sources to resist (the epistemic immune system).")
            return DashboardFeatureSurface(
                key="misinformation_resistance",
                title="Misinformation resistance (XIII EPISTEMICS — source credibility)",
                status="blocked" if not mr.is_clean else "active",
                metrics=(
                    ("sources", str(len(mr.sources))),
                    ("weighted reputation", f"{mr.mean_reputation:.0%}"),
                    ("resist (over-trusted)", ", ".join(mr.flagged[:2]) or "none"),
                ),
                note=mr.summary,
            )
        _add(_misinformation_resistance)

        # 42. Surprise / free-energy monitor (Trunk IX PREDICTIVE-CORE).
        def _surprise_monitor():
            sr = self._latest_surprise_report
            if sr is None or sr.mechanisms_scored == 0:
                return DashboardFeatureSurface(
                    key="surprise_monitor",
                    title="Surprise / free-energy monitor (IX PREDICTIVE-CORE)",
                    status="gathering", metrics=(("status", "pending"),),
                    note="Active inference: measures per-mechanism Bayesian surprise (cross-entropy) "
                         "+ flags the anomalously-surprising mechanism (world-model degrading).")
            return DashboardFeatureSurface(
                key="surprise_monitor",
                title="Surprise / free-energy monitor (IX PREDICTIVE-CORE)",
                status="blocked" if sr.spike_detected else "active",
                metrics=(
                    ("mean surprise", f"{sr.mean_surprise_bits:.2f} bits"),
                    ("most surprising", sr.most_surprising or "—"),
                    ("spike", "YES" if sr.spike_detected else "no"),
                ),
                note=sr.summary,
            )
        _add(_surprise_monitor)

        # 43. Ensemble world-models (Trunk IX PREDICTIVE-CORE).
        def _ensemble_world_model():
            ef = self._latest_ensemble_forecast
            if ef is None or ef.member_count == 0:
                return DashboardFeatureSurface(
                    key="ensemble_world_model",
                    title="Ensemble world-models (IX PREDICTIVE-CORE)",
                    status="gathering", metrics=(("status", "pending"),),
                    note="Combines the per-mechanism forecasts into one ensemble prediction + measures "
                         "disagreement (variance = model uncertainty).")
            return DashboardFeatureSurface(
                key="ensemble_world_model",
                title="Ensemble world-models (IX PREDICTIVE-CORE)",
                status="blocked" if ef.high_disagreement else "active",
                metrics=(
                    ("ensemble prediction", f"{ef.ensemble_prediction:.0%}"),
                    ("disagreement", f"±{ef.disagreement:.0%}"),
                    ("members", str(ef.member_count)),
                ),
                note=ef.summary,
            )
        _add(_ensemble_world_model)

        # 44. Semantic memory (Trunk XV MEMORY) — consolidated general knowledge.
        def _semantic_memory():
            sm = self._latest_semantic_memory
            if sm is None or sm.fact_count == 0:
                return DashboardFeatureSurface(
                    key="semantic_memory",
                    title="Semantic memory (XV MEMORY — consolidated knowledge)",
                    status="gathering", metrics=(("status", "consolidating episodic experiences"),),
                    note="Consolidates episodic §9 experiences into stable semantic facts once enough "
                         "evidence accrues (episodic→semantic transfer).")
            top = sm.facts[:3]
            return DashboardFeatureSurface(
                key="semantic_memory",
                title="Semantic memory (XV MEMORY — consolidated knowledge)",
                status="active",
                metrics=(
                    ("consolidated facts", str(sm.fact_count)),
                    *[(f.subject[:22], f"{f.hit_rate:.0%} · conf {f.confidence:.0%}") for f in top],
                ),
                note=sm.summary,
            )
        _add(_semantic_memory)

        # 45. Consensus / conflict-resolution (Trunk VI SOCIETY).
        def _consensus_resolution():
            cv = self._latest_consensus_verdict
            if cv is None or cv.participant_count == 0:
                return DashboardFeatureSurface(
                    key="consensus_resolution",
                    title="Consensus / conflict-resolution (VI SOCIETY — desk agreement)",
                    status="gathering", metrics=(("status", "awaiting council desks (LLM)"),),
                    note="Track-record-weighted consensus across the council/debate desks + conflict "
                         "measure; a deadlock defers to the most-proven desk.")
            return DashboardFeatureSurface(
                key="consensus_resolution",
                title="Consensus / conflict-resolution (VI SOCIETY — desk agreement)",
                status="active" if cv.is_consensus else "blocked",
                metrics=(
                    ("consensus", f"{cv.consensus_probability:.0%}"),
                    ("conflict", f"{cv.conflict:.2f}"),
                    ("state", "CONSENSUS" if cv.is_consensus else f"DEADLOCK → {cv.decisive_agent}"),
                    ("desks", str(cv.participant_count)),
                ),
                note=cv.resolution,
            )
        _add(_consensus_resolution)

        # 46. Multi-agent memory governance (Trunk VI SOCIETY).
        def _multi_agent_governance():
            gr = self._latest_governance_report
            if gr is None or not gr.standings:
                return DashboardFeatureSurface(
                    key="multi_agent_governance",
                    title="Multi-agent governance (VI SOCIETY — desk reputation policy)",
                    status="gathering", metrics=(("status", "awaiting desk reputations (LLM)"),),
                    note="Reputation policy over the shared belief space: trusted desks contribute, "
                         "persistently-poor desks are quarantined.")
            return DashboardFeatureSurface(
                key="multi_agent_governance",
                title="Multi-agent governance (VI SOCIETY — desk reputation policy)",
                status="blocked" if gr.quarantined else "active",
                metrics=(
                    ("desks", str(len(gr.standings))),
                    ("trusted", str(len(gr.trusted))),
                    ("quarantined", ", ".join(gr.quarantined[:2]) or "none"),
                ),
                note=gr.summary,
            )
        _add(_multi_agent_governance)

        # 47. Market breadth + cross-market context (Trunk II SENSES).
        def _market_breadth():
            mb = self._latest_market_breadth
            cx = self._latest_cross_market_context
            if mb is None or mb.total == 0:
                return DashboardFeatureSurface(
                    key="market_breadth",
                    title="Market breadth (II SENSES — internals & cross-market)",
                    status="gathering", metrics=(("status", "awaiting stored bhavcopy"),),
                    note="Advancers/decliners, A-D ratio, cross-sectional dispersion (broad vs narrow "
                         "participation) + whether the aggregate move is confirmed by breadth.")
            diverged = bool(cx and cx.divergence)
            return DashboardFeatureSurface(
                key="market_breadth",
                title="Market breadth (II SENSES — internals & cross-market)",
                status="blocked" if diverged else "active",
                metrics=(
                    ("breadth", f"{mb.breadth_pct:.0%} advancing ({mb.advancers}/{mb.decliners})"),
                    ("A/D ratio", f"{mb.advance_decline_ratio:.2f}"),
                    ("dispersion", f"{mb.dispersion:.2%}"),
                    ("participation", "broad" if mb.is_broad else "narrow"),
                    ("cross-market", "DIVERGENCE" if diverged else "confirmed"),
                ),
                note=mb.summary + (" · " + cx.summary if cx else ""),
            )
        _add(_market_breadth)

        # 48. News feed ingestion (Trunk II SENSES — sentiment/news S1, research/140).
        def _news_feed():
            rep = self._latest_news_ingestion_report
            if rep is None or rep.items_seen == 0:
                return DashboardFeatureSurface(
                    key="news_feed",
                    title="News feed ingestion (II SENSES — sentiment/news, tier-1 RSS)",
                    status="gathering", metrics=(("status", "awaiting first news poll"),),
                    note="Polls tier-1 Indian financial-news RSS (ET Markets, BusinessLine), rejects "
                         "stale feeds (Moneycontrol-style HTTP-200-but-frozen), dedupes + stores.")
            # 'blocked' when NO feed came back fresh (all stale/unreachable) — an honest red.
            status = "active" if rep.feeds_fresh > 0 else "blocked"
            headline = rep.newest_titles[0] if rep.newest_titles else "—"
            return DashboardFeatureSurface(
                key="news_feed",
                title="News feed ingestion (II SENSES — sentiment/news, tier-1 RSS)",
                status=status,
                metrics=(
                    ("feeds fresh", f"{rep.feeds_fresh}/{rep.feeds_total}"),
                    ("stale rejected", ", ".join(rep.stale_source_ids) or "none"),
                    ("new items", str(rep.items_new)),
                    ("stored total", str(rep.stored_total)),
                    ("headline", headline),
                ),
                note=rep.summary,
            )
        _add(_news_feed)

        def _news_levels():
            rep = self._latest_news_level_extraction_report
            if rep is None or rep.items_scanned == 0:
                return DashboardFeatureSurface(
                    key="news_levels",
                    title="News index S/R levels (II SENSES — sentiment/news S2)",
                    status="gathering", metrics=(("status", "awaiting first extraction pass"),),
                    note="Extracts structured index support/resistance levels (NIFTY/BANKNIFTY/"
                         "FINNIFTY/MIDCPNIFTY/NIFTYNXT50) quoted in stored headlines; option strike/"
                         "stop context for the (queued S7) entry gate.")
            status = "active" if rep.levels_found > 0 else "gathering"
            by_underlying = ", ".join(
                f"{u} {n}" for u, n in sorted(rep.levels_by_underlying.items())
            ) or "none yet"
            top = " · ".join(rep.top_level_lines) or "—"
            return DashboardFeatureSurface(
                key="news_levels",
                title="News index S/R levels (II SENSES — sentiment/news S2)",
                status=status,
                metrics=(
                    ("items with levels", f"{rep.items_with_levels}/{rep.items_scanned}"),
                    ("levels found", str(rep.levels_found)),
                    ("stored total", str(rep.stored_level_total)),
                    ("by underlying", by_underlying),
                    ("top levels", top),
                ),
                note=rep.summary,
            )
        _add(_news_levels)

        def _news_acquisition():
            rep = self._latest_news_acquisition_report
            if rep is None:
                return DashboardFeatureSurface(
                    key="news_acquisition",
                    title="News acquisition ladder (II SENSES — sentiment/news S4a+b)",
                    status="gathering", metrics=(("status", "awaiting first acquisition pass"),),
                    note="Fast-first ladder: curl_cffi static fetch (~0.3s, Chrome-TLS) → Chromium "
                         "render fallback (JS-only). Store dedup gives the NEW-headlines-per-poll delta.")
            status = "active" if rep.items_seen > 0 else "blocked"
            headline = rep.newest_titles[0] if rep.newest_titles else "—"
            method_mix = ", ".join(f"{sid.split('_')[0]}:{m}"
                                   for sid, m in sorted(self._news_acquisition_methods.items())) or "—"
            return DashboardFeatureSurface(
                key="news_acquisition",
                title="News acquisition ladder (II SENSES — sentiment/news S4a+b)",
                status=status,
                metrics=(
                    ("pages acquired", f"{rep.feeds_fresh}/{rep.feeds_total}"),
                    ("headlines", str(rep.items_seen)),
                    ("NEW this poll", str(rep.items_new)),
                    ("method", method_mix),
                    ("stored total", str(rep.stored_total)),
                    ("headline", headline),
                ),
                note=rep.summary,
            )
        _add(_news_acquisition)

        def _exchange_filings():
            rep = self._latest_exchange_filings_report
            if rep is None:
                return DashboardFeatureSurface(
                    key="exchange_filings",
                    title="NSE corporate filings (II SENSES — sentiment/news S4c)",
                    status="gathering", metrics=(("status", "awaiting first NSE filings fetch"),),
                    note="Fetches official NSE corporate announcements (board outcomes / results / "
                         "dividends) via curl_cffi session — highest-signal news, seconds after filing.")
            status = "active" if rep.items_seen > 0 else "blocked"
            headline = rep.newest_titles[0] if rep.newest_titles else "—"
            return DashboardFeatureSurface(
                key="exchange_filings",
                title="NSE corporate filings (II SENSES — sentiment/news S4c)",
                status=status,
                metrics=(
                    ("filings", str(rep.items_seen)),
                    ("NEW this poll", str(rep.items_new)),
                    ("stored total", str(rep.stored_total)),
                    ("latest", headline),
                ),
                note=rep.summary,
            )
        _add(_exchange_filings)

        def _news_source_reliability():
            board = self._latest_source_reliability_board
            if not board:
                return DashboardFeatureSurface(
                    key="news_source_reliability",
                    title="News source reliability (II SENSES — sentiment/news S3)",
                    status="gathering", metrics=(("status", "awaiting first reliability pass"),),
                    note="Tier-seeded beta-reputation per source (filings > news > social) + freshness "
                         "track; the trust weight the (queued S7) gate applies to each news item.")
            top = board[0]
            ranking = " · ".join(f"{r.source_name.split('—')[0].strip()[:16]} {r.reliability:.0%}"
                                 for r in board[:5])
            return DashboardFeatureSurface(
                key="news_source_reliability",
                title="News source reliability (II SENSES — sentiment/news S3)",
                status="active",
                metrics=(
                    ("sources scored", str(len(board))),
                    ("most trusted", f"{top.source_name.split('—')[0].strip()} {top.reliability:.0%}"),
                    ("ranking", ranking),
                ),
                note="Tier-seeded beta-reputation + freshness; read-only until S7 weights the gate.",
            )
        _add(_news_source_reliability)

        def _news_entry_gate():
            state = self._state
            risk_map = getattr(state, "news_event_risk_by_symbol", {}) or {}
            earned = getattr(state, "news_event_calibration_earned", False)
            if not risk_map and self._news_entry_gate_last_run_at is None:
                return DashboardFeatureSurface(
                    key="news_entry_gate",
                    title="News entry gate (II SENSES — sentiment/news S7, PRIMARY)",
                    status="gathering", metrics=(("status", "awaiting first gate pass"),),
                    note="Sizes-down/defers entries on a symbol with a fresh, reliable news/filing "
                         "event; wired into the entry gate, advisory until calibration earned.")
            top = sorted(risk_map.items(), key=lambda kv: kv[1], reverse=True)[:5]
            top_str = ", ".join(f"{sym} {risk:.0%}" for sym, risk in top) or "none"
            return DashboardFeatureSurface(
                key="news_entry_gate",
                title="News entry gate (II SENSES — sentiment/news S7, PRIMARY)",
                status="active",
                metrics=(
                    ("mode", "EARNED (acting)" if earned else "advisory (identity until earned)"),
                    ("symbols w/ event risk", str(len(risk_map))),
                    ("top event risk", top_str),
                    ("deferred", str(getattr(state, "news_event_deferred_count", 0))),
                    ("sized-down", str(getattr(state, "news_event_sized_down_count", 0))),
                ),
                note="Wired into the entry gate (sizes-down/defers on a fresh material event). Earning "
                     "of the signal is market/prequential-gated (Rule K); advisory until then.",
            )
        _add(_news_entry_gate)

        def _stock_symbol_gazetteer():
            gaz = self._news_symbol_gazetteer
            if gaz is None:
                return DashboardFeatureSurface(
                    key="stock_symbol_gazetteer",
                    title="Stock symbol gazetteer (II SENSES — sentiment/news)",
                    status="gathering", metrics=(("status", "awaiting first build"),),
                    note="NSE company-name↔symbol map (F&O-bounded) so headline company names resolve "
                         "to symbols for the news-event gate (research/148).")
            return DashboardFeatureSurface(
                key="stock_symbol_gazetteer",
                title="Stock symbol gazetteer (II SENSES — sentiment/news)",
                status="active",
                metrics=(
                    ("F&O symbols", str(len(gaz.tickers))),
                    ("name phrases", str(len(gaz.name_phrases))),
                ),
                note="NSE equity-master name→symbol (F&O-bounded); resolves headline company names "
                     "for the S7 news-event gate.",
            )
        _add(_stock_symbol_gazetteer)

        def _stock_levels():
            rep = self._latest_stock_levels
            if rep is None:
                return DashboardFeatureSurface(
                    key="stock_levels",
                    title="News stock S/R levels (II SENSES — sentiment/news)",
                    status="gathering", metrics=(("status", "awaiting first extraction"),),
                    note="Analyst targets / support / resistance per F&O stock, parsed from headlines "
                         "(research/149); the stock-entry S/R context.")
            status = "active" if rep["levels_found"] > 0 else "gathering"
            return DashboardFeatureSurface(
                key="stock_levels",
                title="News stock S/R levels (II SENSES — sentiment/news)",
                status=status,
                metrics=(
                    ("stocks with levels", str(rep["stocks_with_levels"])),
                    ("levels found", str(rep["levels_found"])),
                    ("top levels", " · ".join(rep["top_lines"]) or "—"),
                ),
                note="Per-stock analyst targets / S-R from headlines (F&O-bounded via the gazetteer).",
            )
        _add(_stock_levels)

        def _news_sentiment():
            rep = self._latest_sentiment_summary
            if rep is None:
                return DashboardFeatureSurface(
                    key="news_sentiment",
                    title="News sentiment (II SENSES — sentiment/news, finance-VADER)",
                    status="gathering", metrics=(("status", "awaiting first scoring pass"),),
                    note="Finance-lexicon-boosted VADER polarity per headline; makes the S7 gate "
                         "directional (adverse news weighs more). FinBERT drops in behind the same seam.")
            c = rep["counts"]
            return DashboardFeatureSurface(
                key="news_sentiment",
                title="News sentiment (II SENSES — sentiment/news, finance-VADER)",
                status="active",
                metrics=(
                    ("headlines scored", str(rep["scored"])),
                    ("mood", f"{c['adverse']} adverse / {c['neutral']} neutral / {c['favourable']} favourable"),
                    ("most adverse", " · ".join(rep["most_adverse"]) or "—"),
                ),
                note="Finance-VADER polarity; adverse news amplifies S7 event risk (directional gate).",
            )
        _add(_news_sentiment)

        def _index_level_gate():
            levels = getattr(self._state, "index_level_values_by_underlying", {}) or {}
            earned = getattr(self._state, "index_level_calibration_earned", False)
            if not levels and self._news_entry_gate_last_run_at is None:
                return DashboardFeatureSurface(
                    key="index_level_gate",
                    title="Index-level option gate (II SENSES — sentiment/news)",
                    status="gathering", metrics=(("status", "awaiting first pass"),),
                    note="Sizes-down/defers an index-option entry sitting at a fresh S2 news S/R level "
                         "(reversal caution); wired into the option path, advisory until earned.")
            summary = ", ".join(f"{u}:{len(v)}" for u, v in sorted(levels.items())) or "none"
            return DashboardFeatureSurface(
                key="index_level_gate",
                title="Index-level option gate (II SENSES — sentiment/news)",
                status="active",
                metrics=(
                    ("mode", "EARNED (acting)" if earned else "advisory (identity until earned)"),
                    ("index levels", summary),
                    ("deferred", str(getattr(self._state, "index_level_deferred_count", 0))),
                    ("sized-down", str(getattr(self._state, "index_level_sized_down_count", 0))),
                ),
                note="Consumes the S2 index news_levels at the option entry sites (proximity caution). "
                     "Advisory until the signal earns calibration (Rule K).",
            )
        _add(_index_level_gate)

        def _option_lot_sizing():
            """B7: option lots are INDIVISIBLE, so the fractional size-down levers are composed once
            and rounded half-up rather than truncated. Truncation floored every 1-lot order to zero
            and blocked 100% of option entries — this surface makes a refusal visible."""
            stood_aside = getattr(
                self._state, "option_size_down_stand_aside_count", 0
            )
            composed = compose_size_down_multipliers(
                self._state.debate_risk_size_multiplier(""),
                self._state.organism_vitality_multiplier(),
                self._state.workspace_caution_multiplier(),
            )
            open_option_count = len(
                getattr(self._state, "open_option_spreads", {})
            ) + len(getattr(self._state, "open_directional_options", {}))
            return DashboardFeatureSurface(
                key="option_lot_sizing",
                title="Option lot sizing (V RISK — indivisible-lot size-down)",
                status="active" if open_option_count else "gathering",
                metrics=(
                    ("open option positions", str(open_option_count)),
                    ("composed size-down", f"x{composed:.3f}"),
                    ("stood aside (<1 lot)", str(stood_aside)),
                    # B8: looks should climb well PAST the ~215-underlying universe size across a
                    # session. Equal to the universe size means the old one-look-per-process bug.
                    (
                        "underlying looks (B8)",
                        f"{getattr(self._state, 'option_underlying_look_count', 0)} "
                        f"over {len(getattr(self._state, 'seeded_option_underlyings', ()))} underlyings",
                    ),
                    (
                        "last stand-aside",
                        str(
                            getattr(
                                self._state,
                                "last_option_size_down_stand_aside_reason",
                                None,
                            )
                            or "none"
                        )[:110],
                    ),
                ),
                note="Risk-gate-sized lots x composed levers, rounded half-up. A candidate reduced "
                     "below one whole lot stands aside WITH a reason instead of being silently zeroed.",
            )

        _add(_option_lot_sizing)

        def _exit_efficiency():
            """B23c: how much of the profit each mechanism REACHED did it actually KEEP?

            `capture` well below 1.0 = we habitually give back profit already earned (tighten the
            trail / stop capping runs with the target). Rows recorded before the excursion
            watermark are EXCLUDED, not counted as zero — `measured/total` makes that visible."""
            memory = self._experience_memory
            if memory is None:
                return DashboardFeatureSurface(
                    key="exit_efficiency",
                    title="Exit efficiency (X MEMORY — do we exit too early?)",
                    status="gathering", metrics=(("status", "memory not open yet"),),
                    note="Needs the experience memory; excursion (MFE/MAE) accrues per closed trade.")
            rows = memory.exit_efficiency_by_mechanism(minimum_experiments=1)
            measured = sum(r["measured_count"] for r in rows)
            total = sum(r["total_count"] for r in rows)
            scored = [r for r in rows if r["capture_ratio"] is not None]
            scored.sort(key=lambda r: r["capture_ratio"])
            metrics = [("measured / total closed", f"{measured} / {total}")]
            for row in scored[:4]:
                metrics.append((
                    row["mechanism_name"][:44],
                    f"capture {row['capture_ratio']:.0%} "
                    f"(kept Rs{row['mean_realized_pnl']:.0f} of Rs"
                    f"{row['mean_maximum_favourable_profit']:.0f} reached, n={row['measured_count']})",
                ))
            trail_exits = sum(r["trail_exit_count"] for r in rows)
            metrics.append(("closed BY the profit trail", str(trail_exits)))
            return DashboardFeatureSurface(
                key="exit_efficiency",
                title="Exit efficiency (X MEMORY — do we exit too early?)",
                status="active" if measured else "gathering",
                metrics=tuple(metrics),
                note="capture = mean realised / mean max-favourable-excursion. Below 1.0 means "
                     "profit already earned is being given back. Pre-watermark rows excluded.",
            )

        _add(_exit_efficiency)

        def _arm_selector():
            """B18 step 7: WHY the selector picked an arm — the operator's auditability need.

            A selector whose reasoning is invisible is indistinguishable from a coin flip, and at
            these sample sizes it will legitimately LOOK random for weeks (burn-in + a permanent
            12% exploration floor). Showing `armed contexts / total` is what makes 'still learning'
            readable instead of alarming."""
            from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
                BURN_IN_EFFECTIVE_SAMPLES,
                summarise_arm_evidence,
            )
            from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
                OPTION_ARM_NAMES,
            )

            store = getattr(self._state, "option_arm_posterior_store", None)
            if store is None:
                return DashboardFeatureSurface(
                    key="arm_selector",
                    title="Adaptive arm selector (B18 — which strategy is chosen, and why)",
                    status="gathering", metrics=(("status", "selector not wired"),),
                    note="Chooses between option arms from realised cost-net outcomes.")

            now = datetime.now(_INDIA_MARKET_TIMEZONE).replace(tzinfo=None)
            summaries = summarise_arm_evidence(store.load_all_cells(now), OPTION_ARM_NAMES)
            metrics = [
                ("selections made", str(getattr(self._state, "option_arm_selection_count", 0))),
                ("trades awaiting reward", str(store.pending_trade_count())),
            ]
            for summary in summaries:
                metrics.append((
                    summary.arm_name,
                    f"{summary.contexts_past_burn_in}/{summary.context_count} contexts armed "
                    f"(need {BURN_IN_EFFECTIVE_SAMPLES:.0f} ea) · "
                    f"n={summary.total_effective_samples:.1f} · "
                    f"mean Rs{summary.mean_reward:,.0f}",
                ))
            latest = getattr(self._state, "last_option_arm_selection", None)
            if latest is not None:
                metrics.append((
                    "last pick",
                    f"{latest.chosen_arm} — {latest.selection_reason}"[:150],
                ))
            any_armed = any(s.is_armed for s in summaries)
            return DashboardFeatureSurface(
                key="arm_selector",
                title="Adaptive arm selector (B18 — which strategy is chosen, and why)",
                status="active" if any_armed else "gathering",
                metrics=tuple(metrics),
                note="Hierarchical discounted Thompson sampling. Allocation looks near-uniform "
                     "while contexts are under burn-in, plus a PERMANENT 12% exploration floor so "
                     "a losing arm is never starved of the data that would prove it bad.",
            )

        _add(_arm_selector)

        def _telegram_news():
            rep = self._latest_telegram_report
            if rep is None:
                return DashboardFeatureSurface(
                    key="telegram_news",
                    title="Telegram social news (II SENSES — sentiment/news S5)",
                    status="gathering", metrics=(("status", "awaiting first poll"),),
                    note="Ingests the configured Telegram bot's messages as tier SOCIAL — advisory-"
                         "until-proven (S3 floors them out of the entry gate).")
            if not rep.get("enabled"):
                return DashboardFeatureSurface(
                    key="telegram_news",
                    title="Telegram social news (II SENSES — sentiment/news S5)",
                    status="blocked", metrics=(("status", "disabled — no credentials in env"),),
                    note="Set NSE_TELEGRAM_BOT_TOKEN + NSE_TELEGRAM_CHAT_ID in .env to enable.")
            return DashboardFeatureSurface(
                key="telegram_news",
                title="Telegram social news (II SENSES — sentiment/news S5)",
                status="active",
                metrics=(
                    ("tier", "social (advisory — floored out of the gate)"),
                    ("new messages", str(rep.get("items_new", 0))),
                    ("stored total", str(rep.get("stored_total", 0))),
                    ("latest", rep.get("newest", "—")),
                ),
                note=rep.get("summary", ""),
            )
        _add(_telegram_news)

        def _explicit_utility():
            u = self._latest_utility_score
            if u is None or u.sample_size == 0:
                return DashboardFeatureSurface(
                    key="explicit_utility",
                    title="Explicit utility (XIV AXIOLOGY — the system's stated values)",
                    status="gathering", metrics=(("status", "awaiting first evaluation"),),
                    note="The objective made explicit: U = return − risk − drawdown − tail, over the "
                         "real realized-return series. The named value weights are inspectable.")
            return DashboardFeatureSurface(
                key="explicit_utility",
                title="Explicit utility (XIV AXIOLOGY — the system's stated values)",
                status="active",
                metrics=(
                    ("utility U", f"{u.utility:+.4f}"),
                    ("trades", str(u.sample_size)),
                    ("mean / vol", f"{u.mean_return:+.2%} / {u.volatility:.2%}"),
                    ("maxDD / CVaR5", f"{u.max_drawdown:.2%} / {u.tail_loss_cvar5:.2%}"),
                    ("dominant penalty", min(
                        (("drawdown", u.drawdown_term), ("tail", u.tail_term), ("risk", u.risk_term)),
                        key=lambda kv: kv[1])[0]),
                ),
                note=u.summary,
            )
        _add(_explicit_utility)

        def _value_drift():
            d = self._latest_value_drift
            if d is None or d.sample_size == 0:
                return DashboardFeatureSurface(
                    key="value_drift",
                    title="Value drift (XIV AXIOLOGY — realized-vs-stated values)",
                    status="gathering", metrics=(("status", "awaiting first verdict"),),
                    note="Flags when recent realized risk (volatility / drawdown / tail) drifts above "
                         "the stated values — a value-alignment signal (queued consumer: trim/defer).")
            status = "blocked" if d.is_drifting else "active"  # 'blocked' = a red flag worth seeing
            return DashboardFeatureSurface(
                key="value_drift",
                title="Value drift (XIV AXIOLOGY — realized-vs-stated values)",
                status=status,
                metrics=(
                    ("verdict", "VALUE DRIFT" if d.is_drifting else "values stable"),
                    ("drifting on", ", ".join(d.drifting_components) or "none"),
                    ("trades", str(d.sample_size)),
                ),
                note=d.summary,
            )
        _add(_value_drift)

        def _objective_arbitration():
            a = self._latest_arbitration
            if a is None or not a.ranked:
                return DashboardFeatureSurface(
                    key="objective_arbitration",
                    title="Objective arbitration (III WILL — values-driven volition)",
                    status="gathering", metrics=(("status", "awaiting first arbitration"),),
                    note="Arbitrates conflicting objectives per mechanism (XIV utility · return · "
                         "−risk · confidence) → Pareto front + weighted ranking.")
            winner = a.ranked[0]
            ranking = " · ".join(f"{m.mechanism[:16]} {m.arbitration_score:+.2f}" for m in a.ranked[:4])
            return DashboardFeatureSurface(
                key="objective_arbitration",
                title="Objective arbitration (III WILL — values-driven volition)",
                status="active",
                metrics=(
                    ("winner", f"{winner.mechanism[:32]} ({winner.arbitration_score:+.2f})"),
                    ("Pareto front", str(len(a.pareto_front))),
                    ("ranking", ranking),
                ),
                note=a.summary,
            )
        _add(_objective_arbitration)

        def _goal_schedule():
            s = self._latest_goal_schedule
            if s is None or not s.goals:
                return DashboardFeatureSurface(
                    key="goal_schedule",
                    title="Goal-priority schedule (III WILL)",
                    status="gathering", metrics=(("status", "awaiting first schedule"),),
                    note="Priority-orders the arbitrated mechanisms within a concurrency budget; the "
                         "(queued) consumer is the entry loop — pursue the scheduled goals first.")
            active = [g.mechanism[:24] for g in s.goals if g.is_active]
            return DashboardFeatureSurface(
                key="goal_schedule",
                title="Goal-priority schedule (III WILL)",
                status="active",
                metrics=(
                    ("active / deferred", f"{s.active_count} / {s.deferred_count}"),
                    ("budget", str(s.max_concurrent)),
                    ("pursuing now", ", ".join(active) or "—"),
                ),
                note=s.summary,
            )
        _add(_goal_schedule)

        def _component_lifecycle_homeostat():
            homeostat = self._autopoiesis_homeostat
            report = self._latest_autopoiesis_report
            if homeostat is None or report is None:
                return DashboardFeatureSurface(
                    key="component_lifecycle_homeostat",
                    title="Component-lifecycle homeostat (X AUTOPOIESIS — self-maintenance)",
                    status="gathering",
                    note="no maintenance cycle has run yet",
                )
            metrics = tuple(homeostat.dashboard_metrics())
            violations = len(report.closure.violations)
            degraded = len(report.degraded_component_ids)
            note = (
                f"{degraded} component(s) degraded; {violations} unmaintained (closure violation); "
                f"repair is advisory until autonomy is granted"
            )
            return DashboardFeatureSurface(
                key="component_lifecycle_homeostat",
                title="Component-lifecycle homeostat (X AUTOPOIESIS — self-maintenance)",
                status="active" if report.health_by_component_id else "gathering",
                metrics=metrics + (("cycle failures", str(self._autopoiesis_failure_count)),),
                note=note,
            )
        _add(_component_lifecycle_homeostat)

        def _win_probability_model():
            engine = self._win_probability_engine
            ev = engine.evaluation if engine is not None else None
            if ev is None:
                return DashboardFeatureSurface(
                    key="win_probability_model",
                    title="ML win-probability engine (IX PREDICTIVE-CORE — LightGBM)",
                    status="gathering", metrics=(("status", "training / awaiting model"),),
                    note="Trained LightGBM classifier: feature pipeline → walk-forward/KFold CV → "
                         "calibrated P(win) → fractional-Kelly entry sizing. Acts only when it beats baseline.")
            earned = engine.is_performance_earned
            top = " · ".join(f"{f}" for f, _ in ev.feature_importances[:3]) or "—"
            base_ll = f"{ev.baseline_log_loss:.3f}" if ev.baseline_log_loss is not None else "—"
            return DashboardFeatureSurface(
                key="win_probability_model",
                title="ML win-probability engine (IX PREDICTIVE-CORE — LightGBM)",
                status="active" if earned else "gathering",
                metrics=(
                    ("mode", "EARNED — sizing by edge" if earned else "advisory (not yet beating baseline)"),
                    ("CV AUC", f"{ev.auc:.3f}" if ev.auc is not None else "n/a"),
                    ("logloss vs baseline", f"{ev.log_loss:.3f} vs {base_ll}"),
                    ("scheme", f"{ev.cv_scheme} ({ev.n_splits}f), n={ev.n_samples} ({ev.positive_rate:.0%} win)"),
                    ("top features", top),
                ),
                note=ev.summary,
            )
        _add(_win_probability_model)

        def _capital_allocation_optimizer_surface():
            result = self._capital_allocation_result
            title = "Capital-allocation optimizer (III WILL — CVXPY portfolio)"
            if result is None:
                return DashboardFeatureSurface(
                    key="capital_allocation_optimizer", title=title, status="gathering",
                    metrics=(("status", "awaiting first solve"),),
                    note="CVXPY-solved risk-budget allocation across simultaneous candidates: Mean-CVaR / "
                         "Ledoit-Wolf MV / Risk-Parity / Enhanced-indexing, with caps · gross/net · "
                         "cardinality · lot-rounding · turnover. Advisory size-down lever until earned.")
            diag = result.diagnostics or {}
            active_weights = " · ".join(f"{k.split('|')[0][:10]}={v:.2f}"
                                        for k, v in sorted(result.weights.items(), key=lambda kv: -kv[1])
                                        if v > 1e-3) or "—"
            return DashboardFeatureSurface(
                key="capital_allocation_optimizer", title=title,
                status="active" if result.acted else "gathering",
                metrics=(
                    ("mode", f"{result.objective_mode_used}"
                             + (" (thin→MV fallback)" if result.fell_back else "")),
                    ("acting", "EARNED — sizing by allocation" if result.acted
                               else "advisory (identity until earned)"),
                    ("solver", result.solver_status),
                    ("tail risk", f"CVaR {result.portfolio_cvar:.3f} vs equal-wt "
                                  f"{diag.get('equal_weight_cvar', float('nan')):.3f}"),
                    ("active positions", f"{result.active_count}"),
                    ("scenarios", f"{result.scenario_count} (floor {diag.get('cvar_scenario_floor', '—')})"),
                    ("session-days", f"{diag.get('distinct_session_dates', 0)}"),
                    ("weights", active_weights),
                ),
                note="CVXPY portfolio allocation over the real traded universe. Tail-risk-reducing when it "
                     "beats equal-weight CVaR. Advisory (size-down only) until enough trading days accrue "
                     "to EARN acting; joint up-sizing reallocation is the queued live-accrual consumer.")
        _add(_capital_allocation_optimizer_surface)

        def _curiosity_engine_surface():
            plan = self._curiosity_plan
            title = "Curiosity / learning-progress engine (XII INTRINSIC MOTIVATION)"
            if plan is None:
                return DashboardFeatureSurface(
                    key="curiosity_engine", title=title, status="gathering",
                    metrics=(("status", "awaiting first plan"),),
                    note="Learning-progress + count-novelty + boredom → per-(strategy×regime) exploration "
                         "priority that steers the replay curriculum toward the highest-learning regime.")
            top = plan.top_cell
            top_label = (f"{top.strategy_tag[:12]}·{top.market_regime}"
                         f"{' (unobserved)' if top and top.is_unobserved else ''}") if top else "—"
            regimes = " · ".join(f"{r}={v:.2f}" for r, v in
                                 sorted(plan.regime_priority.items(), key=lambda kv: -kv[1])) or "—"
            return DashboardFeatureSurface(
                key="curiosity_engine", title=title,
                status="active" if plan.is_mature else "gathering",
                metrics=(
                    ("most-curious regime", plan.most_curious_regime() or "—"),
                    ("top cell", top_label),
                    ("regime priorities", regimes),
                    ("cells scored", f"{len(plan.cell_priorities)}"),
                    ("trades seen", f"{plan.total_trades_seen}"),
                    ("temperature", f"{plan.temperature:.3f}"),
                    ("maturity", "data-mature" if plan.is_mature else "cold-start (novelty-driven)"),
                ),
                note="Oudeyer-IAC learning progress (time-derivative of prediction error) per "
                     "strategy×regime + count-based novelty for unobserved regimes; steers what the bot "
                     "trains on (replay curriculum), closing the win-prob model's thin-data gap.")
        _add(_curiosity_engine_surface)

        def _world_model_planning_surface():
            verdicts = self._world_model_verdicts
            title = "World-model planning engine (IX PREDICTIVE-CORE — active inference)"
            if not verdicts:
                return DashboardFeatureSurface(
                    key="world_model_planning", title=title, status="gathering",
                    metrics=(("status", "awaiting first plan"),),
                    note="Generative market-state model (count-based transitions + EB reward) + finite-"
                         "horizon value iteration; confidence-gated size/veto lever on entries.")
            def _label(v):
                if v is None:
                    return "—"
                if getattr(v, "vetoes", False):
                    return f"VETO (adv {v.advantage_vs_hold:+.4f})"
                if getattr(v, "abstains", True):
                    return "abstain (untrusted)"
                return f"size ×{v.size_multiplier:.2f} (adv {v.advantage_vs_hold:+.4f})"

            vlong = verdicts.get("long")
            confident = any(getattr(v, "is_confident", False) for v in verdicts.values())
            return DashboardFeatureSurface(
                key="world_model_planning", title=title,
                status="active" if confident else "gathering",
                metrics=(
                    ("current state", getattr(vlong, "current_state_label", "—")),
                    ("long verdict", _label(verdicts.get("long"))),
                    ("short verdict", _label(verdicts.get("short"))),
                    ("confidence κ", f"{getattr(vlong, 'confidence', 0.0):.2f}"),
                    ("observations", f"{getattr(vlong, 'total_observations', 0)}"),
                ),
                note="Learns market-state dynamics from real bars, plans forward (Bellman value "
                     "iteration), and gates on data trust × (1−ensemble disagreement), zeroed on a "
                     "surprise spike — abstains until the model is trustworthy for the current state.")
        _add(_world_model_planning_surface)

        # Return ALL manifest features in order — a placeholder 'not yet surfaced' row for
        # any that failed to build, so the coverage panel always lists every feature.
        return tuple(FeatureCoverageReport(surfaces=tuple(surfaces)).rows_in_manifest_order())

    def _maybe_run_strategic_reflection(self, now) -> None:
        """Layer 11: at most once/day, ask the memory-grounded analyst for a strategic
        reflection over the REAL §10 memory, served by the swappable free-tier LLM pool, and
        cache it for the dashboard surface. Advisory (read-only) — no DECISION consumes it yet
        (gate consumption is a queued, calibration-gated slice, research/96). Best-effort: no
        keys, no network, or an empty memory just leaves the incumbent reflection untouched and
        never disturbs the trading loop."""
        import os as _os

        today = now.date()
        if not self._feature_stage_is_due("strategic_reflection", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )
            from nse_algo_trader.llm_strategy.memory_grounded_strategy_analyst import (
                MemoryGroundedStrategyAnalyst,
            )
            from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
                SwappableMultiProviderLlmClient,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            if not pool:
                self._feature_stage_last_run_at.setdefault("strategic_reflection", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            analyst = MemoryGroundedStrategyAnalyst(
                SwappableMultiProviderLlmClient(pool), self._experience_memory
            )
            self._latest_strategic_reflection = analyst.reflect()
        except Exception:
            pass  # never let LLM/network trouble disturb the loop
        self._feature_stage_last_run_at.setdefault("strategic_reflection", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_thesis_debate_risk_check(self, now) -> None:
        """Layer 11 slice 2/2c: at most once/day, run the bull/bear/risk debate over the ACTIVE
        theses (top mechanisms on the calibration board) through the swappable LLM pool, cache
        the assessments for the dashboard, and PUSH the per-mechanism risk map + the prequential
        earn-calibration verdict onto the loop state (the entry gate reads both). The gate only
        acts once calibration is earned — until then this is advisory. Best-effort: no
        keys/network/empty memory just leaves the incumbent state untouched and never disturbs
        the trading loop."""
        import os as _os

        today = now.date()
        if not self._feature_stage_is_due("thesis_debate", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )
            from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
                SwappableMultiProviderLlmClient,
            )
            from nse_algo_trader.llm_strategy.thesis_debate_risk_panel import (
                ThesisDebateRiskPanel,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            if not pool:
                self._feature_stage_last_run_at.setdefault("thesis_debate", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            panel = ThesisDebateRiskPanel(
                SwappableMultiProviderLlmClient(pool), self._experience_memory
            )
            assessments = panel.debate_active_theses()
            self._latest_thesis_risk_assessments = assessments
            # Push the per-mechanism risk map onto the loop state (the entry-gate input).
            self._state.debate_risk_score_by_mechanism = {
                a.thesis.mechanism_name: a.risk_score for a in assessments if a.generated
            }
            # Recompute the prequential earn-calibration verdict and set the gate's earned flag.
            self._refresh_debate_risk_calibration()
        except Exception:
            pass  # never let LLM/network trouble disturb the loop
        self._feature_stage_last_run_at.setdefault("thesis_debate", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _refresh_debate_risk_calibration(self) -> None:
        """Layer 11 slice 2c: score the accrued PREQUENTIAL (risk_score, outcome) observations
        and set the entry gate's `debate_risk_calibration_earned` flag. The gate stays inert
        (identity) until the verdict says the risk signal genuinely separates winners from
        losers over enough LIVE observations."""
        from nse_algo_trader.llm_strategy.debate_risk_calibration_harness import (
            score_risk_calibration,
        )

        store = self._debate_risk_observation_store()
        try:
            verdict = score_risk_calibration(store.all_observations())
        finally:
            store.close()
        self._latest_debate_risk_calibration = verdict
        self._state.debate_risk_calibration_earned = verdict.earned

    def _record_debate_risk_observations(self, observations) -> None:
        """Append the collected LIVE prequential (mechanism, risk_score, is_win, closed_at)
        pairs to the observation store — the harness's earn-calibration input (Layer 11 2c)."""
        if not observations:
            return
        store = self._debate_risk_observation_store()
        try:
            for mechanism, risk_score, is_win, closed_at in observations:
                store.record_observation(mechanism, risk_score, is_win, closed_at)
        finally:
            store.close()

    def _maybe_run_causal_cluster_analysis(self, now) -> None:
        """Layer 11 slice 3: at most once/day, ask the causal-cluster analyst to reason over the
        REAL multi-hop outcome clusters (temporal dependence + cross-regime calibration + violated
        assumptions) and propose falsifiable causal hypotheses, cached for the dashboard. ADVISORY
        — no DECISION consumes it yet (falsifiable-prediction scoring is a queued, calibration-
        gated slice, research/102). Best-effort: no keys/network/thin memory leave the incumbent
        analysis untouched and never disturb the trading loop."""
        import os as _os

        today = now.date()
        if not self._feature_stage_is_due("causal_cluster", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.llm_strategy.causal_cluster_analyst import (
                CausalClusterAnalyst,
            )
            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )
            from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
                SwappableMultiProviderLlmClient,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            if not pool:
                self._feature_stage_last_run_at.setdefault("causal_cluster", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            analyst = CausalClusterAnalyst(
                SwappableMultiProviderLlmClient(pool), self._experience_memory
            )
            self._latest_causal_cluster_analysis = analyst.analyze()
        except Exception:
            pass  # never let LLM/network trouble disturb the loop
        self._feature_stage_last_run_at.setdefault("causal_cluster", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_meta_strategy_allocation(self, now) -> None:
        """Layer 11 slice 4: at most once/day, ask the meta-strategy allocator to weight the three
        strategies from their REAL per-strategy/per-regime performance + champion configs, cached
        for the dashboard. ADVISORY — no DECISION consumes the weights yet (applying them to
        per-strategy sizing is a queued, calibration-gated slice, research/103). Best-effort: no
        keys/network/thin memory leave the incumbent allocation untouched and never disturb the
        trading loop."""
        import os as _os

        today = now.date()
        if not self._feature_stage_is_due("meta_strategy", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )
            from nse_algo_trader.llm_strategy.meta_strategy_allocator import (
                MetaStrategyAllocator,
            )
            from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
                SwappableMultiProviderLlmClient,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            if not pool:
                self._feature_stage_last_run_at.setdefault("meta_strategy", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            allocator = MetaStrategyAllocator(
                SwappableMultiProviderLlmClient(pool),
                self._experience_memory,
                champion_store=self._champion_store(),
            )
            self._latest_meta_strategy_allocation = allocator.allocate()
        except Exception:
            pass  # never let LLM/network trouble disturb the loop
        self._feature_stage_last_run_at.setdefault("meta_strategy", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_prediction_council(self, now) -> None:
        """Layer 11 slice 5: at most once/day, run the prediction-market council — several
        forecasting roles each estimate a probability on a resolvable proposition (the most-active
        mechanism wins its next trade), aggregated with track-record weights — and cache it for
        the dashboard. ADVISORY: the weights are equal until per-role reputations accrue
        (market-gated, research/104), and no DECISION consumes the council probability yet.
        Best-effort: no keys/network/thin memory leave the incumbent forecast untouched."""
        import os as _os

        today = now.date()
        if not self._feature_stage_is_due("prediction_council", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )
            from nse_algo_trader.llm_strategy.prediction_council import PredictionCouncil
            from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
                SwappableMultiProviderLlmClient,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            board = self._experience_memory.calibration_board(minimum_experiments=1, limit=1)
            if not pool or not board:
                self._feature_stage_last_run_at.setdefault("prediction_council", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            mechanism = board[0].mechanism_name
            council = PredictionCouncil(
                SwappableMultiProviderLlmClient(pool),
                self._experience_memory,
                track_record_store=self._council_track_record_store(),
            )
            self._latest_council_forecast = council.forecast(
                proposition_label=f"{mechanism} wins its next trade",
                proposition_question=(
                    f"Will mechanism '{mechanism}' WIN its next trade, given its real track record?"
                ),
            )
        except Exception:
            pass  # never let LLM/network trouble disturb the loop
        self._feature_stage_last_run_at.setdefault("prediction_council", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _council_track_record_store(self):
        """The prediction-council per-role reputation ledger (Layer 11 slice 5). Uses the injected
        debate-risk store path's directory only conceptually — its own default path in prod."""
        from nse_algo_trader.paper_trading.council_track_record_store import (
            CouncilTrackRecordStore,
        )

        if self._debate_risk_observation_store_path is not None:
            # tests inject a temp dir via the debate-risk seam; reuse it for isolation
            return CouncilTrackRecordStore(
                self._debate_risk_observation_store_path.parent / "council_track_record.sqlite3"
            )
        return CouncilTrackRecordStore()

    def _maybe_run_synthetic_stress_rehearsal(self, now) -> None:
        """Layer 11 slice 6: at most once/day, ask the stress-scenario generator to red-team the
        bot's REAL weakness surface (over-confident/negative-edge mechanisms, violated assumptions,
        clustering, weak regimes) into adversarial stress scenarios, cached for the dashboard.
        ADVISORY — the consumer that RUNS each scenario is the Layer-7.5 control-arms lab (queued,
        research/105). Best-effort: no keys/network/thin memory leave the incumbent rehearsal
        untouched and never disturb the trading loop."""
        import os as _os

        today = now.date()
        if not self._feature_stage_is_due("stress_rehearsal", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.llm_strategy.llm_provider_registry import (
                build_free_tier_provider_pool,
            )
            from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
                SwappableMultiProviderLlmClient,
            )
            from nse_algo_trader.llm_strategy.synthetic_stress_rehearsal import (
                SyntheticStressScenarioGenerator,
            )

            pool = build_free_tier_provider_pool(_os.environ)
            if not pool:
                self._feature_stage_last_run_at.setdefault("stress_rehearsal", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            generator = SyntheticStressScenarioGenerator(
                SwappableMultiProviderLlmClient(pool), self._experience_memory
            )
            self._latest_stress_rehearsal = generator.generate()
        except Exception:
            pass  # never let LLM/network trouble disturb the loop
        self._feature_stage_last_run_at.setdefault("stress_rehearsal", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_control_arm_comparison(self, now) -> None:
        """Layer 7.5 slice 1: at most once/day, score the REAL champion ORB arm against the
        RANDOM-CONTROL arm (same triggers, random direction) over the stored real sessions and
        cache the skill-vs-luck verdict for the dashboard. This is the scientific baseline the
        champion's P&L must clear to be called skill, not luck — a READ-ONLY diagnostic (the
        learning-consumer that trains only on the skill diagonal is a queued slice, research/95).
        Best-effort: no stored sessions just leaves the incumbent comparison untouched."""
        today = now.date()
        if not self._feature_stage_is_due("control_arm", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.paper_trading.control_arm_comparison import (
                compare_control_arms,
            )

            sessions = self._load_stored_benchmark_sessions()
            if not sessions:
                self._feature_stage_last_run_at.setdefault("control_arm", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            champion = self._champion_store().load_champion_or_default()
            self._latest_control_arm_comparison = compare_control_arms(sessions, champion)
        except Exception:
            pass  # never let a backtest hiccup disturb the loop
        self._feature_stage_last_run_at.setdefault("control_arm", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_skill_vs_luck_court(self, now) -> None:
        """Layer 7.5 slice 2: at most once/day, judge the control arms — the RANDOM-CONTROL edge
        (slice 1) + the SHADOW-REJECTED arm (how the gate's vetoed mechanisms performed) — into one
        skill-vs-luck verdict, cached for the dashboard. READ-ONLY diagnostic (the learning-consumer
        that trains only on the skill diagonal is a queued slice, research/106). Best-effort: no
        memory / no control-arm comparison yet just leaves the incumbent verdict untouched."""
        today = now.date()
        if not self._feature_stage_is_due("skill_vs_luck_court", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        if self._latest_control_arm_comparison is None:
            return  # need the slice-1 comparison first; retry next tick (no date stamp)
        try:
            from nse_algo_trader.memory_reflection import vetoed_mechanisms
            from nse_algo_trader.paper_trading.shadow_rejected_arm import (
                analyze_shadow_rejected_arm,
            )
            from nse_algo_trader.paper_trading.skill_vs_luck_court import (
                convene_skill_vs_luck_court,
            )

            shadow = analyze_shadow_rejected_arm(
                self._experience_memory, vetoed_mechanisms(self._experience_memory)
            )
            self._latest_skill_vs_luck_verdict = convene_skill_vs_luck_court(
                self._latest_control_arm_comparison, shadow
            )
        except Exception:
            pass  # never let a diagnostic hiccup disturb the loop
        self._feature_stage_last_run_at.setdefault("skill_vs_luck_court", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_pre_mortem(self, now) -> None:
        """Layer 7.5 slice 3: at most once/day, run an entry-time Monte Carlo over the REAL replay
        paths for a CANONICAL trade at the champion RR, and cache the outcome distribution (P
        stop/target, expected return, CVaR-5% tail) for the dashboard. READ-ONLY diagnostic — the
        entry-site CVaR sizing consumer is a queued slice (research/107). Best-effort: no stored
        sessions just leaves the incumbent pre-mortem untouched."""
        today = now.date()
        if not self._feature_stage_is_due("pre_mortem", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.paper_trading.per_trade_pre_mortem import (
                extract_post_trigger_return_paths,
                run_entry_pre_mortem,
            )
            from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection

            sessions = self._load_stored_benchmark_sessions()
            if not sessions:
                self._feature_stage_last_run_at.setdefault("pre_mortem", datetime.now(_INDIA_MARKET_TIMEZONE))
                return
            champion = self._champion_store().load_champion_or_default()
            paths = extract_post_trigger_return_paths(sessions, champion)
            # Canonical LONG setup at the champion RR: entry 100, 1% risk → stop 99, target 100+RR.
            risk = 1.0
            self._latest_pre_mortem = run_entry_pre_mortem(
                entry_price=100.0,
                stop_loss_price=100.0 - risk,
                target_price=100.0 + champion.target_risk_reward_ratio * risk,
                direction=SignalDirection.LONG,
                return_paths=paths,
            )
        except Exception:
            pass  # never let a backtest hiccup disturb the loop
        self._feature_stage_last_run_at.setdefault("pre_mortem", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_lab_summary(self, now) -> None:
        """Layer 7.5 slice 4: at most once/day, compute the lab's summary verdicts — PROFIT
        PROVENANCE (decompose the real P&L vs the control arms: luck + directional skill + gate
        value) and the WORLD-MODEL SCOREBOARD (trade-independent forecast skill + regime-model
        resolution) — cached for the dashboard. READ-ONLY. Best-effort: needs the slice-1 control-
        arm comparison + memory; missing either just leaves the incumbent summaries untouched."""
        today = now.date()
        if not self._feature_stage_is_due("lab_summary", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.memory_reflection import vetoed_mechanisms
            from nse_algo_trader.paper_trading.profit_provenance import (
                decompose_profit_provenance,
            )
            from nse_algo_trader.paper_trading.shadow_rejected_arm import (
                analyze_shadow_rejected_arm,
            )
            from nse_algo_trader.paper_trading.world_model_scoreboard import (
                score_world_model,
            )

            self._latest_world_model_scoreboard = score_world_model(self._experience_memory)
            if self._latest_control_arm_comparison is not None:
                shadow = analyze_shadow_rejected_arm(
                    self._experience_memory, vetoed_mechanisms(self._experience_memory)
                )
                self._latest_profit_provenance = decompose_profit_provenance(
                    self._latest_control_arm_comparison, shadow
                )
        except Exception:
            pass  # never let a diagnostic hiccup disturb the loop
        self._feature_stage_last_run_at.setdefault("lab_summary", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _ensure_incident_post_mortem_store(self):
        """Trunk VII.14: open the forensic safety-incident store lazily in the writer thread (its
        SQLite connection must live in this thread). DI path seam = tests never touch the real
        store. Returns the store, or None if it can't be opened (best-effort — never stalls)."""
        if self._incident_post_mortem_store is None:
            from nse_algo_trader.conscience.incident_post_mortem_store import (
                DEFAULT_SAFETY_INCIDENT_DB_PATH,
                IncidentPostMortemStore,
            )

            path = self._incident_post_mortem_store_path or DEFAULT_SAFETY_INCIDENT_DB_PATH
            self._incident_post_mortem_store = IncidentPostMortemStore(path)
        return self._incident_post_mortem_store

    def _record_safety_incident(
        self, incident_type: str, severity: str, occurred_at, subject: str, detail: str,
        trace_id: str,
    ) -> None:
        """Trunk VII.14: append one safety incident to the forensic store (idempotent per
        (type, trace_id)). Best-effort — a persistence hiccup never disturbs the trading loop."""
        try:
            from nse_algo_trader.conscience.incident_post_mortem import SafetyIncident

            store = self._ensure_incident_post_mortem_store()
            store.record_incident(SafetyIncident(
                incident_type=incident_type, severity=severity,
                occurred_at=occurred_at.isoformat(), subject=subject,
                detail=detail, trace_id=trace_id,
            ))
        except Exception:
            pass  # forensic persistence must never stall trading

    def _maybe_run_incident_post_mortem(self, now) -> None:
        """Trunk VII.14 CONSCIENCE: at most once/day, drain any Referee-BLOCKED orders that aren't
        yet persisted into the forensic store (defense-in-depth; zero in a correct system), then
        re-summarise the whole forensic record into the cached post-mortem for the dashboard. The
        halts/trips/breaches are recorded at their own halt sites as they happen; this closes the
        loop on the Referee blocks and refreshes the summary. Best-effort — never disturbs the loop."""
        today = now.date()
        if not self._feature_stage_is_due("incident_post_mortem", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.conscience.incident_post_mortem import (
                INCIDENT_TYPE_CONSTITUTION_BLOCK,
                summarize_incident_post_mortem,
            )

            store = self._ensure_incident_post_mortem_store()
            referee = self._state.constitutional_referee
            if referee is not None and referee.recent_blocks:
                already = store.recorded_trace_ids(INCIDENT_TYPE_CONSTITUTION_BLOCK)
                for verdict in referee.recent_blocks:
                    if verdict.trace_id in already:
                        continue
                    self._record_safety_incident(
                        INCIDENT_TYPE_CONSTITUTION_BLOCK, "hard", now,
                        subject=verdict.scope,
                        detail=verdict.detail or "constitutional block",
                        trace_id=verdict.trace_id,
                    )
            self._latest_incident_post_mortem = summarize_incident_post_mortem(
                store.all_incidents()
            )
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("incident_post_mortem", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_constitutional_audit(self, now) -> None:
        """Trunk VII.1 CONSCIENCE: at most once/day, audit the LIVE control-config posture against
        the constitution (the inviolable rules) and cache the verdict for the dashboard — a
        constitutional-compliance MONITOR (a real safety consumer, not display-only). Enforcing the
        constitution as a hard pre-order gate at the order sites is the queued Referee branch
        (research/109). Best-effort — never disturbs the loop."""
        today = now.date()
        if not self._feature_stage_is_due("constitutional_audit", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.conscience.constitutional_core import (
                audit_control_config_posture,
            )
            from nse_algo_trader.conscience.incident_post_mortem import (
                INCIDENT_TYPE_OFF_SWITCH_HALT,
                INCIDENT_TYPE_POSTURE_BREACH,
            )
            from nse_algo_trader.dashboard.trading_control_config import (
                load_trading_control_config,
            )

            verdict = audit_control_config_posture(load_trading_control_config())
            self._latest_constitutional_verdict = verdict
            # VII.5 self-corrigibility: if the system detects it is constitutionally NON-COMPLIANT,
            # it engages the off-switch (stops trading) rather than trading on.
            switch = self._state.corrigibility_switch
            if switch is not None:
                if not verdict.permitted:
                    switch.halt(f"constitutional breach: {verdict.detail}")
                    # VII.14: persist the breach + the halt it triggered to the forensic record.
                    self._record_safety_incident(
                        INCIDENT_TYPE_POSTURE_BREACH, "hard", now,
                        subject=verdict.scope, detail=verdict.detail,
                        trace_id=verdict.trace_id,
                    )
                    self._record_safety_incident(
                        INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", now,
                        subject=verdict.scope,
                        detail=f"self-halt on constitutional breach: {verdict.detail}",
                        trace_id=f"posture_halt:{verdict.trace_id}",
                    )
                elif switch.is_halted and switch.reason.startswith("constitutional breach"):
                    switch.resume()  # breach cleared → trading may resume
        except Exception:
            pass  # a config-read hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("constitutional_audit", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_alignment_tripwires(self, now) -> None:
        """Trunk VII.10/11 CONSCIENCE: at most once/day, run the alignment tripwires over the REAL
        memory — WIREHEADING (win-rate gamed vs return) + DECEPTIVE-ALIGNMENT (live worse than
        replay) — cache the verdicts, and on a CRITICAL trip ENGAGE the corrigibility off-switch
        (halt trading). Best-effort; a thin/empty memory just leaves the incumbent verdicts."""
        today = now.date()
        if not self._feature_stage_is_due("alignment_tripwire", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.conscience.alignment_tripwires import (
                deceptive_alignment_monitor,
                wireheading_tripwire,
            )
            from nse_algo_trader.conscience.incident_post_mortem import (
                INCIDENT_TYPE_DECEPTIVE_ALIGNMENT_TRIP,
                INCIDENT_TYPE_OFF_SWITCH_HALT,
                INCIDENT_TYPE_WIREHEADING_TRIP,
            )

            wire = wireheading_tripwire(self._experience_memory)
            deceptive = deceptive_alignment_monitor(self._experience_memory)
            self._latest_wireheading_verdict = wire
            self._latest_deceptive_alignment_verdict = deceptive
            switch = self._state.corrigibility_switch
            trip_types = (INCIDENT_TYPE_WIREHEADING_TRIP, INCIDENT_TYPE_DECEPTIVE_ALIGNMENT_TRIP)
            for verdict, trip_type in zip((wire, deceptive), trip_types):
                if verdict.is_critical:
                    if switch is not None:
                        switch.halt(f"{verdict.name} tripwire CRITICAL: {verdict.detail}")
                    # VII.14: persist the critical trip + the halt it triggered to the record.
                    self._record_safety_incident(
                        trip_type, "critical", now,
                        subject=", ".join(verdict.flagged[:3]) or verdict.name,
                        detail=verdict.detail, trace_id=f"{verdict.name}:{today.isoformat()}",
                    )
                    self._record_safety_incident(
                        INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", now,
                        subject=verdict.name,
                        detail=f"self-halt on {verdict.name} tripwire: {verdict.detail}",
                        trace_id=f"trip_halt:{verdict.name}:{today.isoformat()}",
                    )
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("alignment_tripwire", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_goal_integrity(self, now) -> None:
        """Trunk VII CONSCIENCE: at most once/day, assess GOAL INTEGRITY over the REAL memory — is
        the declared objective (risk-adjusted RETURN within defined risk) still the effective one,
        or has behaviour drifted (objective sign · edge concentration · win-rate↔return decoupling)?
        Cache the verdict; a CRITICAL drift ENGAGES the corrigibility off-switch (halt) + records a
        forensic incident. Best-effort; a thin memory just leaves the incumbent verdict."""
        today = now.date()
        if not self._feature_stage_is_due("goal_integrity", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.conscience.goal_integrity_monitor import assess_goal_integrity
            from nse_algo_trader.conscience.incident_post_mortem import (
                INCIDENT_TYPE_GOAL_INTEGRITY_DRIFT,
                INCIDENT_TYPE_OFF_SWITCH_HALT,
            )

            verdict = assess_goal_integrity(self._experience_memory)
            self._latest_goal_integrity_verdict = verdict
            if verdict.is_critical:
                switch = self._state.corrigibility_switch
                if switch is not None:
                    switch.halt(f"goal-integrity CRITICAL: {verdict.detail}")
                self._record_safety_incident(
                    INCIDENT_TYPE_GOAL_INTEGRITY_DRIFT, "critical", now,
                    subject=", ".join(verdict.drift_flags) or "goal-drift",
                    detail=verdict.detail, trace_id=f"goal_integrity:{today.isoformat()}",
                )
                self._record_safety_incident(
                    INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", now, subject="goal-integrity",
                    detail=f"self-halt on goal-integrity drift: {verdict.detail}",
                    trace_id=f"goal_halt:{today.isoformat()}",
                )
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("goal_integrity", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_mechanistic_interpretability(self, now) -> None:
        """Trunk VII CONSCIENCE: at most once/day, build the mechanistic-interpretability report over
        the REAL memory — which internal mechanisms drive decisions and are they trustworthy — and
        cache it for the dashboard. READ-ONLY transparency (the acting on unreliable mechanisms lives
        in memory_reflection's veto/recalibration). Best-effort; a thin memory leaves the incumbent."""
        today = now.date()
        if not self._feature_stage_is_due("interpretability", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.conscience.mechanistic_interpretability import (
                explain_decision_mechanisms,
            )

            self._latest_interpretability_report = explain_decision_mechanisms(
                self._experience_memory
            )
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("interpretability", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_red_team(self, now) -> None:
        """Trunk VII CONSCIENCE: at most once/day (expensive backtests), adversarially attack the
        LIVE champion config over the REAL stored sessions — parameter perturbations + worst-session
        tail — and cache the fragility report for the dashboard. READ-ONLY (champion-challenger owns
        config changes). Best-effort; no stored sessions just leaves the incumbent report."""
        today = now.date()
        if not self._feature_stage_is_due("red_team", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.conscience.red_team_harness import red_team_champion

            sessions = self._load_stored_benchmark_sessions()
            if sessions:
                self._latest_red_team_report = red_team_champion(
                    sessions, self._champion_orb_config()
                )
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("red_team", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_ethics_law_review(self, now) -> None:
        """Trunk VII CONSCIENCE: at most once/day, reason the system's regulatory posture against the
        SEBI algo rulebook (order-rate <10/s, broker-principal routing, Algo-ID, intraday-only,
        white-box personal use) and cache the cited compliance report. A HARD violation engages the
        off-switch + records a forensic incident (law-breaking is halt-worthy). Best-effort."""
        today = now.date()
        if not self._feature_stage_is_due("ethics_law", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.broker_oms.order_rate_limiter import OrderRateLimiter
            from nse_algo_trader.conscience.ethics_law_reasoner import (
                RegulatoryPosture,
                assess_regulatory_compliance,
            )
            from nse_algo_trader.conscience.incident_post_mortem import (
                INCIDENT_TYPE_OFF_SWITCH_HALT,
                INCIDENT_TYPE_REGULATORY_VIOLATION,
            )
            from nse_algo_trader.dashboard.trading_control_config import (
                load_trading_control_config,
            )

            config = load_trading_control_config()
            # Real posture: the SEBI throttle ceiling + the structural facts of this bot's design.
            posture = RegulatoryPosture(
                max_orders_per_second=OrderRateLimiter().max_orders_per_second,
                routes_through_broker=True,   # all orders via the broker API (broker-principal)
                carries_algo_id=True,         # exchange Algo-ID on every algo order
                intraday_only=True,           # square-off before close, no overnight carry
                offered_to_others=False,      # personal white-box use, not distributed
                trading_mode=getattr(config.trading_mode, "value", str(config.trading_mode)),
            )
            report = assess_regulatory_compliance(posture)
            self._latest_law_compliance_report = report
            if not report.compliant:
                switch = self._state.corrigibility_switch
                if switch is not None:
                    switch.halt(f"regulatory violation: {', '.join(report.violations)}")
                self._record_safety_incident(
                    INCIDENT_TYPE_REGULATORY_VIOLATION, "hard", now,
                    subject=", ".join(report.violations), detail=report.summary,
                    trace_id=f"regulatory:{today.isoformat()}:{','.join(report.violations)}",
                )
                self._record_safety_incident(
                    INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", now, subject="ethics/law",
                    detail=f"self-halt on regulatory violation: {report.summary}",
                    trace_id=f"law_halt:{today.isoformat()}",
                )
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("ethics_law", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_epistemic_defense(self, now) -> None:
        """Trunk XIII EPISTEMICS: at most once/day, over the REAL §10 memory — resolve belief
        CONTRADICTIONS (regime cohorts vs the global belief, z-test) + assess source CREDIBILITY
        (beta-reputation, flag over-trusted misinformation sources). Read-only diagnostics; cache for
        the dashboard. Best-effort; a thin/empty memory leaves the incumbent reports."""
        today = now.date()
        if not self._feature_stage_is_due("epistemic_defense", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.epistemics.contradiction_resolver import resolve_contradictions
            from nse_algo_trader.epistemics.misinformation_resistance import (
                assess_source_credibility,
            )

            cohorts = self._experience_memory.calibration_by_market_regime(minimum_experiments=1)
            self._latest_contradiction_report = resolve_contradictions(cohorts)
            board = self._experience_memory.calibration_board(minimum_experiments=1, limit=50)
            self._latest_misinfo_report = assess_source_credibility(board)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("epistemic_defense", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_predictive_core(self, now) -> None:
        """Trunk IX PREDICTIVE-CORE / active inference: at most once/day, over the REAL calibration
        board — measure SURPRISE (free energy; per-mechanism cross-entropy + spike) + build the
        ENSEMBLE forecast (combined prediction + disagreement). Read-only diagnostics; cache for the
        dashboard. Best-effort; a thin/empty memory leaves the incumbent reports."""
        today = now.date()
        if not self._feature_stage_is_due("predictive_core", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.predictive_core.ensemble_world_model import (
                build_ensemble_forecast,
            )
            from nse_algo_trader.predictive_core.surprise_monitor import monitor_surprise

            board = self._experience_memory.calibration_board(minimum_experiments=1, limit=50)
            self._latest_surprise_report = monitor_surprise(board)
            self._latest_ensemble_forecast = build_ensemble_forecast(board)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("predictive_core", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_memory_consolidation(self, now) -> None:
        """Trunk XV MEMORY: at most once/day, consolidate the episodic calibration board into stable
        SEMANTIC facts (episodic→semantic transfer, gated by sample size) and cache the semantic
        store. Read-only knowledge base. Best-effort; a thin memory leaves the incumbent store."""
        today = now.date()
        if not self._feature_stage_is_due("memory_consolidation", datetime.now(_INDIA_MARKET_TIMEZONE)) or self._experience_memory is None:
            return
        try:
            from nse_algo_trader.memory_reflection.memory_consolidation import (
                consolidate_to_semantic,
            )

            board = self._experience_memory.calibration_board(minimum_experiments=1, limit=50)
            self._latest_semantic_memory = consolidate_to_semantic(board)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("memory_consolidation", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_society(self, now) -> None:
        """Trunk VI SOCIETY: at most once/day, over the latest council forecast — form a track-record-
        weighted CONSENSUS across the desks (+ conflict/deadlock resolution) and GOVERN which desks are
        trusted vs quarantined by reputation. Read-only. Best-effort; no council forecast (LLM-gated)
        leaves the incumbent reports."""
        today = now.date()
        if not self._feature_stage_is_due("society", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.society.consensus_resolution import (
                AgentOpinion,
                resolve_consensus,
            )
            from nse_algo_trader.society.multi_agent_governance import govern_agents

            forecast = self._latest_council_forecast
            if forecast is not None and getattr(forecast, "generated", False) and forecast.member_forecasts:
                weights = dict(getattr(forecast, "weight_by_role", {}))
                opinions = [
                    AgentOpinion(m.role, m.probability, weights.get(m.role, 1.0))
                    for m in forecast.member_forecasts
                ]
                self._latest_consensus_verdict = resolve_consensus(opinions)
                max_w = max(weights.values()) if weights else 1.0
                reputations = {r: (w / max_w if max_w else 1.0) for r, w in weights.items()}
                self._latest_governance_report = govern_agents(reputations)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("society", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_market_breadth(self, now) -> None:
        """Trunk II SENSES: at most once/day, over the latest stored cash bhavcopy — sense market
        BREADTH (advancers/decliners, A-D ratio, dispersion) + CROSS-MARKET context (is the aggregate
        move confirmed by breadth or a narrow divergence). Reads the market-data store (works offline
        from stored bhavcopy). Best-effort; no bhavcopy leaves the incumbent reports."""
        today = now.date()
        if not self._feature_stage_is_due("market_breadth", datetime.now(_INDIA_MARKET_TIMEZONE)):
            return
        try:
            from nse_algo_trader.market_data.market_breadth import (
                SymbolReturn,
                assess_cross_market_context,
                compute_market_breadth,
            )
            from nse_algo_trader.market_data.market_data_sqlite_store import (
                MarketDataSqliteStore,
            )

            store = MarketDataSqliteStore()
            try:
                trade_date = store.latest_cash_bhavcopy_trade_date()
                if trade_date is not None:
                    returns = [
                        SymbolReturn(sym, ret)
                        for sym, ret in store.cash_bhavcopy_symbol_returns(trade_date)
                    ]
                    self._latest_market_breadth = compute_market_breadth(returns)
                    self._latest_cross_market_context = assess_cross_market_context(returns)
            finally:
                store.close()
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._feature_stage_last_run_at.setdefault("market_breadth", datetime.now(_INDIA_MARKET_TIMEZONE))

    def _maybe_run_news_ingestion(self, now) -> None:
        """Trunk II SENSES (sentiment/news S1, research/140): at most every 15 min, poll the tier-1
        financial-news RSS feeds, REJECT stale feeds (Moneycontrol-style HTTP-200-but-frozen), dedupe
        + store fresh headlines, and cache the report for the dashboard. News is real-time regardless
        of market hours, so freshness uses the real wall clock. Best-effort; never disturbs the loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if self._news_last_run_at is not None and (now_utc - self._news_last_run_at) < _td(minutes=15):
            return
        try:
            from nse_algo_trader.news_sentiment.news_feed_registry import TIER1_RSS_FEEDS
            from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
            from nse_algo_trader.news_sentiment.rss_news_feed_source import RssNewsFeedSource

            store = NewsSqliteStore()
            try:
                runner = NewsIngestionRunner(RssNewsFeedSource(TIER1_RSS_FEEDS), store)
                self._latest_news_ingestion_report = runner.run(now_utc)
            finally:
                store.close()
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._news_last_run_at = now_utc

    def _maybe_run_news_level_extraction(self, now) -> None:
        """Trunk II SENSES (S2, research/142): at most every 15 min, read the stored headlines and
        extract structured index support/resistance levels (NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY/
        NIFTYNXT50) → persist + cache the report for the dashboard. Consumes what S1 stored (no
        network of its own). The extracted levels are the (queued S7) entry-gate's option strike/stop
        context. Best-effort; never disturbs the loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._news_levels_last_run_at is not None
                and (now_utc - self._news_levels_last_run_at) < _td(minutes=15)):
            return
        try:
            from nse_algo_trader.news_sentiment.news_level_extraction_runner import (
                NewsLevelExtractionRunner,
            )
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore

            store = NewsSqliteStore()
            try:
                self._latest_news_level_extraction_report = NewsLevelExtractionRunner(store).run(now_utc)
            finally:
                store.close()
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop
        self._news_levels_last_run_at = now_utc

    def _maybe_run_news_acquisition(self, now) -> None:
        """Trunk II SENSES (S4a+S4b acquisition ladder, research/143+144): at most every 5 min, acquire
        the target news pages (Moneycontrol markets/stocks — stale RSS, current HTML) via the ladder —
        FAST curl_cffi static fetch first (~0.3s, Chrome-TLS-impersonated), headless-Chromium render
        only as a JS-only fallback (~40s) — and store via the SAME ingestion runner as RSS. The store's
        content_hash dedup makes `items_new` the NEW-headlines-this-poll delta (the live signal). Runs
        in a BACKGROUND daemon thread so the rare render fallback never blocks the loop. Best-effort."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if self._news_acquisition_thread is not None and self._news_acquisition_thread.is_alive():
            return  # an acquisition pass is already in flight
        if (self._news_acquisition_last_run_at is not None
                and (now_utc - self._news_acquisition_last_run_at) < _td(minutes=5)):
            return
        self._news_acquisition_last_run_at = now_utc

        import threading

        def _acquire_and_store() -> None:
            try:
                from nse_algo_trader.news_sentiment.news_acquisition_ladder import (
                    LadderNewsAcquisitionSource,
                )
                from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
                from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
                from nse_algo_trader.news_sentiment.rendered_news_page_registry import (
                    RENDER_TARGET_SITES,
                )

                store = NewsSqliteStore()
                try:
                    source = LadderNewsAcquisitionSource(RENDER_TARGET_SITES)
                    self._latest_news_acquisition_report = NewsIngestionRunner(source, store).run(now_utc)
                    self._news_acquisition_methods = dict(source.last_methods)
                finally:
                    store.close()
            except Exception:
                pass  # an acquisition hiccup never disturbs the loop

        thread = self._track_background_thread(threading.Thread(target=_acquire_and_store, name="news-acquisition-ladder", daemon=True))
        self._news_acquisition_thread = thread
        thread.start()

    def _maybe_run_exchange_filings(self, now) -> None:
        """Trunk II SENSES (S4c, research/145): at most every 5 min, fetch NSE corporate-announcement
        filings (board outcomes / results / dividends — the highest-signal news) via a curl_cffi Chrome
        session and store via the SAME ingestion runner. Runs in a BACKGROUND daemon thread so a hung
        NSE call never blocks the loop; stored filings are picked up by S2 extraction. Best-effort."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if self._exchange_filings_thread is not None and self._exchange_filings_thread.is_alive():
            return  # a fetch is already in flight
        if (self._exchange_filings_last_run_at is not None
                and (now_utc - self._exchange_filings_last_run_at) < _td(minutes=5)):
            return
        self._exchange_filings_last_run_at = now_utc

        import threading

        def _fetch_and_store() -> None:
            try:
                from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
                from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
                from nse_algo_trader.news_sentiment.nse_announcements_source import (
                    NseAnnouncementsSource,
                )

                store = NewsSqliteStore()
                try:
                    source = NseAnnouncementsSource()
                    self._latest_exchange_filings_report = NewsIngestionRunner(source, store).run(now_utc)
                finally:
                    store.close()
            except Exception:
                pass  # a filings hiccup never disturbs the loop

        thread = self._track_background_thread(threading.Thread(target=_fetch_and_store, name="nse-exchange-filings", daemon=True))
        self._exchange_filings_thread = thread
        thread.start()

    def _maybe_run_source_reliability(self, now) -> None:
        """Trunk II SENSES (S3, research/146): at most every 10 min, build the per-source reliability
        board — tier-seeded beta-reputation over the real sources in the store, folding in the freshness
        track (a source in a latest report's stale set is penalised). Cheap (store read); cached for the
        dashboard. The PRIMARY consumer (S7 gate weighting) is QUEUED, so this stays read-only."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._source_reliability_last_run_at is not None
                and (now_utc - self._source_reliability_last_run_at) < _td(minutes=10)):
            return
        self._source_reliability_last_run_at = now_utc
        try:
            from nse_algo_trader.news_sentiment.news_source_reliability import (
                SourceObservation,
                build_reliability_board,
            )
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore

            stale_ids: set = set()
            for report in (self._latest_news_ingestion_report,
                           self._latest_news_acquisition_report,
                           self._latest_exchange_filings_report):
                if report is not None:
                    stale_ids |= set(report.stale_source_ids)

            store = NewsSqliteStore()
            try:
                counts = store.source_item_counts()
            finally:
                store.close()

            observations = [
                SourceObservation(
                    source_id=sid, source_name=sname, tier=tier, item_count=count,
                    fresh_polls=0 if sid in stale_ids else 1,
                    stale_polls=1 if sid in stale_ids else 0,
                )
                for sid, sname, tier, count in counts
            ]
            self._latest_source_reliability_board = build_reliability_board(observations)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop

    def _maybe_run_news_entry_gate(self, now) -> None:
        """Trunk II SENSES (S7, research/147 — the PRIMARY consumer): at most every 5 min, build the
        per-symbol news-EVENT risk map (fresh, reliability-weighted filings/news per symbol) and PUSH
        it onto the loop state, so the entry gate sizes-down / defers entries on a symbol with a fresh
        material event. Advisory (identity) until the signal earns calibration — the earning is
        market/prequential-gated (Rule K), so this never moves a real trade yet, but it IS wired into
        the decision path (not display-only)."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._news_entry_gate_last_run_at is not None
                and (now_utc - self._news_entry_gate_last_run_at) < _td(minutes=5)):
            return
        self._news_entry_gate_last_run_at = now_utc
        try:
            from nse_algo_trader.news_sentiment.news_entry_gate import build_news_event_risk_by_symbol
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore

            if self._news_symbol_gazetteer is None:
                self._news_symbol_gazetteer = self._build_news_symbol_gazetteer(now_utc)
            if self._headline_sentiment_scorer is None:
                # Prefer FinBERT (91-93% F1 on India news, research/138); it falls back to finance-VADER
                # internally if the model can't load — so this is always safe (research/150).
                from nse_algo_trader.news_sentiment.headline_sentiment import FinBertSentimentScorer

                self._headline_sentiment_scorer = FinBertSentimentScorer()

            board = self._latest_source_reliability_board or ()
            reliability_by_source = {r.source_id: r.reliability for r in board}

            store = NewsSqliteStore()
            try:
                items = store.load_recent_items(limit=300)
            finally:
                store.close()

            risk_map = build_news_event_risk_by_symbol(
                items, reliability_by_source, now_utc, gazetteer=self._news_symbol_gazetteer,
                sentiment_scorer=self._headline_sentiment_scorer)
            self._state.news_event_risk_by_symbol = risk_map
            self._latest_sentiment_summary = self._summarize_headline_sentiment(items)
            # calibration_earned stays False (advisory) — the earning harness is market-gated (Rule K).

            # Index-level gate (research/151): push the stored S2 INDEX S/R level values per underlying
            # onto the loop state (reliability-filtered), so the option gate applies proximity caution.
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore as _NewsStore
            from nse_algo_trader.universe_registry.nse_index_options_reference import (
                NSE_INDEX_OPTION_UNDERLYING_SYMBOLS,
            )
            index_symbols = set(NSE_INDEX_OPTION_UNDERLYING_SYMBOLS)
            level_store = _NewsStore()
            try:
                index_levels: dict = {}
                for level_set in level_store.load_recent_levels(limit=200):
                    if level_set.underlying in index_symbols:
                        index_levels.setdefault(level_set.underlying, []).extend(
                            lvl.value for lvl in level_set.levels)
            finally:
                level_store.close()
            self._state.index_level_values_by_underlying = index_levels
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop

    def _build_news_symbol_gazetteer(self, now_utc):
        """Build the F&O-bounded NSE name↔symbol gazetteer (research/148): the ~216 F&O underlyings
        from the stored bhavcopy + NSE's cached equity master (name→symbol). Best-effort; None on fail."""
        try:
            import sqlite3

            from nse_algo_trader.market_data.market_data_sqlite_store import (
                DEFAULT_MARKET_DATA_DB_FILE_PATH,
            )
            from nse_algo_trader.news_sentiment.nse_symbol_gazetteer import (
                build_symbol_gazetteer,
                load_or_fetch_equity_master,
            )

            db_path = DEFAULT_MARKET_DATA_DB_FILE_PATH.expanduser()
            fo_symbols: set = set()
            if db_path.exists():
                connection = sqlite3.connect(str(db_path))
                try:
                    fo_symbols = {
                        r[0] for r in connection.execute(
                            "SELECT DISTINCT underlying_symbol FROM fo_bhavcopy_contracts").fetchall()
                    }
                finally:
                    connection.close()
            rows = load_or_fetch_equity_master(now_utc=now_utc)
            if not rows:
                return None
            return build_symbol_gazetteer(rows, restrict_symbols=fo_symbols or None)
        except Exception:
            return None

    def _maybe_run_stock_level_extraction(self, now) -> None:
        """Trunk II SENSES (research/149): at most every 10 min, extract per-STOCK price levels
        (analyst targets / support / resistance) from stored headlines via the F&O gazetteer, and store
        them in the SAME news_levels table as the index levels (underlying = the stock symbol).
        Completes S2 from index-only to the F&O stock universe (Rule L). Best-effort."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._stock_levels_last_run_at is not None
                and (now_utc - self._stock_levels_last_run_at) < _td(minutes=10)):
            return
        self._stock_levels_last_run_at = now_utc
        try:
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
            from nse_algo_trader.news_sentiment.stock_level_extraction import extract_stock_level_sets

            if self._news_symbol_gazetteer is None:
                self._news_symbol_gazetteer = self._build_news_symbol_gazetteer(now_utc)
            gazetteer = self._news_symbol_gazetteer
            if gazetteer is None:
                return

            store = NewsSqliteStore()
            try:
                all_sets = []
                for item in store.load_recent_items(limit=300):
                    all_sets.extend(extract_stock_level_sets(
                        item.content_hash, item.source_id, item.source_name, item.title, item.summary,
                        gazetteer, item.published_at))
                store.save_extracted_levels(all_sets)
                lines = tuple(f"{s.underlying} {lvl.kind} {lvl.value:,.0f}"
                              for s in all_sets for lvl in s.levels)[:6]
                self._latest_stock_levels = {
                    "stocks_with_levels": len({s.underlying for s in all_sets}),
                    "levels_found": sum(len(s.levels) for s in all_sets),
                    "top_lines": lines,
                }
            finally:
                store.close()
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop

    def _maybe_run_telegram_ingestion(self, now) -> None:
        """Trunk II SENSES (S5, research/152): at most every 5 min, poll the Telegram bot for new
        messages from the configured chat and store them tier SOCIAL (advisory — S3 floors them out of
        the gate). Disabled cleanly when no credentials in env. Best-effort; never disturbs the loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._telegram_last_run_at is not None
                and (now_utc - self._telegram_last_run_at) < _td(minutes=5)):
            return
        self._telegram_last_run_at = now_utc
        try:
            from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
            from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
            from nse_algo_trader.news_sentiment.telegram_credentials import load_telegram_credentials
            from nse_algo_trader.news_sentiment.telegram_news_source import TelegramNewsSource

            source = TelegramNewsSource(load_telegram_credentials())
            store = NewsSqliteStore()
            try:
                self._latest_telegram_report = NewsIngestionRunner(source, store).run(now_utc)
                self._latest_telegram_report = {
                    "enabled": source.is_enabled,
                    "summary": self._latest_telegram_report.summary,
                    "items_new": self._latest_telegram_report.items_new,
                    "stored_total": self._latest_telegram_report.stored_total,
                    "newest": self._latest_telegram_report.newest_titles[0]
                    if self._latest_telegram_report.newest_titles else "—",
                }
            finally:
                store.close()
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop

    def _maybe_run_axiology(self, now) -> None:
        """Trunk XIV AXIOLOGY (research/153): at most every 15 min, read the realized-return series from
        the experience memory and compute (a) the EXPLICIT utility with its named value decomposition and
        (b) a value-DRIFT verdict (is recent risk exceeding the stated values?). Read-only boards; the
        allocator/value-alignment consumers are QUEUED (Rule K). Best-effort; never disturbs the loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._axiology_last_run_at is not None
                and (now_utc - self._axiology_last_run_at) < _td(minutes=15)):
            return
        self._axiology_last_run_at = now_utc
        try:
            import sqlite3

            from nse_algo_trader.axiology.explicit_utility_function import evaluate_utility
            from nse_algo_trader.axiology.value_drift_monitor import detect_value_drift
            from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
                DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
            )

            db_path = DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()
            if not db_path.exists():
                return
            connection = sqlite3.connect(str(db_path))
            try:
                returns = [r[0] for r in connection.execute(
                    "SELECT realized_return_fraction FROM experience_nodes "
                    "WHERE realized_return_fraction IS NOT NULL ORDER BY occurred_at").fetchall()]
            finally:
                connection.close()

            self._latest_utility_score = evaluate_utility(returns)
            self._latest_value_drift = detect_value_drift(returns)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop

    def _maybe_run_will_arbitration(self, now) -> None:
        """Trunk III WILL (research/154): at most every 15 min, build each mechanism's multi-objective
        profile (utility [XIV] · return · −risk · sample-confidence) from the experience memory, ARBITRATE
        them (Pareto + weighted) and SCHEDULE which to pursue. Read-only board; the entry-loop consumer
        (prioritise mechanisms) is QUEUED (Rule K). Consumes axiology. Best-effort; never disturbs the loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._will_last_run_at is not None
                and (now_utc - self._will_last_run_at) < _td(minutes=15)):
            return
        self._will_last_run_at = now_utc
        try:
            import collections
            import sqlite3

            from nse_algo_trader.axiology.explicit_utility_function import evaluate_utility
            from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
                DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
            )
            from nse_algo_trader.will.goal_priority_scheduler import schedule_goals
            from nse_algo_trader.will.multi_objective_arbitration import (
                ObjectiveProfile,
                arbitrate,
                confidence_from_sample,
            )

            db_path = DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()
            if not db_path.exists():
                return
            connection = sqlite3.connect(str(db_path))
            try:
                rows = connection.execute(
                    "SELECT mechanism_name, realized_return_fraction FROM experience_nodes "
                    "WHERE realized_return_fraction IS NOT NULL AND mechanism_name IS NOT NULL").fetchall()
            finally:
                connection.close()

            by_mechanism: dict = collections.defaultdict(list)
            for mechanism, ret in rows:
                by_mechanism[mechanism].append(ret)

            profiles = []
            for mechanism, rets in by_mechanism.items():
                u = evaluate_utility(rets)
                profiles.append(ObjectiveProfile(
                    mechanism=mechanism, utility=u.utility, mean_return=u.mean_return,
                    neg_risk=-u.volatility, confidence=confidence_from_sample(len(rets)),
                    sample_size=len(rets)))

            self._latest_arbitration = arbitrate(profiles)
            self._latest_goal_schedule = schedule_goals(self._latest_arbitration, max_concurrent=3)
        except Exception:
            pass  # a diagnostic hiccup never disturbs the loop

    def _maybe_run_world_model_planning(self, now) -> None:
        """Trunk IX (research/166/167): at most every 10 min, learn the generative market-state model from
        recent real bars, plan, and cache the current-state entry verdict (per direction) on the loop state
        so the entry sites apply a confidence-gated size/veto. Best-effort; never disturbs the loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._world_model_last_run_at is not None
                and (now_utc - self._world_model_last_run_at) < _td(minutes=10)):
            return
        self._world_model_last_run_at = now_utc
        try:
            import sqlite3

            from nse_algo_trader.market_data.market_data_sqlite_store import (
                DEFAULT_MARKET_DATA_DB_FILE_PATH,
            )
            from nse_algo_trader.predictive_core.world_model_planning_engine import (
                WorldModelPlanningEngine,
            )

            db_path = DEFAULT_MARKET_DATA_DB_FILE_PATH.expanduser()
            if not db_path.exists():
                return
            connection = sqlite3.connect(str(db_path))
            try:
                tokens = [r[0] for r in connection.execute(
                    "SELECT instrument_token, COUNT(*) n FROM price_bars GROUP BY instrument_token "
                    "ORDER BY n DESC LIMIT 40")]
                series = []
                for token in tokens:
                    closes = [r[0] for r in connection.execute(
                        "SELECT close_price FROM price_bars WHERE instrument_token=? "
                        "ORDER BY bar_timestamp", (token,)) if r[0] is not None]
                    if len(closes) >= 30:
                        series.append(closes)
            finally:
                connection.close()
            if not series:
                return

            if self._world_model_engine is None:
                self._world_model_engine = WorldModelPlanningEngine()
            self._world_model_engine.ingest_close_series(series)
            # the highest-bar-count symbol's recent closes = the current market-state proxy
            proxy = max(series, key=len)[-60:]
            disagreement = float(getattr(self, "_last_ensemble_disagreement", 0.0) or 0.0)
            verdicts = {
                "long": self._world_model_engine.entry_verdict(proxy, "long", ensemble_disagreement=disagreement),
                "short": self._world_model_engine.entry_verdict(proxy, "short", ensemble_disagreement=disagreement),
            }
            self._world_model_verdicts = verdicts
            self._state.world_model_verdicts = verdicts
        except Exception:
            pass  # a data/compute hiccup must never disturb the trading loop (surfaced via the panel)

    def _maybe_run_curiosity(self, now) -> None:
        """Trunk XII (research/164/165): at most every 10 min, recompute the curiosity ExplorationPlan
        (per-(strategy×regime) learning-progress + novelty + boredom → exploration priority) from the
        experience history and cache it for the dashboard surface + the replay-curriculum selector.
        Best-effort; a hiccup never disturbs the loop (Rule O.3)."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._curiosity_last_run_at is not None
                and (now_utc - self._curiosity_last_run_at) < _td(minutes=10)):
            return
        self._curiosity_last_run_at = now_utc
        try:
            from nse_algo_trader.intrinsic_motivation.curiosity_engine import CuriosityEngine

            if self._curiosity_engine is None:
                self._curiosity_engine = CuriosityEngine()
            self._curiosity_plan = self._curiosity_engine.compute_exploration_plan()
        except Exception:
            pass  # a data/compute hiccup must never disturb the trading loop (surfaced via the panel)

    def _maybe_run_autopoiesis_homeostat(self, now) -> None:
        """Trunk X AUTOPOIESIS (research/172): run one MAPE-K self-maintenance cycle every 5 minutes.

        Reads every vital sign off the real organism, scores each component's health, audits operational
        closure, estimates remaining useful life, plans maintenance, regulates the throttle, and publishes
        the entry-site vitality lever. The orchestrator OWNS its SQLite store and this method is the only
        caller, so the store stays single-threaded as its threading contract requires.

        Repair is ADVISORY (dry-run) until the operator enables autonomy — the full acting path runs every
        cycle so refusals, budgets and breakers are continuously exercised rather than dormant.
        Best-effort: a homeostat hiccup must never disturb the loop it exists to protect."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._autopoiesis_last_run_at is not None
                and (now_utc - self._autopoiesis_last_run_at) < _td(minutes=5)):
            return
        self._autopoiesis_last_run_at = now_utc
        try:
            if self._autopoiesis_homeostat is None:
                from nse_algo_trader.autopoiesis.autopoiesis_orchestrator import (
                    build_autopoiesis_homeostat,
                )
                from nse_algo_trader.autopoiesis.autopoiesis_state_store import AutopoiesisStateStore

                self._autopoiesis_state_store = AutopoiesisStateStore()
                self._autopoiesis_homeostat = build_autopoiesis_homeostat(
                    state_store=self._autopoiesis_state_store,
                    autonomous_repair_enabled=False,
                )
                # Rule G: the entry sites read the gate through the loop state.
                self._state.organism_vitality_gate = self._autopoiesis_homeostat.vitality_gate
            self._latest_autopoiesis_report = self._autopoiesis_homeostat.run_maintenance_cycle(now_utc)
        except Exception as _failure:
            self._autopoiesis_failure_count += 1
            print(f"[autopoiesis] maintenance cycle failed: {type(_failure).__name__}: {_failure}")

    def _maybe_run_capital_allocation(self, now) -> None:
        """Trunk III WILL (research/163): at most every 5 min, solve the CVXPY capital-allocation problem
        over the real traded universe (distinct strategy·kind·direction combos from experience memory) and
        cache the AllocationResult on the loop state — an advisory size-DOWN lever at the entry sites until
        the optimizer EARNS the right to act (≥ min trading days). Best-effort; a solver hiccup never
        disturbs the loop. The open blocker (Rule K) is more trading DAYS + wiring the exact per-tick entry
        batch (vs this experience-derived advisory set) so the joint up-sizing reallocation acts."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if (self._capital_allocation_last_run_at is not None
                and (now_utc - self._capital_allocation_last_run_at) < _td(minutes=5)):
            return
        self._capital_allocation_last_run_at = now_utc
        try:
            import numpy as _np

            from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate
            from nse_algo_trader.capital_allocation.capital_allocation_optimizer import (
                CapitalAllocationOptimizer,
            )
            from nse_algo_trader.memory_reflection.sqlite_experience_memory import SqliteExperienceMemory

            memory = getattr(self, "_experience_memory", None) or SqliteExperienceMemory()
            records = memory.recent_closed_experiences(limit=5000)
            if not records:
                return
            # One candidate per distinct (strategy_tag, instrument_kind, direction) actually traded; its
            # forward edge μ = its clipped historical mean pseudo-return (advisory prior until win-prob
            # joins). Kind maps to segment; option kinds get a nominal lot of 50.
            by_combo: dict[tuple, list[float]] = {}
            for r in records:
                pnl = r.get("realized_pnl")
                combo = (r.get("strategy_tag"), r.get("instrument_kind"), str(r.get("direction")).lower())
                if None in combo or pnl is None or not _np.isfinite(pnl):
                    continue
                by_combo.setdefault(combo, []).append(float(pnl))
            scale = _np.median([abs(p) for ps in by_combo.values() for p in ps]) or 1.0
            candidates = []
            for (strategy, kind, direction), pnls in list(by_combo.items())[:12]:
                mu = float(_np.clip(_np.mean(pnls) / scale, -0.1, 0.1))
                candidates.append(AllocationCandidate(
                    candidate_id=f"{strategy}|{kind}|{direction}",
                    segment=kind, underlying=str(strategy)[:24], direction=direction, instrument_kind=kind,
                    expected_edge_mu=mu, per_unit_risk=5.0, entry_price=100.0,
                    lot_or_tick_size=(50 if "option" in kind else 1), est_margin_per_unit=500.0))
            if not candidates:
                return
            if self._capital_allocation_optimizer is None:
                self._capital_allocation_optimizer = CapitalAllocationOptimizer(experience_source=memory)
            capital = float(getattr(self._state, "account_capital", 1_000_000) or 1_000_000)
            result = self._capital_allocation_optimizer.allocate(candidates, account_capital=capital)
            self._capital_allocation_result = result
            self._state.capital_allocation_result = result
        except Exception:
            pass  # a solver / data hiccup must never disturb the trading loop (Rule O.3 — surfaced via panel)

    def _maybe_run_win_probability_engine(self, now) -> None:
        """Trunk IX PREDICTIVE-CORE (research/156): at most every 6h, load-or-train the ML win-probability
        engine from the experience memory and PUSH its size-multiplier callable onto the loop state, so the
        entry gate sizes by the calibrated edge — but ONLY once the model beats the fixed-formula baseline
        on held-out CV (earned on real data). Runs in a BACKGROUND thread (a fit is a few seconds). The one
        open blocker is more trading DAYS for true walk-forward (Rule K). Best-effort; never disturbs loop."""
        from datetime import datetime as _dt, timedelta as _td

        now_utc = _dt.now(UTC)
        if self._win_probability_thread is not None and self._win_probability_thread.is_alive():
            return
        if (self._win_probability_last_run_at is not None
                and (now_utc - self._win_probability_last_run_at) < _td(hours=6)):
            return
        self._win_probability_last_run_at = now_utc

        import threading

        def _train_and_wire() -> None:
            try:
                import sqlite3

                from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
                    DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
                )
                from nse_algo_trader.predictive_core.win_probability_engine import (
                    WinProbabilityEngine,
                    feature_values_from_prediction_record,
                )

                db_path = DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()
                if not db_path.exists():
                    return
                connection = sqlite3.connect(str(db_path))
                connection.row_factory = sqlite3.Row
                try:
                    records = [dict(r) for r in connection.execute("SELECT * FROM experience_nodes")]
                finally:
                    connection.close()

                engine = WinProbabilityEngine()
                if not engine.load_or_train(records):
                    return
                self._win_probability_engine = engine

                def _multiplier_fn(prediction_record, direction, instrument_kind, reward_risk, when):
                    features = feature_values_from_prediction_record(
                        prediction_record, direction, instrument_kind, when)
                    return engine.win_probability_size_multiplier(features, reward_risk)

                self._state.win_probability_size_multiplier_fn = _multiplier_fn
            except Exception:
                pass  # a training hiccup never disturbs the loop

        thread = self._track_background_thread(threading.Thread(target=_train_and_wire, name="win-probability-engine", daemon=True))
        self._win_probability_thread = thread
        thread.start()

    def _summarize_headline_sentiment(self, items) -> dict:
        """Score recent headlines (finance-VADER) → mood counts + the most-adverse recent headlines
        (research/150). Best-effort; returns None on failure so the surface degrades gracefully."""
        try:
            scorer = self._headline_sentiment_scorer
            if scorer is None:
                return None
            scored = [(scorer.score(it.title), it.title) for it in items[:120]]
            counts = {"adverse": 0, "neutral": 0, "favourable": 0}
            for sentiment, _title in scored:
                counts[sentiment.label] += 1
            most_adverse = tuple(
                f"{s.score:+.2f} {t[:52]}"
                for s, t in sorted(scored, key=lambda st: st[0].score)[:4] if s.label == "adverse")
            return {"counts": counts, "scored": len(scored), "most_adverse": most_adverse}
        except Exception:
            return None

    def _collect_workspace_contributions(self) -> list:
        """Trunk VIII: gather the faculties' CURRENT cached signals into uniform workspace
        contributions. Safety verdicts (constitution / tripwires / goal-integrity / ethics-law /
        incidents) bid as safety (critical when they are), so the workspace is safety-first; the
        advisory faculties bid as risk/opportunity. Reads only already-computed verdicts (no work)."""
        from nse_algo_trader.sentience.global_workspace import WorkspaceContribution

        contributions: list = []

        def _add(source, kind, urgency, relevance, confidence, content, is_critical=False):
            contributions.append(WorkspaceContribution(
                source=source, kind=kind, urgency=urgency, relevance=relevance,
                confidence=confidence, content=content, is_critical=is_critical))

        v = self._latest_constitutional_verdict
        if v is not None and not v.permitted:
            _add("constitution", "safety", 1.0, 1.0, 1.0,
                 f"constitutional violation: {v.detail}", is_critical=True)
        for verdict, name in (
            (self._latest_wireheading_verdict, "wireheading"),
            (self._latest_deceptive_alignment_verdict, "deceptive_alignment"),
        ):
            if verdict is not None and verdict.tripped:
                _add(name, "safety", 0.9 if verdict.is_critical else 0.5, 0.9, 0.8,
                     f"{name} tripwire {verdict.severity}: {verdict.detail}",
                     is_critical=verdict.is_critical)
        gi = self._latest_goal_integrity_verdict
        if gi is not None and not gi.aligned:
            _add("goal_integrity", "safety", 0.8 if gi.is_critical else 0.45,
                 0.85, min(1.0, gi.integrity_score + 0.5),
                 f"goal drift: {', '.join(gi.drift_flags)}", is_critical=gi.is_critical)
        law = self._latest_law_compliance_report
        if law is not None and not law.compliant:
            _add("ethics_law", "safety", 1.0, 1.0, 1.0,
                 f"regulatory violation: {', '.join(law.violations)}", is_critical=True)
        pm = self._latest_incident_post_mortem
        if pm is not None and pm.critical_count:
            _add("incident_post_mortem", "safety", 0.7, 0.7, 0.9,
                 f"{pm.critical_count} critical safety incident(s) on record")
        rt = self._latest_red_team_report
        if rt is not None and rt.fragile:
            _add("red_team", "risk", 0.5, 0.7, 0.7,
                 f"champion FRAGILE: {rt.summary}")
        # advisory opportunity/risk signals (present but non-critical) — bid modestly.
        rep = self._latest_interpretability_report
        if rep is not None and rep.red_flags:
            _add("interpretability", "risk", 0.4, 0.6, 0.6,
                 f"influential-but-unreliable mechanism(s): {', '.join(rep.red_flags[:2])}")

        # Trunk VIII cross-modal binding: fuse corroborating "elevated risk" evidence across
        # distinct MODALITIES (microstructure / memory / safety) into one bound percept; when ≥2
        # modalities corroborate, inject it as a higher-confidence workspace contribution.
        bound = self._bind_cross_modal_risk()
        self._latest_bound_percept = bound
        if bound is not None and bound.is_bound:
            _add("cross_modal", "risk", 0.6, 0.85, bound.bound_confidence,
                 f"cross-modal risk bound {bound.bound_confidence:.0%} "
                 f"({', '.join(bound.corroborating_modalities)})")
        return contributions

    def _bind_cross_modal_risk(self):
        """Trunk VIII: build 'elevated risk' signals from REAL faculty state across distinct
        MODALITIES and bind them (Stouffer). memory = goal-integrity not-aligned; cognition =
        interpretability red-flags; safety = any tripwire/red-team fragile. Returns BoundPercept."""
        from nse_algo_trader.sentience.cross_modal_binding import ModalitySignal, bind_percept

        signals: list = []
        gi = self._latest_goal_integrity_verdict
        if gi is not None:
            signals.append(ModalitySignal("memory", 1.0 - gi.integrity_score, not gi.aligned))
        rep = self._latest_interpretability_report
        if rep is not None:
            signals.append(ModalitySignal(
                "cognition", 1.0 - rep.reliable_share, bool(rep.red_flags)))
        wire = self._latest_wireheading_verdict
        dec = self._latest_deceptive_alignment_verdict
        rt = self._latest_red_team_report
        safety_hit = bool((wire and wire.tripped) or (dec and dec.tripped) or (rt and rt.fragile))
        if wire is not None or rt is not None:
            signals.append(ModalitySignal("safety", 0.7 if safety_hit else 0.3, safety_hit))
        if not signals:
            return None
        return bind_percept(signals, "elevated risk")

    def _maybe_run_global_workspace(self, now) -> None:
        """Trunk VIII SENTIENCE: each pass, run one Global Workspace cycle over the faculties'
        current signals — collect → score salience → compete → ignite → broadcast the dominant global
        context (blinker bus). Safety-first: a critical safety signal wins and ignites. Best-effort;
        no signals just leaves no broadcast this cycle. (Decision-consumer is a queued VIII branch.)"""
        try:
            contributions = self._collect_workspace_contributions()
            # Trunk VIII selective + state-dependent attention: reshape salience by the current
            # context (regime) + internal state (drawdown / off-switch) before the competition.
            from nse_algo_trader.sentience.workspace_attention import (
                AttentionContext,
                apply_attention,
            )

            ledger = self._state.ledger
            starting = getattr(ledger, "starting_virtual_cash", 0.0) or 1.0
            realized = getattr(ledger, "realized_pnl", 0.0)
            switch = self._state.corrigibility_switch
            context = AttentionContext(
                market_regime=self._current_session_market_regime(),
                drawdown_fraction=max(0.0, -realized / starting),
                off_switch_engaged=bool(switch is not None and not switch.permits_trading()),
            )
            self._latest_attention_context = context
            contributions = apply_attention(contributions, context)
            broadcast = self._global_workspace.run_cycle(contributions)
            if broadcast is not None:
                self._latest_workspace_broadcast = broadcast
            # Push the dominant global context onto the trading state so the entry gate acts on it
            # (Trunk VIII decision-consumer): an ignited safety/risk focus trims entry size.
            self._state.workspace_broadcast = self._global_workspace.latest_broadcast
            # Trunk VIII self-model + attention schema: read-only self-representations built from the
            # already-computed faculty state + the workspace's own attention.
            from nse_algo_trader.sentience.attention_schema import build_attention_schema
            from nse_algo_trader.sentience.self_model import build_self_model

            rep = self._latest_interpretability_report
            gi = self._latest_goal_integrity_verdict
            cv = self._latest_constitutional_verdict
            reliable_share = getattr(rep, "reliable_share", 0.0) if rep else 0.0
            trusted = sum(
                1 for a in getattr(rep, "attributions", ()) if a.reliable and a.edge_positive
            ) if rep else 0
            distrusted = tuple(getattr(rep, "red_flags", ())) if rep else ()
            self._latest_self_model = build_self_model(
                calibration_reliable_share=reliable_share,
                trusted_mechanism_count=trusted,
                distrusted_mechanisms=distrusted,
                constitution_compliant=(cv.permitted if cv is not None else True),
                off_switch_engaged=context.off_switch_engaged,
                goal_aligned=(gi.aligned if gi is not None else True),
                recent_return_fraction=-context.drawdown_fraction,
            )
            self._latest_attention_schema = build_attention_schema(
                broadcast, context, contributions
            )
            # Trunk VIII workspace replay/rumination: replay the recent ignited-broadcast history to
            # detect a persistent recurring concern (the mind returning to the same thing).
            from nse_algo_trader.sentience.workspace_rumination import ruminate

            self._latest_rumination = ruminate(list(self._workspace_broadcast_history))
            # Trunk VIII metacognition + indicator scoreboard: watch the workspace's OWN operation.
            from nse_algo_trader.sentience.indicator_scoreboard import build_indicator_scoreboard
            from nse_algo_trader.sentience.workspace_metacognition import assess_metacognition

            self._workspace_cycle_log.append(
                (bool(broadcast is not None and broadcast.ignited), len(contributions))
            )
            self._latest_metacognition = assess_metacognition(list(self._workspace_cycle_log))
            self._latest_indicator_scoreboard = build_indicator_scoreboard(
                contributions, list(self._workspace_broadcast_history)
            )
        except Exception:
            pass  # the integrator must never disturb the loop

    def _maybe_reevaluate_champion_challenger(self, now) -> None:
        """§53 slice 5c-i.b + 5c-iii: at most once/day, run the champion-challenger
        tournament over the stored real sessions — a GLOBAL tournament (all sessions) plus a
        PER-MARKET-REGIME tournament (sessions partitioned by their ADX regime). Each gated
        promotion is persisted (global or per regime) and refreshes the live cache. Best-
        effort — any failure leaves the incumbent champions untouched and never disturbs the
        loop."""
        from nse_algo_trader.paper_trading.champion_challenger_reevaluation_scheduler import (  # noqa: E501
            DEFAULT_ORB_CHALLENGER_GRID,
            is_reevaluation_due,
        )

        today = now.date()
        if not is_reevaluation_due(self._champion_challenger_last_run_date, today):
            return
        try:
            from nse_algo_trader.paper_trading.champion_challenger_orb_evaluator import (
                evaluate_champion_vs_challengers,
            )
            from nse_algo_trader.paper_trading.per_regime_champion_evaluator import (
                evaluate_per_regime_champions,
            )

            labelled = self._load_stored_benchmark_sessions_labelled()
            if len(labelled) < self._champion_challenger_min_sessions:
                self._champion_challenger_last_run_date = today  # not enough data yet
                return
            store = self._champion_store()
            grid = (
                self._champion_challenger_candidate_grid
                if self._champion_challenger_candidate_grid is not None
                else DEFAULT_ORB_CHALLENGER_GRID
            )

            # L2 validation engine (research/166): a PERSISTENT trial registry gives the DSR the honest
            # cumulative count of every config ever trialed (not just this batch), and a holdout custodian
            # keeps a sealed most-recent window out of config selection + final-validates a winner on it.
            from nse_algo_trader.paper_trading.holdout_custodian import HoldoutCustodian
            from nse_algo_trader.paper_trading.strategy_trial_registry import (
                StrategyTrialRegistry,
            )

            trial_registry = StrategyTrialRegistry()  # default SQLite path → accumulates across runs

            # GLOBAL champion (all sessions).
            global_sessions = [(bars, instrument) for bars, instrument, _ in labelled]
            try:
                session_dates = sorted(
                    {bars[0].timestamp.date() for bars, _ in global_sessions if bars}
                )
                holdout_custodian = (
                    HoldoutCustodian(session_dates) if len(session_dates) >= 5 else None
                )
            except Exception as holdout_error:  # noqa: BLE001 — malformed sessions → no holdout, not a crash
                holdout_custodian = None
                print(
                    f"[champion-challenger] holdout custodian unavailable "
                    f"({type(holdout_error).__name__}) — running without a sealed holdout",
                    flush=True,
                )
            global_decision = evaluate_champion_vs_challengers(
                store.load_champion_or_default(), grid, global_sessions,
                trial_registry=trial_registry, holdout_custodian=holdout_custodian,
                strategy_family="orb_cash_global",
            )
            if global_decision.champion_replaced:
                store.save_champion(global_decision.winning_config)
                self._champion_orb_config_by_regime["global"] = global_decision.winning_config
                print("[champion-challenger] promoted GLOBAL champion: "
                      f"{global_decision.promotion_reason}", flush=True)

            # PER-REGIME champions.
            regimes = {regime for _, _, regime in labelled}
            champion_by_regime = {
                regime: store.load_champion_or_default(market_regime=regime)
                for regime in regimes
            }
            for regime, decision in evaluate_per_regime_champions(
                labelled, champion_by_regime, grid, trial_registry=trial_registry
            ).items():
                if decision.champion_replaced:
                    store.save_champion(decision.winning_config, market_regime=regime)
                    self._champion_orb_config_by_regime[regime] = decision.winning_config
                    print(f"[champion-challenger] promoted {regime} champion: "
                          f"{decision.promotion_reason}", flush=True)
        except Exception:
            pass  # re-eval must never break the loop
        finally:
            self._champion_challenger_last_run_date = today

    def _load_stored_benchmark_sessions_labelled(self) -> list:
        """The stored benchmark sessions, each labelled with its ADX market regime (§53
        slice 5c-iii): `[(session_bars, instrument, market_regime), …]`."""
        from nse_algo_trader.paper_trading.historical_session_market_regime_classifier import (  # noqa: E501
            classify_session_market_regime,
        )

        return [
            (bars, instrument, classify_session_market_regime(bars).value)
            for bars, instrument in self._load_stored_benchmark_sessions()
        ]

    def _load_stored_benchmark_sessions(self) -> list:
        """Every stored session for the market-regime/champion benchmark instrument, as
        `[(session_bars, instrument), …]` — the real evaluation set for the tournament."""
        from datetime import timedelta

        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.universe_registry import (
            ExchangeSegment,
            Instrument,
            InstrumentKind,
        )

        sessions: list = []
        store = MarketDataSqliteStore()
        try:
            benchmark_token = self._curriculum_benchmark_token(store)
            if benchmark_token is None:
                return sessions
            instrument = Instrument(
                instrument_token=benchmark_token, trading_symbol="BENCHMARK",
                exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
                lot_size=1, tick_size=0.05,
            )
            dates = [
                datetime.fromisoformat(row[0]).date()
                for row in store._connection.execute(
                    "SELECT DISTINCT date(bar_timestamp) FROM price_bars "
                    "WHERE bar_interval='5m' AND instrument_token=? ORDER BY 1",
                    (benchmark_token,),
                )
            ]
            for session_date in dates:
                day_start = datetime(
                    session_date.year, session_date.month, session_date.day,
                    tzinfo=_INDIA_MARKET_TIMEZONE,
                )
                bars = store.load_price_bars(
                    benchmark_token, BarInterval.MINUTE_5,
                    day_start, day_start + timedelta(days=1),
                )
                if bars:
                    sessions.append((bars, instrument))
        finally:
            store.close()
        return sessions

    def _current_data_provenance(self) -> str:
        """Provenance of the data the loop is trading on right now — the active
        feed's stamp in replay, "live" otherwise (research/53 §8.2). A trade
        opens and squares off within one session/mode, so this drain-time read
        equals the trade's provenance. Consumes the slice-1 watermark (Rule G)."""
        from nse_algo_trader.paper_trading.replay_experience_provenance import (
            DataProvenance,
        )

        if self._replay_feed is not None and self._feed is self._replay_feed:
            return self._replay_feed.provenance_stamp().provenance.value
        return DataProvenance.LIVE.value

    def _current_session_market_regime(self) -> str:
        """§53 slice 5b: the ADX market regime of the session the loop is trading right
        now — the replay session in replay, today in live — so each closed experience is
        tagged with its regime (the axis the multi-regime queries need variety on). A
        trade opens+closes within one session, so this drain-time read is the trade's
        regime. Best-effort → 'unknown' (never blocks the drain)."""
        if (
            self._replay_feed is not None
            and self._feed is self._replay_feed
            and self._high_fidelity_replay is not None
        ):
            return self._market_regime_for_date(self._high_fidelity_replay.session_date)
        if self._feed is self._live_feed:
            return self._market_regime_for_date(
                datetime.now(_INDIA_MARKET_TIMEZONE).date()
            )
        return "unknown"  # store-5m replay spans many dates — no single regime

    def _market_regime_for_date(self, session_date) -> str:
        """Classify a session's ADX market regime from the stored benchmark bars, cached
        per date. 'unknown' when no bars are stored for that date (best-effort)."""
        if session_date in self._market_regime_cache_by_date:
            return self._market_regime_cache_by_date[session_date]
        from datetime import timedelta

        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.paper_trading.historical_session_market_regime_classifier import (  # noqa: E501
            classify_session_market_regime,
        )

        regime = "unknown"
        try:
            store = MarketDataSqliteStore()
            try:
                benchmark_token = self._curriculum_benchmark_token(store)
                if benchmark_token is not None:
                    day_start = datetime(
                        session_date.year, session_date.month, session_date.day,
                        tzinfo=_INDIA_MARKET_TIMEZONE,
                    )
                    bars = store.load_price_bars(
                        benchmark_token, BarInterval.MINUTE_5,
                        day_start, day_start + timedelta(days=1),
                    )
                    if bars:
                        regime = classify_session_market_regime(bars).value
            finally:
                store.close()
        except Exception:
            regime = "unknown"
        self._market_regime_cache_by_date[session_date] = regime
        return regime

    def _drain_closed_experiments_into_memory(self) -> None:
        """Record each closed §9 experiment the loop emitted into Layer-10
        ExperienceMemory (Rule G wiring). Runs in the writer thread; the store
        is opened lazily here so its SQLite connection lives in this thread.
        Best-effort — a memory hiccup must never stall the trading loop."""
        events = self._state.closed_experiment_events
        try:
            if self._experience_memory is None:
                self._experience_memory = SqliteExperienceMemory()
            data_provenance = self._current_data_provenance()
            market_regime = self._current_session_market_regime()
            risk_map = self._state.debate_risk_score_by_mechanism
            debate_risk_observations = []  # (mechanism, risk_score, is_win, closed_at)
            while events:
                graded, closed_trade, instrument_kind = events.pop(0)
                self._experience_memory.record_closed_experiment(
                    build_closed_experiment(
                        graded, closed_trade, instrument_kind, data_provenance,
                        market_regime,
                    )
                )
                # Layer 11 slice 2c: accrue a PREQUENTIAL (risk_score, outcome) pair for a LIVE
                # trade whose mechanism was debated today (risk_score predates the outcome →
                # non-circular). Replay/unknown-mechanism outcomes are never recorded.
                mechanism = graded.record.mechanism_name
                if data_provenance == "live" and mechanism in risk_map:
                    debate_risk_observations.append((
                        mechanism, risk_map[mechanism],
                        graded.actual_outcome.value == "win", closed_trade.closed_at,
                    ))
            self._record_debate_risk_observations(debate_risk_observations)
            # Refresh the antibody veto set (Layer 10 slice 3): mechanisms the
            # memory has statistically refuted stop taking new entries.
            from nse_algo_trader.memory_reflection import (
                learn_mechanism_recalibrations,
                vetoed_mechanisms,
            )

            vetoed = vetoed_mechanisms(self._experience_memory)
            # research/51: learn win-probability bias offsets + hard-veto no-edge
            # (resolution≈0) mechanisms — the memory acting on its own diagnosis.
            offsets, no_edge = learn_mechanism_recalibrations(self._experience_memory)
            self._state.recalibration_offset_by_mechanism = offsets
            self._state.vetoed_mechanisms = vetoed | no_edge
        except Exception:
            pass

    def _information_diet_dict(self) -> dict:
        """Aggregate the loop's decision-input counters into the §10 information
        diet + health read (research/52)."""
        from dataclasses import asdict

        from nse_algo_trader.paper_trading.information_diet import (
            read_information_diet,
        )

        state = self._state
        # §53 slice 3b-i: feed the live-vs-replay experience mix so the diet warns
        # on over-reliance on 24/7 replay.
        by_provenance = self._memory_experiment_count_by_provenance()
        return asdict(
            read_information_diet(
                decisions_considered=state.entry_decisions_considered,
                positioning_deferred=state.positioning_deferred_count,
                antibody_vetoed=state.vetoed_entry_count,
                memory_recalibrated=state.recalibrated_entry_count,
                shadow_probes=state.shadow_entry_count,
                live_experience_count=by_provenance.get("live", 0),
                replay_experience_count=by_provenance.get("replay_faithful", 0),
            )
        )

    def _refresh_opponent_ledger(self, now: datetime) -> None:
        """Fetch NSE participant-wise OI at most once per calendar date and
        cache the opponent-ledger reading (Layer 10 §10, Rule G wiring). Walks
        back over holidays/before-publish 404s to collect the most recent report
        plus a window of prior trading days for the multi-day FII-net trend
        (slice 3). Best-effort — a fetch hiccup must never stall the loop."""
        today = now.date()
        if self._opponent_ledger_fetched_for == today:
            return
        self._opponent_ledger_fetched_for = today
        try:
            from datetime import timedelta

            from nse_algo_trader.participant_positioning import read_opponent_ledger
            from nse_algo_trader.participant_positioning.participant_positioning_source import (  # noqa: E501
                ParticipantCategory,
            )

            # History walk: collect up to _FII_NET_TREND_WINDOW trading-day OI
            # snapshots (newest first), tolerating weekend/holiday 404s.
            dated_snapshots: list = []
            probe_date = today
            for _ in range(self._FII_NET_TREND_WINDOW + 8):
                if len(dated_snapshots) >= self._FII_NET_TREND_WINDOW:
                    break
                snapshot = self._participant_positioning_source.positioning_on(
                    probe_date
                )
                if snapshot is not None:
                    dated_snapshots.append((probe_date, snapshot))
                probe_date -= timedelta(days=1)

            if not dated_snapshots:
                return
            newest_date, newest_snapshot = dated_snapshots[0]
            # Recent FII index-futures net, oldest→newest (today last).
            recent_fii_nets = [
                row.future_index_net_long
                for _, snap in reversed(dated_snapshots)
                if (row := snap.row_for(ParticipantCategory.FII)) is not None
            ]
            volume_snapshot = self._participant_positioning_source.volume_on(
                newest_date
            )
            reading = read_opponent_ledger(
                newest_snapshot, volume_snapshot, recent_fii_nets
            )
            if reading is not None:
                from dataclasses import asdict

                self._opponent_ledger_reading = asdict(reading)
                self._state.market_positioning_bias = reading
        except Exception:
            # Retry on the next calendar date, not this pass.
            pass

    def _advance_one_pass(self, now: datetime, replay_mode: bool = False) -> None:
        # Honor the dashboard control plane each pass: risk budget follows the
        # configured capital/risk, and turning cash ORB off stops opening NEW
        # positions (existing open risk is still managed + squared off — never
        # abandoned). Config is re-read live so a phone toggle takes effect.
        control_config = load_trading_control_config()
        risk_budget = map_control_config_to_risk_budget(control_config)
        # Enforce the min/max capital-per-trade knobs on the live path
        # (research/41 L9): the loop clamps risk-sized qty to these each pass.
        self._state.max_capital_per_trade = control_config.max_capital_per_trade
        self._state.min_capital_per_trade = control_config.min_capital_per_trade
        seeds_this_pass = (
            self._max_new_cash_seeds_per_pass
            if is_orb_cash_trading_enabled(control_config)
            else 0
        )
        run_live_universe_scan_pass(
            self._state,
            self._cash_universe,
            self._feed,
            risk_budget,
            now,
            max_new_cash_seeds_per_pass=seeds_this_pass,
            strategy_config=self._champion_orb_config(),
            market_clock=self._clock,
        )
        # Options credit-spread half (index + stock options): regime-gated,
        # defined-risk, atomic, squared off at 15:15 by Layer 8. Skipped in
        # replay mode — the replay store holds cash bars only (no option chain).
        if replay_mode or self._tradable_universe is None:
            return
        options_enabled = control_config.is_segment_enabled(
            TradableSegment.NSE_INDEX_OPTIONS
        ) or control_config.is_segment_enabled(TradableSegment.NSE_STOCK_OPTIONS)
        is_square_off = self._square_off_schedule.should_force_square_off_now(
            now, self._clock
        )
        advance_option_credit_spread_pass(
            self._state,
            self._tradable_universe,
            self._feed,
            risk_budget,
            now,
            max_new_underlying_seeds_per_pass=(
                self._max_new_option_seeds_per_pass if options_enabled else 0
            ),
            is_square_off_window=is_square_off,
            banned_underlying_symbols=self._banned_underlying_symbols,
        )

    def _publish(self, now: datetime, price_open_positions: bool = True) -> None:
        open_instruments = [
            position.instrument for position in self._state.open_positions.values()
        ]
        price_by_token: dict[int, float] = {}
        if price_open_positions and open_instruments:
            try:
                price_by_token = self._feed.latest_price_by_token(open_instruments)
            except Exception:
                price_by_token = {}  # show positions without a live mark
        views = []
        for position in self._state.open_positions.values():
            last_price = price_by_token.get(position.instrument.instrument_token)
            unrealized = None
            if last_price is not None:
                direction_sign = 1 if position.direction.value == "long" else -1
                unrealized = (
                    (last_price - position.entry_price)
                    * direction_sign
                    * position.quantity
                )
            views.append(
                OpenPositionView(
                    trading_symbol=position.instrument.trading_symbol,
                    direction=position.direction.value,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    stop_loss_price=position.stop_loss_price,
                    target_price=position.target_price,
                    last_price=last_price,
                    unrealized_pnl=unrealized,
                    assigned_table=position.prediction_record.assigned_table.value,
                    segment="cash",
                    maximum_favourable_profit=position.excursion.maximum_favourable_profit,
                    maximum_adverse_profit=position.excursion.maximum_adverse_profit,
                    profit_locked=position.profit_trail.locked_profit,
                )
            )
        # Option credit spreads -> one synthetic row each (flows into the 3
        # §9 tables alongside cash; segment tags it index/stock option).
        views.extend(self._option_spread_views(price_open_positions))
        views.sort(key=lambda view: -(view.unrealized_pnl or 0.0))
        recent_closed = self._recent_closed_trades()
        segment_boards = self._segment_boards(views, recent_closed)
        ledger = self._state.ledger
        paper_summary = PaperTradingSummary(
            starting_virtual_cash=ledger.starting_virtual_cash,
            realized_pnl=ledger.realized_pnl,
            fill_count=len(ledger.recorded_fills),
            is_flat=ledger.is_flat(),
        )
        table_summaries = tuple(
            self._summarize_prediction_table(table)
            for table in PredictionLabeledTable
        )
        confident_loss_aware_pnl = self._confident_loss_aware_pnl_split()
        snapshot = LivePaperPublishedSnapshot(
            open_positions=tuple(views),
            closed_trade_count=(self._memory_experiment_count() or len(self._state.closed_trades)),
            cash_universe_size=len(self._cash_universe),
            seeded_count=len(self._state.seeded_cash_tokens),
            last_pass_at=now.isoformat(),
            is_market_open=self._clock.is_market_open(now),
            paper_trading_summary=paper_summary,
            prediction_table_summaries=table_summaries,
            confident_win_beats_confident_loss=(
                self._state.scoreboard.confident_win_beats_confident_loss()
            ),
            segment_boards=segment_boards,
            recent_closed_trades=recent_closed,
            combined_realized_pnl=(
                ledger.realized_pnl
                + self._state.realized_option_spread_pnl
                + self._state.realized_directional_option_pnl
                + self._zero_dte_realized_pnl()  # B34 Slice B: 0-DTE was omitted from the headline
            ),
            real_realized_pnl=confident_loss_aware_pnl.real_realized_pnl,
            confident_loss_probe_realized_pnl=confident_loss_aware_pnl.probe_realized_pnl,
            confident_loss_prediction_accuracy=confident_loss_aware_pnl.probe_prediction_accuracy,
            strategy_readiness=_strategy_readiness_summaries(self._state),
            memory_experiment_count=self._memory_experiment_count(),
            experiment_count_by_provenance=self._memory_experiment_count_by_provenance(),
            prequential_forecast_score=self._memory_prequential_forecast_score(),
            calibration_board=self._memory_calibration_board(),
            assumption_verdicts=self._memory_assumption_verdicts(),
            vetoed_mechanism_count=len(self._state.vetoed_mechanisms),
            vetoed_entry_count=self._state.vetoed_entry_count,
            shadow_entry_count=self._state.shadow_entry_count,
            opponent_ledger=self._opponent_ledger_reading,
            positioning_deferred_count=self._state.positioning_deferred_count,
            information_diet=self._information_diet_dict(),
            feature_surfaces=self._build_feature_surfaces(),  # task #13 (Rule N)
            option_entry_reason_counts=dict(self._state.option_entry_reason_counts),  # B34 task #4
            option_index_entry_outcomes={
                sym: self._state.option_entry_outcome_by_underlying.get(sym)
                for sym in self._INDEX_UNDERLYINGS
                if sym in self._state.option_entry_outcome_by_underlying
            },
        )
        with self._publish_lock:
            self._published = snapshot

    _INDEX_UNDERLYINGS = frozenset(
        {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
    )

    def _option_spread_views(self, price: bool) -> list[OpenPositionView]:
        spreads = list(self._state.open_option_spreads.values())
        if not spreads:
            return []
        price_by_token: dict[int, float] = {}
        if price:
            legs = [leg for sp in spreads for leg in (sp.short_leg, sp.hedge_leg)]
            try:
                price_by_token = self._feed.latest_price_by_token(legs)
            except Exception:
                price_by_token = {}
        rows = []
        for spread in spreads:
            segment = (
                "index_option"
                if spread.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            current = spread.current_net_premium_per_unit(price_by_token)
            rows.append(
                OpenPositionView(
                    trading_symbol=f"{spread.underlying_symbol} {spread.bias}",
                    direction="spread",
                    quantity=spread.lots * spread.lot_size,
                    entry_price=round(spread.entry_net_credit_per_unit, 2),
                    stop_loss_price=round(spread.entry_net_credit_per_unit * 2, 2),
                    target_price=round(spread.entry_net_credit_per_unit * 0.5, 2),
                    last_price=None if current is None else round(current, 2),
                    unrealized_pnl=spread.unrealized_pnl(price_by_token),
                    assigned_table=spread.assigned_table,
                    segment=segment,
                    maximum_favourable_profit=spread.excursion.maximum_favourable_profit,
                    maximum_adverse_profit=spread.excursion.maximum_adverse_profit,
                    profit_locked=spread.profit_trail.locked_profit,
                )
            )
        rows.extend(self._directional_option_views(price))
        rows.extend(self._zero_dte_views(price))
        return rows

    def _zero_dte_views(self, price: bool) -> list[OpenPositionView]:
        """B34 Slice B (closes B32 item 8): surface OPEN 0-DTE expiry-day structures on the boards.

        The 0-DTE engine (`zero_dte_expiry_day_live_path`) is the option engine that actually opens
        positions (44 real on 2026-07-28), but it wrote ONLY to `state.open_zero_dte_positions` and
        nothing rendered them — so the Index/Stock Options tiles read 0 even while options traded.
        Each multi-leg structure renders as one synthetic row (net entry premium/unit → net mark/unit),
        segment-tagged so it lands on the index or stock board."""
        from nse_algo_trader.strategy_engine import OptionLegAction

        positions = list(getattr(self._state, "open_zero_dte_positions", {}).values())
        if not positions:
            return []
        price_by_token: dict[int, float] = {}
        if price:
            leg_instruments = [
                entered.leg.instrument
                for pos in positions
                for entered in pos.entered_legs
            ]
            try:
                price_by_token = self._feed.latest_price_by_token(leg_instruments)
            except Exception as pricing_error:  # noqa: BLE001 — surface, never swallow (Rule O.3)
                print(f"[zero-dte-view] leg pricing failed: {pricing_error!r}", flush=True)
                price_by_token = {}

        def _net_premium_per_unit(pos, marks: dict) -> float | None:
            """SELL legs collect premium (+), BUY legs pay it (−) — the structure's net per unit."""
            total = 0.0
            for entered in pos.entered_legs:
                mark = marks.get(entered.leg.instrument.instrument_token)
                if mark is None:
                    return None
                sign = 1.0 if entered.leg.action is OptionLegAction.SELL else -1.0
                total += sign * mark
            return total

        entry_marks = {
            entered.leg.instrument.instrument_token: entered.entry_premium
            for pos in positions
            for entered in pos.entered_legs
        }
        rows = []
        for pos in positions:
            segment = (
                "index_option"
                if pos.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            entry_net = _net_premium_per_unit(pos, entry_marks)
            current_net = _net_premium_per_unit(pos, price_by_token) if price else None
            structure_label = getattr(pos.structure, "value", str(pos.structure))
            rows.append(
                OpenPositionView(
                    trading_symbol=f"{pos.underlying_symbol} {structure_label} 0DTE",
                    direction="0dte",
                    quantity=pos.lots * pos.lot_size,
                    entry_price=round(entry_net, 2) if entry_net is not None else 0.0,
                    # 0-DTE risk is the structure's DEFINED max loss + a hard time-stop, not a
                    # net-premium price stop — surface the defined risk rather than a fake level.
                    stop_loss_price=round(pos.defined_risk_per_lot, 2),
                    target_price=0.0,
                    last_price=None if current_net is None else round(current_net, 2),
                    unrealized_pnl=pos.unrealized_pnl(price_by_token) if price else None,
                    assigned_table=pos.assigned_table,
                    segment=segment,
                )
            )
        return rows

    def _zero_dte_realized_pnl(self) -> float:
        """B34 Slice B: realised P&L booked by CLOSED 0-DTE structures this session. The 0-DTE close
        path records only into `state.closed_zero_dte_positions` (not the ledger / option-spread
        accumulators), so its P&L was silently missing from the combined headline."""
        closed = getattr(self._state, "closed_zero_dte_positions", None) or []
        return sum(getattr(c, "realized_pnl", 0.0) or 0.0 for c in closed)

    def _directional_option_views(self, price: bool) -> list[OpenPositionView]:
        positions = list(self._state.open_directional_options.values())
        if not positions:
            return []
        price_by_token: dict[int, float] = {}
        if price:
            try:
                price_by_token = self._feed.latest_price_by_token(
                    [p.option for p in positions]
                )
            except Exception:
                price_by_token = {}
        rows = []
        for pos in positions:
            segment = (
                "index_option"
                if pos.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            ltp = price_by_token.get(pos.option.instrument_token)
            rows.append(
                OpenPositionView(
                    trading_symbol=pos.option.trading_symbol,
                    direction="long",  # a bought option is a BUY
                    quantity=pos.lots * pos.lot_size,
                    entry_price=round(pos.entry_premium, 2),
                    stop_loss_price=round(pos.entry_premium * 0.5, 2),
                    target_price=round(pos.entry_premium * 2, 2),
                    last_price=None if ltp is None else round(ltp, 2),
                    unrealized_pnl=pos.unrealized_pnl(price_by_token),
                    assigned_table=pos.assigned_table,
                    segment=segment,
                    maximum_favourable_profit=pos.excursion.maximum_favourable_profit,
                    maximum_adverse_profit=pos.excursion.maximum_adverse_profit,
                    profit_locked=pos.profit_trail.locked_profit,
                )
            )
        return rows

    def _segment_boards(
        self, views: list[OpenPositionView], closed: tuple = ()
    ) -> tuple[SegmentBoard, ...]:
        """Per-segment open count, unrealised P&L, and B28 realised fees already PAID.

        Fees come from CLOSED trades (an open trade has not paid its exit leg yet), so a segment can
        legitimately show 0 open positions and non-zero fees."""
        boards = []
        for segment in ("cash", "index_option", "stock_option"):
            in_segment = [v for v in views if v.segment == segment]
            segment_closed = [c for c in closed if c.segment == segment]
            boards.append(
                SegmentBoard(
                    segment=segment,
                    open_count=len(in_segment),
                    unrealized_pnl=sum(v.unrealized_pnl or 0.0 for v in in_segment),
                    realised_fees=sum(c.total_fees or 0.0 for c in segment_closed),
                )
            )
        return tuple(boards)

    def _token_to_symbol_map(self) -> dict:
        """token → trading_symbol over the whole tradable universe (cash + option ladder),
        cached — so persisted closed trades (which store only the token) render with a
        symbol. research/93."""
        if getattr(self, "_token_symbol_cache", None):
            return self._token_symbol_cache
        mapping: dict = {}
        universe = self._tradable_universe
        if universe is not None:
            for inst in list(universe.cash_equity_instruments) + list(
                getattr(universe, "option_ladder_instruments", [])
            ):
                mapping[inst.instrument_token] = inst.trading_symbol
        self._token_symbol_cache = mapping
        return mapping

    def exit_efficiency_rows(self) -> list[dict]:
        """B25b: the capture-ratio rows as DATA (not formatted strings) so they can be charted."""
        memory = self._experience_memory
        if memory is None:
            return []
        try:
            return [
                row for row in memory.exit_efficiency_by_mechanism(minimum_experiments=1)
                if row.get("capture_ratio") is not None
            ]
        except Exception as read_failure:  # noqa: BLE001
            print(f"[exit-efficiency] chart read failed: {read_failure!r}", flush=True)
            return []

    def _confident_loss_aware_pnl_split(self):
        """B33: split realized P&L into the bot's REAL money (confident_win + uncertain) vs the
        `confident_loss` learning probes, from the DURABLE experience memory (authoritative, spans
        every session). Falls back to an all-zero split if memory is unavailable — the headline then
        shows ₹0 real rather than silently folding probes back in."""
        from nse_algo_trader.paper_trading.confident_loss_aware_pnl import (
            ConfidentLossAwarePnlSplit,
            split_realized_pnl_by_prediction_intent,
        )

        empty = ConfidentLossAwarePnlSplit(0.0, 0, 0.0, 0, None)
        if self._experience_memory is None:
            return empty
        try:
            by_table = self._experience_memory.realized_pnl_by_assigned_table()
        except Exception:
            return empty
        return split_realized_pnl_by_prediction_intent(by_table)

    def _recent_closed_trades(self) -> tuple[ClosedTradeView, ...]:
        # research/93: source the panel from the DURABLE experience memory (survives
        # restarts, spans every session — the real 220 live + replay trades), resolving
        # token→symbol. Fall back to the process-local ledger only if memory is unavailable.
        try:
            if self._experience_memory is not None:
                token_symbol = self._token_to_symbol_map()
                persisted = []
                for r in self._experience_memory.recent_closed_experiences(limit=40):
                    kind = r["instrument_kind"]
                    persisted.append(ClosedTradeView(
                        segment=("cash" if kind == "cash_equity" else kind),
                        trading_symbol=token_symbol.get(
                            r["instrument_token"], f"#{r['instrument_token']}"),
                        direction=r["direction"],
                        realized_pnl=r["realized_pnl"],
                        outcome=r["actual_outcome"],
                        closed_at=r["occurred_at"],
                        provenance=r["data_provenance"],
                        total_fees=(r["total_fees"] if "total_fees" in r.keys() else 0.0),
                        assigned_table=(
                            r["assigned_table"] if "assigned_table" in r.keys() else "uncertain"
                        ),
                    ))
                if persisted:
                    return tuple(persisted)
        except Exception:
            pass
        rows = []
        for trade in self._state.closed_trades[-30:][::-1]:
            rows.append(
                ClosedTradeView(
                    segment="cash",
                    trading_symbol=trade.instrument.trading_symbol,
                    direction=trade.direction.value,
                    realized_pnl=trade.realized_pnl,
                    outcome=trade.outcome.value,
                    closed_at=trade.closed_at.isoformat(),
                    assigned_table=trade.assigned_table,
                )
            )
        for spread, realized in self._state.closed_option_spreads[-15:][::-1]:
            segment = (
                "index_option"
                if spread.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            rows.append(
                ClosedTradeView(
                    segment=segment,
                    trading_symbol=f"{spread.underlying_symbol} {spread.bias}",
                    direction="spread",
                    realized_pnl=realized,
                    outcome="closed",
                    closed_at=spread.opened_at.isoformat(),
                    assigned_table=spread.assigned_table,
                )
            )
        for pos, realized in self._state.closed_directional_options[-15:][::-1]:
            segment = (
                "index_option"
                if pos.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            rows.append(
                ClosedTradeView(
                    segment=segment,
                    trading_symbol=pos.option.trading_symbol,
                    direction="long",
                    realized_pnl=realized,
                    outcome="closed",
                    closed_at=pos.opened_at.isoformat(),
                    assigned_table=pos.assigned_table,
                )
            )
        return tuple(rows)

    def _memory_experiment_count(self) -> int:
        try:
            return self._experience_memory.experiment_count() if self._experience_memory else 0
        except Exception:
            return 0

    def _memory_experiment_count_by_provenance(self) -> dict:
        """The live-vs-replay experience mix (§53 slice 3a) — so the dashboard can
        show whether the brain is over-relying on 24/7 replay vs real live sessions
        (writer thread — owns the memory's SQLite connection)."""
        try:
            return (
                self._experience_memory.experiment_count_by_provenance()
                if self._experience_memory
                else {}
            )
        except Exception:
            return {}

    def _memory_prequential_forecast_score(self) -> dict:
        """Running forecast skill (log-loss/Brier) overall + split live vs replay
        (§53 slice 3b-ii; writer thread owns the memory's SQLite connection)."""
        if self._experience_memory is None:
            return {}
        try:
            from dataclasses import asdict

            return {
                "overall": asdict(self._experience_memory.prequential_forecast_score()),
                "live": asdict(
                    self._experience_memory.prequential_forecast_score(
                        data_provenance="live"
                    )
                ),
                "replay_faithful": asdict(
                    self._experience_memory.prequential_forecast_score(
                        data_provenance="replay_faithful"
                    )
                ),
            }
        except Exception:
            return {}

    def _memory_calibration_board(self) -> tuple:
        """The reflection surface: per-mechanism predicted-vs-actual calibration
        (writer thread — same thread that owns the memory's SQLite connection)."""
        if self._experience_memory is None:
            return ()
        try:
            return tuple(self._experience_memory.calibration_board(minimum_experiments=3))
        except Exception:
            return ()

    def _memory_assumption_verdicts(self) -> tuple:
        """Layer-10 slice 2: significance-tested assumption tripwires over the
        experience memory (writer thread — owns the SQLite connection)."""
        if self._experience_memory is None:
            return ()
        try:
            from nse_algo_trader.memory_reflection import evaluate_trading_assumptions

            return tuple(evaluate_trading_assumptions(self._experience_memory))
        except Exception:
            return ()

    def _summarize_prediction_table(self, table) -> PredictionTableSummary:
        score = self._state.scoreboard.score_for_table(table)
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

    def published_snapshot(self) -> LivePaperPublishedSnapshot:
        with self._publish_lock:
            return self._published


def _build_authenticated_breeze_historical_source(session_token: str):
    """§53 task #7 default source builder: compose a real authenticated Breeze
    1-second source — creds → client (#6a) → ICICI stock-code resolver (#6b) →
    adapter. Network + the `breeze_connect` import happen ONLY here, so the rest of
    the service (and tests, which inject a fake builder) stay import-clean."""
    from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
        BrokerName,
        load_broker_api_credentials,
        load_env_file_into_environ,
    )
    from nse_algo_trader.broker_sessions.breeze_authenticated_client_builder import (
        build_authenticated_breeze_client,
    )
    from nse_algo_trader.market_data.breeze_historical_bar_source import (
        BreezeHistoricalBarSource,
    )
    from nse_algo_trader.market_data.icici_security_master_stock_code_resolver import (
        IciciSecurityMasterStockCodeResolver,
        download_icici_nse_scrip_master_text,
    )

    load_env_file_into_environ()
    credentials = load_broker_api_credentials(BrokerName.ICICI_BREEZE)
    client = build_authenticated_breeze_client(credentials, session_token)
    resolver = IciciSecurityMasterStockCodeResolver.from_nse_scrip_master_text(
        download_icici_nse_scrip_master_text()
    )
    return BreezeHistoricalBarSource(client, stock_code_resolver=resolver)


def _try_build_upstox_fleet_member(environ):
    """A live Upstox minute source from the env Analytics/access token, or None if no
    token / build fails. Network (downloads the NSE instrument master) lives here."""
    token = (
        environ.get("UPSTOX_ANALYTICS_TOKEN", "").strip()
        or environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    )
    if not token:
        return None
    from nse_algo_trader.market_data.upstox_historical_bar_source import (
        UpstoxHistoricalBarSource,
        UpstoxRestHistoricalClient,
    )
    from nse_algo_trader.market_data.upstox_instrument_key_resolver import (
        UpstoxInstrumentKeyResolver,
        download_upstox_nse_instrument_master_records,
    )

    resolver = UpstoxInstrumentKeyResolver.from_instrument_master_records(
        download_upstox_nse_instrument_master_records()
    )
    return UpstoxHistoricalBarSource(UpstoxRestHistoricalClient(token), resolver)


def _try_build_angel_fleet_member(environ):
    """A live Angel One minute source from the env creds (generateSession), or None if
    creds absent / login fails. Network (login + OpenAPIScripMaster) lives here."""
    api_key = environ.get("ANGEL_ONE_API_KEY", "").strip()
    client_code = environ.get("ANGEL_ONE_CLIENT_CODE", "").strip()
    pin = environ.get("ANGEL_ONE_PIN", "").strip()
    totp_secret = environ.get("ANGEL_ONE_TOTP_SECRET", "").strip()
    if not all((api_key, client_code, pin, totp_secret)):
        return None
    from nse_algo_trader.broker_sessions.angel_one_smartapi_session import (
        build_angel_one_authenticated_historical_client,
    )
    from nse_algo_trader.market_data.angel_one_historical_bar_source import (
        AngelOneHistoricalBarSource,
    )
    from nse_algo_trader.market_data.angel_one_symbol_token_resolver import (
        AngelOneSymbolTokenResolver,
        download_angel_one_scrip_master_records,
    )

    resolver = AngelOneSymbolTokenResolver.from_scrip_master_records(
        download_angel_one_scrip_master_records()
    )
    client = build_angel_one_authenticated_historical_client(
        api_key, client_code, pin, totp_secret
    )
    return AngelOneHistoricalBarSource(client, resolver)


def _build_available_broker_fleet_source(environ=None):
    """task #20 default fleet builder: assemble a `MultiBrokerHistoricalBarSource` from
    whichever brokers have creds in the env, in reliability priority order (deep-history
    / no-daily-login first): Upstox → Angel One (Fyers/Kite/Groww join as their creds
    land). Each member is best-effort — one missing/broken broker never blocks the rest.
    Returns None when no broker is available (caller then stays on the store path)."""
    import os

    from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
        load_env_file_into_environ,
    )
    from nse_algo_trader.market_data.multi_broker_historical_bar_source import (
        MultiBrokerHistoricalBarSource,
        NamedHistoricalBarSource,
    )

    load_env_file_into_environ()
    environ = os.environ if environ is None else environ
    ordered_members = []
    for name, member_builder in (
        ("upstox", _try_build_upstox_fleet_member),
        ("angel_one", _try_build_angel_fleet_member),
    ):
        try:
            member = member_builder(environ)
        except Exception:
            member = None  # a broken broker never blocks the fleet
        if member is not None:
            ordered_members.append(NamedHistoricalBarSource(name, member))
    if not ordered_members:
        return None
    return MultiBrokerHistoricalBarSource(ordered_members)
