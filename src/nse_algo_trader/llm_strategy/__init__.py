"""Layer 11 — Strategic LLM / Autonomous-Research-Agent layer (research/96).

The generative/agentic-AI layer, grounded in the real §9/§10 memory. Slice 1: a provider-
neutral LLM seam (`strategy_llm_client`) served by a swap-on-limit pool of free-tier cloud
LLMs (`llm_provider_registry` → `swappable_multi_provider_llm_client`), consumed by the
`memory_grounded_strategy_analyst`. Everything is behind a DI seam so the injected fake in
tests can never reach a real network call (Rule J).
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.causal_cluster_analyst import (
    CausalClusterAnalysis,
    CausalClusterAnalyst,
    CausalHypothesis,
)
from nse_algo_trader.llm_strategy.memory_grounded_strategy_analyst import (
    MemoryGroundedStrategyAnalyst,
    StrategicReflection,
)
from nse_algo_trader.llm_strategy.meta_strategy_allocator import (
    MetaStrategyAllocation,
    MetaStrategyAllocator,
    StrategyAllocationWeight,
)
from nse_algo_trader.llm_strategy.prediction_council import (
    CouncilForecast,
    PredictionCouncil,
)
from nse_algo_trader.llm_strategy.thesis_debate_risk_panel import (
    DebateRiskAssessment,
    ThesisDebateRiskPanel,
    TradeThesis,
)
from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    StrategyLlmClient,
    StrategyLlmRequest,
    StrategyLlmResponse,
)
from nse_algo_trader.llm_strategy.synthetic_stress_rehearsal import (
    StressScenario,
    SyntheticStressRehearsal,
    SyntheticStressScenarioGenerator,
)
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)

__all__ = [
    "CausalClusterAnalysis",
    "CausalClusterAnalyst",
    "CausalHypothesis",
    "CouncilForecast",
    "DebateRiskAssessment",
    "MemoryGroundedStrategyAnalyst",
    "MetaStrategyAllocation",
    "MetaStrategyAllocator",
    "PredictionCouncil",
    "StrategyAllocationWeight",
    "StressScenario",
    "SyntheticStressRehearsal",
    "SyntheticStressScenarioGenerator",
    "StrategicReflection",
    "StrategyLlmClient",
    "StrategyLlmRequest",
    "StrategyLlmResponse",
    "SwappableMultiProviderLlmClient",
    "ThesisDebateRiskPanel",
    "TradeThesis",
    "build_free_tier_provider_pool",
]
