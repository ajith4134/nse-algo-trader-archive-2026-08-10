"""Layer-11 slice 2: a debate-as-risk-check panel (research/96 slice 2, design research/100).

Three INDEPENDENT LLM roles — BULL, BEAR, RISK OFFICER — each debate a proposed `TradeThesis`
(e.g. "keep trading mechanism X, its edge is real"), grounded in the bot's REAL calibration
memory, and each return a structured `soundness ∈ [0,1]` ("probability this thesis actually
works, from my lens"). A pure, deterministic step then distils the three soundness values into
a risk signal:
  * `disagreement_score = max - min`      — how much the roles disagree (the debate spread),
  * `adverse_conviction = 1 - mean`       — how collectively skeptical they are,
  * `risk_score = blend(the two)`          — the number the entry GATE will eventually threshold.

Why three independent calls (not one prompt asking for all three views): a single model/context
produces correlated positions — a real debate needs independent reasoners, which the swappable
pool serves naturally (each call can fail over). Grounding is the point: every role prompt
carries the mechanism's real predicted-vs-actual calibration from `ExperienceMemory`, and the
system prompt forbids inventing numbers — so the debate is about THIS bot's track record.

ADVISORY this slice (surfaced on the dashboard, Rule N). Feeding `risk_score` into the entry
gate to defer/size-down high-risk entries is the PRIMARY purpose but is QUEUED behind the debate
earning calibration first (Rule K) — the same advisory→gating discipline as slice 1's analyst.

Both collaborators are injected (`StrategyLlmClient` seam + `ExperienceMemory` read-model), so
production wires the real SQLite memory + the real provider pool and tests wire an in-memory
memory + a fake LLM (Rule J).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderError,
    StrategyLlmClient,
    StrategyLlmRequest,
)
from nse_algo_trader.memory_reflection.experience_memory import ExperienceMemory

# Each role must return this shape — forced via schema/tool across every provider.
ROLE_VERDICT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "soundness": {"type": "number"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "main_risk": {"type": "string"},
    },
    "required": ["soundness", "key_points", "main_risk"],
    "additionalProperties": False,
}

_SOUNDNESS_DEFINITION = (
    " Return `soundness` as a probability in [0,1] that this thesis actually works out for the "
    "bot (0 = certainly fails, 1 = certainly sound), `key_points` (3 short bullet reasons from "
    "your lens), and `main_risk` (the single biggest risk you see). Reason ONLY from the given "
    "calibration facts — never invent numbers, mechanisms, or trades not present."
)


@dataclass(frozen=True)
class DebateRole:
    """One debating lens: its name (for the served-by trail) + its system instruction."""

    name: str
    system_instruction: str


BULL_ROLE = DebateRole(
    "bull",
    "You are a BULL analyst. Argue that the trading thesis IS sound — marshal the strongest "
    "supporting evidence in the bot's real calibration facts." + _SOUNDNESS_DEFINITION,
)
BEAR_ROLE = DebateRole(
    "bear",
    "You are a BEAR analyst. Argue that the trading thesis is NOT sound — marshal the strongest "
    "disconfirming evidence in the bot's real calibration facts (over-confidence, poor Brier, "
    "thin sample)." + _SOUNDNESS_DEFINITION,
)
RISK_OFFICER_ROLE = DebateRole(
    "risk_officer",
    "You are a RISK OFFICER. Ignore the upside; judge only the DOWNSIDE — how bad the losing "
    "case is, risk-of-ruin, and whether the edge is too fragile/unproven to size into, using "
    "the bot's real calibration facts." + _SOUNDNESS_DEFINITION,
)
# The debate is exactly these three, run independently and in this order.
DEBATE_ROLES: tuple[DebateRole, ...] = (BULL_ROLE, BEAR_ROLE, RISK_OFFICER_ROLE)

_DEFAULT_DISAGREEMENT_WEIGHT = 0.5
_TOP_ACTIVE_THESES = 3
_CALIBRATION_BOARD_SCAN = 30  # rows scanned to find a thesis mechanism's calibration row


@dataclass(frozen=True)
class TradeThesis:
    """The proposition being debated — a mechanism the bot actively trades, and the claim that
    its edge is real. `stated_win_probability` is the mechanism's own predicted win-rate."""

    mechanism_name: str
    strategy_tag: str
    claim: str
    stated_win_probability: float | None = None


