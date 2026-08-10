"""Hermetic tests: the option adapter prefers a live chain source, falls back to stored (Rule J seam)."""

from __future__ import annotations

import sqlite3

import pandas as pd

from nse_algo_trader.portfolio_supervisor.market_store_data_adapters import MarketStoreOptionAdapter


class _FakeLiveChain:
    """A fake LiveOptionChainSource returning a trimmed real-shaped chain (never touches a broker)."""

    def __init__(self, chain=None):
        self._chain = chain

    def option_chain(self, underlying):
        if self._chain is None:
            return None
        return (self._chain.copy(), "2026-08-04", 24500.0)


def _live_chain_df():
    return pd.DataFrame([
        {"option_right_code": "CE", "strike_price": 24500.0, "close_price": 34.5, "underlying_price": 24484.0,
         "expiry_date": "2026-08-04", "open_interest": 1000.0, "total_traded_volume": 5000.0},
        {"option_right_code": "PE", "strike_price": 24500.0, "close_price": 45.0, "underlying_price": 24484.0,
         "expiry_date": "2026-08-04", "open_interest": 1200.0, "total_traded_volume": 6000.0},
    ])


def _stored_db(tmp_path):
    db = tmp_path / "market_data.sqlite3"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE fo_bhavcopy_contracts (underlying_symbol TEXT, trade_date TEXT, "
                "option_right_code TEXT, strike_price REAL, close_price REAL, underlying_price REAL, "
                "expiry_date TEXT, open_interest REAL, total_traded_volume REAL)")
    con.execute("INSERT INTO fo_bhavcopy_contracts VALUES "
                "('NIFTY','2026-06-15','CE',23800,50,23850,'2026-06-16',10,20)")
    con.commit()
    con.close()
    return db


def test_adapter_prefers_live_chain(tmp_path):
    db = _stored_db(tmp_path)
    ad = MarketStoreOptionAdapter(db, index=True, live_chain_source=_FakeLiveChain(_live_chain_df()))
    chain, trade_date = ad.option_chain("NIFTY")
    assert trade_date == "2026-08-04"  # LIVE, not the stored 2026-06-15
    assert set(chain["expiry_date"]) == {"2026-08-04"}
    assert ad.nearest_expiry("NIFTY") == "2026-08-04"  # live expiry


def test_adapter_falls_back_to_stored_when_live_none(tmp_path):
    db = _stored_db(tmp_path)
    ad = MarketStoreOptionAdapter(db, index=True, live_chain_source=_FakeLiveChain(None))
    chain, trade_date = ad.option_chain("NIFTY")
    assert trade_date == "2026-06-15"  # fell back to the stored bhavcopy (Rule J)
    assert len(chain) == 1


def test_adapter_with_no_live_source_uses_stored(tmp_path):
    db = _stored_db(tmp_path)
    ad = MarketStoreOptionAdapter(db, index=True)
    _, trade_date = ad.option_chain("NIFTY")
    assert trade_date == "2026-06-15"
