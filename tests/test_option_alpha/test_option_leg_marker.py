"""Tests for the option-leg marker — real spread mark-to-market P&L from the live chain."""

from __future__ import annotations

import pandas as pd
import pytest

from nse_algo_trader.option_alpha.option_leg_marker import OptionLegMarker


class _FakeChain:
    def __init__(self, prices):  # prices: {(right, strike): ltp}
        self._prices = prices

    def option_chain(self, underlying):
        rows = [{"option_right_code": r, "strike_price": k, "close_price": p,
                 "underlying_price": 100.0, "expiry_date": "2026-08-25", "open_interest": 100,
                 "total_traded_volume": 10, "lot_size": 50} for (r, k), p in self._prices.items()]
        return (pd.DataFrame(rows), "2026-08-04", 100.0)


def _short_strangle_legs():
    return [{"right": "CE", "strike": 110.0, "side": "sell", "entry_price": 5.0},
            {"right": "PE", "strike": 90.0, "side": "sell", "entry_price": 5.0}]


def test_credit_structure_profits_as_premium_decays():
    # sold at 5+5=10 credit; now worth 2+2=4 → profit 6/share × lot 50 × 1 lot = 300
    marker = OptionLegMarker(_FakeChain({("CE", 110.0): 2.0, ("PE", 90.0): 2.0}))
    m = marker.mark("NIFTY", _short_strangle_legs(), lots=1)
    assert m is not None
    assert m.unrealized_pnl == pytest.approx((5.0 - 2.0 + 5.0 - 2.0) * 50 * 1)  # +300
    assert m.entry_value_per_share == pytest.approx(10.0)  # net credit received


def test_credit_structure_loses_as_premium_rises():
    marker = OptionLegMarker(_FakeChain({("CE", 110.0): 9.0, ("PE", 90.0): 9.0}))
    m = marker.mark("NIFTY", _short_strangle_legs(), lots=1)
    assert m.unrealized_pnl < 0  # premium doubled → short strangle loses


def test_missing_leg_holds_no_mark():
    marker = OptionLegMarker(_FakeChain({("CE", 110.0): 2.0}))  # PE strike absent
    assert marker.mark("NIFTY", _short_strangle_legs(), lots=1) is None


def test_no_chain_source_is_none():
    assert OptionLegMarker(None).mark("NIFTY", _short_strangle_legs(), lots=1) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