@dataclass(frozen=True)
class RoleVerdict:
    """One role's structured position. `soundness` is clamped to [0,1] on parse."""

    role: str
    soundness: float
    key_points: tuple[str, ...] = ()
    main_risk: str = ""


@dataclass(frozen=True)
class DebateRiskAssessment:
    """The full debate outcome for one thesis. `generated` is False when the provider pool was
    exhausted mid-debate (surfaced as blocked, never a crash). `risk_score` is the gate-relevant
    blend; `disagreement_score` is the interpretable debate spread."""

    thesis: TradeThesis
    generated: bool
    served_by: str = ""
    verdicts: tuple[RoleVerdict, ...] = ()
    disagreement_score: float = 0.0
    adverse_conviction: float = 0.0
    risk_score: float = 0.0
    grounding_facts: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


# ----- pure risk math (deterministic; unit-tested without any LLM) -----


def compute_disagreement_score(soundness_values: list[float]) -> float:
    """The debate SPREAD: how far apart the roles are. Bounded [0,1] for inputs in [0,1]."""
    if not soundness_values:
        return 0.0
    return max(soundness_values) - min(soundness_values)


def compute_adverse_conviction(soundness_values: list[float]) -> float:
    """Collective skepticism: 1 - mean(soundness). High when all roles lean negative — the case
    pure disagreement misses (a unanimous 'this is bad' is low-spread but high-risk)."""
    if not soundness_values:
        return 0.0
    return _clamp01(1.0 - mean(soundness_values))


def compute_risk_score(
    disagreement_score: float,
    adverse_conviction: float,
    disagreement_weight: float = _DEFAULT_DISAGREEMENT_WEIGHT,
) -> float:
    """The gate-relevant blend of debate-spread and collective-skepticism, in [0,1]. Weights
    are a documented default (not yet tuned — tuning is part of earning calibration)."""
    weight = _clamp01(disagreement_weight)
    blended = weight * disagreement_score + (1.0 - weight) * adverse_conviction
    return _clamp01(blended)


