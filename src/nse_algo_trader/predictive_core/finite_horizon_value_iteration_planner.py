"""Finite-horizon value-iteration planner (research/166/167 §3; Trunk IX). The model-based lookahead.

Given the generative model (transition P̂(s'|s) + reward R̂(s,a)), roll the model FORWARD over a short
horizon by exact dynamic programming (Bellman backup):
    Q_h(s,a) = R̂(s,a) + γ · Σ_s' P̂(s'|s) · V_{h+1}(s'),   V_h(s) = max_a Q_h(s,a),   V_H(s)=0.
Transitions are action-independent market evolution, so the future term is shared across actions in a
state — the action ranking is driven by R̂(s,a), while V(s) still credits being in a state that EVOLVES
into high-value states (so entering when a favourable regime is likely to persist is valued). |S|=9,
|A|=3, H≈5 → microseconds. PURE.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.predictive_core.generative_market_transition_model import GenerativeMarketModel
from nse_algo_trader.predictive_core.market_state_discretizer import ACTIONS, STATE_COUNT

DEFAULT_HORIZON = 5
DEFAULT_DISCOUNT = 0.95


@dataclass(frozen=True)
class StatePlan:
    """The planner's verdict for one state: per-action Q-values + the greedy best action and state value."""

    state_index: int
    action_q_values: dict[str, float]
    best_action: str
    state_value: float

    def advantage_of(self, action: str) -> float:
        """Q(s,action) − Q(s,'hold') — how much better this action is than doing nothing (the entry edge)."""
        return self.action_q_values.get(action, 0.0) - self.action_q_values.get("hold", 0.0)


def plan_finite_horizon(model: GenerativeMarketModel, horizon: int = DEFAULT_HORIZON,
                        discount: float = DEFAULT_DISCOUNT) -> dict[int, StatePlan]:
    """Exact backward-induction value iteration → a StatePlan for every state (Q-values + best action)."""
    transitions = [model.transition_distribution(s) for s in range(STATE_COUNT)]
    immediate_reward = {(s, a): model.expected_reward(s, a) for s in range(STATE_COUNT) for a in ACTIONS}

    values = [0.0] * STATE_COUNT                       # V_H(s) = 0
    last_q: dict[int, dict[str, float]] = {}
    for _ in range(horizon):                           # backward induction, H steps
        next_values = [0.0] * STATE_COUNT
        step_q: dict[int, dict[str, float]] = {}
        for s in range(STATE_COUNT):
            future = discount * sum(transitions[s][s_next] * values[s_next] for s_next in range(STATE_COUNT))
            q = {a: immediate_reward[(s, a)] + future for a in ACTIONS}
            step_q[s] = q
            next_values[s] = max(q.values())
        values = next_values
        last_q = step_q

    plans: dict[int, StatePlan] = {}
    for s in range(STATE_COUNT):
        q = last_q[s]
        best_action = max(q, key=lambda a: q[a])
        plans[s] = StatePlan(state_index=s, action_q_values=q, best_action=best_action, state_value=values[s])
    return plans
