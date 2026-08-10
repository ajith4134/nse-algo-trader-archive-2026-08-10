"""Deep intraday underlying price history for the segment bots — from the stored 5m ``price_bars`` table.

The segment-bot option adapters previously derived an underlying price series from the DAILY F&O bhavcopy
(``AVG(underlying_price)`` per trade-date) — only ~36 points, far below what the volatility-regime engine
(≥250 obs) and the BULL/BEAR directional brain (≥400 samples) need to earn, so the index/stock bots stood
aside for want of history. The market store already holds real **5m intraday** bars for every underlying in
``price_bars`` (2,430 tokens, live through today) — this source unlocks it.

Kite-decoupled (project rule): this reader touches ONLY stored data — the ``price_bars`` table plus a cached
``instrument_token_map.json`` (symbol → real Kite instrument_token). It never imports ``kiteconnect``. The
map is refreshed out-of-band through the broker-session seam (``refresh_underlying_token_map``); if the cache
is absent the source degrades to empty (the caller falls back to the daily series — Rule J, no hard broker
dependency in the analysis path).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

_DEFAULT_DB = Path.home() / ".nse_algo_trader" / "market_data.sqlite3"
_DEFAULT_TOKEN_MAP = Path.home() / ".nse_algo_trader" / "instrument_token_map.json"
# project underlying symbol → Kite index tradingsymbol (indices are not 'EQ'; they carry these names)
_INDEX_ALIAS = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "FINNIFTY": "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MID SELECT",
    "NIFTYNXT50": "NIFTY NEXT 50",
}


class UnderlyingIntradayPriceSource:
    """Serves a deep 5m close series per underlying from stored ``price_bars`` (Kite-independent)."""

    def __init__(self, db_path: Path | None = None, token_map_path: Path | None = None):
        self._db = db_path or _DEFAULT_DB
        self._token_map_path = token_map_path or _DEFAULT_TOKEN_MAP
        self._symbol_to_token: dict[str, int] | None = None

    def _load_token_map(self) -> dict[str, int]:
        if self._symbol_to_token is not None:
            return self._symbol_to_token
        mapping: dict[str, int] = {}
        if self._token_map_path.exists():
            try:
                raw = json.loads(self._token_map_path.read_text()).get("symbol_to_token", {})
                mapping = {str(k): int(v) for k, v in raw.items()}
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                mapping = {}
        self._symbol_to_token = mapping
        return mapping

    def token_for(self, underlying: str) -> int | None:
        """Resolve a project underlying symbol to its real instrument_token (index alias-aware)."""
        mapping = self._load_token_map()
        if underlying in mapping:
            return mapping[underlying]
        alias = _INDEX_ALIAS.get(underlying)
        if alias and alias in mapping:
            return mapping[alias]
        return None

    def close_series(self, underlying: str, max_bars: int = 3000) -> pd.Series:
        """Chronological 5m close series for the underlying; empty if unmapped or no stored bars."""
        token = self.token_for(underlying)
        if token is None or not self._db.exists():
            return pd.Series(dtype=float)
        con = sqlite3.connect(str(self._db))
        try:
            df = pd.read_sql_query(
                "SELECT bar_timestamp, close_price FROM price_bars "
                "WHERE instrument_token=? AND close_price>0 ORDER BY bar_timestamp DESC LIMIT ?",
                con, params=(token, int(max_bars)),
            )
        except (sqlite3.DatabaseError, pd.errors.DatabaseError):
            return pd.Series(dtype=float)
        finally:
            con.close()
        if df.empty:
            return pd.Series(dtype=float)
        return df["close_price"].astype(float).iloc[::-1].reset_index(drop=True)  # back to chronological


def refresh_underlying_token_map(
    token_map_path: Path | None = None,
    now_iso: str | None = None,
) -> int:
    """Rebuild the cached symbol→token map from the live Kite instrument dump, THROUGH the broker seam.

    Kept out of the read path so the analysis adapters never import ``kiteconnect``. Returns the entry count
    (0 if no valid broker session — the caller keeps the existing cache / daily fallback).
    """
    from nse_algo_trader.broker_sessions.authenticated_kite_client_builder import (
        build_authenticated_kite_client_if_valid,
    )

    kite_client = build_authenticated_kite_client_if_valid()
    if kite_client is None:
        return 0
    token_by_symbol: dict[str, int] = {}
    for row in kite_client.instruments("NSE"):
        if row.get("instrument_type") == "EQ" or row.get("segment") == "INDICES":
            token_by_symbol[row["tradingsymbol"]] = int(row["instrument_token"])
    resolved: dict[str, int] = {}
    for project_symbol, kite_symbol in _INDEX_ALIAS.items():
        if kite_symbol in token_by_symbol:
            resolved[project_symbol] = token_by_symbol[kite_symbol]
    for symbol, token in token_by_symbol.items():
        resolved.setdefault(symbol, token)
    path = token_map_path or _DEFAULT_TOKEN_MAP
    path.write_text(json.dumps({
        "fetched_at": now_iso or "",
        "source": "kite:NSE",
        "symbol_to_token": resolved,
    }))
    return len(resolved)
