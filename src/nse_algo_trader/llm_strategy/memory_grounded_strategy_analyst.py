"""The first Layer-11 role: a memory-grounded strategy analyst (research/96 slice 1).

It reads the REAL §9/§10 memory (calibration board = the most over-confident mechanisms,
per-market-regime calibration, experiment counts, recent closed trades), turns those facts
into a grounded prompt, and asks the injected `StrategyLlmClient` for a structured
`StrategicReflection` — findings, hypotheses, and a distrust list of mechanisms to trust
less. It is ADVISORY (read-only) at this slice: the reflection is surfaced on the dashboard
(Rule N); feeding LLM opinions into the entry GATE is a later, calibration-gated slice
(research/96 slice 2+, queued — Rule K).

Grounding is the whole point: the prompt is built ONLY from facts pulled out of the memory
read-model, and the system instruction forbids inventing numbers — so the reflection is
about THIS bot's actual track record, not generic trading advice. The hermetic test asserts
the prompt literally contains the real facts, and that the parsed reflection surfaces.

Depends on the `ExperienceMemory` read-model protocol and the `StrategyLlmClient` seam — both
injected, so production wires the real SQLite memory + the swappable provider pool, and tests
wire an in-memory memory + a fake LLM (Rule J).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderError,
    StrategyLlmClient,
    StrategyLlmRequest,
)
from nse_algo_trader.memory_reflection.experience_memory import ExperienceMemory

# The structured shape the LLM must return — forced via schema/tool across every provider.
STRATEGIC_REFLECTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {"type": "string"}},
        "hypotheses": {"type": "array", "items": {"type": "string"}},
        "distrust_mechanisms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["findings", "hypotheses", "distrust_mechanisms"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTION = (
    "You are a skeptical quantitative strategy analyst reviewing an intraday NSE trading "
    "bot's OWN track record. You are given real calibration facts from its memory. Reason "
    "ONLY from these facts — never invent numbers, mechanisms, or trades not present. "
    "Identify where the bot is over-confident (predicted win-rate above actual), propose "
    "testable hypotheses for WHY, and list mechanisms whose predictions should be trusted "
    "less until they recalibrate. Be concrete and cite the mechanism names from the facts."
)

# How many worst-calibrated mechanisms / regimes / recent trades to put in the prompt.
_TOP_MECHANISMS = 6
_RECENT_TRADES = 12


@dataclass(frozen=True)
class StrategicReflection:
    """The analyst's structured output plus provenance. `generated` is False when the whole
    provider pool was exhausted (surfaced as blocked, not a crash). `grounding_facts` are the
    exact real-memory lines fed to the LLM — kept for transparency and the hermetic assert."""

    generated: bool
    served_by: str
    findings: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    distrust_mechanisms: tuple[str, ...] = ()
    grounding_facts: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


class MemoryGroundedStrategyAnalyst:
    """Builds the grounded prompt from real memory and asks the LLM seam for a reflection."""

    def __init__(
        self, llm_client: StrategyLlmClient, experience_memory: ExperienceMemory
    ) -> None:
        self._llm_client = llm_client
        self._experience_memory = experience_memory

    def build_grounding_facts(self) -> list[str]:
        """Pull the real numbers out of the memory read-model into human-readable fact lines.
        These are exactly what goes into the prompt (and what the test asserts on)."""
        facts: list[str] = []
        total = self._experience_memory.experiment_count()
        facts.append(f"Total graded experiences in memory: {total}.")

        regime_counts = self._experience_memory.experiment_count_by_market_regime()
        if regime_counts:
            spread = ", ".join(f"{r}={n}" for r, n in sorted(regime_counts.items()))
            facts.append(f"Experience count by market regime: {spread}.")

        board = self._experience_memory.calibration_board(
            minimum_experiments=1, limit=_TOP_MECHANISMS
        )
        for row in board:
            pred = _pct(row.predicted_win_rate)
            act = _pct(row.actual_win_rate)
            gap = _gap(row.predicted_win_rate, row.actual_win_rate)
            facts.append(
                f"Mechanism '{row.mechanism_name}' (strategy '{row.strategy_tag}', "
                f"n={row.experiment_count}): predicted win-rate {pred} vs actual {act} "
                f"(over-confidence gap {gap}), mean Brier {_num(row.mean_brier)}, "
                f"mean return {_num(row.mean_return_fraction)}."
            )

        regime_calib = self._experience_memory.calibration_by_market_regime(
            minimum_experiments=1
        )
        for cohort in regime_calib:
            facts.append(
                f"Regime '{cohort.market_regime}' (n={cohort.experiment_count}): "
                f"hit-rate {_pct(cohort.hit_rate)}, mean Brier {_num(cohort.mean_brier)}, "
                f"mean return {_num(cohort.mean_return_fraction)}."
            )

        recent = self._experience_memory.recent_closed_experiences(limit=_RECENT_TRADES)
        if recent:
            wins = sum(1 for r in recent if r.get("actual_outcome") == "win")
            facts.append(
                f"Most recent {len(recent)} closed trades: {wins} wins / "
                f"{len(recent) - wins} losses."
            )
        return facts

    def build_request(self, grounding_facts: list[str]) -> StrategyLlmRequest:
        prompt = (
            "Here are the bot's real calibration facts from memory:\n\n"
            + "\n".join(f"- {fact}" for fact in grounding_facts)
            + "\n\nReturn findings, hypotheses, and distrust_mechanisms grounded in these "
            "facts only."
        )
        return StrategyLlmRequest(
            system_instruction=_SYSTEM_INSTRUCTION,
            user_prompt=prompt,
            response_json_schema=STRATEGIC_REFLECTION_SCHEMA,
            purpose="memory_grounded_strategy_reflection",
        )

    def reflect(self) -> StrategicReflection:
        """Build the grounded prompt, call the swappable LLM pool, parse the reflection. If
        every provider is exhausted, return a non-generated reflection carrying the reason
        (so the dashboard shows 'blocked', never a crash)."""
        facts = self.build_grounding_facts()
        request = self.build_request(facts)
        try:
            response = self._llm_client.generate_structured(request)
        except LlmProviderError as exc:
            return StrategicReflection(
                generated=False,
                served_by="",
                grounding_facts=tuple(facts),
                note=str(exc),
            )
        parsed = response.parsed_output
        return StrategicReflection(
            generated=True,
            served_by=f"{response.served_by_provider}:{response.served_by_model}",
            findings=_string_tuple(parsed.get("findings")),
            hypotheses=_string_tuple(parsed.get("hypotheses")),
            distrust_mechanisms=_string_tuple(parsed.get("distrust_mechanisms")),
            grounding_facts=tuple(facts),
        )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _gap(predicted: float | None, actual: float | None) -> str:
    if predicted is None or actual is None:
        return "n/a"
    return f"{(predicted - actual) * 100:+.0f}pp"
