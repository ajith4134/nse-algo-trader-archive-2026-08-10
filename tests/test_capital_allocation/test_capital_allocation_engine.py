"""Engine-level tests for the Capital-Allocation Optimizer (research/163 §5 acceptance criteria).

Property/invariant (constraints always respected, CVaR ≤ equal-weight, identity-until-earned), mode
selection (CVaR vs MV fallback), cardinality, turnover, and adversarial/failure paths — all with a
hermetic in-memory fake experience source (Rule J), never a real store.
"""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate
from nse_algo_trader.capital_allocation.allocation_constraint_builder import AllocationConstraintConfig
from nse_algo_trader.capital_allocation.capital_allocation_engine_store import (
    CapitalAllocationEngineStore,
)
from nse_algo_trader.capital_allocation.capital_allocation_optimizer import (
    CapitalAllocationConfig,
    CapitalAllocationOptimizer,
    MODE_MEAN_CVAR,
    MODE_MEAN_VARIANCE,
    empirical_cvar,
)

warnings.filterwarnings("ignore")


class FakeExperienceSource:
    """Hermetic in-memory fake (Rule J) — the SAME `recent_closed_experiences` contract the real
    ExperienceMemory exposes; lives only under tests/, never wired into prod."""

    def __init__(self, records):
        self._records = records

    def recent_closed_experiences(self, limit=5000):
        return list(self._records)[:limit]


def _candidate(cid, segment, mu, *, direction="long", price=100.0, lot=1, scen=()):
    return AllocationCandidate(
        candidate_id=cid, segment=segment, underlying=f"U_{cid}", direction=direction,
        instrument_kind=segment, expected_edge_mu=mu, per_unit_risk=5.0, entry_price=price,
        lot_or_tick_size=lot, est_margin_per_unit=price * lot * 0.2, pnl_scenario_returns=scen,
    )


def _fresh_optimizer(config, source=None):
    store = CapitalAllocationEngineStore(Path(tempfile.mkdtemp()) / "state.json")
    return CapitalAllocationOptimizer(experience_source=source, config=config, store=store)


def _rich_scenarios(seed, mean, std, n=300):
    return tuple(np.random.default_rng(seed).normal(mean, std, n))


def _rich_candidate_set():
    return [
        _candidate("c1", "index_option", 0.06, price=100.0, lot=50, scen=_rich_scenarios(1, 0.03, 0.05)),
        _candidate("c2", "stock_option", 0.04, price=200.0, lot=25, scen=_rich_scenarios(2, 0.02, 0.08)),
        _candidate("c3", "cash_equity", 0.02, price=500.0, lot=1, scen=_rich_scenarios(3, 0.0, 0.03)),
    ]


# -- mode selection -------------------------------------------------------------------------------

def test_thin_scenarios_fall_back_to_mean_variance():
    cfg = CapitalAllocationConfig()
    result = _fresh_optimizer(cfg).allocate([_candidate("c1", "cash_equity", 0.05)], 100_000)
    assert result.objective_mode_used == MODE_MEAN_VARIANCE
    assert result.fell_back is True


def test_rich_scenarios_select_mean_cvar():
    cfg = CapitalAllocationConfig()
    result = _fresh_optimizer(cfg).allocate(_rich_candidate_set(), 1_000_000)
    assert result.objective_mode_used == MODE_MEAN_CVAR
    assert result.fell_back is False
    assert result.solver_status in ("optimal", "optimal_inaccurate")


# -- the acceptance bar: CVaR reduction vs equal-weight (research/163 §5 criterion 7) --------------

def test_cvar_allocation_beats_equal_weight_tail_risk():
    cfg = CapitalAllocationConfig(
        constraint_config=AllocationConstraintConfig(max_position_weight=0.6))
    result = _fresh_optimizer(cfg).allocate(_rich_candidate_set(), 1_000_000)
    assert result.portfolio_cvar <= result.diagnostics["equal_weight_cvar"] + 1e-9
    assert result.diagnostics["cvar_reduction_vs_equal"] >= 0.0


# -- constraint invariants (property-based) -------------------------------------------------------

@settings(max_examples=25, deadline=None)
@given(
    mus=st.lists(st.floats(-0.05, 0.1), min_size=2, max_size=6),
    cap=st.floats(0.2, 0.6),
)
def test_constraints_always_respected(mus, cap):
    cands = [_candidate(f"c{i}", "cash_equity", mu, scen=_rich_scenarios(i, mu, 0.05))
             for i, mu in enumerate(mus)]
    cfg = CapitalAllocationConfig(
        constraint_config=AllocationConstraintConfig(max_position_weight=cap, cardinality_k=None))
    result = _fresh_optimizer(cfg).allocate(cands, 1_000_000)
    weights = np.array(list(result.weights.values()))
    assert (weights >= -1e-6).all()                 # long-only
    assert weights.sum() <= 1.0 + 1e-6              # budget
    assert weights.max() <= cap + 1e-6              # per-position cap
    assert np.isfinite(result.portfolio_cvar)       # CVaR is finite (may be <0 if even the tail profits)
    assert result.portfolio_vol >= -1e-9            # vol is a genuine non-negative magnitude


