"""Hermetic test for market breadth + cross-market context (Trunk II; research/137): breadth counts
advancers/decliners + dispersion + broad/narrow; cross-market flags a divergence when the aggregate
move isn't confirmed by breadth. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.market_data.market_breadth import (
    SymbolReturn,
    assess_cross_market_context,
    compute_market_breadth,
)


def _r(*vals):
    return [SymbolReturn(f"S{i}", v) for i, v in enumerate(vals)]


def test_broad_up_day():
    mb = compute_market_breadth(_r(0.02, 0.01, 0.03, 0.015, -0.005))  # 4/5 up
    assert mb.advancers == 4 and mb.decliners == 1 and mb.breadth_pct == 0.8
    assert mb.is_broad and mb.advance_decline_ratio == 4.0


def test_mixed_day_is_narrow():
    mb = compute_market_breadth(_r(0.02, -0.02, 0.01, -0.01, 0.005, -0.005))  # 3/3
    assert not mb.is_broad and mb.breadth_pct == 0.5


def test_dispersion_higher_when_spread():
    tight = compute_market_breadth(_r(0.01, 0.011, 0.009, 0.01))
    wide = compute_market_breadth(_r(0.05, -0.04, 0.06, -0.05))
    assert wide.dispersion > tight.dispersion


def test_empty_breadth_handled():
    mb = compute_market_breadth([])
    assert mb.total == 0 and not mb.is_broad


def test_cross_market_confirmation():
    cx = assess_cross_market_context(_r(0.02, 0.015, 0.01, 0.008, 0.03))  # up + broad
    assert cx.market_return > 0 and cx.confirms and not cx.divergence


def test_cross_market_narrow_rally_divergence():
    # one big winner lifts the equal-weighted MEAN up, but 4/5 stocks decline → narrow rally
    cx = assess_cross_market_context(_r(0.30, -0.02, -0.02, -0.02, -0.02))
    assert cx.market_return > 0            # mean is up (the "index" rose)
    assert cx.breadth_pct == 0.2           # but only 20% of stocks advanced
    assert cx.divergence and not cx.confirms  # the move is NOT backed by the internals
