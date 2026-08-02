"""Unit tests for the capital-allocation engine's component layers (research/163).

Covers the contracts, the scenario-matrix data pipeline, the Ledoit-Wolf covariance estimator, and the
four objective programs in isolation — before the orchestrator integration tests.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from nse_algo_trader.capital_allocation.allocation_candidate import (
    AllocationCandidate,
    AllocationResult,
)
from nse_algo_trader.capital_allocation.experience_scenario_matrix_builder import (
    build_scenario_matrix,
)
from nse_algo_trader.capital_allocation.ledoit_wolf_covariance_estimator import (
    shrunk_covariance_matrix,
)
from nse_algo_trader.capital_allocation.allocation_objective_programs import (
    solve_risk_parity_weights,
)

warnings.filterwarnings("ignore")


def _candidate(cid="c1", segment="cash_equity", direction="long", mu=0.02, scen=()):
    return AllocationCandidate(
        candidate_id=cid, segment=segment, underlying="RELIANCE", direction=direction,
        instrument_kind=segment, expected_edge_mu=mu, per_unit_risk=5.0, entry_price=100.0,
        lot_or_tick_size=1, est_margin_per_unit=25.0, pnl_scenario_returns=scen,
    )


# -- contracts ------------------------------------------------------------------------------------

def test_candidate_rejects_unknown_segment():
    with pytest.raises(ValueError):
        _candidate(segment="futures")


def test_candidate_rejects_negative_risk():
    with pytest.raises(ValueError):
        AllocationCandidate("c", "cash_equity", "X", "long", "cash_equity", 0.0, -1.0, 10.0, 1, 2.0)


def test_direction_sign():
    assert _candidate(direction="long").direction_sign == 1
    assert _candidate(direction="short").direction_sign == -1


def test_result_size_multiplier_identity_when_not_earned():
    result = AllocationResult(weights={"c1": 0.5}, capital={}, lots={}, objective_mode_used="mean_cvar",
                              solver_status="optimal", portfolio_cvar=0.1, portfolio_vol=0.1,
                              active_count=1, turnover=0.0, scenario_count=5, fell_back=False,
                              is_earned=False, diagnostics={})
    # un-earned → identity, never moves size
    assert result.size_multiplier_for("c1", naive_equal_weight=0.25) == 1.0
    assert result.acted is False


def test_result_size_multiplier_scales_when_earned():
    result = AllocationResult(weights={"c1": 0.5}, capital={}, lots={}, objective_mode_used="mean_cvar",
                              solver_status="optimal", portfolio_cvar=0.1, portfolio_vol=0.1,
                              active_count=1, turnover=0.0, scenario_count=500, fell_back=False,
                              is_earned=True, diagnostics={})
    assert result.acted is True
    assert result.size_multiplier_for("c1", naive_equal_weight=0.25) == pytest.approx(2.0)


# -- scenario matrix builder ----------------------------------------------------------------------

def test_scenario_matrix_uses_candidate_carried_scenarios():
    cands = [_candidate("c1", scen=tuple(np.linspace(-0.1, 0.1, 40)))]
    sm = build_scenario_matrix(cands, records=[], scenario_count=128)
    assert sm.returns_matrix.shape == (128, 1)
    assert sm.min_real_sample_count == 40
    assert sm.candidate_ids == ("c1",)


def test_scenario_matrix_matches_records_by_kind_direction():
    records = [
        {"realized_return_fraction": 0.05, "instrument_kind": "cash_equity", "direction": "long",
         "strategy_tag": "orb", "session_date": "2026-01-01"},
        {"realized_return_fraction": -0.03, "instrument_kind": "cash_equity", "direction": "long",
         "strategy_tag": "orb", "session_date": "2026-01-01"},
    ]
    cands = [_candidate("c1", segment="cash_equity", direction="long")]
    sm = build_scenario_matrix(cands, records, scenario_count=64)
    assert sm.min_real_sample_count == 2
    # every bootstrapped scenario is one of the two observed returns
    assert set(np.unique(sm.returns_matrix)).issubset({0.05, -0.03})


def test_scenario_matrix_empty_candidates():
    sm = build_scenario_matrix([], records=[], scenario_count=32)
    assert sm.returns_matrix.size == 0
    assert sm.min_real_sample_count == 0


def test_scenario_matrix_no_history_is_zero_column_not_invented():
    cands = [_candidate("c1")]
    sm = build_scenario_matrix(cands, records=[], scenario_count=16)
    assert sm.min_real_sample_count == 0          # honest: no real data
    assert np.allclose(sm.returns_matrix, 0.0)    # never invents a return


# -- covariance estimator -------------------------------------------------------------------------

def test_covariance_is_psd():
    rng = np.random.default_rng(0)
    matrix = rng.normal(0, 0.05, size=(300, 4))
    cov = shrunk_covariance_matrix(matrix)
    eigenvalues = np.linalg.eigvalsh(cov)
    assert (eigenvalues >= -1e-9).all()
    assert cov.shape == (4, 4)


def test_covariance_single_candidate():
    matrix = np.random.default_rng(1).normal(0, 0.05, size=(100, 1))
    cov = shrunk_covariance_matrix(matrix)
    assert cov.shape == (1, 1)
    assert cov[0, 0] > 0.0


def test_covariance_zero_variance_columns_do_not_produce_nan():
    # zero-variance columns previously produced a NaN covariance (constant-corr divide-by-zero) → guarded
    matrix = np.zeros((300, 3))
    cov = shrunk_covariance_matrix(matrix)
    assert np.all(np.isfinite(cov))
    assert np.linalg.eigvalsh(cov).min() >= -1e-9


# -- risk-parity ----------------------------------------------------------------------------------

def test_risk_parity_weights_sum_to_one_and_nonneg():
    rng = np.random.default_rng(2)
    matrix = rng.normal(0, 0.05, size=(300, 5))
    cov = shrunk_covariance_matrix(matrix)
    w = solve_risk_parity_weights(cov)
    assert w.shape == (5,)
    assert w.min() >= 0.0
    assert w.sum() == pytest.approx(1.0, abs=1e-6)


def test_risk_parity_gives_lower_vol_asset_more_weight():
    # diagonal covariance: asset 0 low variance, asset 1 high variance → ERC overweights asset 0
    cov = np.diag([0.0001, 0.04])
    w = solve_risk_parity_weights(cov)
    assert w[0] > w[1]
