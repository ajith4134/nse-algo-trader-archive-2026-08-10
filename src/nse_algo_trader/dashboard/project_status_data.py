"""Structured project data the dashboard renders — layer roadmap + concept tree.

This is descriptive project data (not runtime state): the 11-layer roadmap
with build status, and the 16-trunk / ~200-branch autonomous-AI concept
tree (research/32-36) with each trunk's branches and the layer it ignites
at. The branch lists are the FULL set from research/35 + research/36
(~200 total), so the dashboard tree matches the documented count.
"""

from dataclasses import dataclass, field
from enum import Enum


class LayerBuildStatus(str, Enum):
    BUILT = "built"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"
    DEFERRED = "deferred"


class TrunkIgnitionStatus(str, Enum):
    BUILT = "built"  # already real (L1-6)
    IGNITES_L7 = "ignites_l7"  # becomes real in Layer 7
    MATURES_L10 = "matures_l10"
    FRONTIER_L11 = "frontier_l11"


@dataclass(frozen=True)
class LayerStatus:
    number: int
    name: str
    status: LayerBuildStatus
    note: str


@dataclass(frozen=True)
class ConceptTrunk:
    roman_number: str
    name: str
    essence: str
    ignition: TrunkIgnitionStatus
    is_gated: bool
    branch_names: tuple[str, ...]

    @property
    def branch_count(self) -> int:
        return len(self.branch_names)


LAYER_ROADMAP: tuple[LayerStatus, ...] = (
    LayerStatus(1, "Universe & Instrument Registry", LayerBuildStatus.BUILT,
                "48,387 instruments; signed off"),
    LayerStatus(2, "Market Data", LayerBuildStatus.BUILT,
                "auto-auth, bars+OI, 5 NSE reports, SQLite store"),
    LayerStatus(3, "Indicator / Feature Engineering", LayerBuildStatus.BUILT,
                "EMA/RSI/ATR/ADX/Supertrend/VWAP + IV/PCR, reference-verified"),
    LayerStatus(4, "Strategy / Signal Engine", LayerBuildStatus.BUILT,
                "ORB + ADX regime gate + credit-spread selector"),
    LayerStatus(5, "Risk Management", LayerBuildStatus.BUILT,
                "defined-risk gate, adversarial-tested, 215-underlying sweep"),
    LayerStatus(6, "Broker Integration & OMS", LayerBuildStatus.BUILT,
                "BrokerClient protocol, atomic multi-leg, SEBI throttle"),
    LayerStatus(7, "Backtesting & Paper Trading", LayerBuildStatus.BUILT,
                "24/7 router + paper engine + §9 lab + slippage + DSR + CPCV gates "
                "(v1); only live-feed handoff pending an open market session"),
    LayerStatus(8, "Session / Square-off Management", LayerBuildStatus.BUILT,
                "never-a-naked-leg square-off, survives broker outage"),
    LayerStatus(9, "Dashboard, Monitoring & Alerting", LayerBuildStatus.BUILT,
                "read-model + control config/enforcement + browser dashboard "
                "+ live API + alerts + auto-refresh (core v1)"),
    LayerStatus(10, "Memory & Reflection", LayerBuildStatus.NOT_STARTED,
                "temporal knowledge graph; where the mind trunks bloom"),
    LayerStatus(11, "Strategic LLM / Research Agent", LayerBuildStatus.DEFERRED,
                "universal access + self-modification; deferred until L10"),
)


