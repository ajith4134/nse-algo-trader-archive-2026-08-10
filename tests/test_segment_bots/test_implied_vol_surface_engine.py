"""Tests for the INDEX-OPTION bot's IV-surface engine — IV recovery + SVI + skew + IV-rank + adversarial."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from vollib.black_scholes_merton import black_scholes_merton as _bsm_price

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolRankStore,
    ImpliedVolSurfaceEngine,
)

_RATE = 0.065


def _synthetic_chain(spot: float, expiry: str, tenor: float, base_iv: float, skew: float) -> pd.DataFrame:
    """Build a real-priced chain from a known smile: iv(k) = base_iv + skew*k (so IV recovery is checkable)."""
    forward = spot * math.exp(_RATE * tenor)
    rows = []
    for strike in np.linspace(spot * 0.85, spot * 1.15, 25):
        k = math.log(strike / forward)
        iv = max(base_iv + skew * k, 0.02)
        for right, flag in (("CE", "c"), ("PE", "p")):
            price = _bsm_price(flag, spot, strike, tenor, _RATE, iv, 0.0)
            if price > 0.01:
                rows.append(
                    {
                        "option_right_code": right,
                        "strike_price": float(strike),
                        "close_price": float(price),
                        "underlying_price": float(spot),
                        "expiry_date": expiry,
                    }
                )
    return pd.DataFrame(rows)


def test_recovers_atm_iv_from_known_smile(tmp_path):
    chain = _synthetic_chain(20000.0, "2026-09-25", 30 / 365.0, base_iv=0.15, skew=0.0)
    engine = ImpliedVolSurfaceEngine("NIFTY", ImpliedVolRankStore(tmp_path), risk_free_rate=_RATE)
    state = engine.fit_and_state(chain, trade_date="2026-08-26")
    assert abs(state.nearest_atm_iv - 0.15) < 0.02  # recovers the injected ATM vol
    assert state.n_contracts > 0
    assert len(state.smiles) == 1


def test_downside_skew_gives_positive_risk_reversal(tmp_path):
    # negative skew coefficient => puts (k<0) have HIGHER iv => RR (put_iv - call_iv) > 0
    chain = _synthetic_chain(20000.0, "2026-09-25", 30 / 365.0, base_iv=0.15, skew=-0.4)
    engine = ImpliedVolSurfaceEngine("NIFTY", ImpliedVolRankStore(tmp_path), risk_free_rate=_RATE)
    state = engine.fit_and_state(chain, trade_date="2026-08-26")
    assert state.risk_reversal_25d > 0.0


def test_iv_rank_gates_to_gathering_then_earns(tmp_path):
    store = ImpliedVolRankStore(tmp_path)
    engine = ImpliedVolSurfaceEngine("NIFTY", store, risk_free_rate=_RATE)
    chain = _synthetic_chain(20000.0, "2026-09-25", 30 / 365.0, base_iv=0.15, skew=-0.2)
    start = date(2026, 1, 1)
    first = engine.fit_and_state(chain, trade_date=start.isoformat())
    assert first.maturity == "gathering" and first.iv_rank is None  # one observation → not earned
    for offset in range(1, 74):  # accrue > _MIN_HISTORY_FOR_IV_RANK sessions
        engine.fit_and_state(chain, trade_date=(start + timedelta(days=offset)).isoformat())
    earned = engine.fit_and_state(chain, trade_date=(start + timedelta(days=90)).isoformat())
    assert earned.maturity == "earned"
    assert earned.iv_rank is not None and 0.0 <= earned.iv_rank <= 1.0


def test_high_iv_rank_flags_rich_vol(tmp_path):
    store = ImpliedVolRankStore(tmp_path)
    engine = ImpliedVolSurfaceEngine("NIFTY", store, risk_free_rate=_RATE)
    low = _synthetic_chain(20000.0, "2026-09-25", 30 / 365.0, base_iv=0.10, skew=-0.1)
    start = date(2026, 1, 1)
    for offset in range(70):
        engine.fit_and_state(low, trade_date=(start + timedelta(days=offset)).isoformat())
    high = _synthetic_chain(20000.0, "2026-09-25", 30 / 365.0, base_iv=0.30, skew=-0.1)  # spike
    state = engine.fit_and_state(high, trade_date=(start + timedelta(days=90)).isoformat())
    assert state.is_rich_vol()  # today's IV is at the top of its own range → sell-premium regime


def test_adversarial_empty_and_below_intrinsic_do_not_crash(tmp_path):
    engine = ImpliedVolSurfaceEngine("NIFTY", ImpliedVolRankStore(tmp_path), risk_free_rate=_RATE)
    empty = pd.DataFrame(
        columns=["option_right_code", "strike_price", "close_price", "underlying_price", "expiry_date"]
    )
    state = engine.fit_and_state(empty, trade_date="2026-08-26")
    assert state.n_contracts == 0 and state.maturity == "gathering"
    # a chain of below-intrinsic (unsolvable) prices must not crash and must count them
    bad = pd.DataFrame(
        {
            "option_right_code": ["CE", "CE"],
            "strike_price": [18000.0, 18500.0],
            "close_price": [1.0, 1.0],  # far below intrinsic for a 20000 spot
            "underlying_price": [20000.0, 20000.0],
            "expiry_date": ["2026-09-25", "2026-09-25"],
        }
    )
    engine.fit_and_state(bad, trade_date="2026-08-26")
    assert engine.last_unsolvable_count >= 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
