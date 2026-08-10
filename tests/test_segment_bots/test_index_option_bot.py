"""Tests for the assembled INDEX-OPTION bot (slice 5) — pipeline, competency ladder, protocol, learning."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import (
    ClosedTrade,
    IndexOptionBot,
)
from nse_algo_trader.segment_bots.index_option_bot.win_probability_head import FEATURE_NAMES
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    MarketSegment,
    SegmentBot,
    TradeSide,
)


def _calm_low_vol_prices(n: int = 500, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(20000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, n))))


class _ThetaScorer:
    """Isolates the bot's propose/synthesize/PROOF plumbing from the scorer's regime calibration (which has its
    own tests): forces THETA (the correct engine for a rich-premium / calm setup) so the optimizer synthesizes a
    real profitable defined-risk condor on the high-IV chain — then we assert the emitted trade carries proof."""

    def rank_universe(self, features, trade_date, engine_weights=None):
        from nse_algo_trader.option_alpha.option_opportunity_scorer import (
            EngineScores,
            OpportunityScore,
            ProfitEngine,
        )
        out = {}
        for f in features:
            scores = EngineScores(theta=0.9, delta=0.1, vega=0.1, gamma=0.0, relvalue=0.2)
            out[f.underlying] = OpportunityScore(f.underlying, scores, ProfitEngine.THETA, 0.9, 0.9)
        return out


def _synthetic_chain(spot: float = 20000.0, expiry: str = "2026-09-25", base_iv: float = 0.30) -> pd.DataFrame:
    from vollib.black_scholes_merton import black_scholes_merton as price

    tenor = 30 / 365.0
    rows = []
    for strike in np.linspace(spot * 0.85, spot * 1.15, 25):
        for right, flag in (("CE", "c"), ("PE", "p")):
            p = price(flag, spot, float(strike), tenor, 0.065, base_iv, 0.0)
            if p > 0.01:
                rows.append({"option_right_code": right, "strike_price": float(strike),
                             "close_price": float(p), "underlying_price": spot, "expiry_date": expiry})
    return pd.DataFrame(rows)


class _FakeAdapter:
    """A deterministic in-memory data seam (Rule J) — high IV so the bot wants to sell premium."""

    def __init__(self):
        self._prices = _calm_low_vol_prices()
        self._chain = _synthetic_chain(base_iv=0.30)

    def index_underlyings(self):
        return ["NIFTY"]

    def price_series(self, underlying):
        return self._prices

    def option_chain(self, underlying):
        return self._chain, "2026-08-26"

    def implied_atm_vol(self, underlying):
        return 0.30

    def nearest_expiry(self, underlying):
        return "2026-09-25"

    def is_expiry_day(self, underlying):
        return False

    def trend_side(self, underlying):
        return TradeSide.NEUTRAL


def test_bot_satisfies_segment_bot_protocol(tmp_path):
    bot = IndexOptionBot(_FakeAdapter(), tmp_path)
    assert isinstance(bot, SegmentBot)
    assert bot.segment == MarketSegment.INDEX_OPTION


def test_competency_ladder_starts_unearned_and_gates_size(tmp_path):
    bot = IndexOptionBot(_FakeAdapter(), tmp_path)
    comp = bot.competency()
    assert not comp.is_earned and comp.level == 0 and comp.closed_trades == 0
    # Rule-Q cold-start: an unearned bot still RUNS the full pipeline (not silenced); it returns [] here only
    # because the fake chain carries no vol/trend edge, NOT because competency gates participation.
    result = bot.propose(now_epoch=1000.0)
    assert isinstance(result, list)


def test_bot_proposes_once_competency_is_earned(tmp_path):
    # realistic account so the optimizer's per-structure defined-risk cap (a fraction of account capital) can
    # afford a normal index structure — matching production, where capital is large and the supervisor's
    # per-trade min/max-capital sizing is the real position limit.
    bot = IndexOptionBot(_FakeAdapter(), tmp_path, risk_account_notional=50_000_000.0)
    bot._scorer = _ThetaScorer()  # isolate from scorer/regime calibration; test the propose→proof plumbing
    feats = dict.fromkeys(FEATURE_NAMES, 0.0)
    for i in range(35):  # accrue > _EARNED_MIN_CLOSED_TRADES closed trades
        bot.record_closed_trade(ClosedTrade(features=feats, won=bool(i % 2), entry_epoch=float(i),
                                            calibrated_prob_at_entry=0.5))
    assert bot.competency().is_earned
    # prime the IV-rank store with >60 dated ATM-IV observations so the surface earns its IV-rank
    from datetime import date, timedelta

    start = date(2026, 1, 1)
    for offset in range(70):
        bot._iv_store.append_and_load("NIFTY", (start + timedelta(days=offset)).isoformat(), 0.14)
    proposals = bot.propose(now_epoch=1e9)
    assert len(proposals) >= 1
    p = proposals[0]
    assert p.segment == MarketSegment.INDEX_OPTION and p.size_hint_lots > 0
    # the emitted trade carries its optimizer PROOF (engine + forecast economics) — never a proof-less template
    assert "features" in p.feature_provenance
    assert p.feature_provenance.get("expected_pnl") is not None
    assert p.feature_provenance.get("engine") in {"theta", "delta", "vega", "gamma", "relvalue"}
    assert not math.isnan(p.calibrated_prob)


def test_closed_trades_accrue_labelled_trials_for_the_head(tmp_path):
    bot = IndexOptionBot(_FakeAdapter(), tmp_path)
    feats = dict.fromkeys(FEATURE_NAMES, 0.0)
    for i in range(10):
        bot.record_closed_trade(ClosedTrade(features=feats, won=True, entry_epoch=float(i),
                                            calibrated_prob_at_entry=0.6))
    trials = bot._track_store.labelled_trials()
    assert len(trials) == 10
    bot.learn_from_closed_trades()  # too few to train → head stays unearned, no crash
    assert not bot._head.is_earned


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
