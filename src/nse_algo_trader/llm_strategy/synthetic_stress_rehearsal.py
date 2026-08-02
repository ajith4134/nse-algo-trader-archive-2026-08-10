"""Layer-11 slice 6: a synthetic stress-scenario generator (research/105) — the last generative
Layer-11 slice, and the red-team feeder for the Layer-7.5 control-arms lab.

Grounded in the bot's REAL weakness surface — its over-confident and negative-edge mechanisms, its
VIOLATED assumptions, its temporally-clustering failures, and its weak per-regime cohorts — this
asks the injected `StrategyLlmClient` to generate concrete adversarial STRESS SCENARIOS: for a
targeted vulnerable mechanism, the market condition that would break it, the predicted failure
mode, and a mitigation, with a severity. It is the "what could go wrong, specifically" generator.

ADVISORY this slice (surfaced on the dashboard, Rule N). The consumer that RUNS each scenario —
replaying the synthetic condition against the current champion configs and scoring realised-vs-
predicted failure — is the Layer-7.5 control-arms lab (queued, research/95). The LLM seam +
`ExperienceMemory` are injected, so tests wire a fake LLM + in-memory memory (Rule J).
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

# The structured shape the LLM must return — an array of adversarial stress scenarios.
STRESS_REHEARSAL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scenario_label": {"type": "string"},
                    "market_condition": {"type": "string"},
                    "targeted_mechanism": {"type": "string"},
                    "predicted_failure_mode": {"type": "string"},
                    "mitigation": {"type": "string"},
                    "severity": {"type": "number"},
                },
                "required": [
                    "scenario_label", "market_condition", "targeted_mechanism",
                    "predicted_failure_mode", "mitigation", "severity",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenarios"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTION = (
    "You are a red-team stress-tester for an intraday NSE trading bot. You are given the bot's "
    "REAL weakness surface: its over-confident and negative-edge mechanisms, its VIOLATED "
    "assumptions, how its failures CLUSTER in time, and its weak market regimes. Reason ONLY from "
    "these facts — never invent mechanisms or numbers. Generate concrete adversarial STRESS "
    "SCENARIOS: for a TARGETED vulnerable mechanism, describe the specific market condition that "
    "would break it, the predicted FAILURE MODE, and a MITIGATION, with a severity in [0,1]. "
    "Prefer a few high-severity, mechanism-specific scenarios over generic market lore."
)

_TOP_MECHANISMS = 6
_ASSUMPTION_CONFIG = AssumptionConfig()


@dataclass(frozen=True)
class StressScenario:
    """One adversarial rehearsal: the condition that breaks a targeted mechanism, its predicted
    failure mode + mitigation, and a severity ∈ [0,1] (clamped on parse)."""

    scenario_label: str
    market_condition: str
    targeted_mechanism: str
    predicted_failure_mode: str
    mitigation: str
    severity: float


@dataclass(frozen=True)
class SyntheticStressRehearsal:
    """The generator's structured output plus provenance. `generated` is False when the whole
    provider pool was exhausted (surfaced as blocked, not a crash)."""

    generated: bool
    served_by: str
    scenarios: tuple[StressScenario, ...] = ()
    grounding_facts: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


class SyntheticStressScenarioGenerator:
    """Builds the grounded prompt from the real weakness surface and asks the LLM seam for
    adversarial stress scenarios."""

    def __init__(
        self, llm_client: StrategyLlmClient, experience_memory: ExperienceMemory
    ) -> None:
        self._llm_client = llm_client
        self._experience_memory = experience_memory

    def build_grounding_facts(self) -> list[str]:
        """Pull the REAL weakness surface into fact lines — over-confident + negative-edge
        mechanisms, violated assumptions, temporal clustering, weak regimes."""
        facts: list[str] = [
            f"Total graded experiences in memory: {self._experience_memory.experiment_count()}."
        ]

        for row in self._experience_memory.calibration_board(
            minimum_experiments=1, limit=_TOP_MECHANISMS
        ):
            edge = "NEGATIVE edge" if row.mean_return_fraction < 0 else "positive edge"
            facts.append(
                f"Mechanism '{row.mechanism_name}' (n={row.experiment_count}): predicted "
                f"{_pct(row.predicted_win_rate)} vs actual {_pct(row.actual_win_rate)} "
                f"(gap {_gap(row.predicted_win_rate, row.actual_win_rate)}), mean return "
                f"{_num(row.mean_return_fraction)} — {edge}."
            )

        for verdict in evaluate_trading_assumptions(
            self._experience_memory, _ASSUMPTION_CONFIG
        ):
            if verdict.status is AssumptionStatus.VIOLATED:
                facts.append(
                    f"VIOLATED assumption '{verdict.assumption_name}' for {verdict.scope}: "
                    f"{verdict.detail}"
                )

        for dep in self._experience_memory.outcome_sequence_dependence(
            minimum_experiments=_ASSUMPTION_CONFIG.minimum_samples
        ):
            if dep.clusters and dep.dependence_gap is not None:
                facts.append(
                    f"Mechanism '{dep.mechanism_name}' fails in CLUSTERS (post-win "
                    f"{_pct(dep.post_win_win_rate)} vs post-loss {_pct(dep.post_loss_win_rate)} "
                    f"win-rate) — losing streaks compound."
                )

        for cohort in self._experience_memory.calibration_by_market_regime(
            minimum_experiments=1
        ):
            if (cohort.mean_return_fraction or 0.0) < 0 or (cohort.hit_rate or 1.0) < 0.5:
                facts.append(
                    f"Weak regime '{cohort.market_regime}' (n={cohort.experiment_count}): "
                    f"hit-rate {_pct(cohort.hit_rate)}, mean return {_num(cohort.mean_return_fraction)}."
                )
        return facts

    def build_request(self, grounding_facts: list[str]) -> StrategyLlmRequest:
        prompt = (
            "Here is the bot's real weakness surface from memory:\n\n"
            + "\n".join(f"- {fact}" for fact in grounding_facts)
            + "\n\nGenerate adversarial stress scenarios grounded in these weaknesses only."
        )
        return StrategyLlmRequest(
            system_instruction=_SYSTEM_INSTRUCTION,
            user_prompt=prompt,
            response_json_schema=STRESS_REHEARSAL_SCHEMA,
            purpose="synthetic_stress_rehearsal",
        )

    def generate(self) -> SyntheticStressRehearsal:
        """Build the grounded prompt, call the swappable pool, parse the scenarios. If every
        provider is exhausted, return a non-generated rehearsal carrying the reason."""
        facts = self.build_grounding_facts()
        request = self.build_request(facts)
        try:
            response = self._llm_client.generate_structured(request)
        except LlmProviderError as exc:
            return SyntheticStressRehearsal(
                generated=False, served_by="", grounding_facts=tuple(facts), note=str(exc)
            )
        return SyntheticStressRehearsal(
            generated=True,
            served_by=f"{response.served_by_provider}:{response.served_by_model}",
            scenarios=_parse_scenarios(response.parsed_output.get("scenarios")),
            grounding_facts=tuple(facts),
        )


def _parse_scenarios(value: object) -> tuple[StressScenario, ...]:
    if not isinstance(value, list):
        return ()
    scenarios: list[StressScenario] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        scenarios.append(
            StressScenario(
                scenario_label=str(item.get("scenario_label") or ""),
                market_condition=str(item.get("market_condition") or ""),
                targeted_mechanism=str(item.get("targeted_mechanism") or ""),
                predicted_failure_mode=str(item.get("predicted_failure_mode") or ""),
                mitigation=str(item.get("mitigation") or ""),
                severity=_clamp01(_as_float(item.get("severity"))),
            )
        )
    return tuple(scenarios)


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
