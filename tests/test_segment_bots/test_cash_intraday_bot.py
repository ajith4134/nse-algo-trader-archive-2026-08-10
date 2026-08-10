"""Tests for the CASH-INTRADAY bot — cross-sectional features, alpha model, long/short book."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.segment_bots.cash_intraday_bot.cash_intraday_bot import CashIntradayBot
from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_alpha_model import (
    CrossSectionalAlphaModel,
    CrossSectionalAlphaStore,
    CrossSectionalSample,
)
from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_features import (
    CROSS_SECTIONAL_FEATURE_NAMES,
    build_cross_sectional_features,
)
from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import ClosedTrade
from nse_algo_trader.segment_bots.segment_bot_protocol import MarketSegment, SegmentBot, TradeSide


def _bars(trend: float, seed: int, n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(trend, 0.01, n)))
    return pd.DataFrame({"open": close, "high": close * 1.005, "low": close * 0.995,
                         "close": close, "volume": rng.integers(1000, 5000, n)})


def _universe(n: int = 60) -> dict[str, pd.DataFrame]:
    # half strong up-trend, half down — a real cross-section to rank
    return {f"S{i}": _bars(trend=0.002 if i % 2 == 0 else -0.002, seed=i) for i in range(n)}


def test_features_are_cross_sectional_ranks_and_zscores():
    feats = build_cross_sectional_features(_universe(50))
    assert list(feats.columns) == list(CROSS_SECTIONAL_FEATURE_NAMES)
    rank_cols = [c for c in feats.columns if c.endswith("_rank")]
    for c in rank_cols:
        assert feats[c].between(0.0, 1.0).all()  # cross-sectional rank in [0,1]
    assert len(feats) == 50


def test_composite_fallback_ranks_momentum_before_training(tmp_path):
    model = CrossSectionalAlphaModel(CrossSectionalAlphaStore(tmp_path))
    assert not model.is_earned
    feats = build_cross_sectional_features(_universe(60))
    alpha = model.score(feats)
    # up-trend names (even index) should score above down-trend names (odd) on the momentum composite
    up = alpha[[s for s in alpha.index if int(s[1:]) % 2 == 0]].mean()
    down = alpha[[s for s in alpha.index if int(s[1:]) % 2 == 1]].mean()
    assert up > down


def test_alpha_model_trains_and_has_positive_rank_ic(tmp_path):
    rng = np.random.default_rng(2)
    samples = []
    for period in range(30):  # >= _MIN_TIME_PERIODS
        for _ in range(80):  # cross-section per period → >2000 samples total
            f = {k: float(rng.random()) for k in CROSS_SECTIONAL_FEATURE_NAMES}
            fwd = 0.8 * (f["ret_5_rank"] - 0.5) - 0.5 * (f["reversal_1_rank"] - 0.5) + rng.normal(0, 0.05)
            samples.append(CrossSectionalSample(features=f, forward_return=fwd, as_of_epoch=float(period)))
    model = CrossSectionalAlphaModel(CrossSectionalAlphaStore(tmp_path))
    report = model.train(samples)
    assert report.trained and model.is_earned
    assert report.walk_forward_rank_ic is not None and report.walk_forward_rank_ic > 0.0


class _FakeAdapter:
    def __init__(self):
        self._bars = _universe(60)

    def universe_bars(self):
        return self._bars

    def last_price(self, symbol):
        return float(self._bars[symbol]["close"].iloc[-1])

    def round_trip_cost_fraction(self, symbol):
        return 0.002  # 20 bps


def test_bot_protocol_and_cold_start(tmp_path):
    bot = CashIntradayBot(_FakeAdapter(), tmp_path)
    assert isinstance(bot, SegmentBot) and bot.segment == MarketSegment.CASH_INTRADAY
    # Rule-Q cold-start: an unearned bot STILL proposes (paper floor) so a track record can accrue — it is
    # NOT silenced. Competency gates size/live weight, not paper participation.
    assert not bot.competency().is_earned
    proposals = bot.propose(now_epoch=1000.0)
    assert len(proposals) >= 2  # builds the book from birth
    assert all(p.size_hint_lots > 0 for p in proposals)


def test_bot_builds_long_short_book_once_earned(tmp_path):
    bot = CashIntradayBot(_FakeAdapter(), tmp_path)
    for i in range(55):  # earn competency
        bot.record_closed_trade(ClosedTrade(features={}, won=bool(i % 2), entry_epoch=float(i),
                                            calibrated_prob_at_entry=0.5))
    assert bot.competency().is_earned
    proposals = bot.propose(now_epoch=1e9)
    assert len(proposals) >= 2
    sides = {p.side for p in proposals}
    assert TradeSide.LONG in sides and TradeSide.SHORT in sides  # a real long/short book
    assert all(p.segment == MarketSegment.CASH_INTRADAY and p.size_hint_lots > 0 for p in proposals)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