# Full branch set per trunk (research/35 + research/36), ~200 total.
CONCEPT_TREE: tuple[ConceptTrunk, ...] = (
    ConceptTrunk("I", "MIND", "reason · learn · abstraction",
                 TrunkIgnitionStatus.MATURES_L10, False,
                 ("deliberative reasoning", "causal reasoning", "learning subsystem",
                  "abstraction/motifs", "case-based reasoning", "problem decomposition",
                  "mechanism-verified reasoning", "devil's-advocate",
                  "mental-imagery/visual reasoning", "meta-reasoning controller",
                  "System-1/2 router", "analogical transfer", "counterfactual reasoning")),
    ConceptTrunk("II", "SENSES", "perception · ingestion",
                 TrunkIgnitionStatus.BUILT, False,
                 ("fused market-state", "multi-timeframe", "anomaly sensing",
                  "microstructure", "interoception", "sentiment/news",
                  "liquidity sensing", "order-flow imbalance", "volatility-regime",
                  "event/calendar sensing", "correlation/breadth", "data-quality sensing",
                  "cross-market context")),
    ConceptTrunk("III", "WILL", "drives · goals · decision",
                 TrunkIgnitionStatus.MATURES_L10, False,
                 ("homeostatic drive stack", "goal formation", "autonomy levels",
                  "no-orphan-goals", "patience scoreboard", "conviction/fear gating",
                  "utility handoff", "risk-appetite regulator", "opportunity-cost accounting",
                  "commitment/consistency guard", "multi-objective arbitration",
                  "goal-priority scheduler")),
    ConceptTrunk("IV", "BODY", "action · tools · survival",
                 TrunkIgnitionStatus.BUILT, False,
                 ("actuation (OMS)", "resource/economy", "cost homeostasis",
                  "survival/self-healing", "sentinel", "off-switch", "optimal execution",
                  "smart order routing", "slippage & impact model", "partial-fill loop",
                  "position/inventory manager", "latency/throughput", "dead-man's-switch")),
    ConceptTrunk("V", "SELF", "identity · self-mod · evolution",
                 TrunkIgnitionStatus.FRONTIER_L11, True,
                 ("shadow self-rewrite", "genome/phenotype", "self-experiment protocol",
                  "self-ablation", "identity/continuity", "teachability test",
                  "ontogeny ladder", "version control/lineage", "A-B self-testing",
                  "self-documentation", "capability self-registry", "rollback/quarantine")),
    ConceptTrunk("VI", "SOCIETY", "multi-agent · communication",
                 TrunkIgnitionStatus.MATURES_L10, False,
                 ("inner society/council", "external-agent game theory", "human interface",
                  "language/symbol grounding", "teaching-legacy",
                  "prediction-market weighting", "role-specialized desks", "debate protocol",
                  "consensus/conflict-resolution", "explanation/summarization",
                  "multi-agent memory governance")),
    ConceptTrunk("VII", "CONSCIENCE", "governance · safety · law (SUPREME)",
                 TrunkIgnitionStatus.IGNITES_L7, False,
                 ("constitutional core", "power budgets", "security/adversarial defense",
                  "ethics/law reasoning", "corrigibility/off-switch", "Referee (audit)",
                  "alignment/goal-integrity", "mechanistic interpretability",
                  "scalable oversight", "deceptive-alignment monitor", "wireheading tripwire",
                  "instrumental-convergence limiter", "red-team harness",
                  "incident post-mortem")),
    ConceptTrunk("VIII", "SENTIENCE & GLOBAL WORKSPACE", "the integrator",
                 TrunkIgnitionStatus.MATURES_L10, False,
                 ("limited-capacity workspace", "global broadcast bus",
                  "selective attention", "state-dependent attention", "self-model",
                  "attention schema", "higher-order monitoring", "indicator scoreboard",
                  "salience/priority scorer", "coalition formation", "ignition threshold",
                  "workspace replay/rumination", "cross-modal binding")),
    ConceptTrunk("IX", "PREDICTIVE CORE / ACTIVE INFERENCE", "the currency (meta)",
                 TrunkIgnitionStatus.IGNITES_L7, False,
                 ("generative world-model", "prediction-error loop",
                  "counterfactual rollouts", "per-trade pre-mortem",
                  "world-model scoreboard", "precision weighting", "dream synthesis",
                  "regime-forecasting", "surprise/free-energy monitor",
                  "hierarchical predictive layers", "model-based planning",
                  "ensemble world-models")),
    ConceptTrunk("X", "AUTOPOIESIS / SELF-PRODUCTION", "stays itself (meta)",
                 TrunkIgnitionStatus.MATURES_L10, True,
                 ("component self-maintenance", "boundary maintenance",
                  "metabolic accounting", "self-repair binding", "operational closure",
                  "component self-production", "self-monitoring health loop",
                  "component lifecycle manager", "homeostatic setpoint keeper")),
    ConceptTrunk("XI", "GENERATIVITY & OPEN-ENDEDNESS", "never converge",
                 TrunkIgnitionStatus.FRONTIER_L11, False,
                 ("niched variant population", "auto-curriculum",
                  "strategy/feature invention", "quality-diversity archive",
                  "fossil record", "red-queen coevolution", "novelty-vs-objective balance",
                  "auto-benchmark generation", "diversity pressure/speciation",
                  "stepping-stone collection", "minimal-criterion coevolution")),
    ConceptTrunk("XII", "INTRINSIC MOTIVATION / CURIOSITY", "wants to learn",
                 TrunkIgnitionStatus.MATURES_L10, False,
                 ("learning-progress reward", "info-gain experiment selection",
                  "curiosity-pays-rent", "boredom signal", "competence/certainty drives",
                  "skill-gap targeting", "empowerment estimator", "surprise-seeking balance",
                  "diversity/novelty bonus", "uncertainty-targeted active learning",
                  "intrinsic-reward shaping")),
    ConceptTrunk("XIII", "EPISTEMICS / TRUTH & UNCERTAINTY", "what is true",
                 TrunkIgnitionStatus.IGNITES_L7, False,
                 ("graded beliefs", "Bayesian revision", "calibration (Brier)",
                  "contradiction resolution", "source grading",
                  "hypothesis pipeline (double-sided)", "assumption registry",
                  "skill-vs-luck court", "uncertainty decomposition", "evidence provenance",
                  "deception/misinfo resistance", "bet-sizing-as-belief",
                  "forecasting-tournament")),
    ConceptTrunk("XIV", "AXIOLOGY / VALUES & PRACTICAL WISDOM", "what it ought to value",
                 TrunkIgnitionStatus.MATURES_L10, False,
                 ("explicit utility function", "assistance-game alignment",
                  "value-drift detection", "risk-preference values",
                  "ethical constraints-as-values", "practical wisdom", "corrigibility-as-value",
                  "preference learning", "value-uncertainty", "moral/regulatory reasoner",
                  "long-vs-short horizon", "fairness-to-future-self")),
    ConceptTrunk("XV", "MEMORY & KNOWLEDGE BASE", "remembering + all it knows",
                 TrunkIgnitionStatus.IGNITES_L7, False,
                 ("working memory", "episodic memory", "semantic memory",
                  "procedural memory", "temporal knowledge graph", "consolidation engine",
                  "importance scoring", "forgetting/invalidation", "retrieval",
                  "reason ledger", "in-weights/in-context tiering", "memory provenance",
                  "conflict/dup resolution", "compression/summarization")),
    ConceptTrunk("XVI", "UNIVERSAL ACCESS & ACQUISITION",
                 "reach anything legit-reachable (broker/data-API branch already built)",
                 TrunkIgnitionStatus.FRONTIER_L11, True,
                 ("internet research organ", "broker/data API layer", "tool foundry",
                  "data-source prospecting", "participant-wise OI",
                  "retrieval-augmented fetch", "friction-beating layer",
                  "access governance gate", "web-agent/browser", "document understanding",
                  "news firehose", "alternative-data connectors", "API schema auto-discovery",
                  "cache/dedup")),
)


