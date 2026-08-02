"""Layer-11 slice 4: a meta-strategy allocator (research/103).

The bot runs three strategies — cash ORB (`opening_range_breakout_v1`), directional options
(`directional_option_orb_v1`), defined-risk spreads (`credit_spread_v1`) — each with a
champion-challenger-tuned config. Champion tuning optimises EACH strategy's config; nothing
decides how much to LEAN on each given their real, differing track records.

This asks the injected `StrategyLlmClient`, grounded in each strategy's real per-regime
performance + its current champion config, for a normalised ALLOCATION WEIGHT per strategy (a
portfolio-of-strategies judgment) with rationale. The weights are re-normalised to sum 1
defensively on parse, so the output is always a valid allocation regardless of what the model
returns. ADVISORY this slice (surfaced on the dashboard, Rule N); scaling real per-strategy
sizing by the weights is the queued, calibration-gated decision-consumer (Rule K).

Both the LLM seam and the `ExperienceMemory` read-model are injected; the champion store is an
optional injected collaborator (its `load_champion_or_default()`), so tests wire fakes (Rule J).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderError,
    StrategyLlmClient,
    StrategyLlmRequest,
)
from nse_algo_trader.memory_reflection.experience_memory import ExperienceMemory

# The structured shape the LLM must return — a weight + rationale per strategy, plus an overall.
META_ALLOCATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "allocations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "strategy_tag": {"type": "string"},
                    "weight": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["strategy_tag", "weight", "rationale"],
                "additionalProperties": False,
            },
        },
        "overall_rationale": {"type": "string"},
    },
    "required": ["allocations", "overall_rationale"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTION = (
    "You are a meta-strategy allocator for an intraday NSE trading bot that runs three "
    "strategies (cash ORB, directional options, credit spreads). You are given each strategy's "
    "REAL track record (win-rate, mean return, sample size), its per-regime calibration, and its "
    "current champion config. Reason ONLY from these facts — never invent numbers. Propose a "
    "capital/attention ALLOCATION WEIGHT for each strategy in [0,1] (they will be normalised to "
    "sum to 1): lean toward strategies with a proven positive edge and away from over-confident, "
    "negative-edge, or too-thin ones. Give a short rationale per strategy and one overall."
)

_CALIBRATION_BOARD_SCAN = 50  # rows scanned to aggregate per-strategy performance


@dataclass(frozen=True)
class StrategyAllocationWeight:
    """One strategy's normalised allocation weight (0..1, the set sums to 1) + why."""

    strategy_tag: str
    weight: float
    rationale: str


@dataclass(frozen=True)
class MetaStrategyAllocation:
    """The allocator's normalised output plus provenance. `generated` is False when the whole
    provider pool was exhausted (surfaced as blocked, not a crash)."""

    generated: bool
    served_by: str
    weights: tuple[StrategyAllocationWeight, ...] = ()
    overall_rationale: str = ""
    grounding_facts: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def weight_by_strategy(self) -> dict[str, float]:
        return {w.strategy_tag: w.weight for w in self.weights}


