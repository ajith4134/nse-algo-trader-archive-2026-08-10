"""Property-based invariant tests (hypothesis) for the engines (research/159, item c).

Example tests check known cases; these check INVARIANTS that must hold for ALL inputs — the edge
coverage the evidence (research/158) says finds bugs example tests miss. Covers the win-probability
sizing math, the axiology explicit utility, and the WILL arbitration.
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from nse_algo_trader.axiology.explicit_utility_function import ValueWeights, evaluate_utility
from nse_algo_trader.predictive_core.win_probability_engine import (
    edge_size_multiplier,
    kelly_fraction,
)
from nse_algo_trader.will.multi_objective_arbitration import (
    ObjectiveProfile,
    arbitrate,
    confidence_from_sample,
)

_prob = st.floats(min_value=0.0, max_value=1.0)
_reward_risk = st.floats(min_value=0.1, max_value=10.0)
_returns = st.lists(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False), min_size=1, max_size=200)


# ---- win-probability sizing -----------------------------------------------------------------------
@given(p=_prob, b=_reward_risk)
def test_edge_multiplier_identity_until_earned(p, b):
    assert edge_size_multiplier(p, b, is_earned=False) == 1.0   # unvalidated model NEVER moves a trade


@given(p=_prob, b=_reward_risk)
def test_edge_multiplier_bounded_when_earned(p, b):
    m = edge_size_multiplier(p, b, is_earned=True)
    assert 0.0 <= m <= 1.0                                       # size-down-only; never exceeds base


@given(p_lo=_prob, p_hi=_prob, b=_reward_risk)
def test_edge_multiplier_monotone_in_win_prob(p_lo, p_hi, b):
    lo, hi = sorted((p_lo, p_hi))
    assert edge_size_multiplier(lo, b, is_earned=True) <= edge_size_multiplier(hi, b, is_earned=True) + 1e-9


@given(p=_prob, b=_reward_risk)
def test_kelly_fraction_never_exceeds_one_and_finite(p, b):
    f = kelly_fraction(p, b)
    assert math.isfinite(f) and f <= 1.0


# ---- axiology explicit utility --------------------------------------------------------------------
@given(returns=_returns)
def test_utility_decomposition_sums_to_total(returns):
    u = evaluate_utility(returns, ValueWeights())
    assert abs((u.return_term + u.risk_term + u.drawdown_term + u.tail_term) - u.utility) < 1e-6


@given(returns=_returns)
def test_utility_risk_measures_nonnegative(returns):
    u = evaluate_utility(returns)
    assert u.volatility >= 0.0 and u.max_drawdown >= 0.0 and u.tail_loss_cvar5 >= -1e-9


# ---- WILL arbitration -----------------------------------------------------------------------------
@st.composite
def _profiles(draw):
    n = draw(st.integers(min_value=1, max_value=6))
    out = []
    for i in range(n):
        util = draw(st.floats(min_value=-5.0, max_value=1.0, allow_nan=False))
        ret = draw(st.floats(min_value=-0.1, max_value=0.1, allow_nan=False))
        risk = draw(st.floats(min_value=0.0, max_value=0.2, allow_nan=False))
        size = draw(st.integers(min_value=1, max_value=300))
        out.append(ObjectiveProfile(f"m{i}", util, ret, -risk, confidence_from_sample(size), size))
    return out


@settings(max_examples=60)
@given(profiles=_profiles())
def test_arbitration_winner_has_max_score_and_pareto_subset(profiles):
    result = arbitrate(profiles)
    assert len(result.ranked) == len(profiles)
    scores = [m.arbitration_score for m in result.ranked]
    assert scores == sorted(scores, reverse=True)                # ranked best-first
    assert all(math.isfinite(s) for s in scores)
    mechanisms = {m.mechanism for m in result.ranked}
    assert set(result.pareto_front) <= mechanisms                # front is a subset of the candidates
