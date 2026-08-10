"""Tests for the deep-intraday underlying price source (stored price_bars + cached token map, Kite-free)."""

from __future__ import annotations

import json
import sqlite3

import pandas as pd

from nse_algo_trader.market_data.underlying_intraday_price_source import UnderlyingIntradayPriceSource


def _seed_db(tmp_path, token: int, closes: list[float]):
    db = tmp_path / "market_data.sqlite3"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE price_bars (instrument_token INTEGER, bar_timestamp TEXT, close_price REAL)")
    for i, c in enumerate(closes):
        con.execute("INSERT INTO price_bars VALUES (?,?,?)", (token, f"2026-08-04T09:{15 + i:02d}:00+05:30", c))
    con.commit()
    con.close()
    return db


def _seed_map(tmp_path, mapping: dict):
    path = tmp_path / "instrument_token_map.json"
    path.write_text(json.dumps({"fetched_at": "", "source": "test", "symbol_to_token": mapping}))
    return path


def test_close_series_is_chronological_and_deep(tmp_path):
    db = _seed_db(tmp_path, 256265, [100.0 + i for i in range(40)])
    tm = _seed_map(tmp_path, {"NIFTY": 256265})
    src = UnderlyingIntradayPriceSource(db, tm)
    series = src.close_series("NIFTY")
    assert len(series) == 40
    assert series.iloc[0] == 100.0 and series.iloc[-1] == 139.0  # oldest → newest (chronological)


def test_index_alias_resolves(tmp_path):
    # the cached map may carry the Kite index name; the alias maps the project symbol to it
    db = _seed_db(tmp_path, 260105, [50.0, 51.0, 52.0])
    tm = _seed_map(tmp_path, {"NIFTY BANK": 260105})
    src = UnderlyingIntradayPriceSource(db, tm)
    assert src.token_for("BANKNIFTY") == 260105
    assert len(src.close_series("BANKNIFTY")) == 3


def test_unmapped_symbol_is_empty(tmp_path):
    db = _seed_db(tmp_path, 1, [1.0])
    tm = _seed_map(tmp_path, {"NIFTY": 256265})
    src = UnderlyingIntradayPriceSource(db, tm)
    assert src.close_series("UNKNOWNSYM").empty  # no fabricated data


def test_missing_cache_degrades_to_empty(tmp_path):
    db = _seed_db(tmp_path, 256265, [100.0])
    src = UnderlyingIntradayPriceSource(db, tmp_path / "does_not_exist.json")
    assert isinstance(src.close_series("NIFTY"), pd.Series) and src.close_series("NIFTY").empty
