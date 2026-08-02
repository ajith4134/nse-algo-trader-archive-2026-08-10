"""Expected-Free-Energy action scorer (research/166/167 §3; Trunk IX active inference).

Active inference selects actions by minimising expected free energy `G(a) = pragmatic + epistemic`:
  • PRAGMATIC (extrinsic) value = −expected reward (prefer high-reward actions) — here the planner's
    Q-value stands in for the negative pragmatic term.
  • EPISTEMIC (intrinsic) value = expected information gain / uncertainty reduction.
Canonical agents let the epistemic term DRIVE exploratory action; for a trading bot that would risk real
capital to reduce model uncertainty, so — an explicit, stated divergence (research/167 §3) — we route the
epistemic term ONLY into the confidence gate, never into a capital-risking action preference. The action
softmax is therefore over the pragmatic (reward/Q) term alone: `P(a) = softmax(γ·Q(s,a))`. PURE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nse_algo_trader.predictive_core.finite_horizon_value_iteration_planner import StatePlan
from nse_algo_trader.predictive_core.generative_market_transition_model import GenerativeMarketModel
from nse_algo_trader.predictive_core.market_state_discretizer import ACTIONS

DEFAULT_PRECISION_GAMMA = 4.0   # softmax inverse-temperature over Q-values (higher = sharper preference)


@dataclass(frozen=True)
class ActionScore:
    """One action's EFE-decomposed score in a state."""

    action: str
    q_value: float                 # planner Q (the negative-pragmatic term)
    select_probability: float      # softmax(γ·Q) — the pragmatic action preference
    epistemic_value: float         # expected info gain (reward-estimate uncertainty) — feeds the GATE only


def _epistemic_value(model: GenerativeMarketModel, state_index: int, action: str) -> float:
    """Info-gain proxy = how UNCERTAIN the reward estimate still is (1 − precision). High for thin cells —
    i.e. how much a fresh observation here would teach the model. Feeds the confidence gate only."""
    return 1.0 - model.reward_confidence(state_index, action)


def score_actions(plan: StatePlan, model: GenerativeMarketModel,
                  precision_gamma: float = DEFAULT_PRECISION_GAMMA) -> dict[str, ActionScore]:
    """EFE-shaped scores for every action in the planned state: softmax over Q (pragmatic) + the epistemic
    (uncertainty) term carried alongside for the gate."""
    q_values = [plan.action_q_values[a] for a in ACTIONS]
    peak = max(q_values)
    exps = {a: math.exp(precision_gamma * (plan.action_q_values[a] - peak)) for a in ACTIONS}
    total = sum(exps.values()) or 1.0
    return {
        a: ActionScore(
            action=a, q_value=plan.action_q_values[a], select_probability=exps[a] / total,
            epistemic_value=_epistemic_value(model, plan.state_index, a))
        for a in ACTIONS
    }
