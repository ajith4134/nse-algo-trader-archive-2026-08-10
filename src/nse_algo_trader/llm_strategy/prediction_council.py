"""Layer-11 slice 5: a prediction-market council with track-record weighting (research/104).

A COUNCIL of distinct forecasting roles — momentum optimist, mean-reversion skeptic, regime
realist, risk officer — each independently forecast a PROBABILITY on a resolvable proposition,
grounded in the real memory. The council's aggregate is a TRACK-RECORD-WEIGHTED average: roles
that have forecast more accurately in the past (lower log-loss over their resolved forecasts)
carry more weight — a prediction market where each member has a reputation. Until reputations
accrue, weights are equal (weighted == simple mean), so the council starts as a plain diverse
ensemble and becomes reputation-weighted as skill is proven (prequential, like slice 2c).

ADVISORY this slice (surfaced on the dashboard, Rule N); recording each member's forecast vs the
resolved outcome to update reputations, and any decision use of the council probability, are the
queued follow-ups (Rule K). The LLM seam + `ExperienceMemory` are injected; the track-record
store is an optional injected collaborator, so tests wire fakes (Rule J).
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

# Each council member must return this shape — a probability + rationale.
COUNCIL_FORECAST_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "probability": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["probability", "rationale"],
    "additionalProperties": False,
}

_FORECAST_DEFINITION = (
    " Return `probability` in [0,1] — your forecast that the proposition is TRUE — and a short "
    "`rationale`. Reason ONLY from the given real memory facts; never invent numbers."
)


@dataclass(frozen=True)
class CouncilRole:
    """One forecasting lens: its name (for the reputation ledger) + its system instruction."""

    name: str
    system_instruction: str


MOMENTUM_ROLE = CouncilRole(
    "momentum",
    "You are a MOMENTUM forecaster who believes trends persist and breakouts follow through."
    + _FORECAST_DEFINITION,
)
MEAN_REVERSION_ROLE = CouncilRole(
    "mean_reversion",
    "You are a MEAN-REVERSION forecaster who believes extremes revert and most breakouts fail."
    + _FORECAST_DEFINITION,
)
REGIME_ROLE = CouncilRole(
    "regime_realist",
    "You are a REGIME realist who weighs which market regime dominates and how the mechanism "
    "calibrates within it." + _FORECAST_DEFINITION,
)
RISK_ROLE = CouncilRole(
    "risk_officer",
    "You are a RISK officer who is skeptical of over-confident theses and thin samples, and "
    "forecasts conservatively when the edge is unproven." + _FORECAST_DEFINITION,
)
COUNCIL_ROLES: tuple[CouncilRole, ...] = (
    MOMENTUM_ROLE, MEAN_REVERSION_ROLE, REGIME_ROLE, RISK_ROLE,
)

_TOP_MECHANISMS = 5
_RECENT_TRADES = 10
_COIN_FLIP_LOG_LOSS_BITS = 1.0  # a role with no track record is weighted as coin-flip skill
_WEIGHT_EPSILON = 1e-6


@dataclass(frozen=True)
class CouncilMemberForecast:
    """One member's probability forecast (clamped [0,1]) + why."""

    role: str
    probability: float
    rationale: str = ""


@dataclass(frozen=True)
class CouncilForecast:
    """The council's aggregate. `weighted_probability` uses track-record weights; `simple_mean_
    probability` is the un-weighted average (equal to weighted until reputations accrue).
    `generated` is False when the whole provider pool was exhausted (surfaced as blocked)."""

    proposition_label: str
    generated: bool
    served_by: str = ""
    member_forecasts: tuple[CouncilMemberForecast, ...] = ()
    weight_by_role: dict[str, float] = field(default_factory=dict)
    weighted_probability: float = 0.0
    simple_mean_probability: float = 0.0
    grounding_facts: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    @property
    def is_reputation_tilted(self) -> bool:
        """True once the weights are not all equal — i.e. track record has started to matter."""
        weights = list(self.weight_by_role.values())
        return bool(weights) and max(weights) - min(weights) > 1e-6


def track_record_weights(
    log_loss_by_role: dict[str, float | None], roles: list[str]
) -> dict[str, float]:
    """Weight ∝ 1/(log_loss+ε): a lower mean log-loss (sharper-and-right forecasts) earns more
    weight. A role with NO record (None) gets the coin-flip baseline, so unproven roles are
    neutral, proven-accurate roles gain weight, and proven-bad ones lose it. Normalised to 1."""
    raw: dict[str, float] = {}
    for role in roles:
        loss = log_loss_by_role.get(role)
        if loss is None:
            loss = _COIN_FLIP_LOG_LOSS_BITS
        raw[role] = 1.0 / (max(0.0, loss) + _WEIGHT_EPSILON)
    total = sum(raw.values())
    if total <= 0:
        equal = 1.0 / len(roles) if roles else 0.0
        return {role: equal for role in roles}
    return {role: weight / total for role, weight in raw.items()}


