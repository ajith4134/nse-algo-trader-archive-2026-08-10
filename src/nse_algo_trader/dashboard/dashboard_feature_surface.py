"""Feature-surface registry — the systematic way EVERY feature shows on the dashboard
(Rule N; research/91).

Instead of hand-writing a panel per feature (which is forgotten), each feature emits a
uniform `DashboardFeatureSurface` (title, live status, headline metrics, optional note).
The dashboard renders them all in one "Feature coverage" panel, and a manifest + audit
make a missing surface a TEST FAILURE + a visible "not yet surfaced" row — so "is the
dashboard up to date with all features?" is answerable at a glance and can't silently rot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A feature's live state. Statuses map to the dashboard's status colours (good/warn/
# neutral), always shown with a label + dot — never colour alone (accessibility).
_VALID_STATUSES = ("active", "gathering", "idle", "blocked", "off", "unknown")


@dataclass(frozen=True)
class DashboardFeatureSurface:
    key: str  # stable manifest key
    title: str
    status: str  # one of _VALID_STATUSES
    metrics: tuple[tuple[str, str], ...] = ()  # (label, value) headline metrics
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unknown feature-surface status: {self.status!r}")

    def to_json_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "status": self.status,
            "metrics": [list(m) for m in self.metrics], "note": self.note,
        }


# The canonical list of features that MUST surface on the dashboard. A feature whose key
# is here but has no built surface renders as "not yet surfaced" and fails the coverage
# audit — the enforcement point behind Rule N. Add a row when a user-visible feature ships.
FEATURE_SURFACE_MANIFEST: tuple[tuple[str, str], ...] = (
    # The 3 segment AI bots + their 2 directional AI features (measured by segment_bot_surface_prober).
    ("index_option_bot", "INDEX-OPTION AI bot (NIFTY/BANKNIFTY/… structures)"),
    ("stock_option_bot", "STOCK-OPTION AI bot (single-name F&O structures)"),
    ("cash_intraday_bot", "CASH-INTRADAY AI bot (cross-sectional long/short book)"),
    ("directional_ai_bull", "Directional AI — BULL side (P↑ → option CE / cash LONG)"),
    ("directional_ai_bear", "Directional AI — BEAR side (P↓ → option PE / cash SHORT)"),
    ("option_book_risk", "Option Book Risk (net greeks · CVaR · live-sizing)"),
    ("trade_evidence", "Trade Evidence (per-trade proof: engine · E[P&L] · P(profit) · defined-risk)"),
    ("multi_broker_sourcing", "Multi-broker data sourcing (failover + gap-fill)"),
    ("pre_trade_cost_gate", "Pre-trade cost gate (L1 reality filter)"),
    ("validation_engine", "Validation engine (DSR honest-N + MinBTL + holdout)"),
    ("ops_floor_crash_safety", "Ops floor (idempotent orders + WAL + reconciliation)"),
    ("strategy_family_promotion", "Strategy promotion ladder (per-family, validation-gated)"),
    ("replay_fidelity", "Replay fidelity tier (market-closed)"),
    ("replay_curriculum", "Deficit-driven replay curriculum (regime coverage)"),
    ("champion_challenger", "Champion-challenger strategy config (global + per-regime)"),
    ("market_impact_fills", "Market-impact fill model"),
    ("market_regime_memory", "Market-regime memory calibration"),
    ("order_flow_toxicity", "Order-flow toxicity (VPIN)"),
    ("strategic_llm_analyst", "Strategic LLM analyst (swappable multi-provider)"),
    ("thesis_debate_risk_panel", "Debate-as-risk-check (bull/bear/risk panel)"),
    ("causal_cluster_analysis", "Causal analysis of multi-hop outcome clusters"),
    ("meta_strategy_allocation", "Meta-strategy allocator (LLM weights across strategies)"),
    ("prediction_council", "Prediction-market council (track-record-weighted)"),
    ("synthetic_stress_rehearsal", "Synthetic stress rehearsal (LLM red-team scenarios)"),
    ("skill_vs_luck_control", "Skill-vs-luck control (RANDOM-CONTROL arm)"),
    ("skill_vs_luck_court", "Skill-vs-luck court (shadow-rejected + verdict)"),
    ("per_trade_pre_mortem", "Per-trade pre-mortem (entry-time Monte Carlo)"),
    ("profit_provenance", "Profit provenance (P&L vs control arms)"),
    ("world_model_scoreboard", "World-model scoreboard (trade-independent forecasts)"),
    ("constitutional_core", "Constitutional core (VII CONSCIENCE — inviolable rules)"),
    ("corrigibility_switch", "Corrigibility / off-switch (VII CONSCIENCE — safe interruptibility)"),
    ("ai_atlas_coverage", "AI concept-tree atlas coverage (16 trunks / ~197 branches)"),
    ("wireheading_tripwire", "Wireheading tripwire (VII CONSCIENCE — reward-proxy gaming)"),
    ("deceptive_alignment_monitor", "Deceptive-alignment monitor (VII — eval-vs-deploy)"),
    ("incident_post_mortem", "Incident post-mortem (VII CONSCIENCE — forensic safety record)"),
    ("goal_integrity", "Goal-integrity monitor (VII CONSCIENCE — objective drift)"),
    ("mechanistic_interpretability", "Mechanistic interpretability (VII CONSCIENCE — decision attribution)"),
    ("scalable_oversight", "Scalable oversight (VII CONSCIENCE — competence ceiling)"),
    ("instrumental_convergence", "Instrumental-convergence limiter (VII CONSCIENCE — power-seeking cap)"),
    ("red_team_harness", "Red-team harness (VII CONSCIENCE — adversarial self-attack)"),
    ("ethics_law_reasoner", "Ethics/law reasoner (VII CONSCIENCE — SEBI compliance)"),
    ("power_budgets", "Power budget (VII CONSCIENCE — daily action cap)"),
    ("market_data_integrity", "Market-data integrity defense (VII CONSCIENCE — adversarial input)"),
    ("global_workspace", "Global Workspace (VIII SENTIENCE — the integrator)"),
    ("self_model", "Self-model (VIII SENTIENCE — what am I right now?)"),
    ("attention_schema", "Attention schema (VIII SENTIENCE — model of own attention)"),
    ("workspace_rumination", "Workspace rumination (VIII SENTIENCE — recurring-concern replay)"),
    ("cross_modal_binding", "Cross-modal binding (VIII SENTIENCE — fused perception)"),
    ("higher_order_monitoring", "Higher-order monitoring (VIII SENTIENCE — metacognition)"),
    ("indicator_scoreboard", "Indicator scoreboard (VIII SENTIENCE — faculty ranking)"),
    ("contradiction_resolution", "Contradiction resolution (XIII EPISTEMICS — belief vs evidence)"),
    ("misinformation_resistance", "Misinformation resistance (XIII EPISTEMICS — source credibility)"),
    ("surprise_monitor", "Surprise / free-energy monitor (IX PREDICTIVE-CORE)"),
    ("ensemble_world_model", "Ensemble world-models (IX PREDICTIVE-CORE)"),
    ("semantic_memory", "Semantic memory (XV MEMORY — consolidated knowledge)"),
    ("consensus_resolution", "Consensus / conflict-resolution (VI SOCIETY — desk agreement)"),
    ("multi_agent_governance", "Multi-agent governance (VI SOCIETY — desk reputation policy)"),
    ("market_breadth", "Market breadth (II SENSES — internals & cross-market)"),
    ("news_feed", "News feed ingestion (II SENSES — sentiment/news, tier-1 RSS)"),
    ("news_levels", "News index S/R levels (II SENSES — sentiment/news S2)"),
    ("news_acquisition", "News acquisition ladder (II SENSES — sentiment/news S4a+b)"),
    ("exchange_filings", "NSE corporate filings (II SENSES — sentiment/news S4c)"),
    ("news_source_reliability", "News source reliability (II SENSES — sentiment/news S3)"),
    ("news_entry_gate", "News entry gate (II SENSES — sentiment/news S7, PRIMARY)"),
    ("stock_symbol_gazetteer", "Stock symbol gazetteer (II SENSES — sentiment/news)"),
    ("stock_levels", "News stock S/R levels (II SENSES — sentiment/news)"),
    ("news_sentiment", "News sentiment (II SENSES — sentiment/news, finance-VADER)"),
    ("index_level_gate", "Index-level option gate (II SENSES — sentiment/news)"),
    ("option_lot_sizing", "Option lot sizing (V RISK — indivisible-lot size-down)"),
    ("exit_efficiency", "Exit efficiency (X MEMORY — do we exit too early?)"),
    ("arm_selector", "Adaptive arm selector (B18 — which strategy is chosen, and why)"),
    ("telegram_news", "Telegram social news (II SENSES — sentiment/news S5)"),
    ("explicit_utility", "Explicit utility (XIV AXIOLOGY — the system's stated values)"),
    ("value_drift", "Value drift (XIV AXIOLOGY — realized-vs-stated values)"),
    ("objective_arbitration", "Objective arbitration (III WILL — values-driven volition)"),
    ("goal_schedule", "Goal-priority schedule (III WILL)"),
    ("win_probability_model", "ML win-probability engine (IX PREDICTIVE-CORE — LightGBM)"),
    ("capital_allocation_optimizer", "Capital-allocation optimizer (III WILL — CVXPY portfolio)"),
    ("curiosity_engine", "Curiosity / learning-progress engine (XII INTRINSIC MOTIVATION)"),
    ("world_model_planning", "World-model planning engine (IX PREDICTIVE-CORE — active inference)"),
    ("component_lifecycle_homeostat", "Component-lifecycle homeostat (X AUTOPOIESIS — self-maintenance)"),
)

MANIFEST_KEYS: frozenset[str] = frozenset(k for k, _ in FEATURE_SURFACE_MANIFEST)


@dataclass(frozen=True)
class FeatureCoverageReport:
    """The full coverage picture: every manifest feature with its surface (or a
    'not yet surfaced' placeholder). What the dashboard panel + the audit consume."""

    surfaces: tuple[DashboardFeatureSurface, ...] = field(default_factory=tuple)

    def by_key(self) -> dict[str, DashboardFeatureSurface]:
        return {s.key: s for s in self.surfaces}

    def missing_keys(self) -> frozenset[str]:
        """Manifest features with no surface (the coverage GAP — must be empty for Rule N)."""
        return MANIFEST_KEYS - set(self.by_key())

    def rows_in_manifest_order(self) -> list[DashboardFeatureSurface]:
        """Every manifest feature in order, with a placeholder 'not yet surfaced' row for
        any that has no built surface — so ALL features are always listed."""
        built = self.by_key()
        return [
            built.get(key, DashboardFeatureSurface(key=key, title=title, status="unknown",
                                                   note="not yet surfaced"))
            for key, title in FEATURE_SURFACE_MANIFEST
        ]
