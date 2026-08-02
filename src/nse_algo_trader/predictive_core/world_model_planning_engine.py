"""World-Model Planning ENGINE — orchestrator (research/166/167; Trunk IX PREDICTIVE-CORE).

Ties the layers into a decision: real bar close-series → discretized (state, next-state, per-action reward)
observations → accumulated counts (carried state) → smoothed generative model → finite-horizon value
iteration → EFE-shaped action scores → a CONFIDENCE-GATED entry verdict. The verdict CHANGES behaviour: a
size-DOWN-only multiplier / veto on a proposed entry, but ONLY when the model is trustworthy for the
current state (κ = visit-fraction, discounted by the ensemble's disagreement, hard-zeroed on a
surprise-monitor Page-Hinkley spike). Below the trust threshold it ABSTAINS (identity) — an un-trusted
world-model never moves a trade (Rule P.4 / the safe rollout). Counts persist via the transition store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.predictive_core.expected_free_energy_action_scorer import score_actions
from nse_algo_trader.predictive_core.finite_horizon_value_iteration_planner import (
    StatePlan,
    plan_finite_horizon,
)
from nse_algo_trader.predictive_core.generative_market_transition_model import (
    GenerativeMarketModel,
    WorldModelCounts,
    accumulate_observations,
)
from nse_algo_trader.predictive_core.market_state_discretizer import (
    MarketState,
    _bar_returns,
    _stddev,
    classify_state,
    compute_volatility_terciles,
    discretize_bar_closes,
)
from nse_algo_trader.predictive_core.world_model_transition_store import WorldModelTransitionStore

N_VISITS_FOR_FULL_CONFIDENCE = 50.0   # visits to a state at which κ (data trust) saturates to 1.0
CONFIDENCE_TAU = 0.30                  # below this trust the engine ABSTAINS (never acts on a thin model)
MIN_SIZE_MULTIPLIER = 0.30             # floor of the size-down lever
VETO_ADVANTAGE = -0.01                 # confident advantage below this (−1% edge vs hold) → veto the entry
_FEATURE_WINDOW = 20


@dataclass(frozen=True)
class WorldModelPlanVerdict:
    """The decision-grade output the entry path consumes."""

    current_state_label: str
    proposed_action: str
    action_q_values: dict[str, float]
    advantage_vs_hold: float           # Q(enter_dir) − Q(hold); >0 = model favours the entry
    confidence: float                  # κ ∈ [0,1] — data trust for the current state
    is_confident: bool                 # κ ≥ τ
    abstains: bool                     # not confident → identity, no veto
    vetoes: bool                       # confident AND the model strongly disfavours the entry
    size_multiplier: float             # ∈ [floor, 1.0] — the size-DOWN-only lever (1.0 = abstain/confirm)
    total_observations: int
    note: str = ""
    diagnostics: dict = field(default_factory=dict)


class WorldModelPlanningEngine:
    """Learns the generative market model from bars + serves confidence-gated planning verdicts."""

    def __init__(self, store: WorldModelTransitionStore | None = None,
                 horizon: int = 5, discount: float = 0.95):
        self._store = store or WorldModelTransitionStore()
        self._counts: WorldModelCounts = self._store.load()
        self._horizon = horizon
        self._discount = discount
        self._vol_cuts: tuple[float, float] | None = None

    # -- learning ----------------------------------------------------------------------------------
    def ingest_close_series(self, close_series_by_symbol: list[list[float]], persist: bool = True) -> int:
        """Fold many symbols' real close-series into the carried counts. Returns #observations added.
        A shared volatility calibration (terciles over the pooled series) keeps the vol buckets stable."""
        pooled = [c for series in close_series_by_symbol for c in series]
        if len(pooled) >= _FEATURE_WINDOW + 2:
            self._vol_cuts = compute_volatility_terciles(pooled, _FEATURE_WINDOW)
        added = 0
        for closes in close_series_by_symbol:
            observations = discretize_bar_closes(closes, window=_FEATURE_WINDOW, vol_cuts=self._vol_cuts)
            accumulate_observations(self._counts, observations)
            added += len(observations)
        if persist:
            import contextlib
            with contextlib.suppress(Exception):
                self._store.save(self._counts)  # persistence failure must not break the loop (Rule O.3)
        return added

    def _model(self) -> GenerativeMarketModel:
        return GenerativeMarketModel(self._counts)

    def plan_all_states(self) -> dict[int, StatePlan]:
        return plan_finite_horizon(self._model(), self._horizon, self._discount)

    @property
    def total_observations(self) -> int:
        return self._counts.total_observations

    # -- current market state ----------------------------------------------------------------------
    def current_state(self, recent_closes: list[float]) -> MarketState | None:
        """Discretize the latest window of closes into a market state (None if too few bars)."""
        if len(recent_closes) < _FEATURE_WINDOW + 1:
            return None
        cuts = self._vol_cuts or compute_volatility_terciles(recent_closes, _FEATURE_WINDOW)
        window_returns = _bar_returns(recent_closes[-_FEATURE_WINDOW - 1:])
        windowed_return = ((recent_closes[-1] - recent_closes[-_FEATURE_WINDOW - 1])
                           / recent_closes[-_FEATURE_WINDOW - 1]) if recent_closes[-_FEATURE_WINDOW - 1] > 0 else 0.0
        return classify_state(windowed_return, _stddev(window_returns), cuts[0], cuts[1])

    # -- the decision-grade verdict ----------------------------------------------------------------
    def entry_verdict(self, recent_closes: list[float], direction: str,
                      ensemble_disagreement: float = 0.0, surprise_spike: bool = False,
                      ) -> WorldModelPlanVerdict:
        """Confidence-gated planning verdict for a proposed entry (`direction` = 'long' | 'short')."""
        action = "enter_long" if str(direction).lower().startswith("long") else "enter_short"
        state = self.current_state(recent_closes)
        if state is None:
            return self._abstain_verdict("?", action, "too few bars to classify the market state")

        model = self._model()
        plan = self.plan_all_states()[state.index]
        advantage = plan.advantage_of(action)
        scores = score_actions(plan, model)

        # confidence κ: data trust for THIS state, discounted by ensemble disagreement, killed by a surprise spike
        visit_trust = min(1.0, model.state_visit_count(state.index) / N_VISITS_FOR_FULL_CONFIDENCE)
        confidence = 0.0 if surprise_spike else visit_trust * (1.0 - max(0.0, min(1.0, ensemble_disagreement)))
        is_confident = confidence >= CONFIDENCE_TAU

        diagnostics = {
            "state_visits": model.state_visit_count(state.index),
            "epistemic_value": scores[action].epistemic_value,
            "select_probability": scores[action].select_probability,
            "best_action": plan.best_action,
            "surprise_spike": surprise_spike,
            "ensemble_disagreement": ensemble_disagreement,
        }

        if not is_confident:
            return WorldModelPlanVerdict(
                current_state_label=state.label, proposed_action=action,
                action_q_values=plan.action_q_values, advantage_vs_hold=advantage, confidence=confidence,
                is_confident=False, abstains=True, vetoes=False, size_multiplier=1.0,
                total_observations=self._counts.total_observations,
                note=f"abstain — world-model not yet trustworthy for {state.label} (κ={confidence:.2f})",
                diagnostics=diagnostics)

        if advantage <= VETO_ADVANTAGE:
            return WorldModelPlanVerdict(
                current_state_label=state.label, proposed_action=action,
                action_q_values=plan.action_q_values, advantage_vs_hold=advantage, confidence=confidence,
                is_confident=True, abstains=False, vetoes=True, size_multiplier=0.0,
                total_observations=self._counts.total_observations,
                note=f"VETO — in {state.label} the model expects {action} to underperform holding "
                     f"(adv {advantage:+.4f})", diagnostics=diagnostics)

        # confident: scale size by how favourable the entry is vs hold (size-DOWN-only, floored)
        if advantage >= 0.0:
            multiplier = 1.0
        else:  # between VETO_ADVANTAGE and 0 → size down proportionally toward the floor
            multiplier = max(MIN_SIZE_MULTIPLIER, 1.0 + advantage / abs(VETO_ADVANTAGE) * (1.0 - MIN_SIZE_MULTIPLIER))
        return WorldModelPlanVerdict(
            current_state_label=state.label, proposed_action=action,
            action_q_values=plan.action_q_values, advantage_vs_hold=advantage, confidence=confidence,
            is_confident=True, abstains=False, vetoes=False, size_multiplier=multiplier,
            total_observations=self._counts.total_observations,
            note=f"{state.label}: {action} advantage {advantage:+.4f} vs hold (κ={confidence:.2f})",
            diagnostics=diagnostics)

    @staticmethod
    def _abstain_verdict(state_label, action, why) -> WorldModelPlanVerdict:
        return WorldModelPlanVerdict(
            current_state_label=state_label, proposed_action=action, action_q_values={}, advantage_vs_hold=0.0,
            confidence=0.0, is_confident=False, abstains=True, vetoes=False, size_multiplier=1.0,
            total_observations=0, note=why)