class ThesisDebateRiskPanel:
    """Runs the three-role debate over a thesis (or the active theses from memory) and distils
    each into a `DebateRiskAssessment`."""

    def __init__(
        self,
        llm_client: StrategyLlmClient,
        experience_memory: ExperienceMemory,
        disagreement_weight: float = _DEFAULT_DISAGREEMENT_WEIGHT,
    ) -> None:
        self._llm_client = llm_client
        self._experience_memory = experience_memory
        self._disagreement_weight = disagreement_weight

    def build_grounding_facts(self, thesis: TradeThesis) -> list[str]:
        """Real memory facts about THIS thesis's mechanism (its calibration row) + regime
        context — exactly what each role prompt carries (and what the hermetic test asserts)."""
        facts: list[str] = [
            f"Total graded experiences in memory: {self._experience_memory.experiment_count()}."
        ]
        row = self._calibration_row_for(thesis.mechanism_name)
        if row is not None:
            facts.append(
                f"Mechanism '{row.mechanism_name}' (strategy '{row.strategy_tag}', "
                f"n={row.experiment_count}): predicted win-rate {_pct(row.predicted_win_rate)} "
                f"vs actual {_pct(row.actual_win_rate)} (over-confidence gap "
                f"{_gap(row.predicted_win_rate, row.actual_win_rate)}), mean Brier "
                f"{_num(row.mean_brier)}, mean return {_num(row.mean_return_fraction)}."
            )
        else:
            facts.append(
                f"Mechanism '{thesis.mechanism_name}' has no calibration row yet "
                "(too few graded experiences) — treat its stated edge as unproven."
            )
        regime_calib = self._experience_memory.calibration_by_market_regime(
            minimum_experiments=1
        )
        for cohort in regime_calib:
            facts.append(
                f"Regime '{cohort.market_regime}' (n={cohort.experiment_count}): "
                f"hit-rate {_pct(cohort.hit_rate)}, mean Brier {_num(cohort.mean_brier)}."
            )
        return facts

    def build_role_request(
        self, role: DebateRole, thesis: TradeThesis, grounding_facts: list[str]
    ) -> StrategyLlmRequest:
        prompt = (
            f"THESIS TO DEBATE: {thesis.claim}\n"
            f"(mechanism '{thesis.mechanism_name}', strategy '{thesis.strategy_tag}', "
            f"stated win-probability {_pct(thesis.stated_win_probability)})\n\n"
            "The bot's real calibration facts:\n"
            + "\n".join(f"- {fact}" for fact in grounding_facts)
            + "\n\nGive your role's soundness, key_points, and main_risk."
        )
        return StrategyLlmRequest(
            system_instruction=role.system_instruction,
            user_prompt=prompt,
            response_json_schema=ROLE_VERDICT_SCHEMA,
            purpose=f"thesis_debate_{role.name}",
        )

    def debate(self, thesis: TradeThesis) -> DebateRiskAssessment:
        """Run all three role calls independently, then compute the risk signal. If any role's
        call exhausts the whole pool, return a non-generated assessment carrying the reason."""
        facts = self.build_grounding_facts(thesis)
        verdicts: list[RoleVerdict] = []
        served: list[str] = []
        for role in DEBATE_ROLES:
            request = self.build_role_request(role, thesis, facts)
            try:
                response = self._llm_client.generate_structured(request)
            except LlmProviderError as exc:
                return DebateRiskAssessment(
                    thesis=thesis,
                    generated=False,
                    grounding_facts=tuple(facts),
                    note=f"{role.name} role: {exc}",
                )
            parsed = response.parsed_output
            verdicts.append(
                RoleVerdict(
                    role=role.name,
                    soundness=_clamp01(_as_float(parsed.get("soundness"))),
                    key_points=_string_tuple(parsed.get("key_points")),
                    main_risk=str(parsed.get("main_risk") or ""),
                )
            )
            served.append(f"{response.served_by_provider}:{response.served_by_model}")

        soundness_values = [v.soundness for v in verdicts]
        disagreement = compute_disagreement_score(soundness_values)
        adverse = compute_adverse_conviction(soundness_values)
        return DebateRiskAssessment(
            thesis=thesis,
            generated=True,
            served_by=", ".join(dict.fromkeys(served)),  # de-duped, order preserved
            verdicts=tuple(verdicts),
            disagreement_score=disagreement,
            adverse_conviction=adverse,
            risk_score=compute_risk_score(disagreement, adverse, self._disagreement_weight),
            grounding_facts=tuple(facts),
        )

    def theses_from_calibration_board(
        self, limit: int = _TOP_ACTIVE_THESES
    ) -> list[TradeThesis]:
        """Derive the ACTIVE theses to debate from the calibration board — the mechanisms the
        bot actually trades (bounded so the daily debate stays within free-tier call budgets)."""
        board = self._experience_memory.calibration_board(minimum_experiments=1, limit=limit)
        return [
            TradeThesis(
                mechanism_name=row.mechanism_name,
                strategy_tag=row.strategy_tag,
                claim=(
                    f"The bot should keep trading mechanism '{row.mechanism_name}' "
                    f"(strategy '{row.strategy_tag}') at its stated win-probability — the edge "
                    "is real and durable."
                ),
                stated_win_probability=row.predicted_win_rate,
            )
            for row in board
        ]

    def debate_active_theses(
        self, limit: int = _TOP_ACTIVE_THESES
    ) -> tuple[DebateRiskAssessment, ...]:
        """Debate each active thesis; the cached result feeds the dashboard (and, later, the
        gate). Order follows the calibration board (worst-calibrated first)."""
        return tuple(self.debate(thesis) for thesis in self.theses_from_calibration_board(limit))

    def _calibration_row_for(self, mechanism_name: str):
        board = self._experience_memory.calibration_board(
            minimum_experiments=1, limit=_CALIBRATION_BOARD_SCAN
        )
        return next((r for r in board if r.mechanism_name == mechanism_name), None)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


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