class MetaStrategyAllocator:
    """Builds the grounded prompt from real per-strategy performance + champion configs and asks
    the LLM seam for a normalised allocation across the strategies."""

    def __init__(
        self,
        llm_client: StrategyLlmClient,
        experience_memory: ExperienceMemory,
        champion_store=None,
    ) -> None:
        self._llm_client = llm_client
        self._experience_memory = experience_memory
        self._champion_store = champion_store

    def build_grounding_facts(self) -> list[str]:
        """Per-strategy aggregates from the calibration board + per-regime cohorts + the current
        champion config — exactly what the prompt carries (and the hermetic test asserts on)."""
        facts: list[str] = [
            f"Total graded experiences in memory: {self._experience_memory.experiment_count()}."
        ]

        # Aggregate the mechanism-level board rows up to the STRATEGY level (experiment-weighted).
        aggregates: dict[str, dict[str, float]] = {}
        for row in self._experience_memory.calibration_board(
            minimum_experiments=1, limit=_CALIBRATION_BOARD_SCAN
        ):
            acc = aggregates.setdefault(
                row.strategy_tag, {"n": 0.0, "win": 0.0, "ret": 0.0}
            )
            acc["n"] += row.experiment_count
            acc["win"] += row.actual_win_rate * row.experiment_count
            acc["ret"] += row.mean_return_fraction * row.experiment_count
        for strategy_tag, acc in sorted(aggregates.items()):
            n = acc["n"]
            facts.append(
                f"Strategy '{strategy_tag}' (n={int(n)}): actual win-rate "
                f"{_pct(acc['win'] / n if n else None)}, mean return "
                f"{_num(acc['ret'] / n if n else None)}."
            )

        for cohort in self._experience_memory.calibration_by_market_regime(
            minimum_experiments=1
        ):
            facts.append(
                f"Regime '{cohort.market_regime}' (n={cohort.experiment_count}): "
                f"hit-rate {_pct(cohort.hit_rate)}, mean return {_num(cohort.mean_return_fraction)}."
            )

        champion = self._current_champion_summary()
        if champion is not None:
            facts.append(champion)
        return facts

    def build_request(self, grounding_facts: list[str]) -> StrategyLlmRequest:
        prompt = (
            "Here are the bot's real per-strategy performance facts from memory:\n\n"
            + "\n".join(f"- {fact}" for fact in grounding_facts)
            + "\n\nReturn an allocation weight per strategy grounded in these facts only."
        )
        return StrategyLlmRequest(
            system_instruction=_SYSTEM_INSTRUCTION,
            user_prompt=prompt,
            response_json_schema=META_ALLOCATION_SCHEMA,
            purpose="meta_strategy_allocation",
        )

    def allocate(self) -> MetaStrategyAllocation:
        """Build the grounded prompt, call the swappable pool, parse + NORMALISE the weights. If
        every provider is exhausted, return a non-generated allocation carrying the reason."""
        facts = self.build_grounding_facts()
        request = self.build_request(facts)
        try:
            response = self._llm_client.generate_structured(request)
        except LlmProviderError as exc:
            return MetaStrategyAllocation(
                generated=False, served_by="", grounding_facts=tuple(facts), note=str(exc)
            )
        parsed = response.parsed_output
        return MetaStrategyAllocation(
            generated=True,
            served_by=f"{response.served_by_provider}:{response.served_by_model}",
            weights=_normalised_weights(parsed.get("allocations")),
            overall_rationale=str(parsed.get("overall_rationale") or ""),
            grounding_facts=tuple(facts),
        )

    def _current_champion_summary(self) -> str | None:
        if self._champion_store is None:
            return None
        try:
            champion = self._champion_store.load_champion_or_default()
        except Exception:
            return None
        return (
            f"Current global champion ORB config: opening range "
            f"{champion.opening_range_minutes}m, target reward "
            f"{champion.target_risk_reward_ratio}R."
        )


def _normalised_weights(value: object) -> tuple[StrategyAllocationWeight, ...]:
    """Parse the raw allocations and re-normalise to sum 1 (weights clamped ≥0). A degenerate
    all-zero/empty set becomes equal weights, so the output is always a valid allocation."""
    if not isinstance(value, list):
        return ()
    raw: list[tuple[str, float, str]] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("strategy_tag"):
            continue
        weight = max(0.0, _as_float(item.get("weight")))
        raw.append((str(item["strategy_tag"]), weight, str(item.get("rationale") or "")))
    if not raw:
        return ()
    total = sum(w for _, w, _ in raw)
    if total <= 0:  # degenerate → equal split so the allocation is still valid
        equal = 1.0 / len(raw)
        return tuple(StrategyAllocationWeight(tag, equal, r) for tag, _, r in raw)
    return tuple(
        StrategyAllocationWeight(tag, weight / total, rationale)
        for tag, weight, rationale in raw
    )


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
