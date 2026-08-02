"""NSE company-name↔symbol gazetteer for headline symbol-matching (Trunk II SENSES; research/148).

Headlines name companies ("InterGlobe Aviation"), not tickers ("INDIGO"). This resolves them, bounded
to the tradable F&O underlyings (Rule L), so the S7 news-event gate covers headline-mentioned stocks,
not just "SYMBOL:" filings. The authoritative map is NSE's official equity master (EQUITY_L.csv:
SYMBOL, NAME OF COMPANY), fetched via the curl_cffi NSE session behind a DI seam (Rule J) and cached
to disk (fetched ≤ daily). Matching is exact-ticker + full-normalized-name-phrase — high precision for
a finite gazetteer (spaCy NER rejected as too heavy, research/143).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from pathlib import Path

_EQUITY_MASTER_CSV = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_NSE_HOME = "https://www.nseindia.com/"
_FETCH_TIMEOUT_SECONDS = 25
DEFAULT_EQUITY_MASTER_CACHE = Path.home() / ".nse_algo_trader" / "nse_equity_master.json"

# Company-name noise stripped before matching so "InterGlobe Aviation" == "InterGlobe Aviation Limited".
_NAME_SUFFIX_NOISE = (
    " limited", " ltd", " ltd.", " (india)", " india", " corporation", " corp", " company", " co",
    " & co", " enterprises", " industries", " & sons",
)
_MIN_NAME_PHRASE_LEN = 7   # a normalized name must be at least this long to match (drops generic words)
_MIN_TICKER_LEN = 3


def _normalize(text: str) -> str:
    lowered = (text or "").lower()
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _normalize_company_name(name: str) -> str:
    normalized = _normalize(name)
    for noise in _NAME_SUFFIX_NOISE:
        if normalized.endswith(noise):
            normalized = normalized[: -len(noise)].strip()
    if normalized.startswith("the "):
        normalized = normalized[4:]
    return normalized


def fetch_nse_equity_master_csv() -> str:
    """The real fetch seam: curl_cffi NSE session → raw EQUITY_L.csv text ("" on failure)."""
    try:
        from curl_cffi import requests as curl_requests
        from typing import Any

        session: Any = curl_requests.Session(impersonate="chrome")  # curl_cffi is untyped
        session.get(_NSE_HOME, timeout=_FETCH_TIMEOUT_SECONDS)
        response = session.get(_EQUITY_MASTER_CSV, headers={"Referer": _NSE_HOME},
                               timeout=_FETCH_TIMEOUT_SECONDS)
        return response.text if response.status_code == 200 else ""
    except Exception:
        return ""


def parse_equity_master_csv(csv_text: str) -> list:
    """PURE: EQUITY_L.csv text → [(symbol, company_name)]. Tolerant of the leading/space-padded header."""
    rows = []
    for line in (csv_text or "").splitlines()[1:]:  # skip header
        parts = line.split(",")
        if len(parts) < 2:
            continue
        symbol = parts[0].strip()
        name = parts[1].strip()
        if symbol and name:
            rows.append((symbol, name))
    return rows


@dataclass
class SymbolGazetteer:
    """Matches F&O symbols in free text by exact ticker or full normalized company-name phrase."""

    tickers: frozenset             # F&O symbols (upper)
    name_phrases: tuple            # (normalized_name, symbol) sorted longest-name-first

    def match_symbols(self, text: str) -> set:
        found = set()
        normalized = _normalize(text)
        padded = f" {normalized} "
        for name, symbol in self.name_phrases:
            if len(name) >= _MIN_NAME_PHRASE_LEN and f" {name} " in padded:
                found.add(symbol)
        # Exact ticker as an uppercase whole word (headlines sometimes use the ticker itself).
        for ticker in re.findall(r"\b[A-Z0-9&-]{3,}\b", text or ""):
            if ticker in self.tickers:
                found.add(ticker)
        return found


def build_symbol_gazetteer(rows, restrict_symbols=None) -> SymbolGazetteer:
    """Build the gazetteer, optionally bounded to a symbol set (the F&O underlyings — Rule L)."""
    restrict = set(restrict_symbols) if restrict_symbols is not None else None
    tickers = set()
    name_phrases = []
    for symbol, name in rows:
        if restrict is not None and symbol not in restrict:
            continue
        tickers.add(symbol)
        normalized = _normalize_company_name(name)
        if len(normalized) >= _MIN_NAME_PHRASE_LEN:
            name_phrases.append((normalized, symbol))
    name_phrases.sort(key=lambda pair: len(pair[0]), reverse=True)  # longest name first
    return SymbolGazetteer(tickers=frozenset(tickers), name_phrases=tuple(name_phrases))


def load_or_fetch_equity_master(fetch_csv=fetch_nse_equity_master_csv,
                                cache_path: Path = DEFAULT_EQUITY_MASTER_CACHE,
                                now_utc: datetime | None = None,
                                max_age: timedelta = timedelta(days=1)) -> list:
    """Return [(symbol, name)] from the on-disk cache if fresh, else fetch + refresh the cache.

    The fetch is the DI seam; on a fetch failure a stale cache is still used (better than nothing)."""
    now_utc = now_utc or datetime.now(UTC)
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if now_utc - fetched_at < max_age:
                return [tuple(r) for r in cached["rows"]]
        except Exception:
            pass  # fall through to a fresh fetch

    rows = parse_equity_master_csv(fetch_csv())
    if rows:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"fetched_at": now_utc.isoformat(), "rows": rows}))
        except Exception:
            pass
        return rows
    # Fetch failed — use a stale cache if one exists.
    if cache_path.exists():
        try:
            return [tuple(r) for r in json.loads(cache_path.read_text())["rows"]]
        except Exception:
            pass
    return []