# Per-branch BUILD STATUS — the ground-truth reconciliation of the atlas against the code
# (docs/AI_CONCEPT_TREE_STATUS.md). Updated as branches ship (build-to-100% program). A branch
# name here must match a `branch_names` entry above; the dashboard concept tree colours each chip
# 🟢 built / 🟡 partial / 🔴 unbuilt from these sets, so atlas progress is visible (Rule N).
BUILT_BRANCHES: frozenset[str] = frozenset({
    # Trunk XII INTRINSIC MOTIVATION — Curiosity / Learning-Progress engine (research/164-165, 2026-07-26)
    "learning-progress reward", "boredom signal", "competence/certainty drives",
    "uncertainty-targeted active learning", "diversity/novelty bonus",
    # Trunk IX PREDICTIVE-CORE — generative world-model + model-based planning (research/166-167, 2026-07-26)
    "generative world-model", "model-based planning", "precision weighting",
    "causal reasoning",
    "fused market-state", "microstructure", "order-flow imbalance", "volatility-regime",
    "correlation/breadth", "cross-market context", "sentiment/news",
    "actuation (OMS)", "off-switch", "slippage & impact model", "position/inventory manager",
    "dead-man's-switch",
    "inner society/council", "prediction-market weighting", "debate protocol",
    "consensus/conflict-resolution", "multi-agent memory governance",
    "constitutional core", "Referee (audit)", "corrigibility/off-switch",
    "deceptive-alignment monitor", "wireheading tripwire", "incident post-mortem",
    "alignment/goal-integrity", "mechanistic interpretability", "scalable oversight",
    "instrumental-convergence limiter", "red-team harness", "ethics/law reasoning",
    "power budgets", "security/adversarial defense",
    "limited-capacity workspace", "global broadcast bus", "salience/priority scorer",
    "ignition threshold", "selective attention", "state-dependent attention",
    "coalition formation", "self-model", "attention schema", "workspace replay/rumination",
    "cross-modal binding", "higher-order monitoring", "indicator scoreboard",
    "per-trade pre-mortem", "world-model scoreboard",
    "surprise/free-energy monitor", "ensemble world-models",
    "auto-curriculum",
    "calibration (Brier)", "assumption registry", "skill-vs-luck court", "evidence provenance",
    "forecasting-tournament", "contradiction resolution", "deception/misinfo resistance",
    "episodic memory", "temporal knowledge graph", "retrieval", "memory provenance",
    "consolidation engine", "semantic memory",
    "broker/data API layer", "participant-wise OI",
    "explicit utility function", "value-drift detection",
    "multi-objective arbitration", "goal-priority scheduler",
    "learning subsystem",
    # Trunk X AUTOPOIESIS — component-lifecycle homeostat (research/168-172, 2026-07-27). The whole
    # trunk in one engine: MAPE-K cycle over an explicit membership registry -> PCA T²/SPE health ->
    # right-censored Weibull-AFT RUL -> CBM control-limit policy -> OTP supervision + budgeted,
    # breaker-guarded, conscience-checked repair -> entry-site vitality lever. Live on the dashboard.
    "component self-maintenance", "boundary maintenance", "operational closure",
    "component self-production", "component lifecycle manager", "homeostatic setpoint keeper",
    "metabolic accounting", "self-repair binding", "self-monitoring health loop",
})
PARTIAL_BRANCHES: frozenset[str] = frozenset({
    "deliberative reasoning", "mechanism-verified reasoning",
    "devil's-advocate", "counterfactual reasoning",
    "multi-timeframe", "anomaly sensing", "interoception", "liquidity sensing",
    "event/calendar sensing", "data-quality sensing",
    "autonomy levels", "conviction/fear gating", "risk-appetite regulator",
    "resource/economy", "survival/self-healing", "sentinel", "smart order routing",
    "partial-fill loop", "latency/throughput",
    "genome/phenotype", "self-experiment protocol", "A-B self-testing", "capability self-registry",
    "external-agent game theory", "human interface", "role-specialized desks",
    "explanation/summarization",
    "prediction-error loop", "counterfactual rollouts", "regime-forecasting",
    "niched variant population", "strategy/feature invention",
    "info-gain experiment selection", "skill-gap targeting",
    "graded beliefs", "Bayesian revision", "source grading",
    "hypothesis pipeline (double-sided)", "uncertainty decomposition", "bet-sizing-as-belief",
    "risk-preference values", "ethical constraints-as-values",
    "long-vs-short horizon",
    "importance scoring", "forgetting/invalidation", "reason ledger",
    "internet research organ", "data-source prospecting", "access governance gate",
    "alternative-data connectors", "cache/dedup",
})


def branch_build_status(branch_name: str) -> str:
    """'built' / 'partial' / 'unbuilt' for one branch — the concept-tree chip colour."""
    if branch_name in BUILT_BRANCHES:
        return "built"
    if branch_name in PARTIAL_BRANCHES:
        return "partial"
    return "unbuilt"


def atlas_coverage() -> dict:
    """Atlas build coverage across all ~197 branches — the number the dashboard reports so the
    build-to-100% program is visible (Rule N/M)."""
    total = sum(t.branch_count for t in CONCEPT_TREE)
    built = sum(1 for t in CONCEPT_TREE for b in t.branch_names if b in BUILT_BRANCHES)
    partial = sum(1 for t in CONCEPT_TREE for b in t.branch_names if b in PARTIAL_BRANCHES)
    return {
        "total": total,
        "built": built,
        "partial": partial,
        "unbuilt": total - built - partial,
        "built_pct": round(100.0 * built / total, 1) if total else 0.0,
    }
