"""Generative market-state transition + reward model (research/166/167 §3; Trunk IX).

The world-model's carried STATE: count tensors accumulated from real bar observations, turned into
smoothed generative distributions:
  • TRANSITION `P̂(s'|s) = (N(s,s')+α)/(N(s)+αK)` — Dirichlet/Jeffreys (α=0.5), with Katz-style backoff
    toward the global next-state marginal for thin source states (the honest answer to sparse data).
  • REWARD `R̂(s,a)` — empirical-Bayes shrinkage of the per-(s,a) mean reward toward the global mean,
    precision-weighted by the cell's visit count (thin cells trust the prior; well-sampled cells trust
    the data). This shrinkage IS a precision-weighting (Trunk IX sibling branch).
Transitions are action-INDEPENDENT market evolution (research/167 §3). Counts persist via the store,
so the model LEARNS across sessions rather than recomputing. PURE apart from accepting/emitting counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.predictive_core.market_state_discretizer import (
    ACTIONS,
    STATE_COUNT,
    StateTransitionObservation,
)

DIRICHLET_ALPHA = 0.5          # Jeffreys prior pseudo-count for transition smoothing
REWARD_PRIOR_STRENGTH = 20.0   # empirical-Bayes prior weight (in "pseudo-observations") for reward shrinkage


@dataclass
class WorldModelCounts:
    """Carried state: raw counts accumulated from observations (the thing that is persisted)."""

    # transition_counts[s][s'] = N(s → s'); reward_sums[s][a] = Σ reward; reward_counts[s][a] = N
    transition_counts: list[list[float]] = field(
        default_factory=lambda: [[0.0] * STATE_COUNT for _ in range(STATE_COUNT)])
    reward_sums: list[dict[str, float]] = field(
        default_factory=lambda: [dict.fromkeys(ACTIONS, 0.0) for _ in range(STATE_COUNT)])
    reward_counts: list[dict[str, float]] = field(
        default_factory=lambda: [dict.fromkeys(ACTIONS, 0.0) for _ in range(STATE_COUNT)])
    total_observations: int = 0

    def state_visit_count(self, state_index: int) -> float:
        return sum(self.transition_counts[state_index])


def accumulate_observations(counts: WorldModelCounts,
                            observations: list[StateTransitionObservation]) -> WorldModelCounts:
    """Fold a batch of observations into the counts (in place) and return them."""
    for obs in observations:
        counts.transition_counts[obs.state_index][obs.next_state_index] += 1.0
        for action, reward in obs.action_rewards.items():
            counts.reward_sums[obs.state_index][action] += reward
            counts.reward_counts[obs.state_index][action] += 1.0
        counts.total_observations += 1
    return counts


class GenerativeMarketModel:
    """Smoothed generative model derived from `WorldModelCounts` — the transition + reward the planner uses."""

    def __init__(self, counts: WorldModelCounts, dirichlet_alpha: float = DIRICHLET_ALPHA,
                 reward_prior_strength: float = REWARD_PRIOR_STRENGTH):
        self._counts = counts
        self._alpha = dirichlet_alpha
        self._reward_prior_strength = reward_prior_strength
        self._global_next_state_marginal = self._compute_global_marginal()
        self._global_reward_mean = self._compute_global_reward_mean()

    def _compute_global_marginal(self) -> list[float]:
        column_totals = [0.0] * STATE_COUNT
        grand_total = 0.0
        for s in range(STATE_COUNT):
            for s_next in range(STATE_COUNT):
                column_totals[s_next] += self._counts.transition_counts[s][s_next]
                grand_total += self._counts.transition_counts[s][s_next]
        if grand_total <= 0:
            return [1.0 / STATE_COUNT] * STATE_COUNT
        return [c / grand_total for c in column_totals]

    def _compute_global_reward_mean(self) -> float:
        total_sum = sum(self._counts.reward_sums[s][a] for s in range(STATE_COUNT) for a in ACTIONS)
        total_n = sum(self._counts.reward_counts[s][a] for s in range(STATE_COUNT) for a in ACTIONS)
        return total_sum / total_n if total_n > 0 else 0.0

    def transition_distribution(self, state_index: int) -> list[float]:
        """P̂(s'|s): Dirichlet-smoothed, Katz-backing-off to the global marginal when the source state
        is thinly observed (few visits → lean on the prior/marginal; many → trust the data)."""
        row = self._counts.transition_counts[state_index]
        n_state = sum(row)
        smoothed = [(row[s_next] + self._alpha) / (n_state + self._alpha * STATE_COUNT)
                    for s_next in range(STATE_COUNT)]
        # Katz backoff weight toward the global marginal — dominant when n_state is small.
        backoff = self._alpha * STATE_COUNT / (n_state + self._alpha * STATE_COUNT)
        blended = [(1.0 - backoff) * smoothed[s_next] + backoff * self._global_next_state_marginal[s_next]
                   for s_next in range(STATE_COUNT)]
        total = sum(blended) or 1.0
        return [p / total for p in blended]   # guaranteed to sum to 1

    def expected_reward(self, state_index: int, action: str) -> float:
        """R̂(s,a): empirical-Bayes shrinkage of the sample mean toward the global mean, precision-weighted
        by the visit count — thin cells ≈ the global prior; well-sampled cells ≈ their own mean."""
        n = self._counts.reward_counts[state_index][action]
        sample_mean = (self._counts.reward_sums[state_index][action] / n) if n > 0 else self._global_reward_mean
        weight = n / (n + self._reward_prior_strength)
        return weight * sample_mean + (1.0 - weight) * self._global_reward_mean

    def reward_confidence(self, state_index: int, action: str) -> float:
        """Precision of the reward estimate ∈ [0,1): n/(n+prior) — how much the data (vs prior) drives R̂."""
        n = self._counts.reward_counts[state_index][action]
        return n / (n + self._reward_prior_strength)

    def state_visit_count(self, state_index: int) -> float:
        return self._counts.state_visit_count(state_index)

    @property
    def total_observations(self) -> int:
        return self._counts.total_observations
