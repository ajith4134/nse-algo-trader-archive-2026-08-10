"""Tests for the INDEX-OPTION structure selector + deterministic policy (slice 3)."""

from __future__ import annotations

import pytest

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolSurfaceState,
)
from nse_algo_trader.segment_bots.index_option_bot.deterministic_index_option_policy import (
    DeterministicIndexOptionPolicy,
)
from nse_algo_trader.segment_bots.index_option_bot.structure_selector import (
    IndexOptionStructureSelector,
)
from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeState,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    BotCompetency,
    OptionStructureKind,
    TradeSide,
)


def _regime(label: str, probs: tuple[float, ...], vrp: float, maturity: str = "earned") -> VolatilityRegimeState:
    return VolatilityRegimeState(
        underlying="NIFTY", regime_label=label, regime_index=0, regime_probabilities=probs,
        garch_forecast_sigma=0.14, har_forecast_sigma=0.14, blended_forecast_sigma=0.14,
        realized_vol=0.13, variance_risk_premium=vrp, n_observations=400, maturity=maturity,
        fitted_at_ist="2026-08-03 10:00:00 IST",
    )


def _surface(iv_rank: float | None, skew: float, maturity: str = "earned") -> ImpliedVolSurfaceState:
    return ImpliedVolSurfaceState(
        underlying="NIFTY", trade_date="2026-08-03", spot=20000.0, nearest_expiry="2026-08-07",
        nearest_atm_iv=0.15, atm_iv_by_expiry={"2026-08-07": 0.15}, risk_reversal_25d=skew,
        term_structure_slope=0.01, iv_rank=iv_rank, iv_percentile=iv_rank, smiles=(),
        n_contracts=200, maturity=maturity,
    )


def _earned_competency(level: int = 5) -> BotCompetency:
    return BotCompetency(level=level, closed_trades=200, rolling_sharpe=1.2, calibration_error=0.05, is_earned=True)


SELECTOR = IndexOptionStructureSelector()


def test_stressed_regime_stands_aside_on_low_iv():
    d = SELECTOR.select("NIFTY", "2026-08-07", _regime("stressed", (0.2, 0.8), vrp=0.0), _surface(0.2, 0.0))
    assert d.stand_aside and d.side == TradeSide.NEUTRAL


def test_rich_iv_positive_vrp_sells_premium():
    d = SELECTOR.select("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.05), _surface(0.85, 0.0))
    assert not d.stand_aside
    assert d.plan.kind in (OptionStructureKind.IRON_CONDOR, OptionStructureKind.SHORT_STRANGLE)
    assert d.plan.net_theta > 0  # short vol / theta-positive
    assert d.conviction > 0.0


def test_rich_put_skew_routes_to_put_credit_spread():
    d = SELECTOR.select("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.05), _surface(0.7, skew=0.05))
    assert d.plan.kind == OptionStructureKind.VERTICAL_CREDIT_SPREAD
    assert d.plan.is_defined_risk


def test_cheap_iv_buys_vol():
    d = SELECTOR.select("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.0), _surface(0.15, 0.0))
    assert not d.stand_aside
    assert d.plan.net_vega > 0  # long vol


def test_expiry_day_calm_uses_iron_fly():
    d = SELECTOR.select("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.02), _surface(0.5, 0.0),
                        is_expiry_day=True)
    assert d.plan.kind == OptionStructureKind.IRON_FLY


def test_policy_emits_proposal_when_earned_and_none_when_gathering():
    policy = DeterministicIndexOptionPolicy()
    regime, surface = _regime("calm", (0.9, 0.1), vrp=0.06), _surface(0.85, 0.0)
    proposal = policy.propose("NIFTY", "2026-08-07", regime, surface, _earned_competency(), now_epoch=1000.0)
    assert proposal is not None
    assert proposal.size_hint_lots > 0
    assert proposal.expected_expectancy > 0  # positive-VRP premium sale has positive modelled edge
    assert proposal.signal_expiry_epoch > 1000.0
    assert not proposal.is_expired(1000.0) and proposal.is_expired(1000.0 + 10_000)
    assert "rationale" in proposal.feature_provenance

    # Rule-Q cold-start: full algorithm, ACTIVATION laddered by SIZE — an unearned bot still proposes at a
    # 1-lot paper floor (so a track record can accrue), not silenced to None. LIVE weight gates elsewhere.
    gathering = BotCompetency(level=0, closed_trades=1, rolling_sharpe=None, calibration_error=None, is_earned=False)
    cold = policy.propose("NIFTY", "2026-08-07", regime, surface, gathering, now_epoch=1000.0)
    assert cold is not None and cold.size_hint_lots >= 1


def test_policy_stands_aside_on_no_edge():
    policy = DeterministicIndexOptionPolicy()
    # mid IV-rank, no trend, calm → selector stands aside → policy returns None
    out = policy.propose("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.0), _surface(0.45, 0.0),
                         _earned_competency(), now_epoch=1000.0)
    assert out is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_earned_trend_trades_directional_debit_spread_at_mid_iv():
    """Slice: an earned directional trend at gathering/mid IV-rank → defined-risk debit spread (not aside)."""
    d = SELECTOR.select("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.0), _surface(0.5, 0.0),
                        trend_side=TradeSide.LONG, trend_conviction=0.25)
    assert not d.stand_aside and d.directionally_earned
    assert d.plan.kind == OptionStructureKind.VERTICAL_DEBIT_SPREAD and d.side == TradeSide.LONG
    assert d.conviction == pytest.approx(0.25)
    # no earned trend at mid IV → still stands aside
    flat = SELECTOR.select("NIFTY", "2026-08-07", _regime("calm", (0.9, 0.1), vrp=0.0), _surface(0.5, 0.0),
                           trend_side=TradeSide.NEUTRAL, trend_conviction=0.0)
    assert flat.stand_aside


def test_policy_trades_directional_trend_below_vol_conviction_floor():
    """A directional-earned decision trades on the arbiter gate even below the vol-structure conviction floor."""
    policy = DeterministicIndexOptionPolicy()
    regime, surface = _regime("calm", (0.9, 0.1), vrp=0.0), _surface(0.5, 0.0)  # mid IV, no vol edge
    gathering = BotCompetency(level=0, closed_trades=0, rolling_sharpe=None, calibration_error=None, is_earned=False)
    p = policy.propose("NIFTY", "2026-08-07", regime, surface, gathering, now_epoch=1000.0,
                       trend_side=TradeSide.LONG, trend_conviction=0.15)  # 0.15 < 0.30 vol floor
    assert p is not None and p.side == TradeSide.LONG
    assert p.structure.kind == OptionStructureKind.VERTICAL_DEBIT_SPREAD and p.size_hint_lots >= 1