def test_per_segment_cap_respected():
    cands = [
        _candidate("i1", "index_option", 0.08, scen=_rich_scenarios(1, 0.05, 0.05)),
        _candidate("i2", "index_option", 0.07, scen=_rich_scenarios(2, 0.04, 0.05)),
        _candidate("c1", "cash_equity", 0.02, scen=_rich_scenarios(3, 0.0, 0.03)),
    ]
    cfg = CapitalAllocationConfig(constraint_config=AllocationConstraintConfig(
        max_position_weight=0.9, max_segment_weight={"index_option": 0.3}))
    result = _fresh_optimizer(cfg).allocate(cands, 1_000_000)
    index_weight = result.weights["i1"] + result.weights["i2"]
    assert index_weight <= 0.3 + 1e-6


# -- cardinality ----------------------------------------------------------------------------------

def test_cardinality_caps_active_positions():
    cands = [_candidate(f"c{i}", "cash_equity", 0.05 - 0.005 * i, scen=_rich_scenarios(i, 0.03, 0.05))
             for i in range(6)]
    cfg = CapitalAllocationConfig(constraint_config=AllocationConstraintConfig(
        max_position_weight=0.5, cardinality_k=2))
    result = _fresh_optimizer(cfg).allocate(cands, 1_000_000)
    assert result.active_count <= 2


# -- turnover -------------------------------------------------------------------------------------

def test_turnover_penalty_reduces_churn():
    cands = _rich_candidate_set()
    # First allocation establishes w_prev; a high-γ optimizer on the same store should churn less.
    high_gamma = CapitalAllocationConfig(constraint_config=AllocationConstraintConfig(
        max_position_weight=0.6, turnover_gamma=5.0))
    opt = _fresh_optimizer(high_gamma)
    first = opt.allocate(cands, 1_000_000)
    second = opt.allocate(cands, 1_000_000)   # same store → w_prev is `first`
    assert second.turnover <= first.turnover + 1e-6


# -- identity until earned (Rule P.4) -------------------------------------------------------------

def test_engine_is_advisory_until_earned():
    # one session-day of history → below the earn threshold → is_earned False → identity multiplier
    records = [{"realized_return_fraction": 0.03, "instrument_kind": "cash_equity", "direction": "long",
                "strategy_tag": "orb", "session_date": "2026-01-01"} for _ in range(400)]
    cfg = CapitalAllocationConfig(min_session_dates_to_earn=10)
    result = _fresh_optimizer(cfg, source=FakeExperienceSource(records)).allocate(
        [_candidate("c1", "cash_equity", 0.05, scen=tuple(np.full(300, 0.03)))], 100_000)
    assert result.is_earned is False
    assert result.acted is False
    assert result.size_multiplier_for("c1", 0.25) == 1.0


def test_engine_earns_after_enough_session_dates():
    records = [{"realized_return_fraction": 0.02 * ((i % 3) - 1), "instrument_kind": "cash_equity",
                "direction": "long", "strategy_tag": "orb", "session_date": f"2026-01-{d:02d}"}
               for d in range(1, 16) for i in range(30)]
    cfg = CapitalAllocationConfig(min_session_dates_to_earn=10)
    result = _fresh_optimizer(cfg, source=FakeExperienceSource(records)).allocate(
        _rich_candidate_set(), 1_000_000)
    assert result.diagnostics["distinct_session_dates"] >= 10
    assert result.is_earned is True


# -- adversarial / failure paths ------------------------------------------------------------------

def test_empty_candidate_set_is_trivial():
    result = _fresh_optimizer(CapitalAllocationConfig()).allocate([], 100_000)
    assert result.active_count == 0
    assert result.solver_status == "trivial"


def test_all_negative_edge_holds_cash():
    cands = [_candidate(f"c{i}", "cash_equity", -0.05, scen=_rich_scenarios(i, -0.05, 0.05))
             for i in range(3)]
    result = _fresh_optimizer(CapitalAllocationConfig()).allocate(cands, 1_000_000)
    # no positive edge + risk penalty → the optimizer should allocate ~nothing (hold cash)
    assert sum(result.weights.values()) <= 0.05


def test_zero_capital_deploys_nothing():
    result = _fresh_optimizer(CapitalAllocationConfig()).allocate(
        _rich_candidate_set(), account_capital=0.0)
    assert all(lot == 0 for lot in result.lots.values())


def test_state_persists_across_optimizer_instances():
    store_path = Path(tempfile.mkdtemp()) / "shared.json"
    records = [{"realized_return_fraction": 0.01, "instrument_kind": "cash_equity", "direction": "long",
                "strategy_tag": "orb", "session_date": f"2026-02-{d:02d}"}
               for d in range(1, 13) for _ in range(20)]
    cfg = CapitalAllocationConfig(min_session_dates_to_earn=10)
    src = FakeExperienceSource(records)
    opt1 = CapitalAllocationOptimizer(src, cfg, CapitalAllocationEngineStore(store_path))
    opt1.allocate(_rich_candidate_set(), 1_000_000)
    # a fresh instance reads the persisted earned-state
    opt2 = CapitalAllocationOptimizer(src, cfg, CapitalAllocationEngineStore(store_path))
    assert opt2.is_performance_earned is True


# -- empirical CVaR helper ------------------------------------------------------------------------

def test_empirical_cvar_is_positive_tail_loss():
    returns = np.array([0.1, 0.05, 0.0, -0.05, -0.2])  # worst 5% ≈ -0.2 → CVaR ≈ 0.2
    cvar = empirical_cvar(returns, alpha=0.8)
    assert cvar > 0.0
    assert cvar >= -returns.min() - 1e-9 or cvar == pytest.approx(0.2, abs=0.05)
