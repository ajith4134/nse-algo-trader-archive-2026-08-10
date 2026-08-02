"""Layer-11 slice 3: causal analysis over multi-hop outcome clusters (research/102).

The Layer-10 memory computes WHAT clusters — per-mechanism temporal dependence
(`outcome_sequence_dependence`: wins/losses that clump, non-iid), per-regime calibration
(`calibration_by_market_regime`: which mechanisms fail in which regime), the over-confident
calibration board, and the VIOLATED statistical assumptions — but none of them says WHY.

This asks the injected `StrategyLlmClient` to reason ACROSS those heterogeneous per-mechanism /
per-regime facts and propose named, FALSIFIABLE causal hypotheses: for a cluster of co-failing
mechanisms, a suspected COMMON cause and the concrete evidence that would confirm or refute it.
The hypotheses extend the statistical assumption registry with causal explanations (a "why" on
top of the "what"). Grounded — the prompt is built ONLY from the real cluster reads, and the
system prompt forbids inventing mechanisms/numbers.

ADVISORY this slice (surfaced on the dashboard, Rule N). Scoring each falsifiable prediction and
turning a confirmed hypothesis into a targeted assumption tripwire / strategy nudge is the queued,
calibration-gated decision-consumer (Rule K). Both collaborators are injected (the LLM seam + the
`ExperienceMemory` read-model), so tests wire an in-memory memory + a fake LLM (Rule J).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderError,
    StrategyLlmClient,
    StrategyLlmRequest,
)
from nse_algo_trader.memory_reflection.assumption_registry import (
    AssumptionConfig,
    AssumptionStatus,
    evaluate_trading_assumptions,
)
from nse_algo_trader.memory_reflection.experience_memory import ExperienceMemory

# The structured shape the LLM must return — an array of falsifiable causal hypotheses.
CAUSAL_ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_label": {"type": "string"},
                    "implicated_mechanisms": {
                        "type": "array", "items": {"type": "string"}
                    },
                    "suspected_common_cause": {"type": "string"},
                    "falsifiable_prediction": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "cluster_label", "implicated_mechanisms",
                    "suspected_common_cause", "falsifiable_prediction", "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTION = (
    "You are a causal-inference analyst for an intraday NSE trading bot. You are given real "
    "multi-hop outcome-cluster facts from its memory: which mechanisms are over-confident, how "
    "their wins/losses CLUSTER over time (non-iid), how they calibrate ACROSS market regimes, and "
    "which statistical assumptions are VIOLATED. Reason ONLY from these facts — never invent "
    "mechanisms, regimes, or numbers. Propose falsifiable CAUSAL hypotheses: for a CLUSTER of "
    "co-failing mechanisms, name the single most likely COMMON cause (e.g. stops too tight in "
    "trends, entering into mean-reversion, event-day gamma, regime-timing lag) and a concrete "
    "prediction that would CONFIRM or REFUTE it. Prefer a few high-signal hypotheses over many."
)

_TOP_MECHANISMS = 6
_ASSUMPTION_CONFIG = AssumptionConfig()


@dataclass(frozen=True)
class CausalHypothesis:
    """One falsifiable causal assumption: which mechanisms cluster, the suspected shared cause,
    and the evidence that would confirm/refute it. `confidence` is clamped to [0,1] on parse."""

    cluster_label: str
    implicated_mechanisms: tuple[str, ...]
    suspected_common_cause: str
    falsifiable_prediction: str
    confidence: float


@dataclass(frozen=True)
class CausalClusterAnalysis:
    """The analyst's structured output plus provenance. `generated` is False when the whole
    provider pool was exhausted (surfaced as blocked, not a crash)."""

    generated: bool
    served_by: str
    hypotheses: tuple[CausalHypothesis, ...] = ()
    grounding_facts: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


class CausalClusterAnalyst:
    """Builds the grounded prompt from the real multi-hop cluster reads and asks the LLM seam
    for falsifiable causal hypotheses."""

    def __init__(
        self, llm_client: StrategyLlmClient, experience_memory: ExperienceMemory
    ) -> None:
        self._llm_client = llm_client
        self._experience_memory = experience_memory

    def build_grounding_facts(self) -> list[str]:
        """Pull the REAL multi-hop cluster numbers into human-readable fact lines — exactly what
        goes into the prompt (and what the hermetic test asserts on)."""
        facts: list[str] = [
            f"Total graded experiences in memory: {self._experience_memory.experiment_count()}."
        ]

        # Over-confident mechanisms (the calibration board).
        for row in self._experience_memory.calibration_board(
            minimum_experiments=1, limit=_TOP_MECHANISMS
        ):
            facts.append(
                f"Mechanism '{row.mechanism_name}' (strategy '{row.strategy_tag}', "
                f"n={row.experiment_count}): predicted {_pct(row.predicted_win_rate)} vs actual "
                f"{_pct(row.actual_win_rate)} (gap {_gap(row.predicted_win_rate, row.actual_win_rate)}), "
                f"mean return {_num(row.mean_return_fraction)}."
            )

        # Cross-regime calibration (which mechanisms fail in which regime).
        for cohort in self._experience_memory.calibration_by_market_regime(
            minimum_experiments=1
        ):
            facts.append(
                f"Regime '{cohort.market_regime}' (n={cohort.experiment_count}): "
                f"hit-rate {_pct(cohort.hit_rate)}, mean return {_num(cohort.mean_return_fraction)}."
            )

        # Temporal multi-hop clustering (non-iid wins/losses).
        for dep in self._experience_memory.outcome_sequence_dependence(
            minimum_experiments=_ASSUMPTION_CONFIG.minimum_samples
        ):
            if dep.clusters and dep.dependence_gap is not None:
                facts.append(
                    f"Mechanism '{dep.mechanism_name}' CLUSTERS in time: post-win win-rate "
                    f"{_pct(dep.post_win_win_rate)} vs post-loss {_pct(dep.post_loss_win_rate)} "
                    f"(dependence gap {dep.dependence_gap:+.0%}) — outcomes are not independent."
                )

        # Violated statistical assumptions (the 'what is broken' the causal 'why' explains).
        for verdict in evaluate_trading_assumptions(
            self._experience_memory, _ASSUMPTION_CONFIG
        ):
            if verdict.status is AssumptionStatus.VIOLATED:
                facts.append(
                    f"VIOLATED assumption '{verdict.assumption_name}' for {verdict.scope}: "
                    f"{verdict.detail}"
                )
        return facts

    def build_request(self, grounding_facts: list[str]) -> StrategyLlmRequest:
        prompt = (
            "Here are the bot's real multi-hop outcome-cluster facts from memory:\n\n"
            + "\n".join(f"- {fact}" for fact in grounding_facts)
            + "\n\nReturn falsifiable causal hypotheses grounded in these facts only."
        )
        return StrategyLlmRequest(
            system_instruction=_SYSTEM_INSTRUCTION,
            user_prompt=prompt,
            response_json_schema=CAUSAL_ANALYSIS_SCHEMA,
            purpose="causal_cluster_analysis",
        )

    def analyze(self) -> CausalClusterAnalysis:
        """Build the grounded prompt, call the swappable pool, parse the hypotheses. If every
        provider is exhausted, return a non-generated analysis carrying the reason (so the
        dashboard shows 'blocked', never a crash)."""
        facts = self.build_grounding_facts()
        request = self.build_request(facts)
        try:
            response = self._llm_client.generate_structured(request)
        except LlmProviderError as exc:
            return CausalClusterAnalysis(
                generated=False, served_by="", grounding_facts=tuple(facts), note=str(exc)
            )
        return CausalClusterAnalysis(
            generated=True,
            served_by=f"{response.served_by_provider}:{response.served_by_model}",
            hypotheses=_parse_hypotheses(response.parsed_output.get("hypotheses")),
            grounding_facts=tuple(facts),
        )


def _parse_hypotheses(value: object) -> tuple[CausalHypothesis, ...]:
    if not isinstance(value, list):
        return ()
    hypotheses: list[CausalHypothesis] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        hypotheses.append(
            CausalHypothesis(
                cluster_label=str(item.get("cluster_label") or ""),
                implicated_mechanisms=_string_tuple(item.get("implicated_mechanisms")),
                suspected_common_cause=str(item.get("suspected_common_cause") or ""),
                falsifiable_prediction=str(item.get("falsifiable_prediction") or ""),
                confidence=_clamp01(_as_float(item.get("confidence"))),
            )
        )
    return tuple(hypotheses)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _gap(predicted: float | None, actual: float | None) -> str:
    if predicted is None or actual is None:
        return "n/a"
    return f"{(predicted - actual) * 100:+.0f}pp"
