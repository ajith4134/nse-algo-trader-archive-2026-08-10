"""Hermetic tests for Trunk III WILL — multi-objective arbitration + goal scheduler (research/154)."""

from nse_algo_trader.will.goal_priority_scheduler import schedule_goals
from nse_algo_trader.will.multi_objective_arbitration import (
    ObjectiveProfile,
    ObjectiveWeights,
    arbitrate,
    confidence_from_sample,
)


def _p(name, utility, ret, risk, n):
    return ObjectiveProfile(mechanism=name, utility=utility, mean_return=ret, neg_risk=-risk,
                            confidence=confidence_from_sample(n), sample_size=n)


def test_dominated_mechanism_excluded_from_pareto_front():
    good = _p("good", utility=0.5, ret=0.02, risk=0.01, n=50)
    dominated = _p("bad", utility=-0.5, ret=-0.02, risk=0.05, n=50)  # worse on every objective
    res = arbitrate([good, dominated])
    assert "good" in res.pareto_front
    assert "bad" not in res.pareto_front
    assert res.ranked[0].mechanism == "good"


def test_confidence_penalises_thin_high_return_sample():
    # A thin high-return mechanism should NOT beat a solid moderate one once confidence is weighted.
    thin_star = _p("thin", utility=0.10, ret=0.09, risk=0.02, n=6)
    solid = _p("solid", utility=0.20, ret=0.02, risk=0.01, n=100)
    res = arbitrate([thin_star, solid], ObjectiveWeights(w_confidence=1.5))
    assert res.ranked[0].mechanism == "solid"


def test_weights_change_the_winner():
    a = _p("high_return", utility=-0.1, ret=0.10, risk=0.08, n=40)
    b = _p("high_utility", utility=0.30, ret=0.01, risk=0.01, n=40)
    return_focused = arbitrate([a, b], ObjectiveWeights(w_utility=0.0, w_return=3.0, w_risk=0.0, w_confidence=0.0))
    utility_focused = arbitrate([a, b], ObjectiveWeights(w_utility=3.0, w_return=0.0, w_risk=0.0, w_confidence=0.0))
    assert return_focused.ranked[0].mechanism == "high_return"
    assert utility_focused.ranked[0].mechanism == "high_utility"


def test_confidence_from_sample_monotone_and_bounded():
    assert confidence_from_sample(0) == 0.0
    assert 0 < confidence_from_sample(10) < confidence_from_sample(40) <= 1.0
    assert confidence_from_sample(1000) == 1.0


def test_schedule_respects_budget_and_priority():
    profiles = [_p(f"m{i}", utility=1.0 - i * 0.2, ret=0.01, risk=0.01, n=50) for i in range(5)]
    res = arbitrate(profiles)
    sched = schedule_goals(res, max_concurrent=2)
    assert sched.active_count == 2 and sched.deferred_count == 3
    assert [g.priority_rank for g in sched.goals] == [1, 2, 3, 4, 5]
    assert sched.goals[0].is_active and not sched.goals[-1].is_active


def test_non_dominated_scheduled_before_dominated():
    nd = _p("nondom", utility=0.5, ret=0.03, risk=0.01, n=60)
    dom = _p("dom", utility=-0.5, ret=-0.03, risk=0.05, n=60)
    # Give the dominated one an artificially high score path is impossible (it's worse on all), so it
    # must still be scheduled after the non-dominated one.
    sched = schedule_goals(arbitrate([dom, nd]), max_concurrent=1)
    assert sched.goals[0].mechanism == "nondom" and sched.goals[0].is_active


def test_empty_is_safe():
    assert arbitrate([]).ranked == ()
    assert schedule_goals(arbitrate([])).goals == ()