class PredictionCouncil:
    """Runs the council of role forecasts over a proposition and aggregates them with
    track-record weights."""

    def __init__(
        self,
        llm_client: StrategyLlmClient,
        experience_memory: ExperienceMemory,
        track_record_store=None,
    ) -> None:
        self._llm_client = llm_client
        self._experience_memory = experience_memory
        self._track_record_store = track_record_store

    def build_grounding_facts(self) -> list[str]:
        """Real memory context each member reasons from (over-confident mechanisms, per-regime
        calibration, recent record)."""
        facts: list[str] = [
            f"Total graded experiences in memory: {self._experience_memory.experiment_count()}."
        ]
        for row in self._experience_memory.calibration_board(
            minimum_experiments=1, limit=_TOP_MECHANISMS
        ):
            facts.append(
                f"Mechanism '{row.mechanism_name}' (n={row.experiment_count}): predicted "
                f"{_pct(row.predicted_win_rate)} vs actual {_pct(row.actual_win_rate)}, mean "
                f"return {_num(row.mean_return_fraction)}."
            )
        for cohort in self._experience_memory.calibration_by_market_regime(
            minimum_experiments=1
        ):
            facts.append(
                f"Regime '{cohort.market_regime}' (n={cohort.experiment_count}): hit-rate "
                f"{_pct(cohort.hit_rate)}."
            )
        recent = self._experience_memory.recent_closed_experiences(limit=_RECENT_TRADES)
        if recent:
            wins = sum(1 for r in recent if r.get("actual_outcome") == "win")
            facts.append(
                f"Most recent {len(recent)} closed trades: {wins} wins / {len(recent) - wins} losses."
            )
        return facts

    def build_member_request(
        self, role: CouncilRole, proposition_question: str, grounding_facts: list[str]
    ) -> StrategyLlmRequest:
        prompt = (
            f"PROPOSITION: {proposition_question}\n\n"
            "The bot's real calibration facts:\n"
            + "\n".join(f"- {fact}" for fact in grounding_facts)
            + "\n\nForecast the probability the proposition is TRUE, from your role's lens."
        )
        return StrategyLlmRequest(
            system_instruction=role.system_instruction,
            user_prompt=prompt,
            response_json_schema=COUNCIL_FORECAST_SCHEMA,
            purpose=f"prediction_council_{role.name}",
        )

    def forecast(
        self, proposition_label: str, proposition_question: str
    ) -> CouncilForecast:
        """Each role forecasts independently; aggregate with track-record weights. If any role's
        call exhausts the whole pool, return a non-generated forecast carrying the reason."""
        facts = self.build_grounding_facts()
        members: list[CouncilMemberForecast] = []
        served: list[str] = []
        for role in COUNCIL_ROLES:
            request = self.build_member_request(role, proposition_question, facts)
            try:
                response = self._llm_client.generate_structured(request)
            except LlmProviderError as exc:
                return CouncilForecast(
                    proposition_label=proposition_label,
                    generated=False,
                    grounding_facts=tuple(facts),
                    note=f"{role.name}: {exc}",
                )
            members.append(
                CouncilMemberForecast(
                    role=role.name,
                    probability=_clamp01(_as_float(response.parsed_output.get("probability"))),
                    rationale=str(response.parsed_output.get("rationale") or ""),
                )
            )
            served.append(f"{response.served_by_provider}:{response.served_by_model}")

        weights = track_record_weights(
            self._log_loss_by_role(), [m.role for m in members]
        )
        weighted = sum(weights.get(m.role, 0.0) * m.probability for m in members)
        return CouncilForecast(
            proposition_label=proposition_label,
            generated=True,
            served_by=", ".join(dict.fromkeys(served)),
            member_forecasts=tuple(members),
            weight_by_role=weights,
            weighted_probability=weighted,
            simple_mean_probability=mean(m.probability for m in members) if members else 0.0,
            grounding_facts=tuple(facts),
        )

    def _log_loss_by_role(self) -> dict[str, float | None]:
        if self._track_record_store is None:
            return {}
        try:
            return self._track_record_store.role_log_loss()
        except Exception:
            return {}


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
